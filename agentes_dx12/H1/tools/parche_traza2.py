import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "recomp", "render", "interp.c")
s = open(p, encoding="utf-8").read()
a = "static void tz_raster(const PicaEstado *e) { tz_anotar(e); if (g_tz_orig) g_tz_orig(e); }"
assert s.count(a) == 1
s = s.replace(a, """static int g_tz_huella_mal;
static void tz_raster(const PicaEstado *e)
{
    int cur = g_ord[2];   /* la huella que ve la re-ejecucion vs la grabada en tiempo real (con la que se eligen parejas) */
    if (g_tz_k < g_n[cur] && huella(e) != g_tab[cur][g_tz_k].h) g_tz_huella_mal++;
    tz_anotar(e);
    if (g_tz_orig) g_tz_orig(e);
}""")
a = "    if (malos && avisos++ < 40) fprintf(stderr, \"[h1-traza] t=%.2f: %d de %d dibujos con registros distintos"
assert s.count(a) == 1
s = s.replace(a, "    if (malos && avisos++ < 40) fprintf(stderr, \"[h1-traza] t=%.2f: %d de %d dibujos con registros distintos; huella de la re-ejecucion != grabada en %d\"")
s = s.replace('dibujos con registros distintos; huella de la re-ejecucion != grabada en %d"\n", g_tz_t[0], malos, g_tz_n[0]);', 'dibujos con registros distintos; huella de la re-ejecucion != grabada en %d\n", g_tz_t[0], malos, g_tz_n[0], g_tz_huella_mal);\n    g_tz_huella_mal = 0;')
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
