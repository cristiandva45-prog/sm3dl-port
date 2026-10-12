"""Quien llama a los wrappers de dsp::DSP y quien carga la direccion del firmware DSP embebido.
Uso: py -I tools\audio_llamadores.py [0xDIR ...]   (sin argumentos: los DSP_* de simbolos.txt)"""
import bisect, os, struct, sys
import capstone
from capstone import arm
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
B, TF = 0x100000, 0x100000 + 2758524
nombres = {}
for l in open(os.path.join(RAIZ, "extraido", "simbolos.txt"), encoding="utf-8"):
    p = l.split()
    if len(p) >= 2 and p[0].startswith("0x"):
        nombres[int(p[0], 16)] = p[1]
fun = {}
for f in ("funciones.tsv", "funciones_extra.tsv"):
    q = os.path.join(RAIZ, "extraido", f)
    if os.path.exists(q):
        for l in open(q):
            a, t = l.split()[:2]
            fun.setdefault(int(a, 16), int(t))
ini = sorted(fun)
def duena(x):
    k = bisect.bisect_right(ini, x) - 1
    return ini[k] if k >= 0 else None
dsp = {a: n for a, n in nombres.items() if n.startswith("DSP_")}
objetivos = ({int(x, 16) for x in sys.argv[1:]} if len(sys.argv) > 1 else set(dsp) | {0x3E31B0, 0x3E32B0})
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
llam = {}
for off in range(0, TF - B, 4):
    w = struct.unpack_from("<I", C, off)[0]
    a = B + off
    if (w >> 24) & 0xF == 0xB:  # bl
        d = a + 8 + (((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4
        if d in objetivos:
            llam.setdefault(d, []).append(a)
    if w in objetivos:
        llam.setdefault(w, []).append(("lit", a))
for d in sorted(llam):
    print(f"{nombres.get(d, hex(d))}:")
    for x in llam[d]:
        if isinstance(x, tuple):
            print(f"   literal en 0x{x[1]:08X} (funcion 0x{duena(x[1]) or 0:08X} {nombres.get(duena(x[1]), '')})")
        else:
            f = duena(x)
            print(f"   bl en 0x{x:08X}  funcion 0x{f:08X} {nombres.get(f, '')}")
