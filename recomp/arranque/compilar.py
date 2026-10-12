r"""Enlaza recomp\arranque\sm3dl.exe: main.c + capa de sistema (con hid, gsp, pica y dsp enchufados: agente C, 8 oct)
+ runtime + la copia del juego (arranque\juego.a).
Uso: py -I recomp\arranque\compilar.py [--sin-servicios]
  (el juego se recompila aparte con compilar_todo.py -d recomp\arranque\partes; ver reconstruir.sh)
  --sin-servicios: solo la capa base (srv/fs/stubs), como antes del 8 oct.
  --gpu-integrada: sin pedir la GPU dedicada (exe de "PC minimo", p. ej. -o sm3dl_intel.exe).
  --d3d12: con el backend Direct3D 12 (elegible con SM3DL_BACKEND=d3d12).
  -o NOMBRE.exe: salida propia (agentes en paralelo: cada uno enlaza SU exe, nunca sm3dl.exe a la vez)."""
import os, subprocess, sys
A = os.path.dirname(os.path.abspath(__file__))
R = os.path.dirname(A)
servicios = "--sin-servicios" not in sys.argv
cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
       "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function",
       "-I", os.path.join(A, "partes"), "-I", os.path.join(R, "sistema"), "-I", os.path.join(R, "runtime")]
fuentes = [os.path.join(A, "main.c"), os.path.join(R, "sistema", "sistema.c"), os.path.join(R, "runtime", "runtime.c")]
libs = ["-ldbghelp"]
if servicios:
    cmd += ["-DSIS_CON_HID", "-DSIS_CON_GSP", "-DSIS_CON_PICA", "-DSIS_CON_DSP", "-DAUDIO_BACKEND_WASAPI", "-DSIS_CON_RASTER"]
    for d in ("hid", "gpu", "render", "audio"):
        cmd += ["-I", os.path.join(R, d)]
    fuentes += [os.path.join(R, *p) for p in (("hid", "hid.c"), ("hid", "servicio_hid.c"), ("gpu", "gsp.c"),
                                              ("render", "pica.c"), ("render", "pica_dibujar.c"), ("render", "interp.c"),
                                              ("render", "texturas.c"), ("render", "texturas_hd.c"), ("render", "raster_gl.c"), ("render", "ventana.c"), ("audio", "dsp.c"), ("audio", "audio_salida.c"))]
    libs += ["-lxinput1_4", "-lole32", "-lopengl32", "-lgdi32", "-luser32", "-ldwmapi"]
    # sonda de posicion de Mario (SM3DL_POS): gancho rt_sonda_llamar de tabla.c
    fuentes += [os.path.join(A, "sonda.c")]
if "--d3d12" in sys.argv and servicios:   # backend D3D12 (8 oct noche): SM3DL_BACKEND=d3d12 lo elige; gl sigue de default
    cmd += ["-DSM3DL_CON_D3D12"]
    fuentes += [os.path.join(R, "render", n) for n in ("d3d12_base.c", "d3d12_recursos.c", "d3d12_presentador.c")]
    libs += ["-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47"]
if "--gpu-integrada" in sys.argv:   # sin NvOptimusEnablement: el driver deja el exe en la GPU integrada
    cmd += ["-DSM3DL_GPU_INTEGRADA"]
salida = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else "sm3dl.exe"
cmd += fuentes + [os.path.join(A, "juego.a")] + libs + ["-o", os.path.join(A, salida)]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout + r.stderr)
sys.exit(r.returncode)
