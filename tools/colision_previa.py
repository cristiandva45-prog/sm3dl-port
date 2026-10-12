"""Previas PNG de colision (rasterizado ortografico con z-buffer, solo Pillow).

render(tris, ruta_png, colores=None)
  tris: [(v1, v2, v3)]  con v = (x, y, z)  (Y arriba, como en el juego)
  colores: lista paralela de (r,g,b) 0..1 o None -> color por normal.
Se dibujan solo las caras cuya normal mira al observador (+Y, +Z, +X).
Genera una imagen con 3 paneles: ARRIBA (X-Z, mirando hacia -Y), LATERAL (X-Y), FRENTE (Z-Y).
"""
import math
import os

from PIL import Image, ImageDraw

VISTAS = (
    # nombre, eje horizontal, eje vertical (signo), eje de profundidad (mayor = mas cerca)
    ("arriba (X a la der., Z hacia abajo)", 0, 2, +1, 1),
    ("lateral (X a la der., Y arriba)", 0, 1, -1, 2),
    ("frente (Z a la der., Y arriba)", 2, 1, -1, 0),
)
LUZ = (0.35, 0.8, 0.45)


def _n(v1, v2, v3):
    a = (v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2])
    b = (v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2])
    n = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    l = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1
    return (n[0] / l, n[1] / l, n[2] / l)


def _panel(tris, cols, h_ax, v_ax, v_sig, d_ax, W, H, bbox):
    img = Image.new("RGB", (W, H), (24, 26, 32))
    px = img.load()
    zb = [-1e30] * (W * H)
    lo, hi = bbox
    ex = max(hi[h_ax] - lo[h_ax], 1e-6)
    ey = max(hi[v_ax] - lo[v_ax], 1e-6)
    s = min((W - 20) / ex, (H - 20) / ey)
    ox = (W - ex * s) / 2
    oy = (H - ey * s) / 2

    def P(v):
        x = ox + (v[h_ax] - lo[h_ax]) * s
        y = oy + ((hi[v_ax] - v[v_ax]) if v_sig < 0 else (v[v_ax] - lo[v_ax])) * s
        return x, y, v[d_ax]

    for (v1, v2, v3), col in zip(tris, cols):
        n = _n(v1, v2, v3)
        if n[d_ax] <= 0.02:
            # cara trasera: la colision es de una cara; se ve el lado "solido" (asi se ve el interior de salas)
            continue
        if col is None:
            base = (abs(n[0]) * 0.6 + 0.3, abs(n[1]) * 0.6 + 0.3, abs(n[2]) * 0.6 + 0.3)
        else:
            base = col
        lam = 0.45 + 0.55 * abs(n[0] * LUZ[0] + n[1] * LUZ[1] + n[2] * LUZ[2])
        rgb = tuple(min(255, int(c * lam * 255)) for c in base)
        a, b, c = P(v1), P(v2), P(v3)
        x0 = max(0, int(min(a[0], b[0], c[0])))
        x1 = min(W - 1, int(max(a[0], b[0], c[0])) + 1)
        y0 = max(0, int(min(a[1], b[1], c[1])))
        y1 = min(H - 1, int(max(a[1], b[1], c[1])) + 1)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-9:
            continue
        for y in range(y0, y1 + 1):
            fy = y + 0.5
            for x in range(x0, x1 + 1):
                fx = x + 0.5
                w1 = ((b[1] - c[1]) * (fx - c[0]) + (c[0] - b[0]) * (fy - c[1])) / den
                w2 = ((c[1] - a[1]) * (fx - c[0]) + (a[0] - c[0]) * (fy - c[1])) / den
                w3 = 1 - w1 - w2
                if w1 < -1e-6 or w2 < -1e-6 or w3 < -1e-6:
                    continue
                z = w1 * a[2] + w2 * b[2] + w3 * c[2]
                i = y * W + x
                if z > zb[i]:
                    zb[i] = z
                    px[x, y] = rgb
        # asegurar que triangulos diminutos se vean
        if x1 - x0 <= 1 and y1 - y0 <= 1:
            for p, q in ((a, b), (b, c), (c, a)):
                _linea(px, zb, W, H, p, q, rgb)
    return img, s


def _linea(px, zb, W, H, p, q, rgb):
    n = int(max(abs(q[0] - p[0]), abs(q[1] - p[1]))) + 1
    for k in range(n + 1):
        t = k / n
        x = int(p[0] + (q[0] - p[0]) * t)
        y = int(p[1] + (q[1] - p[1]) * t)
        z = p[2] + (q[2] - p[2]) * t
        if 0 <= x < W and 0 <= y < H and z >= zb[y * W + x]:
            zb[y * W + x] = z
            px[x, y] = rgb


def render(tris, ruta_png, colores=None, titulo="", W=900, H=600, vistas=(0, 1, 2), anotaciones=None):
    if colores is None:
        colores = [None] * len(tris)
    xs = [v for t in tris for v in t]
    lo = tuple(min(v[i] for v in xs) for i in range(3))
    hi = tuple(max(v[i] for v in xs) for i in range(3))
    paneles = []
    for k in vistas:
        nom, h, v, sg, d = VISTAS[k]
        img, s = _panel(tris, colores, h, v, sg, d, W, H, (lo, hi))
        dr = ImageDraw.Draw(img)
        dr.text((8, 6), f"{titulo}  {nom}", fill=(255, 255, 255))
        dr.text((8, H - 16), f"bbox min {tuple(round(c) for c in lo)} max {tuple(round(c) for c in hi)}  escala {s:.4f} px/u",
                fill=(200, 200, 200))
        if anotaciones:
            ex_h, ex_v = hi[h] - lo[h], hi[v] - lo[v]
            sc = min((W - 20) / max(ex_h, 1e-6), (H - 20) / max(ex_v, 1e-6))
            ox, oy = (W - ex_h * sc) / 2, (H - ex_v * sc) / 2
            for p, txt in anotaciones:
                x = ox + (p[h] - lo[h]) * sc
                y = oy + ((hi[v] - p[v]) if sg < 0 else (p[v] - lo[v])) * sc
                dr.text((x + 2, y - 10), txt, fill=(255, 230, 80))
        paneles.append(img)
    out = Image.new("RGB", (W, H * len(paneles)), (0, 0, 0))
    for i, p in enumerate(paneles):
        out.paste(p, (0, i * H))
    tmp = ruta_png + ".tmp.png"
    out.save(tmp)
    os.replace(tmp, ruta_png)
