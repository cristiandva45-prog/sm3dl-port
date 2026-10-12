r"""Convierte los volcados de SM3DL_PRES_VOLCAR (BGRA crudo) a una tira PNG: GPU (g, fila 0 abajo) | GDI (c).
Uso: py -I tools\raw_a_png.py <carpeta> <n> [reduccion]"""
import os, re, struct, sys, zlib

def png(ruta, w, h, filas):
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    crudo = b"".join(b"\x00" + bytes(f) for f in filas)
    open(ruta, "wb").write(b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + trozo(b"IDAT", zlib.compress(crudo, 6)) + trozo(b"IEND", b""))

d, n = sys.argv[1], sys.argv[2]
red = int(sys.argv[3]) if len(sys.argv) > 3 else 3
imgs = []
for pref, voltear in (("g", True), ("c", False)):
    nombre = [f for f in os.listdir(d) if re.match(rf"{pref}{n}_\d+x\d+\.raw$", f)][0]
    w, h = map(int, re.findall(r"(\d+)x(\d+)", nombre)[0])
    b = open(os.path.join(d, nombre), "rb").read()
    filas = []
    for y in range(0, h, red):
        yy = h - 1 - y if voltear else y
        fila = bytearray()
        for x in range(0, w, red):
            i = (yy * w + x) * 4
            fila += bytes((b[i + 2], b[i + 1], b[i]))
        filas.append(fila)
    imgs.append(filas)
alto = min(len(f) for f in imgs)
tira = [imgs[0][y] + bytes(12) + imgs[1][y] for y in range(alto)]
salida = os.path.join(d, f"tira{n}.png")
png(salida, len(tira[0]) // 3, alto, tira)
print(salida)
