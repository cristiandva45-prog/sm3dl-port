r"""Arma una hoja con las presentaciones seguidas de SM3DL_PRES_SECUENCIA (s<k>_r<ranura>_WxH.raw, BGRA fila 0 abajo).
Uso: py -I tools\secuencia_a_png.py <carpeta> [reduccion] [x0 y0 x1 y1 recorte en pixeles de la ventana]"""
import os, re, struct, sys, zlib

def png(ruta, w, h, filas):
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    crudo = b"".join(b"\x00" + bytes(f) for f in filas)
    open(ruta, "wb").write(b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + trozo(b"IDAT", zlib.compress(crudo, 6)) + trozo(b"IEND", b""))

d = sys.argv[1]
red = int(sys.argv[2]) if len(sys.argv) > 2 else 4
arch = sorted(f for f in os.listdir(d) if re.match(r"s\d+_r-?\d+_\d+x\d+\.raw$", f))
imgs = []
for nombre in arch:
    w, h = map(int, re.findall(r"_(\d+)x(\d+)\.raw", nombre)[0])
    x0, y0, x1, y1 = (map(int, sys.argv[3:7]) if len(sys.argv) > 6 else (0, 0, w, h))
    b = open(os.path.join(d, nombre), "rb").read()
    filas = []
    for y in range(y0, y1, red):
        yy = h - 1 - y
        fila = bytearray()
        for x in range(x0, x1, red):
            i = (yy * w + x) * 4
            fila += bytes((b[i + 2], b[i + 1], b[i]))
        filas.append(fila)
    imgs.append(filas)
    print(nombre)
por_fila = 4
ancho = len(imgs[0][0]) // 3
alto = len(imgs[0])
hoja = []
for g in range(0, len(imgs), por_fila):
    grupo = imgs[g:g + por_fila]
    for y in range(alto):
        fila = bytearray()
        for im in grupo:
            fila += im[y] + bytes(6 * 3)
        fila += bytes((por_fila - len(grupo)) * (ancho + 6) * 3)
        hoja.append(fila)
    hoja.extend([bytearray((por_fila * (ancho + 6)) * 3)] * 6)
salida = os.path.join(d, "secuencia.png")
png(salida, len(hoja[0]) // 3, len(hoja), hoja)
print(salida)
