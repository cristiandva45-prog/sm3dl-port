"""Mosaico lado a lado de dos carpetas de capturas (PNG 400x480): py mosaico.py dirA dirB salida.png [max]"""
import os, sys
from PIL import Image
a, b, sal = sys.argv[1:4]
mx = int(sys.argv[4]) if len(sys.argv) > 4 else 12
la = sorted(os.listdir(a))[:mx]
lb = sorted(os.listdir(b))[:mx]
n = max(len(la), len(lb))
esc = 0.5
W, H = int(400 * esc), int(480 * esc)
m = Image.new("RGB", (W * 2 + 10, H * n), (255, 0, 255))
for i in range(n):
    for j, (d, l) in enumerate(((a, la), (b, lb))):
        if i < len(l):
            im = Image.open(os.path.join(d, l[i])).convert("RGB").resize((W, H))
            m.paste(im, (j * (W + 10), i * H))
m.save(sal)
print("ok", n)
