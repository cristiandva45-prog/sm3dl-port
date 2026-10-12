r"""(H1) corre escenarios del arnes de E2 (GL vs D3D12) con un exe compilado con los fuentes de H1 (agentes_dx12\H1\e2_con_h1.exe),
en una carpeta de trabajo PROPIA (agentes_dx12\H1\trabajo_e2). Uso: py -I agentes_dx12\H1\tools\e2_con_h1.py [escenarios]"""
import importlib.util, os, shutil, sys
H1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(H1))
spec = importlib.util.spec_from_file_location("e2", os.path.join(RAIZ, "agentes_dx12", "E2", "tools", "e2.py"))
e2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2)
e2.EXE = os.path.join(H1, "e2_con_h1.exe")
e2.TRAB = os.path.join(H1, "trabajo_e2")
dst = os.path.join(e2.TRAB, "extraido", "shaders", "cache_d3d12")
if not os.path.isdir(dst):
    shutil.copytree(os.path.join(RAIZ, "agentes_dx12", "E2", "trabajo", "extraido", "shaders", "cache_d3d12"), dst)
nombres = sys.argv[1:] or ["vertices", "estado_copy", "tev", "mips", "luz", "viewport"]
ok = e2.correr_lote(nombres, "gl", "d3d12", 1)
sys.exit(0 if ok else 1)
