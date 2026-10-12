"""Compila decomp/src/*.c para el ARM11 del 3DS y lo enlaza en 0x01000000 junto a code.bin.

Uso: py -I decomp\\build.py   -> decomp\\build\\decomp.elf + decomp.bin + simbolos.json

- Zig (pip install ziglang) como compilador cruzado: arm1176jzf-s, VFPv2, float ABI hard (como el juego).
- Las llamadas a funciones originales se resuelven a su direccion real: los nombres salen de
  extraido/simbolos.txt y los FUN_xxxxxxxx se toman literal. Lo que definimos nosotros gana.
- -ffp-contract=off: el ARM11 no tiene FMA; el compilador no debe fusionar a*b+c.
"""
import json
import os
import re
import subprocess
import sys

from elftools.elf.elffile import ELFFile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SRC = os.path.join(AQUI, "src")
OUT = os.path.join(AQUI, "build")
BASE = 0x01000000
FLAGS = ["-target", "arm-freestanding-eabihf", "-mcpu=arm1176jzf_s", "-marm", "-mfloat-abi=hard",
         "-O2", "-ffreestanding", "-fno-builtin", "-fno-math-errno", "-ffp-contract=off",
         "-fno-strict-aliasing", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fno-exceptions", "-Wall", "-Wno-unused-function", "-I", os.path.join(AQUI, "include")]


def zig(*args):
    r = subprocess.run([sys.executable, "-m", "ziglang", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("fallo: zig " + " ".join(args[:3]))
    if r.stderr.strip():
        print(r.stderr.strip())


def simbolos_juego():
    d = {}
    for linea in open(os.path.join(RAIZ, "extraido", "simbolos.txt"), encoding="utf-8"):
        m = re.match(r"\s*(0x[0-9A-Fa-f]+)\s+(\S+)", linea)
        if m:
            d[m.group(2)] = int(m.group(1), 16)
    return d


def simbolos_de(path, definidos):
    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        st = elf.get_section_by_name(".symtab")
        for s in st.iter_symbols():
            if s.name and s["st_info"]["type"] in ("STT_FUNC", "STT_NOTYPE", "STT_OBJECT"):
                yield s.name, s["st_shndx"] != "SHN_UNDEF"


def main():
    os.makedirs(OUT, exist_ok=True)
    objs = []
    for f in sorted(os.listdir(SRC)):
        if f.endswith(".c"):
            o = os.path.join(OUT, f[:-2] + ".o")
            zig("cc", *FLAGS, "-c", os.path.join(SRC, f), "-o", o)
            objs.append(o)
    definidos, indefinidos = set(), set()
    for o in objs:
        for nombre, def_ in simbolos_de(o, definidos):
            (definidos if def_ else indefinidos).add(nombre)
    juego = simbolos_juego()
    faltan, asignar = [], []
    for n in sorted(indefinidos - definidos):
        m = re.fullmatch(r"FUN_([0-9a-fA-F]{8})", n)
        if m:
            asignar.append((n, int(m.group(1), 16)))
        elif n in juego:
            asignar.append((n, juego[n]))
        else:
            faltan.append(n)
    if faltan:
        raise SystemExit("simbolos sin direccion (no estan en simbolos.txt): " + ", ".join(faltan))
    ld = os.path.join(OUT, "enlace.ld")
    with open(ld, "w", encoding="utf-8") as fh:
        fh.write("ENTRY(0)\nSECTIONS {\n  . = 0x%08X;\n" % BASE)
        fh.write("  .text : { *(.text*) }\n  .rodata : { *(.rodata*) }\n  .data : { *(.data*) }\n")
        fh.write("  .bss : { *(.bss*) *(COMMON) }\n  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }\n}\n")
        for n, a in asignar:
            fh.write(f"{n} = 0x{a:08X};\n")
    elf = os.path.join(OUT, "decomp.elf")
    zig("cc", *FLAGS, "-nostdlib", "-Wl,-T," + ld, "-Wl,--no-gc-sections", "-o", elf, *objs)
    # imagen plana desde BASE + tabla de simbolos propios
    with open(elf, "rb") as fh:
        e = ELFFile(fh)
        fin = BASE
        partes = []
        for seg in e.iter_segments():
            if seg["p_type"] == "PT_LOAD" and seg["p_memsz"]:
                partes.append((seg["p_vaddr"], seg.data(), seg["p_memsz"]))
                fin = max(fin, seg["p_vaddr"] + seg["p_memsz"])
        img = bytearray(fin - BASE)
        for va, datos, _ in partes:
            img[va - BASE:va - BASE + len(datos)] = datos
        propios = {s.name: s["st_value"] & ~1 for s in e.get_section_by_name(".symtab").iter_symbols()
                   if s.name in definidos and s["st_info"]["type"] == "STT_FUNC"}
    open(os.path.join(OUT, "decomp.bin"), "wb").write(img)
    json.dump({"base": BASE, "funciones": propios, "externos": dict(asignar)},
              open(os.path.join(OUT, "simbolos.json"), "w"), indent=1)
    print(f"ok: {len(propios)} funciones propias, {len(asignar)} externas enlazadas, {len(img)} bytes")


if __name__ == "__main__":
    main()
