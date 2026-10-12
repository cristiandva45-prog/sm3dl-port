r"""Compara dos carpetas de capturas (PNG de SM3DL_CAPTURAS, BMP de SM3DL_FOTO_VENTANA) pixel a pixel. EXACTO: cualquier
pixel distinto cuenta. No necesita PIL (lector PNG minimo: RGB/RGBA 8 bits, sin entrelazado; BMP 24/32 bits).
Uso: py -I agentes_dx12\A\tools\comparar_capturas.py <carpetaA> <carpetaB> [--esperar-diferencia]
  exit 0: todos los archivos con el mismo nombre son IGUALES (0 px distintos) y ninguna carpeta tiene archivos que falten en la otra
  --esperar-diferencia (control con sabotaje): exit 0 solo si SE DETECTA al menos una diferencia"""
import os, struct, sys, zlib


def leer_png(ruta):
    d = open(ruta, 'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n', 'no es PNG'
    o, idat, ihdr = 8, b'', None
    while o < len(d):
        n, t = struct.unpack('>I4s', d[o:o + 8])
        body = d[o + 8:o + 8 + n]
        if t == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', body)
        elif t == b'IDAT':
            idat += body
        o += 12 + n
    w, h, prof, tipo, _, _, entre = ihdr
    assert prof == 8 and tipo in (2, 6) and entre == 0, 'PNG no soportado %r' % (ihdr,)
    bpp = 3 if tipo == 2 else 4
    raw = zlib.decompress(idat)
    fila = w * bpp
    prev = bytearray(fila)
    out = bytearray()
    p = 0
    for _ in range(h):
        f = raw[p]
        cur = bytearray(raw[p + 1:p + 1 + fila])
        p += 1 + fila
        for i in range(fila):
            a = cur[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1: cur[i] = (cur[i] + a) & 255
            elif f == 2: cur[i] = (cur[i] + b) & 255
            elif f == 3: cur[i] = (cur[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[i] = (cur[i] + pr) & 255
        out += cur
        prev = cur
    return w, h, bpp, bytes(out)


def leer_bmp(ruta):
    d = open(ruta, 'rb').read()
    off = struct.unpack_from('<I', d, 10)[0]
    w, h, _, bits = struct.unpack_from('<iiHH', d, 18)
    return abs(w), abs(h), bits // 8, d[off:]


def leer(ruta):
    return leer_bmp(ruta) if ruta.lower().endswith('.bmp') else leer_png(ruta)


def main():
    a, b = sys.argv[1], sys.argv[2]
    esperar = '--esperar-diferencia' in sys.argv
    fa = {f for f in os.listdir(a) if f.lower().endswith(('.png', '.bmp'))}
    fb = {f for f in os.listdir(b) if f.lower().endswith(('.png', '.bmp'))}
    comunes = sorted(fa & fb)
    faltan = sorted(fa ^ fb)
    malos = 0
    total_px = 0
    for f in comunes:
        wa, ha, ba, da = leer(os.path.join(a, f))
        wb, hb, bb, db = leer(os.path.join(b, f))
        if (wa, ha, ba) != (wb, hb, bb):
            print('%-22s TAMANO DISTINTO %r vs %r' % (f, (wa, ha, ba), (wb, hb, bb)))
            malos += 1
            continue
        n = len(da) // ba
        dif = sum(1 for i in range(0, len(da), ba) if da[i:i + ba] != db[i:i + ba]) if da != db else 0
        total_px += n
        print('%-22s %dx%d  px distintos: %d%s' % (f, wa, ha, dif, '' if not dif else '   <---'))
        malos += dif > 0
    print('archivos comparados: %d, con diferencias: %d, solo en una carpeta: %d %s' % (len(comunes), malos, len(faltan), faltan[:6]))
    hay_dif = malos > 0 or bool(faltan)
    if esperar:
        print('CONTROL (sabotaje):', 'diferencia DETECTADA' if hay_dif else 'NO se detecto nada: la comparacion NO sirve')
        sys.exit(0 if hay_dif else 1)
    print('RESULTADO:', 'DISTINTO' if hay_dif else 'IGUAL (0 px)')
    sys.exit(1 if hay_dif or not comunes else 0)


if __name__ == '__main__':
    main()
