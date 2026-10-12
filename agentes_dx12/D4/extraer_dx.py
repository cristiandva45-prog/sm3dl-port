# Extrae de recomp\render\raster_backend_d3d12.c los tipos compartidos + el estado comun `dx` (de "typedef struct DxTex"
# a "} dx;") a dx_comun_extraido.h, para que la prueba de D4 use la estructura REAL (no una copia que se desfase).
import os, sys
aqui = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(aqui, "..", "..", "recomp", "render", "raster_backend_d3d12.c")
t = open(src, encoding="utf-8", errors="replace").read()
i = t.index("typedef struct DxTex")
j = t.index("} dx;") + len("} dx;")
open(os.path.join(aqui, "dx_comun_extraido.h"), "w", encoding="utf-8").write(
    "/* GENERADO por extraer_dx.py desde raster_backend_d3d12.c: no editar */\n" + t[i:j] + "\n")
print("extraido", j - i, "bytes")
