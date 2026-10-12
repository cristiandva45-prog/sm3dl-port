"""Reemplaza dibujo() de recomp/render/interp.c por la version con semantica (interp_dibujo_semantica.c.txt). 8 oct."""
import os
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp", "render")
f = os.path.join(R, "interp.c")
t = open(f, encoding="utf-8").read()
nuevo = open(os.path.join(R, "interp_dibujo_semantica.c.txt"), encoding="utf-8").read()
ini = t.index("static void dibujo(PicaEstado *e)")
fin = t.index("/* fin de un cuadro del juego")
t = t[:ini] + nuevo + t[fin:]
pares = [
    ("    g_n[viejo] = 0;\n}", "    g_n[viejo] = 0;\n    g_ncam[viejo] = 0;\n}"),
    ('%u sin pareja, %u valores que saltan\\n",\n                    g_t, g_emparejados, g_sin_mezcla, g_vetados, g_sueltos, g_saltos);',
     '%u sin pareja, %u valores que saltan; %u solo con camara mezclada, %u cortes de camara; programas %u conocidos %u no\\n",\n                    g_t, g_emparejados, g_sin_mezcla, g_vetados, g_sueltos, g_saltos, g_solo_cam, g_cortes, g_reconocidos, g_desconocidos);'),
    ("g_emparejados = g_sueltos = g_sin_mezcla = g_vetados = g_saltos = 0;",
     "g_emparejados = g_sueltos = g_sin_mezcla = g_vetados = g_saltos = g_solo_cam = g_cortes = 0;"),
]
for a, b in pares:
    assert t.count(a) == 1, a
    t = t.split(a)[0] + b + t.split(a)[1]
open(f + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
os.replace(f + ".tmp", f)
print("ok")
