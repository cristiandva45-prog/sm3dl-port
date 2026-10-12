r"""Hoja de contactos de una carpeta de capturas v<vblank>.png (agente P).
Uso: py agentes_noche\P\hoja.py <carpeta> [salida.png] [escala=0.5] [columnas=6] [desde=0] [hasta=inf]
Cada miniatura lleva su vblank arriba a la izquierda. Ademas imprime cuando cambia la imagen (hash)."""
import glob
import hashlib
import os
import re
import sys

from PIL import Image, ImageDraw

d = sys.argv[1]
sal = sys.argv[2] if len(sys.argv) > 2 else os.path.join(d, "hoja.png")
esc = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
cols = int(sys.argv[4]) if len(sys.argv) > 4 else 6
desde = int(sys.argv[5]) if len(sys.argv) > 5 else 0
hasta = int(sys.argv[6]) if len(sys.argv) > 6 else 1 << 30
fs = sorted(f for f in glob.glob(os.path.join(d, "v*.png")) if desde <= int(re.search(r"v(\d+)", os.path.basename(f)).group(1)) <= hasta)
if not fs:
    sys.exit("sin capturas")
w, h = int(400 * esc), int(480 * esc)
filas = (len(fs) + cols - 1) // cols
L = Image.new("RGB", (cols * (w + 4), filas * (h + 4)), (90, 0, 90))
dr = ImageDraw.Draw(L)
prev = None
for k, f in enumerate(fs):
    im = Image.open(f).convert("RGB")
    hs = hashlib.md5(im.tobytes()).hexdigest()[:8]
    vb = re.search(r"v(\d+)", os.path.basename(f)).group(1)
    if hs != prev:
        print(f"v{vb}: imagen nueva {hs}")
    prev = hs
    x, y = (k % cols) * (w + 4), (k // cols) * (h + 4)
    L.paste(im.resize((w, h)), (x, y))
    dr.rectangle([x, y, x + 44, y + 12], fill=(0, 0, 0))
    dr.text((x + 2, y + 1), vb.lstrip("0") or "0", fill=(255, 255, 0))
L.save(sal)
print(f"{len(fs)} capturas -> {sal}")
