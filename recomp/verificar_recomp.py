"""Verificador de la recompilacion estatica: original (Unicorn, ARM) contra recompilada (nativa x86-64).

La recompilada corre en recomp\\build\\anfitrion.exe (Windows bloquea cargar DLLs propias con Smart App
Control, pero deja correr un .exe propio) y habla con este script por stdin/stdout.
Reutiliza generadores, espias, stubs con guion y comparacion de decomp/verificar.py.

Uso: py -I recomp\\verificar_recomp.py [nombre ...] [-n 2000]
"""
import ctypes
import hashlib  # noqa: F401  (reservado)
import os
import struct
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "decomp"))
import verificar as V  # noqa: E402
from unicorn import arm_const as A  # noqa: E402

EXE = os.path.join(AQUI, "build", "anfitrion.exe")


class CPU(ctypes.Structure):
    _fields_ = [("r", ctypes.c_uint32 * 16), ("n", ctypes.c_uint32), ("z", ctypes.c_uint32), ("c", ctypes.c_uint32),
                ("v", ctypes.c_uint32), ("s", ctypes.c_uint32 * 32), ("fn", ctypes.c_uint32), ("fz", ctypes.c_uint32),
                ("fc", ctypes.c_uint32), ("fv", ctypes.c_uint32), ("tls", ctypes.c_uint32), ("tls_rw", ctypes.c_uint32),
                ("excl", ctypes.c_uint32), ("excl_addr", ctypes.c_uint32), ("fpscr", ctypes.c_uint32)]


TAM_CPU = ctypes.sizeof(CPU)
REG_IDX = {getattr(A, f"UC_ARM_REG_R{i}"): i for i in range(13)}
REG_IDX.update({A.UC_ARM_REG_SP: 13, A.UC_ARM_REG_LR: 14, A.UC_ARM_REG_PC: 15})
S_IDX = {getattr(A, f"UC_ARM_REG_S{i}"): i for i in range(32)}


def fnv(b):
    h = 1469598103934665603
    for x in b:
        h ^= x
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


class AnfitrionPipe:
    def __init__(self):
        self.p = subprocess.Popen([EXE, os.path.join(os.path.dirname(AQUI), "extraido", "code.bin")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.cpu = CPU()
        self.stubs, self.log, self.guion, self.err = {}, [], [], None

    # --- tuberia ---
    def _enviar(self, op, datos=b""):
        self.p.stdin.write(struct.pack("<II", op, len(datos)) + datos)
        self.p.stdin.flush()

    def _recibir(self):
        cab = self.p.stdout.read(8)
        if len(cab) < 8:
            raise RuntimeError("el anfitrion se cayo (posible acceso a memoria no mapeada)")
        op, n = struct.unpack("<II", cab)
        return op, self.p.stdout.read(n)

    # --- API tipo Unicorn para reutilizar los stubs ---
    def mem_read(self, addr, n):
        self._enviar(3, struct.pack("<II", addr, n))
        op, d = self._recibir()
        assert op == 201
        return d

    def mem_write(self, addr, datos):
        self._enviar(2, struct.pack("<I", addr) + bytes(datos))

    def reg_read(self, rid):
        if rid in REG_IDX:
            return self.cpu.r[REG_IDX[rid]]
        return self.cpu.s[S_IDX[rid]]

    def reg_write(self, rid, v):
        if rid in REG_IDX:
            self.cpu.r[REG_IDX[rid]] = v & 0xFFFFFFFF
        elif rid in S_IDX:
            self.cpu.s[S_IDX[rid]] = v & 0xFFFFFFFF

    def hash(self, addr, n):
        self._enviar(6, struct.pack("<II", addr, n))
        op, d = self._recibir()
        assert op == 202
        return struct.unpack("<Q", d)[0]

    # --- eventos ---
    def _externo(self, addr):
        if V.ESPIA <= addr < V.ESPIA + 4 * V.N_ESPIAS:
            k = (addr - V.ESPIA) // 4
            this = self.cpu.r[0]
            ret = int.from_bytes(self.mem_read(this + 0x100 + 4 * k, 4), "little")
            cnt = int.from_bytes(self.mem_read(this + 0x44, 4), "little")
            self.mem_write(this + 0x44, ((cnt + 1) & 0xFFFFFFFF).to_bytes(4, "little"))
            self.log.append(("vf", k, this, self.cpu.r[1]))
            self.cpu.r[0] = ret
            self.cpu.s[0] = ret
        elif addr in self.stubs:
            ret = self.stubs[addr](self, self)
            if ret is not None:
                self.cpu.r[0] = ret & 0xFFFFFFFF
        elif self.err is None:
            self.err = f"llamada a 0x{addr:08X}: ni recompilada ni con stub"

    def correr(self, func, caso, datos_ref):
        self._enviar(1)
        for a, b in caso.get("mem", []):
            self.mem_write(a, b)
        self.stubs = caso.get("stubs", {})
        self.log, self.guion, self.err = [], list(caso.get("guion", [])), None
        ctypes.memset(ctypes.addressof(self.cpu), 0, TAM_CPU)
        for i, v in enumerate(caso.get("r", [])):
            self.cpu.r[i] = v & 0xFFFFFFFF
        for i, v in enumerate(caso.get("s", [])):
            self.cpu.s[i] = int.from_bytes(V.pf(v), "little") if isinstance(v, float) else v
        self.cpu.r[13] = V.PILA + V.PILA_T - 0x100
        self.cpu.r[14] = V.TRAMPA
        self._enviar(4, struct.pack("<I", func) + bytes(self.cpu))
        while True:
            op, d = self._recibir()
            if op == 200:
                ctypes.memmove(ctypes.addressof(self.cpu), d, TAM_CPU)
                break
            addr = struct.unpack_from("<I", d)[0]
            ctypes.memmove(ctypes.addressof(self.cpu), d[4:], TAM_CPU)
            if op == 100:
                self._externo(addr)
            elif self.err is None:
                self.err = f"{'instruccion sin soporte' if op == 101 else 'svc'} en 0x{addr:08X}"
            self._enviar(5, bytes(self.cpu))
        # memoria: por hash; solo si difiere se trae entera (para mostrar donde)
        heap_h = self.hash(V.HEAP, V.HEAP_T)
        datos_h = self.hash(V.DATOS[0], V.DATOS[1] - V.DATOS[0])
        heap = datos_ref["heap"] if heap_h == datos_ref["heap_h"] else self.mem_read(V.HEAP, V.HEAP_T)
        datos = datos_ref["datos"] if datos_h == datos_ref["datos_h"] else self.mem_read(V.DATOS[0], V.DATOS[1] - V.DATOS[0])
        return {"err": self.err, "r0": self.cpu.r[0], "s0": self.cpu.s[0], "heap": heap, "datos": datos,
                "log": list(self.log)}


def main():
    args = sys.argv[1:]
    n = 2000
    if "-n" in args:
        k = args.index("-n")
        n = int(args[k + 1])
        del args[k:k + 2]
    juego = V.simbolos_juego()
    nombres = args or list(V.CASOS)
    orig, anf = V.Maquina(), AnfitrionPipe()
    ok = 0
    for nom in nombres:
        if nom not in juego:
            print(f"--  {nom}: no esta en simbolos.txt")
            continue
        addr, gen = juego[nom], V.CASOS[nom]
        fallo = None
        nt = 0
        for k in range(n):
            caso = V.gen_touch(None) if gen == "touch" else gen()
            orig.poner_stubs(caso.get("stubs", {}))
            a = orig.correr(addr, caso)
            if a["err"] == V.NO_TERMINO:  # la original no termino: el nativo se colgaria; se descarta
                nt += 1
                continue
            a["heap_h"], a["datos_h"] = fnv_rapido(a["heap"]), fnv_rapido(a["datos"])
            b = anf.correr(addr, caso, a)
            fallo = V.comparar(a, b)
            if fallo:
                fallo = f"prueba {k}: {fallo}\n  regs={[hex(x) for x in caso.get('r', [])]}"
                break
        if fallo:
            print(f"FALLA {nom} (0x{addr:08X}): {fallo}")
        elif nt == n:
            print(f"SIN DATOS {nom} (0x{addr:08X}): la original no termino en ninguna de las {n} pruebas")
        else:
            ok += 1
            print(f"OK    {nom} (0x{addr:08X}): {n - nt} pruebas iguales" + (f" ({nt} descartadas: no termino)" if nt else ""))
    print(f"\n{ok}/{len(nombres)} verificadas (recompilacion estatica, nativa x86-64)")


_CACHE = {}


def fnv_rapido(b):
    """CRC32 (igual al del anfitrion; zlib lo calcula en C, rapido)."""
    import zlib
    return zlib.crc32(b)


if __name__ == "__main__":
    main()
