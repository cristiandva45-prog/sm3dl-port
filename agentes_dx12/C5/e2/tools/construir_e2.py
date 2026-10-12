r"""Compila el arnes de comparacion GL vs D3D12 (sin correr nada): agentes_dx12\E2\prueba_e2.exe.
Un solo exe con los DOS backends (-DSM3DL_CON_D3D12 + d3d12_{base,recursos,presentador}.c, las mismas banderas que
recomp\arranque\compilar.py --d3d12). El backend se elige al correr con SM3DL_BACKEND=gl|d3d12.
Uso (desde cualquier lado): py -I agentes_dx12\E2\tools\construir_e2.py [--solo-sintaxis]"""
import os
import subprocess
import sys

E2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(E2)))  # C5b: copia privada en agentes_dx12/C5/e2
RD = os.path.join(RAIZ, "recomp", "render")
GD = os.path.join(RAIZ, "recomp", "gpu")
base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
        "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function", "-DSM3DL_CON_D3D12"]
inc = ["-I", RD, "-I", GD]
fuentes = [os.path.join(E2, "prueba_e2.c")] + [os.path.join(RD, n) for n in (
    "pica.c", "pica_dibujar.c", "texturas.c", "d3d12_base.c", "d3d12_recursos.c", "d3d12_presentador.c")] + [
    os.path.join(GD, "gsp.c")]
libs = ["-lopengl32", "-lgdi32", "-luser32", "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-ldbghelp"]
if "--solo-sintaxis" in sys.argv:
    cmd = base + inc + ["-fsyntax-only", fuentes[0]]
else:
    cmd = base + inc + fuentes + libs + ["-o", os.path.join(E2, "prueba_e2.exe")]
r = subprocess.run(cmd, capture_output=True, text=True)
salida = (r.stdout + r.stderr).strip()
print("prueba_e2", "sintaxis" if "--solo-sintaxis" in sys.argv else "exe", "rc", r.returncode)
if salida:
    print(salida[:6000])
sys.exit(r.returncode)
