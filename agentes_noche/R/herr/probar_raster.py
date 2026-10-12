"""Verificador del rasterizador REAL (agente R): arma un guion de registros PICA, lo corre en prueba_raster.exe
(raster_gl.c + pica.c + gsp.c reales, GPU real) y compara pixel a pixel contra las referencias en Python:
  tev : tools/tev_ref.py (agente G) — las 332 recetas reales (recetas.json) + configuraciones al azar
  luz : tools/luz_frag_ref.py (agente I) — las 105 configuraciones reales (configs.json) con luces al azar
Uso:  py -I agentes_noche/R/herr/probar_raster.py tev|luz|estado [--sabotaje N] [--uber] [-d DIBUJOS] [--azar N]
Sale con 1 si algo no coincide (con --sabotaje, DEBE salir con 1).
"""
import argparse
import json
import math
import os
import random
import struct
import subprocess
import sys
from array import array

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.join(RAIZ, "tools"))
import tev_ref  # noqa: E402

DIR_R = os.path.join(RAIZ, "agentes_noche", "R")
EXE = os.path.join(DIR_R, "prueba_raster.exe")

VERT = """#version 330 core
layout(location = 0) in vec4 v0;
layout(location = 1) in vec4 v1;
layout(location = 2) in vec4 v2;
layout(location = 3) in vec4 v3;
layout(location = 4) in vec4 v4;
layout(location = 5) in vec4 v5;
uniform vec4 pica_c[96];
uniform ivec4 pica_i[4];
uniform bool pica_b[16];
out vec4 pica_o0;  // posicion.xyzw
vec4 r[16];
vec4 o[16];
void pica_main() { o[0] = v0; o[1] = v1; o[2] = v2; o[3] = v3; o[4] = v4; o[5] = v5; }
void main() {
    for (int k = 0; k < 16; k++) { r[k] = vec4(0.0); o[k] = vec4(0.0); }
    pica_main();
    pica_o0 = o[0];
    gl_Position = vec4(o[0].x, o[0].y, -o[0].z, o[0].w);
}
"""

ANCHO, ALTO = 256, 4
DIR_COLOR, DIR_DEPTH = 0x18000000, 0x18100000
DIR_VTX = 0x18200000
DIR_TEX = [0x18300000, 0x18310000, 0x18320000]
TEV_BASE = [0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8]


def f24(x):
    """float -> float24 PICA (1.7.16, sesgo 63), truncando la mantisa."""
    if x == 0:
        return 0
    b = struct.unpack("<I", struct.pack("<f", x))[0]
    s, e, m = b >> 31, (b >> 23) & 0xFF, b & 0x7FFFFF
    e = e - 127 + 63
    assert 0 < e < 127, x
    return (s << 23) | (e << 16) | (m >> 7)


class Guion:
    def __init__(self):
        self.w = array("I")
        self.lecturas = 0

    def reg(self, r, v):
        self.w.extend((1, r, v & 0xFFFFFFFF))

    def mem(self, dir_, datos):
        datos = bytes(datos)
        n = len(datos)
        datos += b"\0" * ((-n) % 4)
        self.w.extend((2, dir_, n))
        self.w.frombytes(datos)

    def tex(self, dir_, w, h, rgba):
        self.w.extend((3, dir_, w, h))
        self.w.extend(rgba)

    def leer(self, x, y, w, h):
        self.w.extend((4, x, y, w, h))
        self.lecturas += w * h

    def limpiar(self, c):
        self.w.extend((5, c))

    def vert(self, txt):
        b = txt.encode()
        n = len(b)
        b += b"\0" * ((-n) % 4)
        self.w.extend((6, n))
        self.w.frombytes(b)

    def correr(self, sabotaje=0):
        self.w.append(0)
        g = os.path.join(DIR_R, "guion.bin")
        s = os.path.join(DIR_R, "salida.bin")
        self.w.tofile(open(g, "wb"))
        args = [EXE, g, s] + ([str(sabotaje)] if sabotaje else [])
        p = subprocess.run(args, capture_output=True, text=True, cwd=RAIZ)
        err = [l for l in p.stderr.splitlines() if "[arnes]" in l or "no compila" in l or "SABOTAJE" in l
               or "ERROR" in l.upper()]
        for l in err[:12]:
            print("   ", l[:300])
        if p.returncode:
            print("   exe rc", p.returncode, p.stderr[-1500:])
        d = open(s, "rb").read()
        return [tuple(d[4 * k:4 * k + 4]) for k in range(len(d) // 4)]


def preparar(g, uber):
    """framebuffer 256x4 RGBA8, viewport, vertex shader de paso con OUTMAP, atributos, blend ONE/ZERO."""
    g.w.extend((8, 1 if uber else 0))
    g.vert(VERT)
    g.reg(0x117, 0)                      # RGBA8
    g.reg(0x116, 3)                      # D24S8
    g.reg(0x11C, DIR_DEPTH // 8)
    g.reg(0x11D, DIR_COLOR // 8)
    g.reg(0x11E, ANCHO | ((ALTO - 1) << 12))
    g.reg(0x112, 0xF); g.reg(0x113, 0xF); g.reg(0x114, 0); g.reg(0x115, 0)
    g.reg(0x041, f24(ANCHO / 2)); g.reg(0x043, f24(ALTO / 2)); g.reg(0x068, 0)
    g.reg(0x04D, f24(-1.0)); g.reg(0x04E, 0); g.reg(0x06D, 1)
    g.reg(0x040, 0)                      # sin culling
    g.reg(0x065, 0)                      # sin tijera
    g.reg(0x107, 0xF00 | (1 << 4))       # sin depth test (ALWAYS), mascara de color RGBA, sin escritura de z
    g.reg(0x104, 0)                      # sin alpha test
    g.reg(0x100, 0x100)                  # blend
    g.reg(0x101, (1 << 16) | (0 << 20) | (1 << 24) | (0 << 28))   # ADD, ONE / ZERO
    g.reg(0x1C6, 1)                      # luz apagada
    # vertex shader: 6 entradas, permutacion identidad, salidas o0-o5
    g.reg(0x2B9, 5); g.reg(0x2BB, 0x543210); g.reg(0x2BC, 0); g.reg(0x2BD, 0x3F)
    g.reg(0x04F, 6)
    g.reg(0x050, 0x03020100)             # o0 posicion
    g.reg(0x051, 0x0B0A0908)             # o1 color
    g.reg(0x052, 0x07060504)             # o2 cuaternion (prim en PRUEBA_TEV)
    g.reg(0x053, 0x15141312)             # o3 vista (sec en PRUEBA_TEV)
    g.reg(0x054, 0x0F0E0D0C)             # o4 tc0.uv tc1.uv
    g.reg(0x055, 0x11101716)             # o5 tc2.uv tc0.w ranura 17
    g.reg(0x242, 5)
    # atributos: 6 float x4 en un loader, stride 96
    g.reg(0x200, DIR_VTX // 8)
    g.reg(0x201, 0xFFFFFF)
    g.reg(0x202, 5 << 28)
    g.reg(0x203, 0); g.reg(0x204, 0x543210); g.reg(0x205, (6 << 28) | (96 << 16))
    g.reg(0x25E, 0)
    g.limpiar(0)


def triangulos(frags, fila=0):
    """frags: lista de 6 vec4 (los atributos v0..v5 SIN la posicion: v0 se pone aqui). 1 triangulo por pixel."""
    v = array("f")
    for i, at in enumerate(frags):
        for (px, py) in ((i - 0.25, fila - 0.25), (i + 1.25, fila - 0.25), (i + 0.5, fila + 1.25)):
            v.extend((px / ANCHO * 2 - 1, py / ALTO * 2 - 1, -0.5, 1.0))
            for a in at:
                v.extend(a)
    return v


def dibujar(g, frags, fila=0):
    v = triangulos(frags, fila)
    g.mem(DIR_VTX, v.tobytes())
    g.reg(0x228, 3 * len(frags))
    g.reg(0x22A, 0)
    g.reg(0x22E, 1)


def texturas(g, cols):
    """cols[k] = lista de 256 rgba u8 de la unidad k: textura 256x8 con la columna i = cols[k][i]."""
    regs = [(0x81, 0x82, 0x83, 0x84, 0x85, 0x8E), (0x91, 0x92, 0x93, 0x94, 0x95, 0x96),
            (0x99, 0x9A, 0x9B, 0x9C, 0x9D, 0x9E)]
    for k, col in enumerate(cols):
        px = array("I", [c[0] | (c[1] << 8) | (c[2] << 16) | (c[3] << 24) for c in col]) * 8
        g.tex(DIR_TEX[k], 256, 8, px)
        b, dim, par, lod, dr, fmt = regs[k]
        g.reg(b, 0); g.reg(dim, (256 << 16) | 8); g.reg(par, 0); g.reg(lod, 0); g.reg(dr, DIR_TEX[k] // 8)
        g.reg(fmt, 0)
    g.reg(0x080, 7)


BORDES = [0, 1, 2, 126, 127, 128, 129, 253, 254, 255]


def u8(rng):
    return rng.choice(BORDES) if rng.random() < 0.25 else rng.randrange(256)


def rgba(rng):
    return [u8(rng) for _ in range(4)]


def tev_azar(rng):
    fu = [0, 1, 2, 3, 4, 5, 13, 14, 15]
    mods = [0, 1, 2, 3, 4, 5, 8, 9, 12, 13]
    f = []
    for _ in range(6):
        s = sum(rng.choice(fu) << (4 * j) for j in range(3)) | sum(rng.choice(fu) << (16 + 4 * j) for j in range(3))
        o = sum(rng.choice(mods) << (4 * j) for j in range(3)) | sum(rng.randrange(8) << (12 + 4 * j) for j in range(3))
        c = rng.randrange(10) | (rng.choice([0, 1, 2, 3, 4, 5, 8, 9]) << 16)
        e = rng.randrange(4) | (rng.randrange(4) << 16)
        f.append((s, o, c, e))
    return f


def probar_tev(a):
    rng = random.Random(a.semilla)
    recetas = json.load(open(os.path.join(RAIZ, "extraido", "shaders", "frag", "recetas.json"), encoding="utf-8"))
    casos = [(r["nombre"], [tuple(x) for x in r["firma"]]) for r in recetas]
    if a.solo:
        casos = [c for c in casos if c[0] in a.solo.split(",")]
    casos += [(f"A{k}", tev_azar(rng)) for k in range(a.azar)]
    g = Guion()
    preparar(g, a.uber)
    g.w.extend((7, 1))                   # PRUEBA_TEV: luz primaria/secundaria = salidas del vertice
    esperado = []                        # por dibujo: (nombre, [256 rgba])
    for nombre, firma in casos:
        for d in range(a.dibujos):
            consts = [rgba(rng) for _ in range(6)]
            buf = rgba(rng)
            upd = rng.choice([0, 0xFF00, rng.randrange(256) << 8])
            for k, (s, o, c, e) in enumerate(firma):
                b = TEV_BASE[k]
                cc = consts[k]
                g.reg(b, s); g.reg(b + 1, o); g.reg(b + 2, c); g.reg(b + 3, cc[0] | (cc[1] << 8) | (cc[2] << 16) | (cc[3] << 24))
                g.reg(b + 4, e)
            g.reg(0x0E0, upd)
            g.reg(0x0FD, buf[0] | (buf[1] << 8) | (buf[2] << 16) | (buf[3] << 24))
            ent = [dict(vtx=rgba(rng), prim=rgba(rng), sec=rgba(rng), t0=rgba(rng), t1=rgba(rng), t2=rgba(rng))
                   for _ in range(256)]
            texturas(g, [[e["t%d" % k] for e in ent] for k in range(3)])
            frags = [[[x / 255 for x in e["vtx"]], [x / 255 for x in e["prim"]], [x / 255 for x in e["sec"]],
                      [(i + 0.5) / 256, 0.5, (i + 0.5) / 256, 0.5], [(i + 0.5) / 256, 0.5, 1.0, 1.0]]
                     for i, e in enumerate(ent)]
            dibujar(g, frags)
            g.leer(0, 0, 256, 1)
            ref = []
            for e in ent:
                r = dict(e, t3=[0, 0, 0, 0], buf=buf, const=consts, update=upd)
                try:
                    ref.append(tuple(tev_ref.correr(firma, r)))
                except tev_ref.NoModelado:
                    ref.append(None)
            esperado.append((nombre, ref))
    print(f"tev: {len(casos)} configuraciones x {a.dibujos} dibujos x 256 fragmentos, guion {len(g.w) * 4 // 1024} KB")
    px = g.correr(a.sabotaje)
    if len(px) != 256 * len(esperado):
        print("FALLA: el arnes devolvio", len(px), "pixeles, se esperaban", 256 * len(esperado))
        return 1
    malos = {}
    casos_ok = casos_n = sin_modelo = 0
    for d, (nombre, ref) in enumerate(esperado):
        for i, r in enumerate(ref):
            if r is None:
                sin_modelo += 1
                continue
            casos_n += 1
            got = px[256 * d + i]
            if tuple(got) == r:
                casos_ok += 1
            else:
                malos.setdefault(nombre, []).append((i, got, r))
    nombres = sorted({n for n, _ in esperado}, key=lambda n: (n[0], int(n[1:])))
    reales = [n for n in nombres if n.startswith("R")]
    azar = [n for n in nombres if n.startswith("A")]
    print(f"fragmentos iguales: {casos_ok}/{casos_n} (sin modelo en la referencia: {sin_modelo})")
    print(f"recetas reales iguales: {sum(1 for n in reales if n not in malos)}/{len(reales)}; "
          f"al azar iguales: {sum(1 for n in azar if n not in malos)}/{len(azar)}")
    for n in list(malos)[:6]:
        i, got, r = malos[n][0]
        print(f"   {n}: {len(malos[n])} malos, p. ej. frag {i}: gpu {got} ref {r}")
    return 1 if malos else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["tev", "luz", "estado"])
    ap.add_argument("--sabotaje", type=int, default=0)
    ap.add_argument("--uber", action="store_true", help="fragment shader por uniforms (sin especializar)")
    ap.add_argument("-d", "--dibujos", type=int, default=1)
    ap.add_argument("--azar", type=int, default=200)
    ap.add_argument("--solo", default="")
    ap.add_argument("--semilla", type=int, default=1234)
    a = ap.parse_args()
    if a.modo == "tev":
        rc = probar_tev(a)
    elif a.modo == "luz":
        import probar_raster_luz
        rc = probar_raster_luz.probar(a, sys.modules[__name__])
    else:
        import probar_raster_estado
        rc = probar_raster_estado.probar(a, sys.modules[__name__])
    print("RESULTADO:", "FALLA" if rc else "OK")
    sys.exit(rc)


if __name__ == "__main__":
    main()
