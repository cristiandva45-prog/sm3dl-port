r"""Convierte framebuffers crudos de la pantalla de arriba (RGB565, 400x240 guardado en columnas de 240 px,
stride 480, como los vuelca SM3DL_REPETIR_VOLCAR) a PNG, y arma una tira con todos lado a lado.
Uso: py -I tools\fb_a_png.py <carpeta> [A B C oro t0]"""
import sys, os, zlib, struct

def png(ruta, w, h, filas):
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    crudo = b"".join(b"\x00" + bytes(f) for f in filas)
    with open(ruta, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + trozo(b"IDAT", zlib.compress(crudo, 6)) + trozo(b"IEND", b""))

def leer(ruta):
    b = open(ruta, "rb").read()
    W, H = 400, 240
    img = [[0] * (W * 3) for _ in range(H)]
    for x in range(W):
        for y in range(H):
            o = x * 480 + (H - 1 - y) * 2
            v = b[o] | (b[o + 1] << 8)
            r, g, bl = (v >> 11) & 31, (v >> 5) & 63, v & 31
            img[y][3 * x:3 * x + 3] = [r * 255 // 31, g * 255 // 63, bl * 255 // 31]
    return img

d = sys.argv[1]
nombres = sys.argv[2:] or ["A", "B", "C", "oro", "t0"]
imgs = [leer(os.path.join(d, n + ".fb")) for n in nombres if os.path.exists(os.path.join(d, n + ".fb"))]
tira = [sum((im[y] + [0, 0, 0] * 4 for im in imgs), []) for y in range(240)]
png(os.path.join(d, "tira.png"), len(tira[0]) // 3, 240, tira)
print("tira:", os.path.join(d, "tira.png"), "con", nombres)
