r"""Ubica en el ROM el origen de un vertex shader que el juego subio y no esta en programas.tsv.

El raster vuelca cada programa desconocido a extraido\shaders\desconocidos\<fnv512>_e<entrada>.bin
(4096 palabras de codigo + 4096 de swizzles). Aqui se buscan las primeras palabras de codigo (no ceros) en
code.bin y en todo el romfs, descomprimiendo Yaz0 y abriendo SARC/NARC por dentro (recursivo).

Uso: py -I tools\buscar_shader_rom.py [n_palabras=16]
"""
import os
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import szs  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 16


def firmas():
    d = os.path.join(RAIZ, "extraido", "shaders", "desconocidos")
    out = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".bin"):
            pal = struct.unpack_from("<4096I", open(os.path.join(d, f), "rb").read())
            out[f[:-4]] = struct.pack("<%dI" % N, *pal[:N])
    return out


def abrir(datos, ruta, visitar, prof=0):
    visitar(ruta, datos)
    if prof > 4:
        return
    try:
        if datos[:4] == b"Yaz0":
            abrir(szs.yaz0(datos), ruta + "|yaz0", visitar, prof + 1)
        elif datos[:4] in (b"SARC", b"NARC"):
            for nombre, b in szs.sarc(datos):
                abrir(b, ruta + "/" + nombre, visitar, prof + 1)
    except Exception as e:  # archivo raro: se reporta y se sigue
        print("  (no abre %s: %s)" % (ruta, e))


def main():
    fs = firmas()
    print("%d firmas de %d palabras" % (len(fs), N))
    hallados = {k: [] for k in fs}

    def visitar(ruta, datos):
        for k, firma in fs.items():
            i = datos.find(firma)
            if i >= 0:
                hallados[k].append("%s @0x%X (magic %r)" % (ruta, i, datos[:4]))

    abrir(open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read(), "code.bin", visitar)
    base = os.path.join(RAIZ, "extraido", "romfs")
    for dp, _, archivos in os.walk(base):
        for a in archivos:
            p = os.path.join(dp, a)
            abrir(open(p, "rb").read(), os.path.relpath(p, base), visitar)
    for k, h in hallados.items():
        print("== %s: %d" % (k, len(h)))
        for x in h[:8]:
            print("   " + x)


if __name__ == "__main__":
    main()
