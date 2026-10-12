"""Enlaza agentes_noche\S\sm3dl_S_sinR.exe: igual que compilar.py pero con recomp\render de ANTES de R (.antes_R),
para separar mis cambios de los del rasterizador en curso."""
import os, shutil, subprocess, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = os.path.join(RAIZ, "recomp"); A = os.path.join(R, "arranque")
V = os.path.join(RAIZ, "agentes_noche", "S", "render_R0")
os.makedirs(V, exist_ok=True)
for f in os.listdir(os.path.join(R, "render")):
    src = os.path.join(R, "render", f)
    if f.endswith(".antes_R"): shutil.copy(src, os.path.join(V, f[:-len(".antes_R")]))
    elif not os.path.exists(os.path.join(V, f)) and f.endswith((".c", ".h")) and not os.path.exists(src + ".antes_R"):
        shutil.copy(src, os.path.join(V, f))
cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
       "-fno-strict-aliasing", "-msse2", "-Wno-unused-function", "-I", V,
       "-I", os.path.join(A, "partes"), "-I", os.path.join(R, "sistema"), "-I", os.path.join(R, "runtime"),
       "-DSIS_CON_HID", "-DSIS_CON_GSP", "-DSIS_CON_PICA", "-DSIS_CON_DSP", "-DAUDIO_BACKEND_WASAPI", "-DSIS_CON_RASTER"]
for d in ("hid", "gpu", "audio"): cmd += ["-I", os.path.join(R, d)]
fuentes = [os.path.join(A, "main.c"), os.path.join(R, "sistema", "sistema.c"), os.path.join(R, "runtime", "runtime.c"),
           os.path.join(R, "hid", "hid.c"), os.path.join(R, "hid", "servicio_hid.c"), os.path.join(R, "gpu", "gsp.c"),
           os.path.join(V, "pica.c"), os.path.join(V, "pica_dibujar.c"), os.path.join(V, "texturas.c"), os.path.join(V, "raster_gl.c"),
           os.path.join(V, "ventana.c"), os.path.join(R, "audio", "dsp.c"), os.path.join(R, "audio", "audio_salida.c")]
cmd += fuentes + [os.path.join(A, "juego.a"), "-ldbghelp", "-lxinput1_4", "-lole32", "-lopengl32", "-lgdi32", "-luser32",
                  "-o", os.path.join(RAIZ, "agentes_noche", "S", "sm3dl_S_sinR.exe")]
r = subprocess.run(cmd, capture_output=True, text=True)
print((r.stdout + r.stderr)[-3000:]); sys.exit(r.returncode)
