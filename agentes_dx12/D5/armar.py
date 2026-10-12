# Arma y compila la prueba de D5: copia la parte COMUN de raster_backend_d3d12.c (tipos + estado dx, sin las partes
# ni la tabla) a gen\dx_comun.c, y compila prueba_d5.c (que incluye esa copia + el raster_d3d12_dibujar.inc REAL).
import os, subprocess, sys
D = os.path.dirname(os.path.abspath(__file__))
R = os.path.abspath(os.path.join(D, "..", "..", "recomp", "render"))
t = open(os.path.join(R, "raster_backend_d3d12.c"), encoding="utf-8").read()
corte = t.index("/* ---------------------------------------------------------------- las partes */")
open(os.path.join(D, "gen", "dx_comun.c"), "w", encoding="utf-8").write(t[:corte])
# el contrato de la firma raiz de D1 (DX_RS_*), copiado de su parte para no desfasarse
rs = [l for l in open(os.path.join(R, "raster_d3d12_prog.inc"), encoding="utf-8") if l.startswith("#define DX_RS_")]
open(os.path.join(D, "gen", "dx_rs.h"), "w", encoding="utf-8").write("".join(rs))
cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O1", "-g", "-Wall", "-Wno-unused-function",
       "-I", R, "-I", os.path.join(D, "gen"), os.path.join(D, "prueba_d5.c"),
       os.path.join(R, "d3d12_base.c"), os.path.join(R, "d3d12_recursos.c"),
       "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-o", os.path.join(D, "prueba_d5.exe")]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout + r.stderr)
sys.exit(r.returncode)
