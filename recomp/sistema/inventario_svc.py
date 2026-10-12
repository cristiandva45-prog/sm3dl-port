r"""Inventario de las svc del juego: numero, cuantas, en que direcciones (y en que funcion segun funciones.tsv).
Uso: py -I recomp\sistema\inventario_svc.py   (imprime una tabla markdown)"""
import bisect
import os
import struct
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CODE = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
BASE, TAM_TEXT = 0x00100000, 2758524
fun = {}
for linea in open(os.path.join(RAIZ, "extraido", "funciones.tsv")):
    a, t = linea.split()
    fun[int(a, 16)] = int(t)
p = os.path.join(RAIZ, "extraido", "funciones_extra.tsv")
if os.path.exists(p):
    for linea in open(p):
        a, t = linea.split()[:2]
        fun.setdefault(int(a, 16), int(t))
ini = sorted(fun)
nombres = {}
for linea in open(os.path.join(RAIZ, "extraido", "simbolos.txt"), encoding="utf-8", errors="replace"):
    partes = linea.split()
    if len(partes) >= 2 and partes[0].startswith("0x"):
        try:
            nombres[int(partes[0], 16)] = partes[1]
        except ValueError:
            pass


def funcion(a):
    k = bisect.bisect_right(ini, a) - 1
    return ini[k] if k >= 0 else None


por = defaultdict(list)
for off in range(0, TAM_TEXT, 4):
    w = struct.unpack_from("<I", CODE, off)[0]
    if (w & 0xFFFFFF00) == 0xEF000000:  # svc #NN, condicion siempre
        por[w & 0xFF].append(BASE + off)
total = sum(len(v) for v in por.values())
print(f"total: {total} svc, {len(por)} numeros distintos")
for n in sorted(por):
    fs = sorted({funcion(a) for a in por[n]})
    ej = ", ".join(f"0x{f:06X}" + (f" {nombres[f]}" if f in nombres else "") for f in fs[:4])
    print(f"| 0x{n:02X} | {len(por[n])} | {len(fs)} | {ej}{' …' if len(fs) > 4 else ''} |")
