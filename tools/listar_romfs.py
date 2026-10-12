"""Lista (y opcionalmente extrae) los archivos del RomFS de un .3ds descifrado.

Uso: py -I listar_romfs.py <rom.3ds> <salida.txt> [carpeta_para_extraer]
"""
import os
import struct
import sys

MEDIA = 0x200


def main():
    rom, salida = sys.argv[1], sys.argv[2]
    destino = sys.argv[3] if len(sys.argv) > 3 else None
    f = open(rom, "rb")
    ncsd = f.read(0x200)
    p0 = struct.unpack_from("<I", ncsd, 0x120)[0] * MEDIA
    f.seek(p0)
    ncch = f.read(0x200)
    romfs_off = p0 + struct.unpack_from("<I", ncch, 0x1B0)[0] * MEDIA
    f.seek(romfs_off)
    ivfc = f.read(0x60)
    assert ivfc[:4] == b"IVFC", "RomFS sin cabecera IVFC"
    # El nivel 3 empieza tras la cabecera IVFC + hash maestro, alineado al bloque del nivel 3
    master_hash = struct.unpack_from("<I", ivfc, 0x8)[0]
    lv3_bloque = 1 << struct.unpack_from("<I", ivfc, 0x4C)[0]
    lv3 = romfs_off + ((0x60 + master_hash + lv3_bloque - 1) & ~(lv3_bloque - 1))
    f.seek(lv3)
    cab = struct.unpack("<10I", f.read(0x28))
    dir_meta_off, dir_meta_tam = cab[3], cab[4]
    file_meta_off, file_meta_tam = cab[7], cab[8]
    datos_off = cab[9]
    f.seek(lv3 + dir_meta_off)
    dmeta = f.read(dir_meta_tam)
    f.seek(lv3 + file_meta_off)
    fmeta = f.read(file_meta_tam)

    filas = []

    def nombre(meta, off, base):
        largo = struct.unpack_from("<I", meta, off + base)[0]
        return meta[off + base + 4 : off + base + 4 + largo].decode("utf-16le")

    def recorrer_dir(off, ruta):
        _, _, hijo, archivo, _ = struct.unpack_from("<5I", dmeta, off)
        while archivo != 0xFFFFFFFF:
            _, sig, d_off, d_tam, _ = struct.unpack_from("<IIQQI", fmeta, archivo)
            n = nombre(fmeta, archivo, 0x1C)
            filas.append((ruta + "/" + n, d_tam, lv3 + datos_off + d_off))
            archivo = sig
        while hijo != 0xFFFFFFFF:
            _, sig_h, _, _, _ = struct.unpack_from("<5I", dmeta, hijo)
            recorrer_dir(hijo, ruta + "/" + nombre(dmeta, hijo, 0x14))
            hijo = sig_h

    recorrer_dir(0, "")
    with open(salida, "w", encoding="utf-8") as out:
        for ruta, tam, _ in filas:
            out.write(f"{tam:>12,}  {ruta}\n")

    if destino:
        for ruta, tam, off in filas:
            p = os.path.join(destino, *ruta.strip("/").split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            f.seek(off)
            with open(p, "wb") as o:
                o.write(f.read(tam))
    print(f"{len(filas)} archivos, {sum(t for _, t, _ in filas) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
