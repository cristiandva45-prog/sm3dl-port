"""Extrae las texturas de archivos CGFX (.bcmdl / .szs) a PNG.

Decodifica los 14 formatos de la GPU PICA200 del 3DS, con el entrelazado
en mosaicos de 8x8 (orden Morton) y la imagen invertida verticalmente.

Uso:
  py -I texturas.py <archivo.szs|.bcmdl> <carpeta_salida>
  py -I texturas.py --todo <carpeta_romfs> <carpeta_salida>     # todas las del juego
"""
import os
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cgfx  # noqa: E402

FORMATOS = {0: ("RGBA8", 32), 1: ("RGB8", 24), 2: ("RGBA5551", 16), 3: ("RGB565", 16), 4: ("RGBA4", 16),
            5: ("LA8", 16), 6: ("HILO8", 16), 7: ("L8", 8), 8: ("A8", 8), 9: ("LA4", 8), 10: ("L4", 4),
            11: ("A4", 4), 12: ("ETC1", 4), 13: ("ETC1A4", 8)}

# A8/A4: la PICA entrega (0,0,0,a) (Azahar texture_decode). Antes era 255 para que los PNG se vieran en
# cualquier visor, y texturas.c copio ese blanco: la verificacion C-vs-Python daba verde con los dos mal
# (7 oct: iconos de boton invisibles en los globos-guia). Para exportar PNG visibles, poner 255 aqui.
SOLO_ALFA_RGB = 0

ETC_TABLA = [(2, 8), (5, 17), (9, 29), (13, 42), (18, 60), (24, 80), (33, 106), (47, 183)]
MORTON = [((i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4), ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4)) for i in range(64)]


def _c(v):
    return 0 if v < 0 else 255 if v > 255 else v


def etc1_bloque(bloque, alfa):
    """Decodifica un bloque ETC1 de 4x4. Devuelve dict (x,y)->(r,g,b,a)."""
    hi, lo = bloque >> 32, bloque & 0xFFFFFFFF
    flip, diff = hi & 1, (hi >> 1) & 1
    t1, t2 = (hi >> 5) & 7, (hi >> 2) & 7
    if diff:
        def d3(v):
            return v - 8 if v & 4 else v
        r1, g1, b1 = (hi >> 27) & 31, (hi >> 19) & 31, (hi >> 11) & 31
        r2, g2, b2 = r1 + d3((hi >> 24) & 7), g1 + d3((hi >> 16) & 7), b1 + d3((hi >> 8) & 7)
        ex = [lambda v: (v << 3) | (v >> 2)] * 1
        c1 = tuple(ex[0](v & 31) for v in (r1, g1, b1))
        c2 = tuple(ex[0](v & 31) for v in (r2, g2, b2))
    else:
        c1 = tuple(((hi >> s) & 15) * 17 for s in (28, 20, 12))
        c2 = tuple(((hi >> s) & 15) * 17 for s in (24, 16, 8))
    out = {}
    for x in range(4):
        for y in range(4):
            p = x * 4 + y
            segundo = (y >= 2) if flip else (x >= 2)
            base, tabla = (c2, ETC_TABLA[t2]) if segundo else (c1, ETC_TABLA[t1])
            idx = ((lo >> (p + 16)) & 1) * 2 + ((lo >> p) & 1)
            mod = (tabla[0], tabla[1], -tabla[0], -tabla[1])[idx]
            a = ((alfa >> (4 * p)) & 15) * 17 if alfa is not None else 255
            out[(x, y)] = (_c(base[0] + mod), _c(base[1] + mod), _c(base[2] + mod), a)
    return out


def decodificar(datos, ancho, alto, fmt):
    img = Image.new("RGBA", (ancho, alto))
    px = img.load()
    nombre, bpp = FORMATOS[fmt]
    o = 0
    for ty in range(0, alto, 8):
        for tx in range(0, ancho, 8):
            if nombre in ("ETC1", "ETC1A4"):
                for bx, by in ((0, 0), (4, 0), (0, 4), (4, 4)):
                    alfa = None
                    if nombre == "ETC1A4":
                        alfa = struct.unpack_from("<Q", datos, o)[0]
                        o += 8
                    bloque = struct.unpack_from("<Q", datos, o)[0]
                    o += 8
                    for (x, y), c in etc1_bloque(bloque, alfa).items():
                        X, Y = tx + bx + x, ty + by + y
                        if X < ancho and Y < alto:
                            px[X, Y] = c
                continue
            for i in range(64):
                x, y = MORTON[i]
                if bpp == 32:
                    a, b, g, r = datos[o:o + 4]
                    o += 4
                elif bpp == 24:
                    b, g, r = datos[o:o + 3]
                    a = 255
                    o += 3
                elif bpp == 16:
                    v = datos[o] | (datos[o + 1] << 8)
                    o += 2
                    if nombre == "RGBA5551":
                        r, g, b = ((v >> 11) & 31) * 255 // 31, ((v >> 6) & 31) * 255 // 31, ((v >> 1) & 31) * 255 // 31
                        a = 255 if v & 1 else 0
                    elif nombre == "RGB565":
                        r, g, b, a = ((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31, 255
                    elif nombre == "RGBA4":
                        r, g, b, a = ((v >> 12) & 15) * 17, ((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17
                    elif nombre == "LA8":
                        r = g = b = v >> 8
                        a = v & 255
                    else:  # HILO8 (mapas de normales): HI->R, LO->G
                        r, g, b, a = v >> 8, v & 255, 255, 255
                elif bpp == 8:
                    v = datos[o]
                    o += 1
                    if nombre == "L8":
                        r = g = b = v
                        a = 255
                    elif nombre == "A8":
                        r = g = b = SOLO_ALFA_RGB
                        a = v
                    else:  # LA4
                        r = g = b = (v >> 4) * 17
                        a = (v & 15) * 17
                else:  # 4 bits: dos pixeles por byte, primero el nibble bajo
                    v = (datos[o] >> (4 * (i & 1))) & 15
                    if i & 1:
                        o += 1
                    if nombre == "L4":
                        r = g = b = v * 17
                        a = 255
                    else:  # A4
                        r = g = b = SOLO_ALFA_RGB
                        a = v * 17
                X, Y = tx + x, ty + y
                if X < ancho and Y < alto:
                    px[X, Y] = (r, g, b, a)
    return img.transpose(Image.FLIP_TOP_BOTTOM)


def texturas_de(b):
    """Devuelve (nombre, ancho, alto, fmt, bytes) de cada TXOB del CGFX."""
    u32 = cgfx.u32
    out = []
    for nombre, o in cgfx.leer(b).get("texturas", []):
        if b[o + 4:o + 8] != b"TXOB":
            continue
        alto, ancho = u32(b, o + 0x18), u32(b, o + 0x1C)
        fmt = u32(b, o + 0x34)
        # La imagen va embebida desde +0x3C: alto, ancho, largo (con mipmaps), offset relativo a los pixeles
        img = o + 0x3C
        pixeles = cgfx.rel(b, img + 12)
        if fmt not in FORMATOS or not pixeles:
            out.append((nombre, ancho, alto, fmt, None))
            continue
        largo = u32(b, img + 8)
        datos = b[pixeles:pixeles + largo]  # el nivel 0 va primero; los mipmaps siguientes se ignoran
        out.append((nombre, ancho, alto, fmt, datos))
    return out


def extraer(ruta, destino, resumen):
    os.makedirs(destino, exist_ok=True)
    for _, b in cgfx.archivos_cgfx(ruta):
        for nombre, ancho, alto, fmt, datos in texturas_de(b):
            nom_fmt = FORMATOS.get(fmt, (f"?{fmt}", 0))[0]
            if datos is None:
                resumen.append(f"{nombre}\t{ancho}x{alto}\t{nom_fmt}\tSIN DATOS")
                continue
            esperado = ancho * alto * FORMATOS[fmt][1] // 8
            if len(datos) < esperado:
                resumen.append(f"{nombre}\t{ancho}x{alto}\t{nom_fmt}\tCORTO {len(datos)}<{esperado}")
                continue
            archivo = os.path.join(destino, nombre.replace("/", "_") + ".png")
            decodificar(datos, ancho, alto, fmt).save(archivo)
            resumen.append(f"{nombre}\t{ancho}x{alto}\t{nom_fmt}\tok")


def main():
    resumen = []
    if sys.argv[1] == "--todo":
        raiz, destino = sys.argv[2], sys.argv[3]
        for carpeta, _, archivos in os.walk(raiz):
            for a in sorted(archivos):
                if a.endswith(".szs"):
                    extraer(os.path.join(carpeta, a), os.path.join(destino, a[:-4]), resumen)
    else:
        extraer(sys.argv[1], sys.argv[2], resumen)
    ok = sum(1 for r in resumen if r.endswith("ok"))
    print(f"texturas: {len(resumen)}  convertidas: {ok}  con problema: {len(resumen) - ok}")
    for r in resumen[:15]:
        print("  " + r)
    malos = [r for r in resumen if not r.endswith("ok")]
    for r in malos[:10]:
        print("  PROBLEMA " + r)


if __name__ == "__main__":
    main()
