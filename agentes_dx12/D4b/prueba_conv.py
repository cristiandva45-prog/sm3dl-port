# convierte UN VS del inventario de E1 con la cadena de B parcheada (salida en D4b\out_prueba) y muestra el HLSL de entrada
import importlib.util, os, sys
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
spec = importlib.util.spec_from_file_location("cad", os.path.join(RAIZ, "agentes_dx12", "B", "cadena_shaders.py"))
cad = importlib.util.module_from_spec(spec); spec.loader.exec_module(cad)
cad.GLSL = sys.argv[2] if len(sys.argv) > 2 else os.path.join(RAIZ, "agentes_dx12", "E1", "trabajo", "glsl")
r = cad.convertir_uno(sys.argv[1], True, os.path.join(os.path.dirname(__file__), "out_prueba"))
print(r)
