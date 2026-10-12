r"""(P3, 10 oct) arnes de E2 con exes PROPIOS (sin tocar archivos de E2): carpeta de trabajo agentes_dx12\P3\trabajo_e2.
  construir      : P3\e2_p3.exe (fuentes de hoy) y P3\e2_ref.exe (raster_gl.c.antes_P3 = antes de P3, via P3\ref\raster_gl.c)
  e2             : todos los escenarios de E2, GL vs D3D12 con e2_p3.exe (esperado: 24/29 como hoy)
  enteros        : los 3 escenarios de D4b (mix/p16/p3), GL vs D3D12 con e2_p3.exe
  ref            : MISMO backend, A = e2_ref.exe, B = e2_p3.exe, EXACTO (tol 0): gl y d3d12 -> todo IGUAL
  sab N          : como ref pero B con SM3DL_P3_SABOTAJE=N: debe DETECTAR en los escenarios de vertices
Uso (desde la raiz): py -I agentes_dx12\P3\tools\p3_e2.py <orden>"""
import importlib.util, os, shutil, subprocess, sys
P3 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(P3))
E2D = os.path.join(RAIZ, "agentes_dx12", "E2")
spec = importlib.util.spec_from_file_location("e2", os.path.join(E2D, "tools", "e2.py"))
e2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2)
EXE_P3, EXE_REF = os.path.join(P3, "e2_p3.exe"), os.path.join(P3, "e2_ref.exe")
e2.EXE = EXE_P3
e2.TRAB = os.path.join(P3, "trabajo_e2")
e2.CACHE_TRAB = os.path.join(e2.TRAB, "extraido", "shaders", "cache_d3d12")
if not os.path.isdir(e2.CACHE_TRAB):
    shutil.copytree(os.path.join(E2D, "trabajo", "extraido", "shaders", "cache_d3d12"), e2.CACHE_TRAB)
_correr = e2.correr
def correr(backend, g_words, nombre, env_extra=None, etiqueta=None):
    env = dict(env_extra or {})
    e2.EXE = EXE_REF if env.pop("P3_EXE", "") == "ref" else EXE_P3
    try:
        return _correr(backend, g_words, nombre, env, etiqueta)
    finally:
        e2.EXE = EXE_P3
e2.correr = correr


def construir():
    RD, GD = os.path.join(RAIZ, "recomp", "render"), os.path.join(RAIZ, "recomp", "gpu")
    os.makedirs(os.path.join(P3, "ref"), exist_ok=True)
    shutil.copyfile(os.path.join(RD, "raster_gl.c.antes_P3"), os.path.join(P3, "ref", "raster_gl.c"))
    base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
            "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function", "-DSM3DL_CON_D3D12"]
    fuentes = [os.path.join(E2D, "prueba_e2.c")] + [os.path.join(RD, n) for n in (
        "pica.c", "pica_dibujar.c", "texturas.c", "texturas_hd.c", "d3d12_base.c", "d3d12_recursos.c", "d3d12_presentador.c")] + [
        os.path.join(GD, "gsp.c")]
    libs = ["-lopengl32", "-lgdi32", "-luser32", "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-ldbghelp"]
    ok = True
    for exe, inc in ((EXE_P3, []), (EXE_REF, ["-I", os.path.join(P3, "ref")])):
        r = subprocess.run(base + inc + ["-I", RD, "-I", GD] + fuentes + libs + ["-o", exe], capture_output=True, text=True)
        s = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "argument unused" not in l)
        print(os.path.basename(exe), "rc", r.returncode, s[:3000])
        ok &= r.returncode == 0
    return ok


VTX = ["vertices_arrays", "vertices_u8", "vertices_u16", "vertices_cpu", "vertices_sin_elem", "tev", "luz", "mips",
       "estado", "memoria", "alta_x2"]


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else "e2"
    if orden == "enteros":
        return enteros(sys.argv[2:])
    if orden == "construir":
        sys.exit(0 if construir() else 1)
    if orden == "e2":
        b, m, z = e2.correr_lote(list(e2.ESCENARIOS), "gl", "d3d12", 1)
        sys.exit(0)
    nombres = sys.argv[2:] or VTX
    if orden == "ref":
        ok = True
        for be in ("gl", "d3d12"):
            b, m, z = e2.correr_lote(nombres, be, be, 0, {"P3_EXE": "p3"}, False,
                                     "%s: A = ANTES de P3, B = P3, EXACTO (debe dar todo IGUAL)" % be)
            ok &= m == 0 and b > 0
        print("REF:", "BIEN" if ok else "MAL")
        sys.exit(0 if ok else 1)
    if orden == "sab":
        n = sys.argv[2] if len(sys.argv) > 2 else "1"
        nombres = sys.argv[3:] or VTX
        for be in ("gl", "d3d12"):
            e2.correr_lote(nombres, be, be, 0, {"P3_EXE": "p3", "SM3DL_P3_SABOTAJE": n}, True,
                           "%s: SABOTAJE P3 %s en B: debe DETECTAR" % (be, n))
        sys.exit(0)
    raise SystemExit(__doc__)


# el lado A usa el exe de referencia en 'ref'/'sab': se marca con P3_EXE=ref en el env comun del escenario
_comparar = e2.comparar
def comparar(nombre, g, env_extra, a, b, tol, env_b=None, sabotaje=False):
    if env_b and "P3_EXE" in env_b:
        env_extra = dict(env_extra or {}); env_extra["P3_EXE"] = "ref"
    return _comparar(nombre, g, env_extra, a, b, tol, env_b, sabotaje)
e2.comparar = comparar



def enteros(argv):
    r"""los escenarios de D4b (mix/p16/p3) con e2_p3.exe y la carpeta propia (importa D4b\e2_enteros.py sin tocarlo)"""
    s = importlib.util.spec_from_file_location("e2_enteros", os.path.join(RAIZ, "agentes_dx12", "D4b", "e2_enteros.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    m.e2.EXE, m.e2.TRAB, m.e2.CACHE_TRAB = e2.EXE, e2.TRAB, e2.CACHE_TRAB
    sys.argv = [sys.argv[0]] + argv
    m.main()


if __name__ == "__main__":
    main()
