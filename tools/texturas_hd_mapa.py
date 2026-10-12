"""Mapa de texturas para el sistema de reemplazo HD (T3, 9 oct 2026).

Para cada textura del ROM (CGFX de modelos + BCLIM de LayoutData) reconstruye los bytes CRUDOS del nivel 0 tal como
los sube el juego, calcula la CLAVE con el MISMO fnv que raster_gl.c y escribe:
  texturas_hd_fuente\\tex_<w>x<h>_f<fmt>_<CLAVE %08X>.png   (original decodificado = nombre del reemplazo)
  texturas_hd_fuente\\mapa.tsv   (clave, w, h, fmt, archivo del ROM, textura, escena, estado)

CLAVE (raster_gl.c:82, fnv): h = 2166136261; por cada palabra u32 little-endian del nivel 0: h ^= p; h *= 16777619.
Palabras = tex_tamano(w,h,fmt)/4, con tex_tamano = ceil(w/8)*ceil(h/8)*64*bpp/8 (rellena a multiplo de 8, texturas.c:74).
fmt = numeracion PICA 0..13 (la de texturas.py; BCLIM se traduce con BCLIM_A_PICA).

Uso:
  py -I tools\\texturas_hd_mapa.py [--romfs extraido\\romfs] [--salida texturas_hd_fuente] [--limite N] [--solo-clave]
  py -I tools\\texturas_hd_mapa.py --autoprueba       # vectores fnv + sabotaje, sin tocar el ROM
  py -I tools\\texturas_hd_mapa.py --verificar        # re-decodifica y compara con extraido\\texturas_png (0 px distintos)
"""
import argparse
import os
import struct
import sys
import time

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import cgfx  # noqa: E402
import szs  # noqa: E402
import texturas  # noqa: E402

BCLIM_A_PICA = {0: 7, 1: 8, 2: 9, 3: 5, 4: 6, 5: 3, 6: 1, 7: 2, 8: 4, 9: 0, 10: 12, 11: 13, 12: 10, 13: 11}
BPP = [texturas.FORMATOS[i][1] for i in range(14)]


def tex_tamano(w, h, fmt):
    """Igual que texturas.c tex_tamano."""
    if fmt < 0 or fmt > 13 or w <= 0 or h <= 0:
        return 0
    return ((w + 7) // 8) * ((h + 7) // 8) * 64 * BPP[fmt] // 8


def fnv(datos):
    """FNV-1a por palabras u32 LE, igual que raster_gl.c fnv(p, n) con n = len//4."""
    h = 2166136261
    n = len(datos) // 4
    for p in struct.unpack_from("<%dI" % n, datos):
        h = ((h ^ p) * 16777619) & 0xFFFFFFFF
    return h


def clave_nivel0(datos, w, h, fmt):
    """Devuelve (clave, completo). completo=False si el archivo trae menos bytes que tex_tamano (el juego leeria
    memoria vecina: clave dudosa)."""
    t = tex_tamano(w, h, fmt)
    nivel0 = bytes(datos[:t])
    return fnv(nivel0), len(nivel0) == t


def nombre_png(w, h, fmt, clave):
    return "tex_%dx%d_f%d_%08X.png" % (w, h, fmt, clave)


def texturas_romfs(romfs, limite=0, filtro=""):
    """Genera (archivo_rom, escena, nombre, w, h, fmt, datos_crudos_nivel0_o_mas, origen)."""
    n = 0
    for carpeta, _, archivos in os.walk(romfs):
        for a in sorted(archivos):
            if not a.endswith(".szs"):
                continue
            ruta = os.path.join(carpeta, a)
            if filtro and filtro not in ruta:
                continue
            rel = os.path.relpath(ruta, romfs).replace("\\", "/")
            escena = a[:-4]
            try:
                for _, b in cgfx.archivos_cgfx(ruta):
                    for nombre, w, h, fmt, datos in texturas.texturas_de(b):
                        yield rel, escena, nombre, w, h, fmt, datos, "cgfx"
            except Exception as e:  # un szs roto no debe parar el censo
                print("  AVISO %s: %s" % (rel, e), file=sys.stderr)
            if carpeta.replace("\\", "/").endswith("LayoutData") or "/LayoutData" in carpeta.replace("\\", "/") + "/":
                try:
                    b = open(ruta, "rb").read()
                    if b[:4] == b"Yaz0":
                        b = szs.yaz0(b)
                    for nom, c in szs.sarc(b):
                        i = c.rfind(b"imag")
                        if not nom.endswith(".bclim") or i < 0:
                            continue
                        w, h, fb = struct.unpack_from("<HHI", c, i + 8)
                        fmt = BCLIM_A_PICA.get(fb)
                        if fmt is None:
                            continue
                        yield rel, escena, nom, w, h, fmt, c[:i], "bclim"
                except Exception as e:
                    print("  AVISO bclim %s: %s" % (rel, e), file=sys.stderr)
            n += 1
            if limite and n >= limite:
                return


def autoprueba():
    # 1) fnv contra el C: vectores calculados a mano con la definicion (h=2166136261; h^=p; h*=16777619)
    assert fnv(b"") == 2166136261
    p = 0x01020304
    esperado = ((2166136261 ^ p) * 16777619) & 0xFFFFFFFF
    assert fnv(struct.pack("<I", p)) == esperado, "fnv una palabra"
    a, b = 0xAABBCCDD, 0x11223344
    e2 = ((esperado ^ 0) * 16777619) & 0xFFFFFFFF
    assert fnv(struct.pack("<II", p, 0)) == e2, "fnv dos palabras"
    # sobre bytes sueltos (<4) no cuenta (n = len/4 como el C)
    assert fnv(struct.pack("<I", p) + b"\x01\x02\x03") == esperado
    # 2) tex_tamano contra texturas.c (BPP/rellenado a 8)
    assert tex_tamano(8, 8, 0) == 256 and tex_tamano(4, 4, 12) == 32 and tex_tamano(16, 8, 13) == 128
    assert tex_tamano(30, 30, 7) == 32 * 32
    # 3) sabotaje: cambiar UN bit del nivel 0 debe cambiar la clave; cambiar un byte del nivel 1 NO
    nivel0 = bytes(range(256)) * 1
    nivel1 = bytes(64)
    k0, _ = clave_nivel0(nivel0 + nivel1, 8, 8, 0)
    k_mip, _ = clave_nivel0(nivel0 + bytes([1]) * 64, 8, 8, 0)
    assert k0 == k_mip, "la clave no debe depender de los mips"
    mal = bytearray(nivel0)
    mal[100] ^= 1
    k_mal, _ = clave_nivel0(bytes(mal), 8, 8, 0)
    assert k_mal != k0, "SABOTAJE no detectado"
    print("autoprueba OK (fnv, tex_tamano, independencia de mips, sabotaje de 1 bit detectado: %08X != %08X)" % (k0, k_mal))


def comparar_con_png(img, ruta_png):
    """Cuenta pixeles distintos contra extraido\\texturas_png (-1 si no existe o tamano distinto)."""
    if not os.path.exists(ruta_png):
        return -1
    o = Image.open(ruta_png).convert("RGBA")
    if o.size != img.size:
        return -2
    a, b = img.convert("RGBA").tobytes(), o.tobytes()
    return sum(1 for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4]) if a != b else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--romfs", default=os.path.join(RAIZ, "extraido", "romfs"))
    ap.add_argument("--salida", default=os.path.join(RAIZ, "texturas_hd_fuente"))
    ap.add_argument("--png-ref", default=os.path.join(RAIZ, "extraido", "texturas_png"))
    ap.add_argument("--limite", type=int, default=0, help="solo los N primeros .szs (pruebas)")
    ap.add_argument("--solo-clave", action="store_true", help="no escribe PNG")
    ap.add_argument("--filtro", default="", help="solo rutas que contengan este texto")
    ap.add_argument("--autoprueba", action="store_true")
    ap.add_argument("--sabotaje", action="store_true", help="corrompe 1 byte antes de comparar: la verificacion DEBE fallar")
    args = ap.parse_args()
    if args.autoprueba:
        autoprueba()
        return
    os.makedirs(args.salida, exist_ok=True)
    t0 = time.time()
    claves = {}      # clave -> (w,h,fmt,pixeles md5)
    filas = []
    cuenta = dict(total=0, unicas=0, dudosas=0, dif_png=0, sin_ref=0, sin_datos=0, choque=0)
    for rel, escena, nombre, w, h, fmt, datos, origen in texturas_romfs(args.romfs, args.limite, args.filtro):
        cuenta["total"] += 1
        if datos is None or fmt not in texturas.FORMATOS:
            cuenta["sin_datos"] += 1
            filas.append(("", w, h, fmt, rel, nombre, escena, "SIN_DATOS"))
            continue
        if args.sabotaje and origen == "cgfx" and not cuenta.get("_sab"):
            cuenta["_sab"] = 1
            datos = bytearray(datos)
            datos[0] ^= 0xFF
            datos = bytes(datos)
        clave, completo = clave_nivel0(datos, w, h, fmt)
        estado = "ok" if completo else "CLAVE_DUDOSA_corto"
        if not completo:
            cuenta["dudosas"] += 1
        archivo = nombre_png(w, h, fmt, clave)
        ident = (w, h, fmt)
        if clave in claves and claves[clave] != ident:
            cuenta["choque"] += 1
            estado += "+CHOQUE_wh_fmt"
        if clave not in claves:
            claves[clave] = ident
            cuenta["unicas"] += 1
            if not args.solo_clave or origen == "cgfx":
                nivel0 = datos[:tex_tamano(w, h, fmt)]
                if len(nivel0) < tex_tamano(w, h, fmt):
                    nivel0 = nivel0 + bytes(tex_tamano(w, h, fmt) - len(nivel0))
                img = texturas.decodificar(nivel0, w, h, fmt)
                if not args.solo_clave:
                    img.save(os.path.join(args.salida, archivo))
                if origen == "cgfx":
                    ref = os.path.join(args.png_ref, escena, nombre.replace("/", "_") + ".png")
                    d = comparar_con_png(img, ref)
                    if d == -1:
                        cuenta["sin_ref"] += 1
                    elif d != 0:
                        cuenta["dif_png"] += 1
                        estado += "+DIF_PNG(%d)" % d
        filas.append(("%08X" % clave, w, h, fmt, rel, nombre, escena, estado))
        if cuenta["total"] % 500 == 0:
            print("  ...%d texturas, %d unicas, %.0f s" % (cuenta["total"], cuenta["unicas"], time.time() - t0), flush=True)
    tmp = os.path.join(args.salida, "mapa.tsv.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("clave\tw\th\tfmt\tarchivo_rom\ttextura\tescena\testado\n")
        for fila in filas:
            f.write("\t".join(str(c) for c in fila) + "\n")
    os.replace(tmp, os.path.join(args.salida, "mapa.tsv"))
    print("RESULTADO %s  (%.0f s)" % (cuenta, time.time() - t0))
    if cuenta["dif_png"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
