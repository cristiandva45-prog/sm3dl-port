"""Lector basico de CGFX (.bcmdl): lista el contenido de cada seccion.

CGFX (NW4C, 3DS): cabecera 'CGFX' + bloque 'DATA' con 16 diccionarios ('DICT')
de: modelos, texturas, LUTs, materiales, shaders, camaras, luces, nieblas,
entornos, anim. esqueleticas, anim. de textura/material, anim. de visibilidad,
anim. de camara, anim. de luz, anim. de niebla, emisores.
Los offsets son relativos a la posicion donde estan escritos.

Uso:
  py -I cgfx.py listar <archivo.bcmdl | archivo.szs>
  py -I cgfx.py censo  <carpeta_romfs> <salida.tsv>
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import szs  # noqa: E402

SECCIONES = ["modelos", "texturas", "luts", "materiales", "shaders", "camaras", "luces", "nieblas",
             "entornos", "anim_esqueleto", "anim_material", "anim_visibilidad", "anim_camara",
             "anim_luz", "anim_niebla", "emisores"]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def rel(d, o):
    """Lee un offset relativo en o y devuelve la posicion absoluta (0 si es nulo)."""
    v = u32(d, o)
    return o + v if v else 0


def cadena(d, o):
    return d[o:d.index(b"\0", o)].decode("ascii", "replace") if o else ""


def diccionario(d, o):
    if not o:
        return []
    assert d[o:o + 4] == b"DICT", f"DICT esperado en {o:#x}"
    n = u32(d, o + 8)
    out = []
    # nodo raiz (0x10 bytes) en o+0x0C; entradas a partir de o+0x1C
    for i in range(n):
        e = o + 0x1C + 0x10 * i
        nombre = cadena(d, rel(d, e + 8))
        datos = rel(d, e + 12)
        out.append((nombre, datos))
    return out


def leer(datos):
    assert datos[:4] == b"CGFX", "no es CGFX"
    tam_cab = struct.unpack_from("<H", datos, 6)[0]
    data = tam_cab
    assert datos[data:data + 4] == b"DATA", "bloque DATA no encontrado"
    out = {}
    for i, sec in enumerate(SECCIONES):
        cuenta = u32(datos, data + 8 + 8 * i)
        if cuenta:
            out[sec] = diccionario(datos, rel(datos, data + 8 + 8 * i + 4))
    return out


def detalle_modelo(d, o):
    """Datos rapidos de un modelo: magia, mallas, materiales, si tiene esqueleto."""
    magia = d[o + 4:o + 8].decode("ascii", "replace")
    info = {"tipo": magia}
    # CMDL: tras la cabecera de objeto vienen (cuenta, offset) de animGroups, mallas, materiales...
    # Busqueda tolerante: diccionarios DICT referenciados en los primeros 0xC0 bytes.
    dicts = []
    for k in range(0, 0xC0, 4):
        p = o + k
        if p + 8 > len(d):
            break
        v = u32(d, p + 4)
        if v and p + 4 + v + 4 <= len(d) and d[p + 4 + v:p + 8 + v] == b"DICT":
            dicts.append((k, [n for n, _ in diccionario(d, p + 4 + v)]))
    info["dicts"] = dicts
    info["esqueleto"] = magia == "CMDL" and any(d[x:x + 4] == b"CSKL" for x in range(o, min(o + 0x400, len(d) - 4)))
    return info


def archivos_cgfx(ruta):
    if ruta.endswith(".szs"):
        for nombre, b in szs.sarc(szs.yaz0(open(ruta, "rb").read())):
            if b[:4] == b"CGFX":
                yield nombre, b
    else:
        yield os.path.basename(ruta), open(ruta, "rb").read()


def main():
    accion = sys.argv[1]
    if accion == "listar":
        for nombre, b in archivos_cgfx(sys.argv[2]):
            print(f"== {nombre} ({len(b):,} bytes)")
            for sec, entradas in leer(b).items():
                print(f"  {sec} ({len(entradas)}): {', '.join(n for n, _ in entradas[:20])}{' ...' if len(entradas) > 20 else ''}")
                if sec == "modelos":
                    for n, o in entradas[:3]:
                        print(f"     {n}: {detalle_modelo(b, o)}")
    elif accion == "censo":
        raiz, salida = sys.argv[2], sys.argv[3]
        totales = collections.Counter()
        archivos_con = collections.Counter()
        errores = []
        filas = []
        for carpeta, _, archivos in os.walk(raiz):
            for a in archivos:
                if not a.endswith(".szs"):
                    continue
                ruta = os.path.join(carpeta, a)
                try:
                    for nombre, b in archivos_cgfx(ruta):
                        secs = leer(b)
                        for sec, ent in secs.items():
                            totales[sec] += len(ent)
                            archivos_con[sec] += 1
                        filas.append((os.path.relpath(ruta, raiz), nombre,
                                      *[len(secs.get(s, [])) for s in SECCIONES]))
                except Exception as ex:  # noqa: BLE001
                    errores.append(f"{a}: {ex}")
        with open(salida + ".tmp", "w", encoding="utf-8") as f:
            f.write("szs\tarchivo\t" + "\t".join(SECCIONES) + "\n")
            for r in filas:
                f.write("\t".join(str(x) for x in r) + "\n")
        os.replace(salida + ".tmp", salida)
        print(f"archivos CGFX: {len(filas)}  errores: {len(errores)}")
        for e in errores[:5]:
            print("  ERROR", e)
        for s in SECCIONES:
            if totales[s]:
                print(f"  {s:18} {totales[s]:6} entradas en {archivos_con[s]:5} archivos")


if __name__ == "__main__":
    main()
