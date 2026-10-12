"""Verifica la LOGICA del recompilador sin ejecutar nada nativo en Windows:
el C generado (gen/juego.c) se compila para ARM con memoria identica y corre en Unicorn, al lado de la original.

Uso: py -I recomp\\verificar_recomp_arm.py [nombre ...] [-n 2000]
(El anfitrion nativo x86-64, recomp\\verificar_recomp.py, queda para cuando Smart App Control lo permita.)
"""
import os
import struct
import subprocess
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn import arm_const as A

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "decomp"))
import verificar as V  # noqa: E402

BASE_R = 0x02000000
CPU_DIR = 0x0D000000
PILA_NAT = 0x0C000000
TAM_CPU = (16 + 4 + 32 + 4 + 5) * 4
FLAGS = ["-target", "arm-freestanding-eabihf", "-mcpu=arm1176jzf_s", "-marm", "-mfloat-abi=hard", "-O2",
         "-ffreestanding", "-fno-builtin", "-fno-math-errno", "-ffp-contract=off", "-fno-strict-aliasing",
         "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-DRECOMP_IDENTIDAD",
         "-Wno-unused-label", "-Wno-unused-variable", "-Wno-parentheses-equality", "-I", os.path.join(AQUI, "runtime")]


def construir():
    out = os.path.join(AQUI, "build")
    os.makedirs(out, exist_ok=True)
    ld = os.path.join(out, "arm.ld")
    open(ld, "w").write("ENTRY(rt_entrada)\nSECTIONS {\n . = 0x%08X;\n .text : { *(.text*) }\n .rodata : { *(.rodata*) }\n"
                        " .data : { *(.data*) }\n .bss : { *(.bss*) *(COMMON) }\n /DISCARD/ : { *(.ARM.exidx*) *(.comment) }\n}\n" % BASE_R)
    elf = os.path.join(out, "recomp_arm.elf")
    r = subprocess.run([sys.executable, "-m", "ziglang", "cc", *FLAGS, "-nostdlib", "-Wl,--no-gc-sections", "-Wl,-T," + ld, "-o", elf,
                        os.path.join(AQUI, "gen", "juego.c"), os.path.join(AQUI, "runtime", "runtime_arm.c")],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit("no compila el C generado para ARM")
    with open(elf, "rb") as fh:
        e = ELFFile(fh)
        partes, fin = [], BASE_R
        for seg in e.iter_segments():
            if seg["p_type"] == "PT_LOAD" and seg["p_memsz"]:
                partes.append((seg["p_vaddr"], seg.data()))
                fin = max(fin, seg["p_vaddr"] + seg["p_memsz"])
        img = bytearray(fin - BASE_R)
        for va, d in partes:
            img[va - BASE_R:va - BASE_R + len(d)] = d
        sim = {s.name: s["st_value"] & ~1 for s in e.get_section_by_name(".symtab").iter_symbols() if s.name}
    return bytes(img), sim


class CPUenMem:
    """Registros del CPU virtual guardado en memoria del emulador, con la API de Unicorn (para los stubs)."""
    R = {getattr(A, f"UC_ARM_REG_R{i}"): i for i in range(13)}
    R.update({A.UC_ARM_REG_SP: 13, A.UC_ARM_REG_LR: 14, A.UC_ARM_REG_PC: 15})
    S = {getattr(A, f"UC_ARM_REG_S{i}"): i for i in range(32)}

    def __init__(self, uc):
        self.uc = uc
        self.log, self.guion = [], []

    def _off(self, rid):
        if rid in self.R:
            return self.R[rid] * 4
        return (16 + 4 + self.S[rid]) * 4

    def reg_read(self, rid):
        return struct.unpack("<I", self.uc.mem_read(CPU_DIR + self._off(rid), 4))[0]

    def reg_write(self, rid, v):
        self.uc.mem_write(CPU_DIR + self._off(rid), struct.pack("<I", v & 0xFFFFFFFF))

    def mem_read(self, a, n):
        return self.uc.mem_read(a, n)

    def mem_write(self, a, d):
        self.uc.mem_write(a, bytes(d))


class MaquinaRecomp:
    def __init__(self, img, sim):
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(V.BASE, V.FIN_JUEGO - V.BASE)
        uc.mem_write(V.BASE, V.CODE)
        uc.mem_map(BASE_R, (len(img) + 0xFFFF) & ~0xFFFF)
        uc.mem_write(BASE_R, img)
        for b, t in ((V.HEAP, V.HEAP_T), (V.PILA, V.PILA_T), (V.ESPIA, 0x1000), (V.TRAMPA, 0x1000),
                     (CPU_DIR, 0x1000), (PILA_NAT, 0x100000)):
            uc.mem_map(b, t)
        uc.reg_write(A.UC_ARM_REG_C1_C0_2, uc.reg_read(A.UC_ARM_REG_C1_C0_2) | (0xF << 20))
        uc.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.uc, self.sim = uc, sim
        self.datos0 = bytes(uc.mem_read(V.DATOS[0], V.DATOS[1] - V.DATOS[0]))
        self.cpu = CPUenMem(uc)
        self.stubs, self.err = {}, None
        uc.hook_add(UC_HOOK_CODE, self._externo, begin=sim["rt_externo"], end=sim["rt_externo"])
        for n in ("rt_desconocida", "rt_svc"):
            uc.hook_add(UC_HOOK_CODE, self._otro, n, begin=sim[n], end=sim[n])

    def _volver(self, uc):
        uc.reg_write(A.UC_ARM_REG_PC, uc.reg_read(A.UC_ARM_REG_LR))

    def _otro(self, uc, addr, size, nombre):
        if self.err is None:
            self.err = f"{nombre} en 0x{uc.reg_read(A.UC_ARM_REG_R1):08X}"
        uc.emu_stop()

    def _externo(self, uc, a, size, _):
        addr = uc.reg_read(A.UC_ARM_REG_R1)
        c = self.cpu
        if V.ESPIA <= addr < V.ESPIA + 4 * V.N_ESPIAS:
            k = (addr - V.ESPIA) // 4
            this = c.reg_read(A.UC_ARM_REG_R0)
            ret = struct.unpack("<I", uc.mem_read(this + 0x100 + 4 * k, 4))[0]
            cnt = struct.unpack("<I", uc.mem_read(this + 0x44, 4))[0]
            uc.mem_write(this + 0x44, struct.pack("<I", (cnt + 1) & 0xFFFFFFFF))
            c.log.append(("vf", k, this, c.reg_read(A.UC_ARM_REG_R1)))
            c.reg_write(A.UC_ARM_REG_R0, ret)
            c.reg_write(A.UC_ARM_REG_S0, ret)
        elif addr in self.stubs:
            ret = self.stubs[addr](c, c)
            if ret is not None:
                c.reg_write(A.UC_ARM_REG_R0, ret)
        elif self.err is None:
            self.err = f"llamada a 0x{addr:08X}: ni recompilada ni con stub"
        self._volver(uc)

    def correr(self, func, caso):
        uc = self.uc
        uc.mem_write(V.HEAP, bytes(V.HEAP_T))
        uc.mem_write(V.DATOS[0], self.datos0)
        for a, b in caso.get("mem", []):
            uc.mem_write(a, b)
        self.stubs, self.err = caso.get("stubs", {}), None
        self.cpu.log, self.cpu.guion = [], list(caso.get("guion", []))
        regs = [0] * 16
        for i, v in enumerate(caso.get("r", [])):
            regs[i] = v & 0xFFFFFFFF
        regs[13], regs[14] = V.PILA + V.PILA_T - 0x100, V.TRAMPA
        s = [0] * 32
        for i, v in enumerate(caso.get("s", [])):
            s[i] = struct.unpack("<I", V.pf(v))[0] if isinstance(v, float) else v
        uc.mem_write(CPU_DIR, struct.pack("<16I4I32I4I5I", *regs, 0, 0, 0, 0, *s, 0, 0, 0, 0, 0, 0, 0, 0, 0x03000000))
        uc.reg_write(A.UC_ARM_REG_R0, CPU_DIR)
        uc.reg_write(A.UC_ARM_REG_R1, func)
        uc.reg_write(A.UC_ARM_REG_SP, PILA_NAT + 0x100000 - 0x100)
        uc.reg_write(A.UC_ARM_REG_LR, V.TRAMPA)
        uc.reg_write(A.UC_ARM_REG_FPSCR, V.FPSCR_3DS)
        try:
            uc.emu_start(self.sim["rt_entrada"], V.TRAMPA, count=5_000_000)
            if self.err is None and uc.reg_read(A.UC_ARM_REG_PC) != V.TRAMPA:
                self.err = V.NO_TERMINO
        except UcError as e:
            if self.err is None:
                self.err = f"{e} pc=0x{uc.reg_read(A.UC_ARM_REG_PC):08X}"
        return {"err": self.err, "r0": self.cpu.reg_read(A.UC_ARM_REG_R0), "s0": self.cpu.reg_read(A.UC_ARM_REG_S0),
                "heap": bytes(uc.mem_read(V.HEAP, V.HEAP_T)),
                "datos": bytes(uc.mem_read(V.DATOS[0], V.DATOS[1] - V.DATOS[0])), "log": list(self.cpu.log)}


def main():
    args = sys.argv[1:]
    n = 2000
    if "-n" in args:
        k = args.index("-n")
        n = int(args[k + 1])
        del args[k:k + 2]
    img, sim = construir()
    juego = V.simbolos_juego()
    nombres = args or list(V.CASOS)
    orig, rec = V.Maquina(), MaquinaRecomp(img, sim)
    ok = 0
    for nom in nombres:
        addr, gen = juego[nom], V.CASOS[nom]
        fallo = None
        nt = 0
        for k in range(n):
            caso = V.gen_touch(None) if gen == "touch" else gen()
            orig.poner_stubs(caso.get("stubs", {}))
            a = orig.correr(addr, caso)
            if a["err"] == V.NO_TERMINO:
                nt += 1
                continue
            b = rec.correr(addr, caso)
            fallo = V.comparar(a, b)
            if fallo:
                fallo = f"prueba {k}: {fallo}\n  regs={[hex(x) for x in caso.get('r', [])]}"
                break
        if not fallo and nt == n:
            fallo = "SIN DATOS: la original no termino en ninguna prueba"
        print(f"{'FALLA' if fallo else 'OK   '} {nom} (0x{addr:08X}): {fallo or f'{n - nt} pruebas iguales'}"
              + (f" ({nt} descartadas: no termino)" if nt else ""))
        ok += not fallo
    print(f"\n{ok}/{len(nombres)} verificadas (recompilacion estatica, logica del traductor)")


if __name__ == "__main__":
    main()
