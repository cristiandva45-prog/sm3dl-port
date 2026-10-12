r"""PEDIDO DE INTEGRACION para S (stubs.c, cfg:u): bloque 0x000D0000 = version de EULA aceptada {minor, major, 0, 0}.
En ceros el juego cree que la EULA no se acepto y, al activar StreetPass, lanza el applet de error (0x406) y se
queda esperando su respuesta (pantalla en blanco). Azahar fuerza 0x7F.0x7F por la misma razon (cfg.cpp).
Uso: py -I agentes_noche\P\parche_cfg_eula.py [ruta\stubs.c]  (por defecto la copia de diagnostico de P)"""
import os, sys
r = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sis_diag", "stubs.c")
t = open(r, encoding="utf-8").read()
if "0x000D0000" in t:
    sys.exit("ya aplicado")
old = "    default: return 0;\n    }\n}\n\nstatic void cfg_atender"
new = ("    case 0x000D0000: if (tam >= 2) { dst[0] = 0x7F; dst[1] = 0x7F; } return 1;                     /* EULA aceptada 127.127 */\n"
       + old)
assert t.count(old) == 1
t = t.replace(old, new)
open(r + ".tmp", "w", encoding="utf-8").write(t)
os.replace(r + ".tmp", r)
print("parche EULA aplicado a", r)
