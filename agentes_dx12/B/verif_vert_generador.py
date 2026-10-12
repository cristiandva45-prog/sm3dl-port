"""Los .vert que lee raster_gl.c (extraido\\shaders\\glsl\\, 21 programas de programas.tsv) deben ser exactamente lo que
produce HOY tools\\shader_glsl.py desde los .shbin del RomFS. Regenera en memoria (no escribe nada en el proyecto) y
compara byte a byte. Uso: py -I agentes_dx12\\B\\verif_vert_generador.py"""
import os
import sys

B = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(B))
sys.path.append(os.path.join(RAIZ, "tools"))  # al final: tools\dis.py tapa el modulo estandar 'dis'
import shader_glsl  # noqa: E402
import shbin  # noqa: E402

d = os.path.join(RAIZ, "extraido", "shaders")
filas = [l.split("\t")[0] for l in open(os.path.join(d, "glsl", "programas.tsv"), encoding="utf-8") if not l.startswith("#")]
iguales = distintos = faltan = 0
for v in filas:
    base, e = v[:-5].rsplit("_e", 1)
    ruta = os.path.join(d, base + ".shbin")
    if not os.path.exists(ruta):
        faltan += 1
        print("sin .shbin:", v)
        continue
    sh = shbin.Shbin(open(ruta, "rb").read())
    nuevo = shader_glsl.Programa(sh, int(e)).glsl(base + ".shbin")
    viejo = open(os.path.join(d, "glsl", v), encoding="utf-8").read()
    if nuevo == viejo:
        iguales += 1
    else:
        distintos += 1
        print("DISTINTO:", v)
print(f"{len(filas)} programas: {iguales} identicos al generador actual, {distintos} distintos, {faltan} sin .shbin")
sys.exit(1 if distintos or faltan else 0)
