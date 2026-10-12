r"""(P2) arnes de E2 (GL vs D3D12) con un exe compilado con el arbol ACTUAL (con los sellos de P2): agentes_dx12\P2\e2_con_p2.exe,
carpeta de trabajo PROPIA agentes_dx12\P2\trabajo_e2 (el exe de E2 es del 9 oct y no ve los cambios).
Uso: py -I agentes_dx12\P2\e2_p2.py [escenarios]   (sin escenarios: todos los de e2.py)"""
import importlib.util, os, shutil, subprocess, sys
P2 = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(P2))
E2 = os.path.join(RAIZ, "agentes_dx12", "E2")
RD = os.path.join(RAIZ, "recomp", "render")
GD = os.path.join(RAIZ, "recomp", "gpu")
EXE = os.path.join(P2, "e2_con_p2.exe")
base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
        "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function", "-DSM3DL_CON_D3D12"]
fuentes = [os.path.join(E2, "prueba_e2.c")] + [os.path.join(RD, n) for n in (
    "pica.c", "pica_dibujar.c", "texturas.c", "texturas_hd.c", "d3d12_base.c", "d3d12_recursos.c", "d3d12_presentador.c")] + [os.path.join(GD, "gsp.c")]
libs = ["-lopengl32", "-lgdi32", "-luser32", "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-ldbghelp"]
r = subprocess.run(base + ["-I", RD, "-I", GD] + fuentes + libs + ["-o", EXE], capture_output=True, text=True)
print("e2_con_p2.exe rc", r.returncode, (r.stdout + r.stderr).strip()[:3000])
if r.returncode:
    sys.exit(2)
spec = importlib.util.spec_from_file_location("e2", os.path.join(E2, "tools", "e2.py"))
e2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2)
e2.EXE = EXE
e2.TRAB = os.path.join(P2, "trabajo_e2")
dst = os.path.join(e2.TRAB, "extraido", "shaders", "cache_d3d12")
if not os.path.isdir(dst):
    shutil.copytree(os.path.join(E2, "trabajo", "extraido", "shaders", "cache_d3d12"), dst)
nombres = sys.argv[1:] or list(e2.ESCENARIOS)
sys.exit(0 if e2.correr_lote(nombres, "gl", "d3d12", 1) else 1)
