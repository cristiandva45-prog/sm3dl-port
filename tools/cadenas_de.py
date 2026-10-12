"""Cadenas que usa una funcion y los metodos de su vtable (literal pool -> .rodata).

Uso: py -I tools\\cadenas_de.py <dir> [<dir> ...] [--vt]
  --vt : ademas sigue la primera vtable que el ctor escribe y junta las cadenas de sus metodos.
Sirve para nombrar estados: sus anims ("Jump", "SquatWait"...) salen aqui.
"""
import os
import re
import struct
import sys

import capstone

BASE = 0x00100000
AQUI = os.path.dirname(os.path.abspath(__file__))
B = open(os.path.join(AQUI, "..", "extraido", "code.bin"), "rb").read()
RO = (0x003A2000, 0x003E1000 + 76244)
TXT = (0x00100000, 0x00100000 + 2758524)
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)


def u32(a):
    return struct.unpack_from("<I", B, a - BASE)[0]


def cadena(a):
    if not (RO[0] <= a < RO[1]):
        return None
    fin = B.index(b"\0", a - BASE)
    s = B[a - BASE:fin]
    if len(s) < 4:
        return None
    try:
        t = s.decode("ascii")
        if all(32 <= ord(c) < 127 for c in t):
            return t
    except UnicodeDecodeError:
        pass
    try:
        t = s.decode("shift_jis")
        if len(t) >= 3 and all(ord(c) > 0x3000 or c.isalnum() for c in t) and any(ord(c) > 0x3000 for c in t):
            return t
    except UnicodeDecodeError:
        pass
    return None


def literales(a, n=200):
    lits = []
    for ins in md.disasm(B[a - BASE:a - BASE + 4 * n], a):
        m = re.search(r"\[pc, #(-?0x[0-9a-f]+|-?\d+)\]", ins.op_str)
        if ins.mnemonic.startswith("ldr") and m:
            lits.append(u32(ins.address + 8 + int(m.group(1), 0)))
        if (ins.mnemonic.startswith("pop") and "pc" in ins.op_str) or (ins.mnemonic == "bx" and ins.op_str == "lr"):
            break
    return lits


def main():
    args = sys.argv[1:]
    vt = "--vt" in args
    args = [x for x in args if x != "--vt"]
    sys.stdout.reconfigure(encoding="utf-8")
    for t in args:
        a = int(t, 16)
        lits = literales(a)
        cads = [c for c in (cadena(v) for v in lits) if c]
        if vt:
            for v in lits:
                if RO[0] <= v < RO[1] and any(TXT[0] <= u32(v + 4 * i) < TXT[1] for i in range(4)):
                    for i in range(0, 30):
                        p = u32(v + 4 * i)
                        if TXT[0] <= p < TXT[1]:
                            cads += [c for c in (cadena(x) for x in literales(p, 120)) if c]
                    break
        vistos = []
        for c in cads:
            if c not in vistos:
                vistos.append(c)
        print(f"0x{a:08X}: " + " | ".join(vistos[:14]))


if __name__ == "__main__":
    main()
