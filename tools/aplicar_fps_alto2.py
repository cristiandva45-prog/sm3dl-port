"""Modo monitor, 2a version (8 oct): medido en el 1-1, 36 % de los refrescos repetian imagen porque la tanda de
intermedios (~14 ms de cada 33) bloqueaba el unico hilo y el tramo se cortaba antes del cuadro real.
  - DOS juegos de ranuras (0-7 y 8-15): la tanda nueva se escribe en uno mientras se muestra el otro;
  - el presentador corre tambien DENTRO de la tanda (gsp_interp_tic, entre un intermedio y el siguiente);
  - el tramo empieza en (cierre del cuadro + L), con L = lo que tarda la tanda (maximo que decae) + 2 ms: tramos
    contiguos al ritmo del juego, y siempre se llega al cuadro real."""
import os
B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp")

def parchear(rel, pares):
    ruta = os.path.join(B, *rel.split("/"))
    t = open(ruta, encoding="utf-8").read()
    for a, b in pares:
        assert t.count(a) == 1, (rel, a[:90])
        t = b.join(t.split(a))
    open(ruta + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
    os.replace(ruta + ".tmp", ruta)

parchear("render/presentador_gl.inc", [("#define PRES_RANURAS 8", "#define PRES_RANURAS 16   /* dos juegos de 8 (modo monitor) */")])

parchear("gpu/gsp_interp.inc", [
    ("static struct { int n, valido; double t0, delta; } g_alto;\n",
     "typedef struct { int n, valido, juego; double t0, delta; } Tramo;\n"
     "static Tramo g_alto, g_alto_sig;   /* el que se muestra y el siguiente (empieza en su t0) */\n"
     "void (*gsp_interp_tic)(void);      /* ventana: presentar si ya paso un refresco (se llama dentro de la tanda) */\n"
     "static double g_alto_l = 16.0;     /* retraso del tramo: lo que tarda la tanda (maximo que decae) + 2 ms */\n"),
    ("    if (gsp_interp_alta) gsp_interp_alta(sal, 0);    /* guarda la copia en alta REAL de C */\n"
     "    if (!gsp_interp_guardar(sal, 0)) { g_alto.valido = 0; if (gsp_interp_alta) gsp_interp_alta(sal, 2); return; }\n",
     "    int juego = g_alto.valido ? g_alto.juego ^ 1 : 0, base = juego * ALTO_MAX;\n"
     "    if (gsp_interp_alta) gsp_interp_alta(sal, 0);    /* guarda la copia en alta REAL de C */\n"
     "    if (!gsp_interp_guardar(sal, base)) { g_alto_sig.valido = 0; if (gsp_interp_alta) gsp_interp_alta(sal, 2); return; }\n"
     "    if (gsp_interp_tic) gsp_interp_tic();\n"),
    ("            if (!gsp_interp_guardar(sal, k)) break;\n            hechos++;\n",
     "            if (!gsp_interp_guardar(sal, base + k)) break;\n            hechos++;\n"
     "            if (gsp_interp_tic) gsp_interp_tic();   /* el presentador no se queda esperando la tanda entera */\n"),
    ("    double fin = alto_ms(), costo = fin - t;\n    g_alto.n = hechos;\n    g_alto.delta = delta;\n    g_alto.t0 = fin;\n    g_alto.valido = 1;\n",
     "    double fin = alto_ms(), costo = fin - t;\n"
     "    g_alto_l = g_alto_l * 0.98 > costo + 2.0 ? g_alto_l * 0.98 : costo + 2.0;\n"
     "    if (g_alto_l > delta) g_alto_l = delta;\n"
     "    g_alto_sig.n = hechos;\n    g_alto_sig.delta = delta;\n    g_alto_sig.juego = juego;\n"
     "    g_alto_sig.t0 = t + g_alto_l;   /* anclado al CIERRE del cuadro: tramos contiguos */\n"
     "    if (g_alto_sig.t0 < fin) g_alto_sig.t0 = fin;\n"
     "    g_alto_sig.valido = 1;\n"),
    ("tanda media %.2f ms, peor %.2f ms\\n\",\n                g_alto_cuadros, n, hz, delta, g_alto_sin, g_alto_costo / g_alto_cuadros, g_alto_costo_peor);",
     "tanda media %.2f ms, peor %.2f ms; retraso del tramo %.1f ms\\n\",\n"
     "                g_alto_cuadros, n, hz, delta, g_alto_sin, g_alto_costo / g_alto_cuadros, g_alto_costo_peor, g_alto_l);"),
    ("int gsp_interp_alto_ranura(void)\n{\n    if (!g_alto.valido) return -1;\n    if (g_alto.n <= 1) return 0;\n"
     "    double p = (alto_ms() - g_alto.t0) / g_alto.delta;\n    int k = 1 + (int)(p * g_alto.n);\n    if (k < 1) k = 1;\n"
     "    return k >= g_alto.n ? 0 : k;\n}",
     "int gsp_interp_alto_ranura(void)\n{\n    double ahora = alto_ms();\n"
     "    if (g_alto_sig.valido && ahora >= g_alto_sig.t0) { g_alto = g_alto_sig; g_alto_sig.valido = 0; }\n"
     "    if (!g_alto.valido) return -1;\n    int base = g_alto.juego * ALTO_MAX;\n    if (g_alto.n <= 1) return base;\n"
     "    double p = (ahora - g_alto.t0) / g_alto.delta;\n    int k = 1 + (int)(p * g_alto.n);\n    if (k < 1) k = 1;\n"
     "    return base + (k >= g_alto.n ? 0 : k);\n}"),
])

parchear("render/ventana_gpu.c", [
    ("    gsp_interp_hz = gpu_hz;\n}", "    gsp_interp_hz = gpu_hz;\n    { extern void (*gsp_interp_tic)(void); gsp_interp_tic = ventana_presentador; }\n}"),
    ("static unsigned g_alto_pres, g_alto_rep;\n", "static unsigned g_alto_pres, g_alto_rep;\nvoid ventana_presentador(void);\n"),
])
print("ok")
