r"""Enlaza recomp\arranque\sm3dl.exe: main.c + capa de sistema (con hid, gsp, pica y dsp enchufados: agente C, 8 oct)
+ runtime + la copia del juego (arranque\juego.a).
Uso: py -I recomp\arranque\compilar.py [--sin-servicios]
  (el juego se recompila aparte con compilar_todo.py -d recomp\arranque\partes; ver reconstruir.sh)
  --sin-servicios: solo la capa base (srv/fs/stubs), como antes del 8 oct.
  --gpu-integrada: sin pedir la GPU dedicada (exe de "PC minimo", p. ej. -o sm3dl_intel.exe).
  -o NOMBRE.exe: salida propia (agentes en paralelo: cada uno enlaza SU exe, nunca sm3dl.exe a la vez)."""
import os, subprocess, sys
# VARIANTE de recomp/arranque/compilar.py (agente A, D3D12 paso 1): enlaza el arbol ACTUAL pero con el raster de ANTES
# (agentes_dx12/A/antes/raster_gl.c + raster_uber.c + presentador_gl.inc = respaldos .antes_dx12_A) -> recomp/arranque/sm3dl_A0.exe.
# Sirve de linea base para comparar contra sm3dl_A.exe aislando SOLO el cambio de este paso (el sm3dl.exe.antes_alineado
# es de las 14:05 y no lleva los cambios posteriores de ventana_gpu.c). Uso: py -I agentes_dx12/A/tools/compilar_antes.py
RAIZ = os.getcwd()
A = os.path.join(RAIZ, "recomp", "arranque")
R = os.path.join(RAIZ, "recomp")
ANTES = os.path.join(RAIZ, "agentes_dx12", "A", "antes")
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
                                              ("render", "texturas.c"), ("render", "raster_gl_ANTES"), ("render", "ventana.c"), ("audio", "dsp.c"), ("audio", "audio_salida.c"))]
    libs += ["-lxinput1_4", "-lole32", "-lopengl32", "-lgdi32", "-luser32", "-ldwmapi"]
    # sonda de posicion de Mario (SM3DL_POS): gancho rt_sonda_llamar de tabla.c
    fuentes += [os.path.join(A, "sonda.c")]
if "--gpu-integrada" in sys.argv:   # sin NvOptimusEnablement: el driver deja el exe en la GPU integrada
    cmd += ["-DSM3DL_GPU_INTEGRADA"]
salida = "sm3dl_A0.exe"
fuentes = [os.path.join(ANTES, "raster_gl.c") if f.endswith("raster_gl_ANTES") else f for f in fuentes]
cmd += fuentes + [os.path.join(A, "juego.a")] + libs + ["-o", os.path.join(A, salida)]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout + r.stderr)
sys.exit(r.returncode)
