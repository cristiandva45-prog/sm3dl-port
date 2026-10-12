r"""(H1) pares .bgra (cinta / lento) -> PNG: lado a lado (cinta | lento | diferencia) + recorte del bbox de la diferencia."""
import glob, os, sys
from PIL import Image, ImageChops
d = sys.argv[1]
for c in sorted(glob.glob(os.path.join(d, "par*_cinta_*.bgra"))):
    l = c.replace("_cinta_", "_lento_")
    w, h = map(int, os.path.basename(c).split("_")[2].split("x"))
    def ab(p):
        return Image.frombytes("RGBA", (w, h), open(p, "rb").read(), "raw", "BGRA").convert("RGB")
    a, b = ab(c), ab(l)
    df = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v else 0)
    bb = df.getbbox()
    base = c.replace("_cinta_", "_").replace(".bgra", "")
    m = 40
    x0, y0, x1, y1 = max(0, bb[0] - m), max(0, bb[1] - m), min(w, bb[2] + m), min(h, bb[3] + m)
    tri = Image.new("RGB", ((x1 - x0) * 3, y1 - y0))
    tri.paste(a.crop((x0, y0, x1, y1)), (0, 0)); tri.paste(b.crop((x0, y0, x1, y1)), (x1 - x0, 0))
    tri.paste(df.crop((x0, y0, x1, y1)).convert("RGB"), (2 * (x1 - x0), 0))
    tri.save(base + "_recorte.png")
    peq = Image.new("RGB", (w // 2 * 3, h // 2)); peq.paste(a.resize((w // 2, h // 2)), (0, 0)); peq.paste(b.resize((w // 2, h // 2)), (w // 2, 0)); peq.paste(df.convert("RGB").resize((w // 2, h // 2)), (w, 0))
    peq.save(base + "_entero.png")
    print(os.path.basename(base), "bbox", bb)
