"""Lector de archivos .szs del juego (Yaz0 + SARC).

Uso:
  py -I szs.py censo  <carpeta_romfs> <salida.tsv>   # que formatos hay dentro de todos los .szs
  py -I szs.py listar <archivo.szs>                  # lista el contenido de uno
  py -I szs.py extraer <archivo.szs> <carpeta>       # extrae su contenido
"""
import collections
import os
import struct
import sys


def yaz0(datos):
    """Descomprime Yaz0. Si no es Yaz0, devuelve los datos tal cual."""
    if datos[:4] != b"Yaz0":
        return datos
    tam = struct.unpack_from(">I", datos, 4)[0]
    out = bytearray(tam)
    src, dst = 16, 0
    while dst < tam:
        cabecera = datos[src]
        src += 1
        for bit in range(7, -1, -1):
            if dst >= tam:
                break
            if cabecera & (1 << bit):
                out[dst] = datos[src]
                src += 1
                dst += 1
            else:
                b1, b2 = datos[src], datos[src + 1]
                src += 2
                dist = ((b1 & 0x0F) << 8 | b2) + 1
                n = b1 >> 4
                if n == 0:
                    n = datos[src] + 0x12
                    src += 1
                else:
                    n += 2
                for _ in range(n):
                    out[dst] = out[dst - dist]
                    dst += 1
    return bytes(out)


def narc(datos):
    """NARC (heredado del DS): secciones BTAF (tabla de archivos), BTNF (nombres), GMIF (datos)."""
    off = struct.unpack_from("<H", datos, 0x0C)[0]
    secciones = {}
    for _ in range(struct.unpack_from("<H", datos, 0x0E)[0]):
        magia, tam = datos[off:off + 4], struct.unpack_from("<I", datos, off + 4)[0]
        secciones[magia] = off
        off += tam
    btaf, btnf, gmif = secciones[b"BTAF"], secciones[b"BTNF"], secciones[b"GMIF"]
    n = struct.unpack_from("<H", datos, btaf + 8)[0]
    rangos = [struct.unpack_from("<II", datos, btaf + 12 + 8 * i) for i in range(n)]
    base_datos = gmif + 8
    tabla = btnf + 8
    nombres = {}

    def recorrer(dir_id, ruta):
        sub, primero, _ = struct.unpack_from("<IHH", datos, tabla + 8 * (dir_id & 0xFFF))
        p, fid = tabla + sub, primero
        while True:
            largo = datos[p]
            p += 1
            if largo == 0:
                break
            nombre = datos[p:p + (largo & 0x7F)].decode("utf-8", "replace")
            p += largo & 0x7F
            if largo & 0x80:
                hijo = struct.unpack_from("<H", datos, p)[0]
                p += 2
                recorrer(hijo, ruta + nombre + "/")
            else:
                nombres[fid] = ruta + nombre
                fid += 1

    try:
        recorrer(0xF000, "")
    except (struct.error, IndexError):
        pass  # NARC sin tabla de nombres
    return [(nombres.get(i, f"archivo_{i:04d}"), datos[base_datos + a:base_datos + b]) for i, (a, b) in enumerate(rangos)]


def sarc(datos):
    """Devuelve lista de (nombre, bytes). Soporta NARC y SARC (little y big endian)."""
    if datos[:4] == b"NARC":
        return narc(datos)
    assert datos[:4] == b"SARC", "no es SARC ni NARC"
    e = "<" if datos[6:8] == b"\xff\xfe" else ">"
    inicio_datos = struct.unpack_from(e + "I", datos, 0x0C)[0]
    sfat = 0x14
    assert datos[sfat:sfat + 4] == b"SFAT"
    n = struct.unpack_from(e + "H", datos, sfat + 6)[0]
    nodos = [struct.unpack_from(e + "IIII", datos, sfat + 12 + 16 * i) for i in range(n)]
    sfnt = sfat + 12 + 16 * n
    nombres = sfnt + 8
    out = []
    for _, attr, ini, fin in nodos:
        if attr & 0x01000000:
            off = nombres + (attr & 0xFFFF) * 4
            nombre = datos[off:datos.index(b"\0", off)].decode("utf-8", "replace")
        else:
            nombre = f"sin_nombre_{ini:08x}"
        out.append((nombre, datos[inicio_datos + ini:inicio_datos + fin]))
    return out


def tipo(b):
    m = b[:4]
    if m in (b"BCH\0",):
        return "BCH"
    for magia, nombre in ((b"CGFX", "CGFX"), (b"BY\0", "BYML"), (b"YB", "BYML"), (b"SARC", "SARC"), (b"Yaz0", "Yaz0"),
                          (b"CLYT", "BCLYT"), (b"CLAN", "BCLAN"), (b"CLIM", "BCLIM"), (b"CSTM", "BCSTM"), (b"CWAV", "BCWAV"),
                          (b"CTPK", "CTPK"), (b"SPBD", "PTCL"), (b"MsgS", "MSBT"), (b"MsgP", "MSBP"), (b"darc", "DARC"),
                          (b"CFNT", "BCFNT"), (b"CSAR", "BCSAR"), (b"DVLB", "SHBIN")):
        if b.startswith(magia):
            return nombre
    if len(b) >= 0x28 and b[-0x28:-0x24] == b"CLIM":
        return "BCLIM"
    return "?" + m.hex()


def main():
    accion = sys.argv[1]
    if accion == "censo":
        raiz, salida = sys.argv[2], sys.argv[3]
        por_tipo = collections.Counter()
        ext = collections.Counter()
        ejemplos = collections.defaultdict(list)
        filas = []
        for carpeta, _, archivos in os.walk(raiz):
            for a in archivos:
                if not a.endswith(".szs"):
                    continue
                ruta = os.path.join(carpeta, a)
                try:
                    contenido = sarc(yaz0(open(ruta, "rb").read()))
                except Exception as ex:  # noqa: BLE001
                    filas.append((os.path.relpath(ruta, raiz), "ERROR", str(ex), 0))
                    continue
                for nombre, b in contenido:
                    t = tipo(b)
                    por_tipo[t] += 1
                    ext[os.path.splitext(nombre)[1].lower()] += 1
                    if len(ejemplos[t]) < 4:
                        ejemplos[t].append(os.path.relpath(ruta, raiz) + ":" + nombre)
                    filas.append((os.path.relpath(ruta, raiz), nombre, t, len(b)))
        with open(salida + ".tmp", "w", encoding="utf-8") as f:
            f.write("szs\tarchivo\ttipo\tbytes\n")
            for r in filas:
                f.write("\t".join(str(x) for x in r) + "\n")
        os.replace(salida + ".tmp", salida)
        print("archivos internos:", len(filas))
        print("por formato:")
        for t, c in por_tipo.most_common():
            print(f"  {t:12} {c:6}   ej: {'; '.join(ejemplos[t][:2])}")
        print("extensiones:", ext.most_common(15))
    elif accion == "listar":
        for nombre, b in sarc(yaz0(open(sys.argv[2], "rb").read())):
            print(f"  {len(b):>10,}  {tipo(b):8} {nombre}")
    elif accion == "extraer":
        destino = sys.argv[3]
        for nombre, b in sarc(yaz0(open(sys.argv[2], "rb").read())):
            p = os.path.join(destino, *nombre.split("/"))
            os.makedirs(os.path.dirname(p) or destino, exist_ok=True)
            with open(p, "wb") as f:
                f.write(b)


if __name__ == "__main__":
    main()
