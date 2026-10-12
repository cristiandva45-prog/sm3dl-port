r"""Diagnostico de los escenarios estado_* (agente E2): para cada dibujo cuya lectura (op 4) sale fuera de +-tol entre
GL y D3D12 cuando la ANTERIOR estaba igual (= el dibujo que introduce la diferencia), imprime los registros PICA de ese
dibujo decodificados (blend, logic op, alpha test, stencil, profundidad, mascaras, cull, tijera) y cuantos px cambia.
Uso: py -I agentes_dx12\E2\tools\diag_estado.py estado_blend [--tol 1]   (antes: e2.py estado_blend, deja las salidas)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2  # noqa: E402

nombre = sys.argv[1] if len(sys.argv) > 1 else "estado_blend"
tol = int(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 1
regs_por_dibujo, actual = [], {}
orig_reg = None


def grabar(self, r, v):
    actual[r] = v
    return orig_reg(self, r, v)


orig_reg = e2.pr.Guion.reg
e2.pr.Guion.reg = grabar
orig_leer = e2.pr.Guion.leer


def leer(self, *a):
    regs_por_dibujo.append(dict(actual))
    return orig_leer(self, *a)


e2.pr.Guion.leer = leer
e2.ESCENARIOS[nombre]()
A = open(os.path.join(e2.TRAB, nombre + ".gl_A.salida"), "rb").read()
B = open(os.path.join(e2.TRAB, nombre + ".d3d12_B.salida"), "rb").read()
segs = [l.split() for l in open(os.path.join(e2.TRAB, nombre + ".gl_A.salida.mapa"))]
segs = [s for s in segs if s[1] == "4"]
FACT = "ZERO ONE SRC_C 1-SRC_C DST_C 1-DST_C SRC_A 1-SRC_A DST_A 1-DST_A CONST_C 1-CONST_C CONST_A 1-CONST_A SAT ONE".split()
EQ = "ADD SUB REVSUB MIN MAX ADD ADD ADD".split()
CMP = "NEVER ALWAYS EQ NE LT LE GT GE".split()
SOP = "KEEP ZERO REPL INCR DECR INV INCRW DECRW".split()
LOP = "CLEAR AND AND_REV COPY SET COPY_INV NOOP INV NAND OR NOR XOR EQUIV AND_INV OR_REV OR_INV".split()
prev_mal = False
n_intro = 0
for k, s in enumerate(segs):
    off, n = int(s[2]), int(s[3])
    a, b = A[off:off + n], B[off:off + n]
    fuera = [p for p in range(n // 4) if max(abs(a[4 * p + j] - b[4 * p + j]) for j in range(4)) > tol]
    mal = bool(fuera)
    if mal and not prev_mal:
        n_intro += 1
        r = regs_por_dibujo[k]
        r100, r101, r104, r105, r106, r107 = (r.get(x, 0) for x in (0x100, 0x101, 0x104, 0x105, 0x106, 0x107))
        blend = (r100 >> 8) & 1
        txt = ("blend %s=%s(%s,%s) a=%s(%s,%s) const %08X" % ("on", EQ[r101 & 7], FACT[(r101 >> 16) & 15], FACT[(r101 >> 20) & 15],
               EQ[(r101 >> 8) & 7], FACT[(r101 >> 24) & 15], FACT[(r101 >> 28) & 15], r.get(0x103, 0))) if blend else \
            "logic %s" % LOP[r.get(0x102, 0) & 15]
        print("dibujo %3d: %4d px fuera (1er x=%d y=%d GL %s D3D %s) | %s | alfa %s %s ref %d | stencil %s %s ref %d m %02X/%02X "
              "ops %s/%s/%s | z %s %s mascara_color %X zwrite %d | acceso color %X z %X fmt_ds %d cull %d tijera %d" % (
                  k, len(fuera), fuera[0] % 256, fuera[0] // 256, a[4 * fuera[0]:4 * fuera[0] + 4].hex(),
                  b[4 * fuera[0]:4 * fuera[0] + 4].hex(), txt, "on" if r104 & 1 else "off", CMP[(r104 >> 4) & 7], (r104 >> 8) & 255,
                  "on" if r105 & 1 else "off", CMP[(r105 >> 4) & 7], (r105 >> 16) & 255, (r105 >> 24) & 255, (r105 >> 8) & 255,
                  SOP[r106 & 7], SOP[(r106 >> 4) & 7], SOP[(r106 >> 8) & 7], "on" if r107 & 1 else "off", CMP[(r107 >> 4) & 7],
                  (r107 >> 8) & 15, (r107 >> 12) & 1, r.get(0x113, 0), r.get(0x115, 0), r.get(0x116, 0), r.get(0x040, 0), r.get(0x065, 0)))
    prev_mal = mal
print("%d dibujos introducen diferencia (de %d)" % (n_intro, len(segs)))
