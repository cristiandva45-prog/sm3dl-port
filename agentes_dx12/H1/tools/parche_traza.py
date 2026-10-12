r"""(H1) interp.c: SM3DL_H1_TRAZA=1 -> guarda, por cada dibujo de una re-ejecucion, los 96 registros que llegan a
pica_raster (camino de siempre y cinta) y, en la siguiente re-ejecucion del MISMO t, avisa el primer dibujo distinto."""
import os
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
p = os.path.join(RAIZ, "recomp", "render", "interp.c")
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a
    s = s.replace(a, b)


rep("""static void rap_raster(const PicaEstado *e) { raster_cinta_dibujar(g_rap_j, &e->vs.f[0].x); }""",
    """/* SM3DL_H1_TRAZA=1 (diagnostico de H1): registros que recibe pica_raster en cada dibujo de la re-ejecucion */
static int g_tz_on = -1, g_tz_k, g_tz_n[2], g_tz_lado;
static float g_tz_t[2];
static PicaVec4 (*g_tz)[2][96];
static void (*g_tz_orig)(const PicaEstado *e);
static void tz_anotar(const PicaEstado *e)
{
    if (g_tz && g_tz_k < MAX_DIB) memcpy(g_tz[g_tz_k][g_tz_lado], e->vs.f, sizeof e->vs.f);
    g_tz_k++;
}
static void tz_raster(const PicaEstado *e) { tz_anotar(e); if (g_tz_orig) g_tz_orig(e); }
static void rap_raster(const PicaEstado *e) { if (g_tz_on > 0) tz_anotar(e); raster_cinta_dibujar(g_rap_j, &e->vs.f[0].x); }
static void tz_empezar(float t, int rapido)
{
    if (g_tz_on < 0) { const char *s = getenv("SM3DL_H1_TRAZA"); g_tz_on = s && *s == '1'; }
    if (g_tz_on <= 0) return;
    if (!g_tz && !(g_tz = calloc(MAX_DIB, sizeof *g_tz))) { g_tz_on = 0; return; }
    g_tz_lado = rapido;
    g_tz_t[rapido] = t;
    g_tz_k = 0;
}
static void tz_terminar(void)
{
    if (g_tz_on <= 0) return;
    g_tz_n[g_tz_lado] = g_tz_k;
    if (g_tz_lado != 0 || g_tz_t[0] != g_tz_t[1]) return;   /* compara al terminar la re-ejecucion que sigue a la cinta */
    g_tz_t[1] = -1;
    static int avisos;
    if (g_tz_n[0] != g_tz_n[1]) { if (avisos++ < 40) fprintf(stderr, "[h1-traza] dibujos: re-ejecucion %d, cinta %d\\n", g_tz_n[0], g_tz_n[1]); return; }
    int malos = 0;
    for (int k = 0; k < g_tz_n[0] && k < MAX_DIB; k++) {
        if (!memcmp(g_tz[k][0], g_tz[k][1], sizeof g_tz[k][0])) continue;
        if (malos++ < 3 && avisos++ < 40) {
            int cur = g_ord[2];
            const InterpPrograma *pp = k < g_n[cur] && g_rap ? g_rap[k].prog : NULL;
            fprintf(stderr, "[h1-traza] t=%.2f dibujo %d (%s, prof %d st %d):", g_tz_t[0], k, pp ? pp->nombre : "?",
                    k < g_n[cur] && g_rap ? ((const PicaEstado *)(const void *)g_rap[k].pre)->depth_test : -1,
                    k < g_n[cur] && g_rap ? ((const PicaEstado *)(const void *)g_rap[k].pre)->stencil_test : -1);
            for (int q = 0, m = 0; q < 96 && m < 4; q++)
                if (memcmp(&g_tz[k][0][q], &g_tz[k][1][q], sizeof(PicaVec4))) {
                    m++;
                    fprintf(stderr, " c%d lento (%g %g %g %g) cinta (%g %g %g %g) real (%g %g %g %g)", q, g_tz[k][0][q].x, g_tz[k][0][q].y,
                            g_tz[k][0][q].z, g_tz[k][0][q].w, g_tz[k][1][q].x, g_tz[k][1][q].y, g_tz[k][1][q].z, g_tz[k][1][q].w,
                            k < g_n[cur] ? g_tab[cur][k].f[q].x : 0, k < g_n[cur] ? g_tab[cur][k].f[q].y : 0,
                            k < g_n[cur] ? g_tab[cur][k].f[q].z : 0, k < g_n[cur] ? g_tab[cur][k].f[q].w : 0);
                }
            fprintf(stderr, "\\n");
        }
    }
    if (malos && avisos++ < 40) fprintf(stderr, "[h1-traza] t=%.2f: %d de %d dibujos con registros distintos\\n", g_tz_t[0], malos, g_tz_n[0]);
}""")
# en rapido_listo: la cinta empieza su traza; en repetir(): la re-ejecucion de siempre envuelve pica_raster
rep("""    g_rap_cur = 0;
    return raster_cinta_lista(g_n[g_ord[2]]);""", """    g_rap_cur = 0;
    int ok = raster_cinta_lista(g_n[g_ord[2]]);
    if (ok && g_tz_on > 0) {   /* la re-ejecucion de siempre de este mismo intermedio no se envolvio: deshacer */
        if (pica_raster == tz_raster) pica_raster = g_tz_orig;
        tz_empezar(g_t, 1);
    }
    return ok;""")
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
