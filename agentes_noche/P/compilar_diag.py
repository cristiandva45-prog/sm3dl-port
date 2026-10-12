r"""Build de DIAGNOSTICO del agente P (no toca archivos ajenos): copia recomp\sistema a agentes_noche\P\sis_diag,
le aplica parches de registro (volcado de palabras IPC de los servicios en VOLCAR) y enlaza
recomp\arranque\sm3dl_Pdiag.exe con esa copia delante en el include path.
Uso: py -I agentes_noche\P\compilar_diag.py"""
import os, shutil, subprocess, sys
P = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(P))
R = os.path.join(RAIZ, "recomp")
A = os.path.join(R, "arranque")
D = os.path.join(P, "sis_diag")
if os.path.isdir(D):
    shutil.rmtree(D)
os.makedirs(D)
for f in os.listdir(os.path.join(R, "sistema")):
    if f.endswith((".c", ".h")):
        shutil.copy(os.path.join(R, "sistema", f), D)
# parche: volcar las palabras normales de los comandos IPC de ciertos servicios
r = os.path.join(D, "ipc.c")
t = open(r, encoding="utf-8").read()
old = "    int e = ipc_decodificar(&p);\n"
new = ("    { const char *v = getenv(\"SM3DL_VOLCAR_IPC\");\n"
       "      if (v && strstr(v, s->nombre)) { fprintf(stderr, \"[ipc-volcado] %s id 0x%04X:\", s->nombre, p.id);\n"
       "        for (u32 k = 1; k <= p.normales + p.traducidos && k < 16; k++) fprintf(stderr, \" %08X\", p.cmd[k]);\n"
       "        fprintf(stderr, \"\\n\"); } }\n") + old
assert t.count(old) == 1
t = t.replace(old, new)
if "#include <stdlib.h>" not in t:
    t = "#include <stdlib.h>\n" + t
open(r, "w", encoding="utf-8").write(t)

if "--exefs" in sys.argv:
    subprocess.run([sys.executable, "-I", os.path.join(P, "parche_fs_exefs.py"), os.path.join(D, "fs.c")], check=True)
if "--eula" in sys.argv:
    subprocess.run([sys.executable, "-I", os.path.join(P, "parche_cfg_eula.py"), os.path.join(D, "stubs.c")], check=True)
if "--applets" in sys.argv:
    subprocess.run([sys.executable, "-I", os.path.join(P, "parche_apt_applets.py"), os.path.join(D, "stubs.c")], check=True)
# --estable: render de antes de la tanda (copias .antes_R de pica.c/pica.h/raster_gl.c) en agentes_noche/P/render;
# los includes "../render/..." de sis_diag la encuentran primero. Sin --estable esa carpeta se borra.
RD = os.path.join(P, "render")
if os.path.isdir(RD):
    shutil.rmtree(RD)
if "--estable" in sys.argv:
    shutil.copytree(os.path.join(R, "render"), RD, ignore=shutil.ignore_patterns("*.exe", "*.pdb", "*.antes_*"))
    for f in ("pica.c", "pica.h", "raster_gl.c"):
        o = os.path.join(R, "render", f + ".antes_R")
        if os.path.exists(o):
            shutil.copy(o, os.path.join(RD, f))
else:
    RD = os.path.join(R, "render")
cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
       "-fno-strict-aliasing", "-msse2", "-Wno-unused-function",
       "-I", os.path.join(A, "partes"), "-I", D, "-I", RD, "-I", os.path.join(R, "runtime")]
cmd += ["-DSIS_CON_HID", "-DSIS_CON_GSP", "-DSIS_CON_PICA", "-DSIS_CON_DSP", "-DAUDIO_BACKEND_WASAPI", "-DSIS_CON_RASTER"]
for d in ("hid", "gpu", "audio"):
    cmd += ["-I", os.path.join(R, d)]
fuentes = [os.path.join(A, "main.c"), os.path.join(D, "sistema.c"), os.path.join(R, "runtime", "runtime.c")]
RASTER = os.path.join(RD, "raster_gl.c")
if "--topo3" in sys.argv:   # pedido para R: topologia 3 (Shader) sin geometry shader = lista de triangulos (Azahar)
    s = open(RASTER, encoding="utf-8").read()
    RASTER = os.path.join(P, "raster_gl_diag.c")
    a = "    if (topo > 2) {"
    if s.count(a) == 1:   # raster nuevo de R
        s = s.replace(a, "    if (topo == 3) topo = 0;   /* P: Shader = List sin GS */" + chr(10) + a)
    else:                 # raster de antes de la tanda
        assert s.count("if (e->idx.topologia > 2)") == 1 and s.count("MODO[e->idx.topologia]") == 1
        s = s.replace("if (e->idx.topologia > 2)", "if (e->idx.topologia > 3)")
        s = s.replace("MODO[e->idx.topologia]", "MODO[e->idx.topologia == 3 ? 0 : e->idx.topologia]")
    open(RASTER, "w", encoding="utf-8").write(s)
fuentes += [os.path.join(R, *p) for p in (("hid", "hid.c"), ("hid", "servicio_hid.c"), ("gpu", "gsp.c"),
                                          ("audio", "dsp.c"), ("audio", "audio_salida.c"))]
fuentes += [os.path.join(RD, f) for f in ("pica.c", "pica_dibujar.c", "texturas.c", "ventana.c")]
fuentes.append(RASTER)
libs = ["-ldbghelp", "-lxinput1_4", "-lole32", "-lopengl32", "-lgdi32", "-luser32"]
cmd += fuentes + [os.path.join(A, "juego.a")] + libs + ["-o", os.path.join(A, "sm3dl_Pdiag.exe")]
x = subprocess.run(cmd, capture_output=True, text=True)
print((x.stdout + x.stderr)[-3000:])
sys.exit(x.returncode)
