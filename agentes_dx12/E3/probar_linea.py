r"""Prueba E3 (9 oct): extrae TAL CUAL el bloque E3-LINEA de recomp\gpu\gsp_interp.inc, compila el simulador y lo corre.
Uso: py -I agentes_dx12\E3\probar_linea.py [--sabotaje=linea|salto]
  --sabotaje=linea : el ancla vuelve a ser la hora de cierre (sin linea)       -> TIENE que FALLAR
  --sabotaje=salto : sin el salto del desfase cuando el cuadro llega tarde    -> TIENE que FALLAR
Sale con el codigo del simulador (0 = PASA)."""
import os, subprocess, sys
E3 = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(E3))
INC = os.path.join(RAIZ, "recomp", "gpu", "gsp_interp.inc")
SAB = {"linea": ("double t0 = s->t0_ant + ALTO_CUADRO_MS;", "double t0 = t0_min;"),
       "salto": ("if (t0 < t0_min) {", "if (0) {")}
sab = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--sabotaje=")), None)
txt = open(INC, encoding="utf-8").read()
i, f = txt.find("/* E3-LINEA-INICIO"), txt.find("/* E3-LINEA-FIN */")
if i < 0 or f < 0:
    sys.exit("no encuentro el bloque E3-LINEA en " + INC)
bloque = txt[i:f]
if sab:
    viejo, nuevo = SAB[sab]
    if bloque.count(viejo) != 1:
        sys.exit("el sabotaje '%s' no encuentra su texto: no sabotearia nada" % sab)
    bloque = bloque.replace(viejo, nuevo)
    print("[probar_linea] SABOTAJE %s: '%s' -> '%s'" % (sab, viejo, nuevo))
h = os.path.join(E3, "linea_extraida.h")
tmp = h + ".tmp"
with open(tmp, "w", encoding="utf-8") as o:
    o.write("/* GENERADO por probar_linea.py desde recomp\\gpu\\gsp_interp.inc: no editar */\n" + bloque + "\n")
os.replace(tmp, h)
exe = os.path.join(E3, "sim_linea.exe")
r = subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-Wall",
                    "-Wno-unused-function", "-ffp-contract=off", os.path.join(E3, "sim_linea.c"), "-o", exe],
                   capture_output=True, text=True)
if r.returncode:
    print(r.stdout + r.stderr)
    sys.exit("no compila el simulador")
r = subprocess.run([exe])
sys.exit(r.returncode)
