"""Desensamblador rapido de code.bin sin Ghidra (capstone), con literales y nombres resueltos.

Uso: py -I tools\\dis.py <dir> [<dir> ...] [-n 24]
Para hasta el primer retorno (bx lr / pop {...pc}) o -n instrucciones.
Las cargas del literal pool (ldr rX,[pc,#k]) muestran el valor y, si es direccion, su nombre.
"""
import os
import re
import struct
import sys

import capstone

BASE = 0x00100000
AQUI = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(AQUI, "..", "extraido", "code.bin")
SIMB = os.path.join(AQUI, "..", "extraido", "simbolos.txt")


def cargar_nombres():
    nombres = {}
    for linea in open(SIMB, encoding="utf-8"):
        m = re.match(r"\s*(0x[0-9A-Fa-f]+)\s+(\S+)", linea)
        if m:
            nombres[int(m.group(1), 16)] = m.group(2)
    return nombres


def main():
    args = sys.argv[1:]
    n = 24
    if "-n" in args:
        i = args.index("-n")
        n = int(args[i + 1])
        del args[i:i + 2]
    b = open(BIN, "rb").read()
    nombres = cargar_nombres()
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    sys.stdout.reconfigure(encoding="utf-8")

    def u32(a):
        return struct.unpack_from("<I", b, a - BASE)[0]

    for t in args:
        a = int(t, 16)
        print(f"=== 0x{a:08X} {nombres.get(a, '')}")
        for k, ins in enumerate(md.disasm(b[a - BASE:a - BASE + 4 * n], a)):
            nota = ""
            m = re.search(r"\[pc, #(-?0x[0-9a-f]+|-?\d+)\]", ins.op_str)
            if ins.mnemonic.startswith("ldr") and m:
                lit = ins.address + 8 + int(m.group(1), 0)
                v = u32(lit)
                nota = f"   ; =0x{v:08X} {nombres.get(v, '')}"
            elif ins.mnemonic in ("bl", "b", "blx") and ins.op_str.startswith("#"):
                d = int(ins.op_str[1:], 0)
                nota = f"   ; {nombres.get(d, '')}"
            print(f"  {ins.address:08X}  {ins.mnemonic:6} {ins.op_str}{nota}")
            if (ins.mnemonic == "bx" and ins.op_str == "lr") or (ins.mnemonic.startswith("pop") and "pc" in ins.op_str) \
                    or (ins.mnemonic == "b" and k > 0):
                break
        print()


if __name__ == "__main__":
    main()
