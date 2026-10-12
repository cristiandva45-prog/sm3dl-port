"""Bateria por instruccion: cada FORMA de instruccion que usa el juego, probada sola, contra la original.

1. Censo: recorre todas las funciones y agrupa sus instrucciones por forma (mnemonico + tipos de operando,
   desplazamientos, modo de direccionamiento, writeback). Toma hasta K ejemplares REALES de cada forma.
2. Cada ejemplar se traduce como una funcion de UNA instruccion y se prueba EN SU DIRECCION ORIGINAL
   (asi los literales relativos al pc valen lo mismo). Unicorn ejecuta exactamente esa instruccion.
3. Estado al azar (registros, NZCV, s0-s31 con floats raros, banderas del FPSCR, registro de hilo, memoria)
   y comparacion completa: r0-r14, NZCV, s0-s31, banderas FPSCR, registros de hilo y la memoria tocada.

Uso: py -I recomp\\bateria.py [-k 3] [-n 60] [--solo <mnemonico>]
"""
import os
import random
import re
import struct
import subprocess
import sys
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import recomp as RC  # noqa: E402
from capstone import arm  # noqa: E402
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UcError  # noqa: E402
from unicorn import arm_const as A  # noqa: E402

HEAP, VENTANA, CENTRO = 0x08000000, 0x2000, 0x08001000
FPSCR = 0x03000000
R = random.Random(77)
CTRL = {arm.ARM_INS_B, arm.ARM_INS_BL, arm.ARM_INS_BLX, arm.ARM_INS_BX, arm.ARM_INS_SVC, arm.ARM_INS_CDP}


def forma(i):
    """Clave de forma de una instruccion (sin condicion: las banderas al azar cubren ambos caminos)."""
    base = i.mnemonic
    if i.cc not in (arm.ARM_CC_AL, arm.ARM_CC_INVALID):
        m = base.split(".")
        for suf in ("eq", "ne", "hs", "lo", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le"):
            if m[0].endswith(suf) and len(m[0]) > len(suf):
                m[0] = m[0][:-len(suf)]
                break
        base = ".".join(m)
    partes = [base, "S" if i.update_flags else "", "W" if i.writeback else ""]
    for o in i.operands:
        if o.type == arm.ARM_OP_REG:
            n = i.reg_name(o.reg)
            k = "pc" if n == "pc" else ("sp" if n == "sp" else n[0] if n[0] in "sd" and n[1:].isdigit() else "r")
            partes.append(k + (f"<{o.shift.type}{'r' if o.shift.type >= 6 else ''}" if o.shift.type else "") +
                          ("-" if o.subtracted else ""))
        elif o.type == arm.ARM_OP_MEM:
            b = i.reg_name(o.mem.base)
            partes.append(f"[{'pc' if b == 'pc' else 'sp' if b == 'sp' else 'r'}{',x' if o.mem.index else ''}"
                          f"{'-' if o.subtracted else ''}{'<' + str(o.shift.type) if o.shift.type else ''}]")
        else:
            partes.append({arm.ARM_OP_IMM: "#", arm.ARM_OP_FP: "f", arm.ARM_OP_PIMM: "p", arm.ARM_OP_CIMM: "c"}.get(o.type, "?"))
    return " ".join(p for p in partes if p)


def es_control(i):
    if i.id in CTRL:
        return True
    return RC.Traductor.termina(i) or any(o.type == arm.ARM_OP_REG and i.reg_name(o.reg) == "pc" and k == 0
                                          for k, o in enumerate(i.operands))


def censo(k_por_forma):
    tam = RC.tamanos()
    inicios = sorted(tam)
    formas = defaultdict(list)
    for a in inicios:
        t = RC.Traductor(a, RC.limite(tam, inicios, a), set())
        for ad, i in t.recorrer().items():
            if i is None or es_control(i):
                continue
            formas[forma(i)].append(ad)
    elegidos = {}
    for f, lst in formas.items():
        elegidos[f] = R.sample(lst, min(k_por_forma, len(lst)))
    return formas, elegidos


def generar_c(direcciones, salida):
    cuerpo = []
    for a in direcciones:
        t = RC.Traductor(a, a + 4, set())
        lineas, _ = t.generar()
        txt = "\n".join(lineas)
        txt = txt.replace(f"rt_llamar(c, 0x{a + 4:08X}u); return; /* cae fuera de la funcion */", "return;")
        txt = txt.replace(f"{{ rt_llamar(c, 0x{a + 4:08X}u); return; }}", "return;")
        cuerpo.append(txt)
    with open(salida, "w", encoding="utf-8") as fh:
        fh.write("/* GENERADO por recomp/bateria.py */\n#include \"recomp.h\"\n#define FFN(x) F(FB(x))\n\n")
        fh.write("\n\n".join(cuerpo))
        fh.write("\n\nvoid rt_llamar(CPU *c, u32 addr)\n{\n    switch (addr) {\n")
        for a in direcciones:
            fh.write(f"    case 0x{a:08X}u: f_{a:08X}(c); return;\n")
        fh.write("    default: rt_externo(c, addr); return;\n    }\n}\n")


def compilar(c_file, exe):
    r = subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-s",
                        "-ffp-contract=off", "-fno-strict-aliasing", "-msse2", "-Wno-unused-label", "-Wno-unused-variable",
                        "-Wno-parentheses-equality", "-I", os.path.join(AQUI, "runtime"), "-o", exe, c_file,
                        os.path.join(AQUI, "runtime", "runtime.c"), os.path.join(AQUI, "runtime", "anfitrion_pipe.c")],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:])
        raise SystemExit("no compila la bateria")


# ---------------- estado al azar ----------------
FESP = [0x00000000, 0x80000000, 0x3F800000, 0xBF800000, 0x7F800000, 0xFF800000, 0x7FC00000, 0x7F800001,
        0x00000001, 0x807FFFFF, 0x3DCCCCCD, 0x4B000000, 0x4F000000, 0xCF000000, 0x7F7FFFFF]


def u32r():
    return R.choice([0, 1, 2, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFF, 0x8000, 0x7FFF, R.getrandbits(32),
                     R.getrandbits(8), R.getrandbits(16), R.randint(0, 40), (1 << R.randint(0, 31))])


def f32r():
    x = R.random()
    if x < 0.35:
        return R.choice(FESP)
    if x < 0.55:
        return struct.unpack("<I", struct.pack("<f", float(R.randint(-300, 300))))[0]
    if x < 0.8:
        return struct.unpack("<I", struct.pack("<f", R.uniform(-4, 4) * 10 ** R.randint(-5, 6)))[0]
    return R.getrandbits(32)


def estado(i):
    r = [u32r() for _ in range(15)]
    # memoria: base/indices apuntando a la ventana de prueba
    for k, o in enumerate(i.operands):
        if o.type == arm.ARM_OP_MEM:
            b = i.reg_name(o.mem.base)
            if b != "pc":
                r[RC.REG[b]] = (CENTRO - o.mem.disp + 8 * R.randint(-4, 4)) & 0xFFFFFFFF
            if o.mem.index:
                r[RC.REG[i.reg_name(o.mem.index)]] = 8 * R.randint(0, 8)
        elif o.type == arm.ARM_OP_REG and k > 0 and i.operands[k - 1].type == arm.ARM_OP_MEM:
            r[RC.REG[i.reg_name(o.reg)]] = 8 * R.randint(0, 8)  # post-indice por registro
    m = i.mnemonic.split(".")[0]
    if m.startswith(("ldm", "stm", "vldm", "vstm")) and i.operands:
        r[RC.REG[i.reg_name(i.operands[0].reg)]] = CENTRO + 8 * R.randint(-4, 4)
    r[13] = CENTRO + 8 * R.randint(-4, 4) if not any(
        o.type == arm.ARM_OP_MEM and i.reg_name(o.mem.base) == "sp" for o in i.operands) else r[13]
    return {"r": r, "nzcv": R.getrandbits(4), "fnzcv": R.getrandbits(4), "s": [f32r() for _ in range(32)],
            "tls": u32r(), "tls_rw": 0,  # Unicorn no implementa TPIDRURW: siempre 0
            "mem": bytes(R.getrandbits(8) for _ in range(VENTANA))}


# ---------------- original (Unicorn) ----------------
class Orig:
    def __init__(self):
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        try:
            uc.ctl_set_cpu_model(A.UC_CPU_ARM_1176)
        except Exception:
            pass
        uc.mem_map(RC.BASE, 0x00500000 - RC.BASE)
        uc.mem_write(RC.BASE, RC.CODE)
        uc.mem_map(HEAP, 0x00100000)
        uc.mem_map(0x00600000, 0x1000)
        uc.mem_write(0x00600000, struct.pack("<I", 0xF57FF01F))  # clrex
        uc.reg_write(A.UC_ARM_REG_C1_C0_2, uc.reg_read(A.UC_ARM_REG_C1_C0_2) | (0xF << 20))
        uc.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.uc = uc
        self.code0 = bytes(uc.mem_read(RC.BASE, 0x00500000 - RC.BASE))

    def correr(self, a, e):
        uc = self.uc
        uc.emu_start(0x00600000, 0x00600004, count=1)  # limpiar el monitor exclusivo
        uc.mem_write(HEAP, e["mem"])
        for k in range(13):
            uc.reg_write(A.UC_ARM_REG_R0 + k, e["r"][k])
        uc.reg_write(A.UC_ARM_REG_SP, e["r"][13])
        uc.reg_write(A.UC_ARM_REG_LR, e["r"][14])
        cpsr = uc.reg_read(A.UC_ARM_REG_CPSR)
        uc.reg_write(A.UC_ARM_REG_CPSR, (cpsr & 0x0FFFFFFF) | (e["nzcv"] << 28))
        for k in range(32):
            uc.reg_write(A.UC_ARM_REG_S0 + k, e["s"][k])
        uc.reg_write(A.UC_ARM_REG_FPSCR, FPSCR | (e["fnzcv"] << 28))
        uc.reg_write(A.UC_ARM_REG_C13_C0_3, e["tls"])
        try:
            uc.emu_start(a, a + 4, count=1)
            err = None
        except UcError as ex:
            err = str(ex)
        r = [uc.reg_read(A.UC_ARM_REG_R0 + k) for k in range(13)] + [uc.reg_read(A.UC_ARM_REG_SP), uc.reg_read(A.UC_ARM_REG_LR)]
        return {"err": err, "r": r, "nzcv": uc.reg_read(A.UC_ARM_REG_CPSR) >> 28,
                "fnzcv": uc.reg_read(A.UC_ARM_REG_FPSCR) >> 28, "s": [uc.reg_read(A.UC_ARM_REG_S0 + k) for k in range(32)],
                "tls_rw": 0, "mem": bytes(uc.mem_read(HEAP, VENTANA))}


# ---------------- recompilada (anfitrion nativo por tuberia) ----------------
class Nativa:
    FMT = "<16I4I32I4I5I"

    def __init__(self, exe):
        self.p = subprocess.Popen([exe, os.path.join(os.path.dirname(AQUI), "extraido", "code.bin")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _env(self, op, d=b""):
        self.p.stdin.write(struct.pack("<II", op, len(d)) + d)
        self.p.stdin.flush()

    def _rec(self):
        cab = self.p.stdout.read(8)
        if len(cab) < 8:
            raise RuntimeError("el anfitrion se cayo")
        op, n = struct.unpack("<II", cab)
        return op, self.p.stdout.read(n)

    def correr(self, a, e):
        self._env(2, struct.pack("<I", HEAP) + e["mem"])
        r = list(e["r"]) + [0]
        n, z, c, v = (e["nzcv"] >> 3) & 1, (e["nzcv"] >> 2) & 1, (e["nzcv"] >> 1) & 1, e["nzcv"] & 1
        fn, fz, fc, fv = (e["fnzcv"] >> 3) & 1, (e["fnzcv"] >> 2) & 1, (e["fnzcv"] >> 1) & 1, e["fnzcv"] & 1
        cpu = struct.pack(self.FMT, *r, n, z, c, v, *e["s"], fn, fz, fc, fv, e["tls"], e["tls_rw"], 0, 0, FPSCR)
        self._env(4, struct.pack("<I", a) + cpu)
        err = None
        while True:
            op, d = self._rec()
            if op == 200:
                break
            err = err or f"evento {op} en 0x{struct.unpack_from('<I', d)[0]:08X}"
            self._env(5, d[4:])
        x = struct.unpack(self.FMT, d)
        self._env(3, struct.pack("<II", HEAP, VENTANA))
        _, mem = self._rec()
        return {"err": err, "r": list(x[0:15]), "nzcv": (x[16] << 3) | (x[17] << 2) | (x[18] << 1) | x[19],
                "fnzcv": (x[52] << 3) | (x[53] << 2) | (x[54] << 1) | x[55], "s": list(x[20:52]),
                "tls_rw": x[57], "mem": mem}


def comparar(o, n):
    if o["err"] or n["err"]:
        return f"error original={o['err']} nativa={n['err']}"
    for k in range(15):
        if o["r"][k] != n["r"][k]:
            return f"r{k}: 0x{o['r'][k]:08X} != 0x{n['r'][k]:08X}"
    if o["nzcv"] != n["nzcv"]:
        return f"NZCV {o['nzcv']:04b} != {n['nzcv']:04b}"
    for k in range(32):
        if o["s"][k] != n["s"][k]:
            return f"s{k}: 0x{o['s'][k]:08X} != 0x{n['s'][k]:08X}"
    if o["fnzcv"] != n["fnzcv"]:
        return f"FPSCR NZCV {o['fnzcv']:04b} != {n['fnzcv']:04b}"
    if o["mem"] != n["mem"]:
        k = next(j for j in range(VENTANA) if o["mem"][j] != n["mem"][j])
        return f"memoria distinta en 0x{HEAP + k:08X}"
    return None


def main():
    args = sys.argv[1:]
    k_forma = int(args[args.index("-k") + 1]) if "-k" in args else 3
    n = int(args[args.index("-n") + 1]) if "-n" in args else 60
    solo = args[args.index("--solo") + 1] if "--solo" in args else None
    formas, elegidos = censo(k_forma)
    if solo:
        elegidos = {f: v for f, v in elegidos.items() if f.split()[0].startswith(solo)}
    dirs = sorted({a for v in elegidos.values() for a in v})
    print(f"censo: {sum(len(v) for v in formas.values())} instrucciones (sin control de flujo), {len(formas)} formas;"
          f" probando {len(dirs)} ejemplares")
    c_file = os.path.join(AQUI, "gen", "bateria.c")
    exe = os.path.join(AQUI, "build", "bateria.exe")
    generar_c(dirs, c_file)
    compilar(c_file, exe)
    orig, nat = Orig(), Nativa(exe)
    fallan = []
    for f in sorted(elegidos, key=lambda f: -len(formas[f])):
        for a in elegidos[f]:
            i = next(RC.md.disasm(RC.CODE[a - RC.BASE:a - RC.BASE + 4], a))
            for t in range(n):
                e = estado(i)
                res = comparar(orig.correr(a, e), nat.correr(a, e))
                if res:
                    fallan.append((f, len(formas[f]), a, i, res))
                    break
            else:
                continue
            break
    ok = len(elegidos) - len(fallan)
    usos_mal = sum(u for _, u, *_ in fallan)
    print(f"\n{ok}/{len(elegidos)} formas OK ({n} pruebas por ejemplar).")
    print(f"formas con falla: {len(fallan)}, que cubren {usos_mal} instrucciones del juego\n")
    for f, usos, a, i, res in sorted(fallan, key=lambda x: -x[1]):
        print(f"FALLA [{usos:6} usos] {f}\n      ej. 0x{a:08X} {i.mnemonic} {i.op_str} -> {res}")


if __name__ == "__main__":
    main()
