r"""Junta las capturas PPM de sm3dl.exe (recomp\arranque\capturas\) en un mosaico PNG, sin dependencias.
Fila = un momento (300, 600, ... presentaciones); columnas = pantalla de arriba (400x240) y de abajo (320x240).

Uso: py -I recomp\arranque\capturas_png.py [salida.png]
"""
import glob
import os
import re
import struct
import sys
import zlib

A = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(A, "capturas")


def leer_ppm(r):
    b = open(r, "rb").read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", b)
    w, h = int(m.group(1)), int(m.group(2))
    return w, h, b[m.end():m.end() + w * h * 3]


def png(r, w, h, px):
    filas = b"".join(b"\0" + px[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(r, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + trozo(b"IDAT", zlib.compress(filas, 6)) + trozo(b"IEND", b""))


def main():
    salida = sys.argv[1] if len(sys.argv) > 1 else os.path.join(D, "mosaico.png")
    momentos = sorted({re.search(r"_(\d+)\.ppm$", x).group(1) for x in glob.glob(os.path.join(D, "*.ppm"))})
    W, H, SEP = 400 + 8 + 320, 240, 8
    total_h = len(momentos) * (H + SEP)
    lienzo = bytearray(b"\x40\x40\x40" * W * total_h)
    for k, mo in enumerate(momentos):
        for nombre, x0 in (("arriba", 0), ("abajo", 408)):
            r = os.path.join(D, f"{nombre}_{mo}.ppm")
            if not os.path.exists(r):
                continue
            w, h, px = leer_ppm(r)
            for y in range(h):
                o = ((k * (H + SEP) + y) * W + x0) * 3
                lienzo[o:o + w * 3] = px[y * w * 3:(y + 1) * w * 3]
    png(salida, W, total_h, bytes(lienzo))
    print(f"{len(momentos)} momentos -> {salida}")
    for mo in momentos:  # resumen de color: si todo es un solo color, decirlo
        for nombre in ("arriba", "abajo"):
            r = os.path.join(D, f"{nombre}_{mo}.ppm")
            if os.path.exists(r):
                _, _, px = leer_ppm(r)
                colores = len({px[i:i + 3] for i in range(0, len(px), 3 * 97)})
                print(f"  {nombre}_{mo}: ~{colores} colores distintos (muestra), primer pixel {px[:3].hex()}")


if __name__ == "__main__":
    main()
