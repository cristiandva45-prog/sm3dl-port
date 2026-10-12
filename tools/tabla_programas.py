r"""Tabla para que el rasterizador identifique en ejecucion QUE programa de vertex shader subio el juego.

Por cada shbin de extraido\shaders y cada entrada: archivo .vert generado (tools\shader_glsl.py), main, cantidad
de palabras de codigo y FNV-1a de 32 bits sobre esas palabras (el mismo calculo que recomp\render\raster_gl.c).
La memoria de programa del PICA puede tener restos de un programa anterior DETRAS del actual (8 oct: RectDrawer
de 104 palabras sobre 008F2C de 428), asi que se compara el PREFIJO de n palabras.

Uso: py -I tools\tabla_programas.py  ->  extraido\shaders\glsl\programas.tsv
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import shbin  # noqa: E402


def fnv(palabras):
    h = 2166136261
    for w in palabras:
        h ^= w
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def main():
    d = os.path.join(RAIZ, "extraido", "shaders")
    filas = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".shbin"):
            continue
        s = shbin.Shbin(open(os.path.join(d, f), "rb").read())
        cod = list(s.codigo)
        for k, ent in enumerate(s.entradas):
            vert = f"{f[:-6]}_e{k}.vert"
            if not os.path.exists(os.path.join(d, "glsl", vert)):
                continue
            filas.append((vert, ent["main"], len(cod), fnv(cod)))
    salida = os.path.join(d, "glsl", "programas.tsv")
    with open(salida, "w", encoding="ascii") as fh:
        fh.write("# vert\tmain\tpalabras\tfnv32_codigo\n")
        for v, m, n, h in filas:
            fh.write(f"{v}\t{m}\t{n}\t{h:08X}\n")
    print(f"{len(filas)} programas -> {salida}")


if __name__ == "__main__":
    main()
