r"""Prueba F1 (guardado de la cache de PSO) sobre la parte C1 (raster_d3d12_init.inc) SIN el juego.
Arma agentes_dx12\C1\gen_esqueleto.c = raster_backend_d3d12.c (tipos + estado dx) con las partes reemplazadas por SOLO
raster_d3d12_init.inc + un dx_dibujo_iniciar falso, y enlaza prueba_f1.c con d3d12_{base,recursos,presentador}.c.
Uso (desde cualquier lado): py -I agentes_dx12\C1\compilar_prueba.py  -> agentes_dx12\C1\prueba_f1.exe"""
import os, subprocess, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
REN = os.path.join(RAIZ, "recomp", "render")
src = open(os.path.join(REN, "raster_backend_d3d12.c"), encoding="utf-8").read()
corte = src.index("/* ---------------------------------------------------------------- las partes */")
init = os.path.join(REN, "raster_d3d12_init.inc").replace("\\", "/")
gen = src[:corte] + (
    "/* GENERADO por compilar_prueba.py: solo la parte C1 (prueba F1 del guardado de PSO) */\n"
    "static int dx_prueba_dibujo_ok = 1;\n"
    "static int dx_dibujo_iniciar(void) { return dx_prueba_dibujo_ok; }\n"
    "#define DX_PENDIENTE(nombre) AVISO_UNA_VEZ(AV_GS, \"[d3d12] %s: pendiente (relleno)\", nombre)\n"
    "#include \"" + init + "\"\n")
open(os.path.join(AQUI, "gen_esqueleto.c"), "w", encoding="utf-8").write(gen)
cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O1", "-g", "-Wall", "-Wno-unused-function",
       "-I", REN, os.path.join(AQUI, "prueba_f1.c")] + \
      [os.path.join(REN, n) for n in ("d3d12_base.c", "d3d12_recursos.c", "d3d12_presentador.c")] + \
      ["-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-luser32", "-lgdi32", "-o", os.path.join(AQUI, "prueba_f1.exe")]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout + r.stderr)
sys.exit(r.returncode)
