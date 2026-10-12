r"""Extrae las FUENTES del juego (BCFNT de LocalizedData\UsSpanish\LayoutData\Font.szs) para que la interfaz del port
(menu de ajustes, "PULSA CUALQUIER TECLA") use la tipografia original y no una de Windows.

Salida por fuente en extraido\fuentes\:
  <nombre>.rgba   hojas de glifos apiladas en vertical, RGBA8 (decodificadas con tools\texturas.py)
  <nombre>.txt    cabecera "hoja_w hoja_h n_hojas celda_w celda_h columnas filas linea ascenso" y luego una linea por
                  caracter: "codigo indice izquierda ancho_glifo ancho_caracter"
Uso: py -I tools\extraer_fuente.py [--muestra "texto"]   (la muestra se guarda en extraido\fuentes\muestra_<f>.png)
"""
import os
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.append(AQUI)
import szs  # noqa: E402
import texturas  # noqa: E402

FUENTES = ("MarioFont32", "MessageFont18", "MessageFont14", "PictureFont20")


def leer_cfnt(b):
    assert b[:4] == b"CFNT"
    # FINF (CTR): firma, tamano, tipo u8, salto de linea u8, caracter alterno u16, ancho por defecto (3), codificacion,
    # punteros a TGLP/CWDH/CMAP (apuntan a los datos, 8 bytes despues de cada firma), alto, ancho, ascenso
    finf = b.find(b"FINF")
    tipo, linea, alterno = struct.unpack_from("<BBH", b, finf + 8)
    tglp, cwdh, cmap = struct.unpack_from("<III", b, finf + 16)
    alto, ancho, ascenso = struct.unpack_from("<BBB", b, finf + 28)
    # TGLP (CTR): celda w,h, linea base, ancho max, tamano de hoja u32, N HOJAS u16, formato, columnas, filas, w, h, datos
    cw, ch, base, maxw, sh_sz, n_sh, fmt, cols, rows, sw, shh, datos = struct.unpack_from("<BBBBIHHHHHHI", b, tglp)
    hojas = []
    for k in range(n_sh):
        crudo = b[datos + k * sh_sz: datos + (k + 1) * sh_sz]
        hojas.append(texturas.decodificar(crudo, sw, shh, fmt).convert("RGBA"))
    # CWDH: anchos por indice de glifo (lista enlazada)
    anchos = {}
    c = cwdh
    while c:
        i0, i1, sig = struct.unpack_from("<HHI", b, c)
        for i in range(i0, i1 + 1):
            anchos[i] = struct.unpack_from("<bBB", b, c + 8 + 3 * (i - i0))
        c = sig
    # CMAP: codigo -> indice (directo, tabla o scan)
    mapa = {}
    c = cmap
    while c:
        c0, c1, metodo, _, sig = struct.unpack_from("<HHHHI", b, c)
        if metodo == 0:
            off = struct.unpack_from("<H", b, c + 12)[0]
            for cc in range(c0, c1 + 1):
                mapa[cc] = off + cc - c0
        elif metodo == 1:
            for cc in range(c0, c1 + 1):
                ix = struct.unpack_from("<H", b, c + 12 + 2 * (cc - c0))[0]
                if ix != 0xFFFF:
                    mapa[cc] = ix
        else:
            n = struct.unpack_from("<H", b, c + 12)[0]
            for k in range(n):
                cc, ix = struct.unpack_from("<HH", b, c + 14 + 4 * k)
                mapa[cc] = ix
        c = sig
    return dict(hojas=hojas, cw=cw, ch=ch, cols=cols, rows=rows, sw=sw, sh=shh, linea=linea, ascenso=ascenso,
                anchos=anchos, mapa=mapa, fmt=fmt)


def muestra(f, texto, ruta):
    from PIL import Image
    x, total = 0, sum((f["anchos"].get(f["mapa"].get(ord(ch), 0), (0, 0, f["cw"]))[2]) for ch in texto)
    img = Image.new("RGBA", (total + 8, f["ch"] + 8), (90, 140, 220, 255))
    x = 4
    for ch in texto:
        ix = f["mapa"].get(ord(ch))
        if ix is None:
            x += f["cw"] // 2
            continue
        izq, ancho_g, ancho_c = f["anchos"].get(ix, (0, f["cw"], f["cw"]))
        por_hoja = f["cols"] * f["rows"]
        hoja, r = divmod(ix, por_hoja)
        fila, col = divmod(r, f["cols"])
        celda = f["hojas"][hoja].crop((col * (f["cw"] + 1), fila * (f["ch"] + 1), col * (f["cw"] + 1) + f["cw"],
                                       fila * (f["ch"] + 1) + f["ch"]))
        img.alpha_composite(celda, (x + izq, 4))
        x += ancho_c
    img.save(ruta)


def main():
    d = open(os.path.join(RAIZ, "extraido", "romfs", "LocalizedData", "UsSpanish", "LayoutData", "Font.szs"), "rb").read()
    if d[:4] == b"Yaz0":
        d = szs.yaz0(d)
    salida = os.path.join(RAIZ, "extraido", "fuentes")
    os.makedirs(salida, exist_ok=True)
    texto = sys.argv[sys.argv.index("--muestra") + 1] if "--muestra" in sys.argv else None
    for nom, b in szs.sarc(d):
        base = os.path.splitext(os.path.basename(nom))[0]
        if base not in FUENTES:
            continue
        f = leer_cfnt(b)
        with open(os.path.join(salida, base + ".rgba"), "wb") as fh:
            for h in f["hojas"]:
                fh.write(h.tobytes())
        with open(os.path.join(salida, base + ".txt"), "w", encoding="ascii") as fh:
            fh.write(f"{f['sw']} {f['sh']} {len(f['hojas'])} {f['cw']} {f['ch']} {f['cols']} {f['rows']} {f['linea']} "
                     f"{f['ascenso']}\n")
            for cc in sorted(f["mapa"]):
                ix = f["mapa"][cc]
                izq, ag, ac = f["anchos"].get(ix, (0, f["cw"], f["cw"]))
                fh.write(f"{cc} {ix} {izq} {ag} {ac}\n")
        print(f"{base}: formato {f['fmt']}, celda {f['cw']}x{f['ch']}, {len(f['hojas'])} hojas, {len(f['mapa'])} caracteres")
        if texto:
            muestra(f, texto, os.path.join(salida, f"muestra_{base}.png"))


if __name__ == "__main__":
    main()
