"""Extrae el ejecutable de un .3ds descifrado y lo deja listo para Ghidra.

Lee la particion 0 (NCCH), saca el exheader y el ExeFS, descomprime .code
(BLZ) si hace falta y escribe:
  - code.bin      : el ejecutable plano (text + ro + data, como en memoria)
  - exheader.bin  : el exheader crudo
  - code.elf      : ELF ARM con segmentos, secciones y los nombres de simbolos.txt
                    (si existe en la carpeta de salida), para importar en Ghidra
  - info.txt      : direcciones y tamanos de cada segmento

Uso: py -I extraer_code.py <rom.3ds> <carpeta_salida>
"""
import os
import struct
import sys

MEDIA = 0x200


def blz_descomprimir(comp):
    """Descompresion BLZ (LZ inverso) del .code de 3DS, como en ctrtool."""
    pie, extra = struct.unpack_from("<II", comp, len(comp) - 8)
    tam_dec = len(comp) + extra
    dec = bytearray(tam_dec)
    dec[: len(comp)] = comp
    idx = len(comp) - ((pie >> 24) & 0xFF)
    fin = len(comp) - (pie & 0xFFFFFF)
    out = tam_dec
    while idx > fin:
        idx -= 1
        control = comp[idx]
        for _ in range(8):
            if idx <= fin or idx <= 0 or out <= 0:
                break
            if control & 0x80:
                idx -= 2
                seg = comp[idx] | (comp[idx + 1] << 8)
                largo = ((seg >> 12) & 0xF) + 3
                desp = (seg & 0x0FFF) + 2
                for _ in range(largo):
                    if out + desp >= tam_dec:
                        raise ValueError("BLZ corrupto: desplazamiento fuera de rango")
                    dato = dec[out + desp]
                    out -= 1
                    dec[out] = dato
            else:
                out -= 1
                idx -= 1
                dec[out] = comp[idx]
            control = (control << 1) & 0xFF
    return bytes(dec)


def tabla_simbolos(simbolos):
    """simbolos: lista de (direccion, nombre). Devuelve (symtab, strtab) para .text (seccion 1)."""
    strtab = bytearray(b"\0")
    symtab = bytearray(b"\0" * 16)
    for direccion, nombre in sorted(simbolos):
        nombre_off = len(strtab)
        strtab += nombre.encode() + b"\0"
        # st_info = GLOBAL(1)<<4 | FUNC(2); st_shndx = 1 (.text)
        symtab += struct.pack("<IIIBBH", nombre_off, direccion, 0, 0x12, 0, 1)
    return bytes(symtab), bytes(strtab)


def escribir_elf(ruta, segmentos, entrada, simbolos=()):
    """segmentos: lista de (nombre, vaddr, datos, tam_memoria, flags_p, flags_sh)."""
    symtab, strtab = tabla_simbolos(simbolos)
    shstr = b"\0" + b"".join(s[0].encode() + b"\0" for s in segmentos) + b".shstrtab\0.symtab\0.strtab\0"
    n_ph = len(segmentos)
    n_sh = len(segmentos) + 4  # nulo + segmentos + shstrtab + symtab + strtab
    off = 0x34 + 0x20 * n_ph
    off = (off + 0xFFF) & ~0xFFF
    cuerpo = bytearray()
    phs, shs = [], [b"\0" * 0x28]
    nombre_off = 1
    for nombre, vaddr, datos, tam_mem, pflags, shflags in segmentos:
        foff = off + len(cuerpo)
        phs.append(struct.pack("<8I", 1, foff, vaddr, vaddr, len(datos), tam_mem, pflags, 0x1000))
        tipo = 8 if not datos else 1  # SHT_NOBITS para .bss
        shs.append(struct.pack("<10I", nombre_off, tipo, shflags, vaddr, foff, tam_mem if not datos else len(datos), 0, 0, 4, 0))
        nombre_off += len(nombre) + 1
        cuerpo += datos
        cuerpo += b"\0" * ((-len(cuerpo)) % 0x1000)
    shstr_off = off + len(cuerpo)
    cuerpo += shstr
    cuerpo += b"\0" * ((-len(cuerpo)) % 4)
    shstr_idx = len(shs)
    shs.append(struct.pack("<10I", nombre_off, 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0))
    nombre_off += len(".shstrtab") + 1
    symtab_off = off + len(cuerpo)
    cuerpo += symtab
    strtab_idx = len(shs) + 1
    # sh_link = indice de .strtab, sh_info = primer simbolo no local, entsize 16
    shs.append(struct.pack("<10I", nombre_off, 2, 0, 0, symtab_off, len(symtab), strtab_idx, 1, 4, 16))
    nombre_off += len(".symtab") + 1
    strtab_off = off + len(cuerpo)
    cuerpo += strtab
    cuerpo += b"\0" * ((-len(cuerpo)) % 4)
    shs.append(struct.pack("<10I", nombre_off, 3, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0))
    sh_off = off + len(cuerpo)
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\0" * 8
    cab = ident + struct.pack("<HHIIIIIHHHHHH", 2, 40, 1, entrada, 0x34, sh_off, 0x05000000, 0x34, 0x20, n_ph, 0x28, n_sh, shstr_idx)
    with open(ruta + ".tmp", "wb") as f:
        f.write(cab)
        f.write(b"".join(phs))
        f.write(b"\0" * (off - 0x34 - 0x20 * n_ph))
        f.write(cuerpo)
        f.write(b"".join(shs))
    os.replace(ruta + ".tmp", ruta)


def main():
    rom, salida = sys.argv[1], sys.argv[2]
    os.makedirs(salida, exist_ok=True)
    with open(rom, "rb") as f:
        ncsd = f.read(0x200)
        assert ncsd[0x100:0x104] == b"NCSD", "no es un .3ds (NCSD)"
        p0_off = struct.unpack_from("<I", ncsd, 0x120)[0] * MEDIA
        f.seek(p0_off)
        ncch = f.read(0x200)
        assert ncch[0x100:0x104] == b"NCCH", "particion 0 no es NCCH"
        assert ncch[0x18F] & 0x4, "la ROM esta cifrada: hay que descifrarla primero"
        exh = f.read(0x800)
        exefs_off, exefs_tam = struct.unpack_from("<II", ncch, 0x1A0)
        f.seek(p0_off + exefs_off * MEDIA)
        exefs = f.read(exefs_tam * MEDIA)

    with open(os.path.join(salida, "exheader.bin"), "wb") as f:
        f.write(exh)

    nombre = exh[0:8].rstrip(b"\0").decode()
    comprimido = bool(exh[0xD] & 1)
    text_addr, text_pag, text_tam = struct.unpack_from("<III", exh, 0x10)
    ro_addr, ro_pag, ro_tam = struct.unpack_from("<III", exh, 0x20)
    data_addr, data_pag, data_tam = struct.unpack_from("<III", exh, 0x30)
    bss_tam = struct.unpack_from("<I", exh, 0x3C)[0]

    code = None
    for i in range(10):
        n, o, t = struct.unpack_from("<8sII", exefs, i * 0x10)
        if n.rstrip(b"\0") == b".code":
            code = exefs[0x200 + o : 0x200 + o + t]
    assert code is not None, "no hay .code en el ExeFS"
    if comprimido:
        code = blz_descomprimir(code)

    with open(os.path.join(salida, "code.bin"), "wb") as f:
        f.write(code)

    t0 = 0
    r0 = text_pag * 0x1000
    d0 = r0 + ro_pag * 0x1000
    text = code[t0 : t0 + text_tam]
    ro = code[r0 : r0 + ro_tam]
    data = code[d0 : d0 + data_tam]
    bss_addr = data_addr + data_tam
    segmentos = [
        (".text", text_addr, text, text_tam, 5, 0x6),     # R+X / ALLOC+EXEC
        (".rodata", ro_addr, ro, ro_tam, 4, 0x2),         # R / ALLOC
        (".data", data_addr, data, data_tam, 6, 0x3),     # RW / ALLOC+WRITE
        (".bss", bss_addr, b"", bss_tam, 6, 0x3),
    ]
    simbolos = []
    ruta_sim = os.path.join(salida, "simbolos.txt")
    if os.path.exists(ruta_sim):
        for linea in open(ruta_sim, encoding="utf-8"):
            partes = linea.split("#")[0].split()  # todo lo que va tras '#' es comentario
            if len(partes) == 2:
                simbolos.append((int(partes[0], 16), partes[1]))
    escribir_elf(os.path.join(salida, "code.elf"), segmentos, text_addr, simbolos)

    info = [
        f"proceso:     {nombre}",
        f"comprimido:  {comprimido}",
        f"code.bin:    {len(code):,} bytes",
        f".text   0x{text_addr:08X}  {text_tam:>10,} bytes",
        f".rodata 0x{ro_addr:08X}  {ro_tam:>10,} bytes",
        f".data   0x{data_addr:08X}  {data_tam:>10,} bytes",
        f".bss    0x{bss_addr:08X}  {bss_tam:>10,} bytes",
        f"entrada 0x{text_addr:08X}",
        f"simbolos aplicados: {len(simbolos)}",
    ]
    with open(os.path.join(salida, "info.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(info) + "\n")
    print("\n".join(info))


if __name__ == "__main__":
    main()
