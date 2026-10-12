"""Desensambla un rango de code.bin con los nombres de simbolos.txt. Uso: py -I tools\audio_dis.py 0xINI 0xFIN"""
import os, sys, struct
import capstone
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
B = 0x100000
nom = {}
for l in open(os.path.join(RAIZ, "extraido", "simbolos.txt"), encoding="utf-8"):
    p = l.split()
    if len(p) >= 2 and p[0].startswith("0x"):
        nom[int(p[0], 16)] = p[1]
a, b = int(sys.argv[1], 16), int(sys.argv[2], 16)
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
for i in md.disasm(C[a - B:b - B], a):
    extra = ""
    if i.mnemonic.startswith("bl") and i.op_str.startswith("#"):
        d = int(i.op_str[1:], 16)
        extra = nom.get(d, "")
    if "[pc, #" in i.op_str and i.mnemonic.startswith("ldr"):
        k = int(i.op_str.split("#")[1].rstrip("]"), 16)
        v = struct.unpack_from("<I", C, i.address + 8 + k - B)[0]
        extra = f"=0x{v:08X} {nom.get(v, '')}"
    if i.address in nom:
        print(f"{nom[i.address]}:")
    print(f"{i.address:08X} {i.mnemonic:8} {i.op_str:30} {extra}")
