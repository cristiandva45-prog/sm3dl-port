r"""D4b (9 oct 2026): escenarios EXTRA para el arnes de E2 (sin tocar sus archivos: lo importa) con atributos ENTEROS
de la PICA, para ver el camino nativo nuevo de punta a punta (armar_crudo -> D4 crudos con *_SINT/_UINT -> D5 dibujar
con la firma + constantes raiz del selector -> VS REAL de la cache "vulkanizar-2" -> pixeles) contra GL.
Offsets = los de armar_crudo (cada atributo alineado al tamano de SU componente, seguidos en el loader 0).
  mix : v0 FLOAT x4 pos, v1 UBYTE x4 color 0/1, v2 BYTE x3, v3 SHORT x2, v4 SHORT x3, v5 BYTE x1 (stride 36): el
        layout entero completo enlaza y dibuja (v2..v5 no llegan al pixel en este programa).
  p16 : v0 SHORT x4 pos (x, y en +-140, z en [-128,0], w = 128: el SIGNO se ve), v1 UBYTE x4 color, v2..v5 FLOAT x4.
  p3  : v0 SHORT x3 pos (x, y en -1..1, z en {-1,0}) con BASURA en el 4o short (el VS debe poner w = 1), v1..v5 FLOAT x4.
  (Ojo: el color NO sirve para probar el signo: la PICA usa min(|c|, 1) -> -1 y 255 dan lo mismo.)
Uso (desde la raiz): py -I agentes_dx12\D4b\e2_enteros.py [--sab N]   N = SM3DL_D4_SABOTAJE del lado d3d12: 1 lo deben
detectar todos, 3 (signo) p16, 4 (w = 1) p3. Ademas exige que el log d3d12 diga "con enteros nativos" > 0."""
import importlib.util
import os
import random
import re
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
spec = importlib.util.spec_from_file_location("e2", os.path.join(RAIZ, "agentes_dx12", "E2", "tools", "e2.py"))
e2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2)
eq, pr = e2.eq, e2.pr

BYTE, UBYTE, SHORT, FLOAT = 0, 1, 2, 3
TAM = {BYTE: 1, UBYTE: 1, SHORT: 2, FLOAT: 4}
PACK = {BYTE: "b", UBYTE: "B", SHORT: "h", FLOAT: "f"}


def variante(nombre, rng):
    """[(tipo, componentes, generador de un valor por componente)] de v0..v5"""
    f01 = lambda: rng.random()
    if nombre == "mix":
        return [(FLOAT, 4, None), (UBYTE, 4, lambda: rng.randrange(2)), (BYTE, 3, lambda: rng.randrange(-3, 4)),
                (SHORT, 2, lambda: rng.randrange(-4, 5)), (SHORT, 3, lambda: rng.randrange(-2, 3)),
                (BYTE, 1, lambda: rng.randrange(-128, 128))]
    if nombre == "p16":
        return [(SHORT, 4, None), (UBYTE, 4, lambda: rng.randrange(2))] + [(FLOAT, 4, f01)] * 4
    if nombre == "p3":
        return [(SHORT, 3, None)] + [(FLOAT, 4, f01)] * 5
    raise SystemExit(nombre)


def esc_enteros(semilla, nombre):
    rng = random.Random(semilla)
    g = eq.nuevo_guion(256, 4)
    at = variante(nombre, rng)
    offs, off = [], 0
    for t, nc, _ in at:                       # = armar_crudo: alineacion al tamano del componente
        off = (off + TAM[t] - 1) & ~(TAM[t] - 1)
        offs.append(off)
        off += TAM[t] * nc
    stride = (off + 3) & ~3
    g.reg(0x201, sum((t | ((nc - 1) << 2)) << (4 * k) for k, (t, nc, _) in enumerate(at)))
    g.reg(0x202, 5 << 28)
    g.reg(0x203, 0); g.reg(0x204, 0x543210); g.reg(0x205, (6 << 28) | (stride << 16))
    for d in range(16):
        nv = 3 * rng.randrange(2, 24)
        v = bytearray()
        for k in range(nv):
            r = bytearray(rng.randrange(256) for _ in range(stride))     # basura en todo hueco (y en el 4o leido)
            for (t, nc, gen), o in zip(at, offs):
                if gen is None and t == FLOAT:
                    val = [rng.uniform(-1.1, 1.1), rng.uniform(-1.1, 1.1), rng.uniform(-1, 0), 1.0]
                elif gen is None and nc == 4:   # p16
                    val = [rng.randrange(-140, 141), rng.randrange(-140, 141), rng.randrange(-128, 1), 128]
                elif gen is None:               # p3
                    val = [rng.randrange(-1, 2), rng.randrange(-1, 2), rng.randrange(-1, 1)]
                else:
                    val = [gen() for _ in range(nc)]
                struct.pack_into("<%d%s" % (nc, PACK[t]), r, o, *val)
            v += r
        g.mem(pr.DIR_VTX, bytes(v))
        g.reg(0x228, nv)
        g.reg(0x22A, 0)
        g.reg(0x25E, rng.choice([0, 0, 0x100, 0x200]))
        g.reg(0x22E, 1)
        g.leer(0, 0, 256, 4)
        g.reg(0x25E, 0)
    return g


def main():
    sab = sys.argv[sys.argv.index("--sab") + 1] if "--sab" in sys.argv else None
    env_b = {"SM3DL_D4_SABOTAJE": sab} if sab else None
    debe = {"1": {"mix", "p16", "p3"}, "3": {"p16"}, "4": {"p3"}}.get(sab, set())
    ok = True
    for nombre, sem in (("mix", 41), ("p16", 42), ("p3", 43)):
        esc = "d4b_enteros_" + nombre
        r = e2.comparar(esc, esc_enteros(sem, nombre), {}, "gl", "d3d12", 1, env_b, bool(sab))
        log = os.path.join(e2.TRAB, esc + ".d3d12_B.salida.log")
        txt = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
        nat = [int(x) for x in re.findall(r"\((\d+) con enteros nativos", txt)]
        print("   log d3d12: %s" % (("%d crudos con enteros nativos" % max(nat)) if nat else "SIN crudos enteros (cayo a floats?)"))
        ok &= bool(nat) and max(nat) > 0
        if not sab:
            ok &= bool(r)
        elif nombre in debe:
            ok &= bool(r)
            print("   sabotaje %s: %s" % (sab, "DETECTADO" if r else "NO detectado"))
    print("D4b e2_enteros:", ("con sabotaje %s: %s" % (sab, "detectado donde debe" if ok else "NO detectado")) if sab
          else ("IGUAL a GL por el camino nativo" if ok else "FALLA"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
