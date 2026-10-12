r"""Prueba liviana de D2 (raster_d3d12_cb.inc): genera dx_tipos_gen.h con los tipos/estado comun de
raster_backend_d3d12.c (copiados TAL CUAL, asi la prueba no se desincroniza del esqueleto), compila prueba_d2.c con
d3d12_base.c + d3d12_recursos.c y la corre: normal (debe dar 0) y con cada sabotaje (debe dar != 0).
Uso: py -I agentes_dx12\D2\construir.py   (segundos, sin ventana, sin el juego)"""
import os, subprocess, sys
D = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(D))
REN = os.path.join(RAIZ, "recomp", "render")

src = open(os.path.join(REN, "raster_backend_d3d12.c"), encoding="utf-8").read().split("\n")
ini = next(i for i, l in enumerate(src) if l.startswith("typedef struct DxTex"))
fin = next(i for i, l in enumerate(src) if "las partes" in l)
with open(os.path.join(D, "dx_tipos_gen.h"), "w", encoding="utf-8") as f:
    f.write("/* GENERADO por construir.py desde recomp\\render\\raster_backend_d3d12.c (lineas %d-%d). No editar. */\n" % (ini + 1, fin))
    f.write("\n".join(src[ini:fin]) + "\n")

exe = os.path.join(D, "prueba_d2.exe")
cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O1", "-g", "-Wall", "-Wno-unused-function",
       "-I", REN, "-I", D, os.path.join(D, "prueba_d2.c"), os.path.join(REN, "d3d12_base.c"),
       os.path.join(REN, "d3d12_recursos.c"), "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-o", exe]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode:
    print(r.stdout + r.stderr); sys.exit(1)
if r.stderr.strip(): print(r.stderr)

malos = 0
for nombre, env in (("normal", {}), ("sab 1 (cb_va +256)", {"SM3DL_D2_SABOTAJE": "1"}),
                    ("sab 2 (viewport volteado)", {"SM3DL_D2_SABOTAJE": "2"}),
                    ("sab layout (+4 esperado)", {"SM3DL_D2_SAB_LAYOUT": "1"})):
    e = dict(os.environ); e.pop("SM3DL_D2_SABOTAJE", None); e.update(env)
    p = subprocess.run([exe], capture_output=True, text=True, env=e, cwd=D, timeout=60)
    print("=== %s -> codigo %d" % (nombre, p.returncode)); print(p.stderr.strip())
    esperado_ok = nombre == "normal"
    if (p.returncode == 0) != esperado_ok:
        print("!!! %s: resultado INESPERADO" % nombre); malos += 1
print("RESUMEN: %s" % ("todo como se esperaba (normal verde, los 3 sabotajes rojos)" if not malos else "%d INESPERADOS" % malos))
sys.exit(malos != 0)
