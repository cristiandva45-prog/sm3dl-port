r"""D4b (9 oct 2026): arma agentes_dx12\D4b\cache_mezcla\ = la cache instalada (extraido\shaders\cache_d3d12\) con los
VS cambiados por los que acaba de dejar `py -I tools\precompilar_d3d12.py regenerar --hilos 2 --solo "^vert/"` en
agentes_dx12\E1\trabajo\out\ (cadena "vulkanizar-2": entradas uint4 + selector b4) y VERSION.txt de la cadena nueva.
Despues: `py -I tools\precompilar_d3d12.py instalar --desde agentes_dx12\D4b\cache_mezcla` (valida TODO, cambia la
carpeta con os.replace y verifica). Solo los VS cambian: los PS/GS/auxiliares no pasan por entradas_enteras().
Uso (desde la raiz): py -I agentes_dx12\D4b\mezclar_cache.py"""
import importlib.util
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
INST = os.path.join(RAIZ, "extraido", "shaders", "cache_d3d12")
TRAB = os.path.join(RAIZ, "agentes_dx12", "E1", "trabajo")
DEST = os.path.join(AQUI, "cache_mezcla")

spec = importlib.util.spec_from_file_location("cad", os.path.join(RAIZ, "agentes_dx12", "B", "cadena_shaders.py"))
cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad)

shutil.rmtree(DEST, ignore_errors=True)
shutil.copytree(INST, DEST)
n = 0
for f in sorted(os.listdir(os.path.join(TRAB, "glsl", "vert"))):
    if not f.endswith(".vert"):
        continue
    h = cad.fnv_texto(open(os.path.join(TRAB, "glsl", "vert", f), "rb").read())
    nuevo = os.path.join(TRAB, "out", "vert__" + f + ".dxil")
    destino = os.path.join(DEST, f"V_{h:08X}.dxil")
    if not os.path.exists(nuevo) or not os.path.exists(destino):
        sys.exit(f"falta {nuevo} o {destino}: correr antes regenerar --solo \"^vert/\"")
    vk = open(os.path.join(TRAB, "out", "vert__" + f + ".vk.glsl"), encoding="utf-8").read()
    if "dx_vconv" not in vk:
        sys.exit(f"{f}: el .vk.glsl no trae la conversion (cadena vieja?)")
    shutil.copyfile(nuevo, destino)
    n += 1
open(os.path.join(DEST, "VERSION.txt"), "w", newline="\n").write(cad.CADENA_VERSION + "\n")
print(f"{n} VS cambiados en {DEST}; VERSION {cad.CADENA_VERSION}")
