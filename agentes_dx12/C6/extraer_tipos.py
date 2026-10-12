# Saca los tipos compartidos (DxTex..DX_LEC) de raster_backend_d3d12.c a tipos_dx.h, para que la prueba use EXACTAMENTE
# las mismas estructuras que el backend (si la sesion principal las cambia, la prueba las sigue sola).
import os, sys
raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(raiz, "recomp", "render", "raster_backend_d3d12.c"), encoding="utf-8", errors="replace").read()
i = src.index("typedef struct DxTex {")
j = src.index("#define DX_LEC(p)")
j = src.index("\n", j) + 1
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tipos_dx.h")
open(out, "w", encoding="utf-8").write("/* GENERADO por extraer_tipos.py desde raster_backend_d3d12.c: no editar */\n" + src[i:j])
print("tipos_dx.h:", j - i, "bytes")
