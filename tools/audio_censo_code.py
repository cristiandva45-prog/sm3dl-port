"""Censo de la ruta de audio en code.bin: firmware DSP embebido (magic DSP1), cadenas de nn::snd / nw::snd,
y quien llama a los wrappers del DSP. Uso: py -I tools\audio_censo_code.py"""
import os, re, struct, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
B = 0x100000
for m in re.finditer(rb"DSP1", C):
    o = m.start()
    print(f"DSP1 en 0x{B+o:08X}  (posible cabecera de firmware en 0x{B+o-0x100:08X}; tamano declarado {struct.unpack_from('<I', C, o+4)[0]:#x})")
for pat in [rb"[ -~]*(?:snd|Snd|SND|dsp|Dsp|DSP|Sound|sound|Voice|voice|bcsar|bcstm|bcwav|Wave|Stream|Seq|Aac|aac|cdc)[ -~]*"]:
    vistos = set()
    for m in re.finditer(pat, C):
        s = m.group().decode()
        if len(s) >= 5 and s not in vistos:
            vistos.add(s)
            print(f"0x{B+m.start():08X}  {s[:120]}")
