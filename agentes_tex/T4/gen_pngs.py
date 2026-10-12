# Genera PNGs sinteticos (todos los tipos/filtros/compresiones) + su RGBA esperado (.raw) en la carpeta dada.
import sys, os, zlib, struct, random
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
random.seed(7)
def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
def paeth(a, b, c):
    p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)
def filtrar(rows, bpp, modo):
    res = bytearray(); prev = bytes(len(rows[0]))
    for y, row in enumerate(rows):
        ft = modo if modo < 5 else y % 5
        res.append(ft); r = bytearray()
        for i, v in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            pr = [0, a, b, (a + b) >> 1, paeth(a, b, c)][ft]
            r.append((v - pr) & 255)
        res += r; prev = row
    return bytes(res)
def escribir(nombre, w, h, tipo, prof, rows, rgba, extra=b"", modo=5, comp="dyn", plte=None):
    bpp = max(1, prof * {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipo] // 8)
    raw = filtrar(rows, bpp, modo)
    if comp == "dyn": z = zlib.compress(raw, 9)
    elif comp == "stored": z = zlib.compress(raw, 0)
    else:
        c = zlib.compressobj(9, zlib.DEFLATED, 15, 9, zlib.Z_FIXED); z = c.compress(raw) + c.flush()
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, prof, tipo, 0, 0, 0))
    if plte: data += chunk(b"PLTE", plte)
    data += extra + chunk(b"IDAT", z[:len(z) // 2]) + chunk(b"IDAT", z[len(z) // 2:]) + chunk(b"IEND", b"")
    open(os.path.join(out, nombre + ".png"), "wb").write(data)
    open(os.path.join(out, nombre + ".raw"), "wb").write(bytes(rgba))
def ruido(n): return [random.randrange(256) for _ in range(n)]
# 1) RGBA8 con ruido + degradado (comprime dinamico), todos los filtros por fila
w, h = 37, 29
px = [(x * 6 & 255, y * 8 & 255, (x ^ y) * 9 & 255, 255 if (x + y) % 5 else 90) for y in range(h) for x in range(w)]
rows = [bytes(v for p in px[y * w:(y + 1) * w] for v in p) for y in range(h)]
escribir("rgba8_f5", w, h, 6, 8, rows, [v for p in px for v in p], modo=5)
for m in range(5): escribir("rgba8_filtro%d" % m, w, h, 6, 8, rows, [v for p in px for v in p], modo=m)
escribir("rgba8_fijo", w, h, 6, 8, rows, [v for p in px for v in p], comp="fijo")
escribir("rgba8_stored", w, h, 6, 8, rows, [v for p in px for v in p], comp="stored")
# 2) RGB8 ruidoso
w, h = 16, 9
d = ruido(w * h * 3); rows = [bytes(d[y * w * 3:(y + 1) * w * 3]) for y in range(h)]
escribir("rgb8", w, h, 2, 8, rows, [v for i in range(w * h) for v in (d[3*i], d[3*i+1], d[3*i+2], 255)])
# 3) gris 8, gris 4 bits, gris 1 bit
w, h = 10, 6
d = ruido(w * h); rows = [bytes(d[y * w:(y + 1) * w]) for y in range(h)]
escribir("gris8", w, h, 0, 8, rows, [v for g in d for v in (g, g, g, 255)])
g4 = [random.randrange(16) for _ in range(w * h)]
rows = []
for y in range(h):
    b = bytearray((w * 4 + 7) // 8)
    for x in range(w): b[x // 2] |= g4[y * w + x] << (4 - 4 * (x % 2))
    rows.append(bytes(b))
escribir("gris4", w, h, 0, 4, rows, [v for g in g4 for v in (g * 17,) * 3 + (255,)])
g1 = [random.randrange(2) for _ in range(w * h)]
rows = []
for y in range(h):
    b = bytearray((w + 7) // 8)
    for x in range(w): b[x // 8] |= g1[y * w + x] << (7 - x % 8)
    rows.append(bytes(b))
escribir("gris1", w, h, 0, 1, rows, [v for g in g1 for v in (g * 255,) * 3 + (255,)])
# 4) paleta 2 bits + tRNS
pal = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)]; al = [255, 128, 0, 77]
w, h = 7, 5; ix = [random.randrange(4) for _ in range(w * h)]
rows = []
for y in range(h):
    b = bytearray((w * 2 + 7) // 8)
    for x in range(w): b[x // 4] |= ix[y * w + x] << (6 - 2 * (x % 4))
    rows.append(bytes(b))
escribir("paleta2", w, h, 3, 2, rows, [v for i in ix for v in pal[i] + (al[i],)],
         extra=chunk(b"tRNS", bytes(al)), plte=bytes(v for p in pal for v in p))
# 5) gris+alfa 8, RGBA 16
w, h = 6, 6; d = ruido(w * h * 2); rows = [bytes(d[y * w * 2:(y + 1) * w * 2]) for y in range(h)]
escribir("grisalfa", w, h, 4, 8, rows, [v for i in range(w * h) for v in (d[2*i], d[2*i], d[2*i], d[2*i+1])])
d = ruido(w * h * 8); rows = [bytes(d[y * w * 8:(y + 1) * w * 8]) for y in range(h)]
escribir("rgba16", w, h, 6, 16, rows, [d[8 * i + 2 * k] for i in range(w * h) for k in range(4)])
# 6) RGB con tRNS (color transparente)
w, h = 4, 4; d = ruido(w * h * 3); d[0:3] = [1, 2, 3]; d[9:12] = [1, 2, 3]
rows = [bytes(d[y * w * 3:(y + 1) * w * 3]) for y in range(h)]
esp = [v for i in range(w * h) for v in (d[3*i], d[3*i+1], d[3*i+2], 0 if d[3*i:3*i+3] == [1, 2, 3] else 255)]
escribir("rgb_trns", w, h, 2, 8, rows, esp, extra=chunk(b"tRNS", struct.pack(">HHH", 1, 2, 3)[0:0] + bytes([0, 1, 0, 2, 0, 3])))
# 7) imagenes de prueba de reemplazo: 4x4 original -> PNG 8x8, damero, y gradiente impar 5x3
def lisos(nombre, w, h, f):
    px = [f(x, y) for y in range(h) for x in range(w)]
    rows = [bytes(v for p in px[y * w:(y + 1) * w] for v in p) for y in range(h)]
    escribir(nombre, w, h, 6, 8, rows, [v for p in px for v in p])
lisos("damero8", 8, 8, lambda x, y: (255, 255, 255, 255) if (x + y) % 2 == 0 else (0, 0, 0, 255))
lisos("alfa8", 8, 8, lambda x, y: (255, 0, 0, 255) if x % 2 == 0 else (0, 255, 0, 0))
lisos("impar5x3", 5, 3, lambda x, y: (x * 50, y * 80, 100, 255))
lisos("fila_arriba", 4, 4, lambda x, y: (255, 0, 0, 255) if y == 0 else (0, 0, 255, 255))
print("ok", len(os.listdir(out)))
