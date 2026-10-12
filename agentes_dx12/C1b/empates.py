r"""C1b: pres_capa PUNTO escalada con EMPATES en x y en y, GL vs D3D12, con el arnes de E2 (prueba_e2.exe) sin el juego.
Uso: py -I agentes_dx12\C1b\empates.py [--sab]   (--sab = SM3DL_C1_SABOTAJE=1 en D3D12: debe dar MAL)
Pasos (capa 0 = 40x30): 30x30 (empates en x), 30x45 (empates en y), 3,2-33,47 (corrida), 50x50, 20x15."""
import importlib.util, os, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
spec = importlib.util.spec_from_file_location("e2", os.path.join(RAIZ, "agentes_dx12", "E2", "tools", "e2.py"))
e2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(e2)
eq, pr = e2.eq, e2.pr
e2.EXE = os.path.join(AQUI, "prueba_e2_c1b.exe"); e2.TRAB = os.path.join(AQUI, "trabajo")   # exe y carpeta propios
import random
rng = random.Random(55)
W, H = 240, 400
g = eq.nuevo_guion(W, H)
g.w.extend((11, 2))
g.limpiar(rng.randrange(1 << 32))
eq.tris_azar(g, rng, 16, W, H)
g.w.extend((12, pr.DIR_COLOR, eq.DIR_SAL, W * H * 4, W * H * 4, W, H, W, H, 0))
g.w.extend((13, eq.DIR_SAL, 0, W * 4, 400, 240))
g.w.extend((19, eq.DIR_SAL, 0, W * 4, 400, 240))
g.w.extend((16, 0, 40, 30, 7, 0, 0, 40, 30))
PASOS = [(0, 0, 30, 30), (0, 0, 30, 45), (3, 2, 33, 47), (1, 1, 51, 51), (5, 9, 25, 24)]
for (x0, y0, x1, y1) in PASOS:
    g.w.extend((14, 64, 64)); g.w.extend((17, 0, x0, y0, x1, y1, 0)); g.w.extend((18, 64, 64))
env_b = {"SM3DL_C1_SABOTAJE": "1"} if "--sab" in sys.argv else None
os.makedirs(e2.TRAB, exist_ok=True)
_, da, ma, _ = e2.correr("gl", g.w, "c1b_empates", None, "gl_A")
_, db, mb, eb = e2.correr("d3d12", g.w, "c1b_empates", env_b, "d3d12_B")
seg = [(off, n) for (op, cod, off, n, t, f) in ma if cod == 18 and t == "P"]
tot = 0
for (x0, y0, x1, y1), (off, n) in zip(PASOS, seg):
    a, b = da[off:off + n], db[off:off + n]
    px = [(k // 4 % 64, 63 - k // 4 // 64) for k in range(0, n, 4) if len(b) == n and max(abs(a[k + j] - b[k + j]) for j in range(4)) > 1]
    if len(b) != n: px = ["truncado"]
    tot += len(px)
    print("capa0 punto %2d,%2d-%2d,%2d: %4d px fuera de +-1  xs=%s ys(desde arriba)=%s" % (
        x0, y0, x1, y1, len(px), sorted({p[0] for p in px})[:40], sorted({p[1] for p in px})[:50]))
if len(seg) != len(PASOS): print("segmentos", len(seg), "!=", len(PASOS)); tot = -1
print("RESULTADO:", "IGUAL" if tot == 0 else "DISTINTO (%d px)" % tot)
sys.exit(0 if tot == 0 else 1)
