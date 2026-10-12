"""Modo de cuadros "monitor" (>60 FPS, 8 oct). Parchea gsp_interp.inc, ventana_gpu.c, ventana.c, ventana.h, enchufes.c.
Al cerrar cada cuadro del juego se fabrican en tanda N-1 intermedios (t = k/N) + el real, cada uno en una ranura de la
GPU (raster_pres_guardar); N = refresco del monitor x duracion del cuadro (144 Hz x 33 ms = 5). El tramo empieza
cuando la tanda termina (mientras tanto se ve el cuadro anterior, que es la imagen correcta de ese instante). Un tic de
2 ms (sis_periodico) presenta UNA vez por refresco del monitor (temporizacion de DWM), la ranura que toca por reloj."""
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

ALTO_C = r'''
/* ---------------------------------------------------------------- MODO "MONITOR" (>60 FPS, 8 oct)
   Ver tools\aplicar_fps_alto.py. Ranura 0 = el cuadro REAL; ranura k (1..N-1) = intermedio t = k/N. */
int (*gsp_interp_guardar)(u32 sal, int ranura);   /* ventana_gpu.c: la pantalla 'sal' en alta -> ranura de la GPU */
int *gsp_interp_alto;                             /* ventana_gpu.c: 1 = modo monitor */
double (*gsp_interp_hz)(void);                    /* ventana_gpu.c: refresco del monitor */
static struct { int n, valido; double t0, delta; } g_alto;
static u32 g_alto_cuadros, g_alto_sin;
static double g_alto_costo, g_alto_costo_peor;
static double alto_ms(void)
{
    long long f, t;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t);
    return (double)t * 1000.0 / (double)f;
}
#define ALTO_MAX 8
static void alto_cerrar(u32 sal, u32 ts, int normal)
{
    static double ult, delta = 33.4;
    double t = alto_ms();
    if (ult > 0) { double d = t - ult; if (d > 10 && d < 120) delta = delta * 0.8 + d * 0.2; }
    ult = t;
    if (!gsp_interp_guardar) return;
    double hz = gsp_interp_hz ? gsp_interp_hz() : 60.0;
    int n = (int)(delta * hz / 1000.0 + 0.5);
    if (n < 1) n = 1;
    if (n > ALTO_MAX) n = ALTO_MAX;
    if (gsp_interp_alta) gsp_interp_alta(sal, 0);    /* guarda la copia en alta REAL de C */
    if (!gsp_interp_guardar(sal, 0)) { g_alto.valido = 0; if (gsp_interp_alta) gsp_interp_alta(sal, 2); return; }
    int hechos = 1, tocado = 0;
    if (normal && g_ncuadros >= 2 && g_imgs[2] && n > 1) {
        for (int k = 1; k < n; k++) {
            repetir_cuadro(3, (float)k / (float)n, -1, sal, ts, NULL);
            tocado = 1;
            if (k == 1) {   /* cambio de escena / menu (>10 % sin pareja): sin intermedios */
                uint32_t emp = 0, sue = 0;
                if (gsp_interp_cuenta) gsp_interp_cuenta(&emp, &sue);
                if (emp == 0 || sue * 10 > emp + sue) break;
            }
            if (!gsp_interp_guardar(sal, k)) break;
            hechos++;
        }
    }
    if (tocado) {   /* el framebuffer de C vuelve a ser el REAL (memoria + copia en alta) */
        if (gsp_antes_de_escribir) gsp_antes_de_escribir(sal, ts);
        gsp_escribir_fisica(sal, g_imgs[2], ts);
        if (gsp_interp_alta) gsp_interp_alta(sal, 1);
    } else if (gsp_interp_alta) gsp_interp_alta(sal, 2);
    double fin = alto_ms(), costo = fin - t;
    g_alto.n = hechos;
    g_alto.delta = delta;
    g_alto.t0 = fin;
    g_alto.valido = 1;
    g_alto_cuadros++;
    g_alto_sin += hechos == 1;
    g_alto_costo += costo;
    if (costo > g_alto_costo_peor) g_alto_costo_peor = costo;
    if (g_alto_cuadros % 300 == 0)
        fprintf(stderr, "[alto] %u cuadros: %d por cuadro (refresco %.0f Hz, cuadro %.1f ms), %u sin intermedios; tanda media %.2f ms, peor %.2f ms\n",
                g_alto_cuadros, n, hz, delta, g_alto_sin, g_alto_costo / g_alto_cuadros, g_alto_costo_peor);
}

/* la ranura que toca mostrar AHORA (-1: todavia nada) */
int gsp_interp_alto_ranura(void)
{
    if (!g_alto.valido) return -1;
    if (g_alto.n <= 1) return 0;
    double p = (alto_ms() - g_alto.t0) / g_alto.delta;
    int k = 1 + (int)(p * g_alto.n);
    if (k < 1) k = 1;
    return k >= g_alto.n ? 0 : k;
}
'''

parchear("gpu/gsp_interp.inc", [
    ("/* DIAGNOSTICO F9 (8 oct, pozo de veneno): ver tools\\aplicar_interp_diag.py */",
     ALTO_C + "\n/* DIAGNOSTICO F9 (8 oct, pozo de veneno): ver tools\\aplicar_interp_diag.py */"),
    ("    if (gsp_interp_vivo && *gsp_interp_vivo) {\n        if (!forma_normal || saltar_sig) {",
     "    if (gsp_interp_vivo && *gsp_interp_vivo && gsp_interp_alto && *gsp_interp_alto) {\n"
     "        alto_cerrar(sal, ts, forma_normal && !saltar_sig);\n"
     "        saltar_sig = !forma_normal;\n"
     "    } else if (gsp_interp_vivo && *gsp_interp_vivo) {\n        if (!forma_normal || saltar_sig) {"),
])

PRES_C = r'''
/* ---- MODO "MONITOR" (ver tools\aplicar_fps_alto.py) ---- */
#include <dwmapi.h>
extern int (*gsp_interp_guardar)(uint32_t sal, int ranura);
extern int *gsp_interp_alto;
extern double (*gsp_interp_hz)(void);
int gsp_interp_alto_ranura(void);
int raster_pres_guardar(int r);
static int g_alto_on;
static int gpu_guardar(uint32_t sal, int ranura)
{
    unsigned tex = 0, gen = 0;
    int s = 0;
    if (raster_alta_textura(sal, g_arr_fmt, g_arr_stride, 400, 240, &tex, &s, &gen) <= 1) return 0;
    return raster_pres_guardar(ranura);
}
static double gpu_hz(void)
{
    static double hz;
    static ULONGLONG cuando;
    if (!hz || GetTickCount64() - cuando > 2000) {
        DWM_TIMING_INFO ti;
        memset(&ti, 0, sizeof ti);
        ti.cbSize = sizeof ti;
        if (DwmGetCompositionTimingInfo(NULL, &ti) == S_OK && ti.rateRefresh.uiDenominator && ti.rateRefresh.uiNumerator)
            hz = (double)ti.rateRefresh.uiNumerator / ti.rateRefresh.uiDenominator;
        if (hz < 30 || hz > 500) hz = 60;
        cuando = GetTickCount64();
    }
    return hz;
}
static void gpu_alto_enganchar(void)
{
    gsp_interp_guardar = gpu_guardar;
    gsp_interp_alto = &g_alto_on;
    gsp_interp_hz = gpu_hz;
}
static unsigned g_alto_pres, g_alto_rep;
'''

parchear("render/ventana_gpu.c", [
    ("static unsigned g_gpu_n, g_gpu_verif_n, g_gpu_verif_mal;\n",
     "static unsigned g_gpu_n, g_gpu_verif_n, g_gpu_verif_mal;\n" + PRES_C),
    # gpu_pintar con ranura
    ("static void gpu_pintar(void)\n{", "static void gpu_pintar_ranura(int ranura)\n{"),
    ("    int alta = g_capa_hud && g_arr_ok && raster_alta_textura(g_arr_dir, g_arr_fmt, g_arr_stride, 400, 240, &tex, &s, &gen) > 1;",
     "    int alta = ranura >= 0 ? g_capa_hud\n"
     "             : g_capa_hud && g_arr_ok && raster_alta_textura(g_arr_dir, g_arr_fmt, g_arr_stride, 400, 240, &tex, &s, &gen) > 1;"),
    ("        raster_pres_base(-1, dx + corr, dy, dx + dw + corr, dy + dh, aj.suave);   /* corr: sabotaje de la verificacion */",
     "        raster_pres_base(ranura, dx + corr, dy, dx + dw + corr, dy + dh, aj.suave);   /* corr: sabotaje de la verificacion */"),
    ("    if (verif && g_gpu_n % 120 == 60 && alta && !g_menu) {",
     "    if (verif && ranura < 0 && g_gpu_n % 120 == 60 && alta && !g_menu) {"),
])
# envoltorio + el tic del presentador, al final del archivo
ruta = os.path.join(B, "render", "ventana_gpu.c")
t = open(ruta, encoding="utf-8").read()
t += r'''
static void gpu_pintar(void) { gpu_pintar_ranura(g_alto_on ? gsp_interp_alto_ranura() : -1); }

/* tic de 2 ms (enchufes.c): en modo monitor presenta UNA vez por refresco, justo despues de cada uno (DWM) */
void ventana_presentador(void)
{
    if (!g_alto_on || g_gpu != 1 || !aj.unica || g_menu || !g_v) return;
    static long long ult_vblank;
    DWM_TIMING_INFO ti;
    memset(&ti, 0, sizeof ti);
    ti.cbSize = sizeof ti;
    long long vb = 0;
    if (DwmGetCompositionTimingInfo(NULL, &ti) == S_OK && ti.qpcRefreshPeriod) vb = (long long)ti.qpcVBlank;
    else {   /* sin DWM: por reloj */
        LARGE_INTEGER q, f;
        QueryPerformanceCounter(&q);
        QueryPerformanceFrequency(&f);
        vb = q.QuadPart / (f.QuadPart / (long long)gpu_hz());
    }
    if (vb == ult_vblank) return;   /* ya se presento en este refresco */
    ult_vblank = vb;
    int r = gsp_interp_alto_ranura();
    static int r_antes = -2;
    static double t0_antes;
    g_alto_pres++;
    if (r == r_antes && !g_sucio_pint && !g_ultimo_con_ui && !g_titulo) { g_alto_rep++; return; }   /* nada nuevo */
    r_antes = r;
    (void)t0_antes;
    gpu_pintar_ranura(r);
    if (g_alto_pres % 1440 == 0)
        fprintf(stderr, "[alto-pres] %u refrescos (%.0f Hz): %u con imagen repetida (%.1f %%)\n", g_alto_pres, gpu_hz(), g_alto_rep,
                100.0 * g_alto_rep / g_alto_pres);
}
'''
open(ruta + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
os.replace(ruta + ".tmp", ruta)

parchear("render/ventana.h", [
    ("uint32_t ventana_botones(void);\n",
     "uint32_t ventana_botones(void);\n/* tic de 2 ms: en el modo de cuadros \"monitor\" presenta una vez por refresco del monitor */\nvoid ventana_presentador(void);\n"),
])

parchear("sistema/enchufes.c", [
    ("    sis_periodico(gsp_reporte, 2000000000ull);\n}",
     "    sis_periodico(gsp_reporte, 2000000000ull);\n#ifdef SIS_CON_RASTER\n"
     "    sis_periodico(ventana_presentador, 2000000ull);       /* modo de cuadros \"monitor\" (>60 FPS) */\n#endif\n}"),
])

parchear("render/ventana.c", [
    # tercer valor de FPS
    ("static int aj_presentar_gpu;   /* presentar=gpu en el .ini (ventana_gpu.c) */\n",
     "static int aj_presentar_gpu;   /* presentar=gpu en el .ini (ventana_gpu.c) */\n"
     "static int aj_fps_alto;        /* fps=monitor: tantos cuadros como refresque el monitor (ventana_gpu.c) */\n"
     "static int g_alto_on;          /* definido en ventana_gpu.c */\n"),
    ("            aj.fps30 ? 30 : 60, aj.resol);",
     "            aj_fps_alto ? 0 : aj.fps30 ? 30 : 60, aj.resol);"),
    ("        else if (!strncmp(l, \"fps=\", 4)) aj.fps30 = atoi(l + 4) == 30;",
     "        else if (!strncmp(l, \"fps=\", 4)) { aj.fps30 = atoi(l + 4) == 30; aj_fps_alto = !strncmp(l + 4, \"monitor\", 7) || atoi(l + 4) == 0; }"),
    ("    case OP_FPS: _snwprintf(t, n, L\"%ls\", aj.fps30 ? L\"30 (original)\" : L\"60 (interpolados)\"); break;",
     "    case OP_FPS: _snwprintf(t, n, L\"%ls\", aj_fps_alto ? L\"Monitor (interpolados)\" : aj.fps30 ? L\"30 (original)\" : L\"60 (interpolados)\"); break;"),
    ("    case OP_FPS: aj.fps30 = !aj.fps30; interp_vivo = !aj.fps30; break;",
     "    case OP_FPS:   /* 30 -> 60 -> monitor -> 30; monitor presenta por la GPU */\n"
     "        if (aj.fps30) { aj.fps30 = 0; aj_fps_alto = 0; }\n"
     "        else if (!aj_fps_alto) { aj_fps_alto = 1; aj_presentar_gpu = 1; if (g_gpu == 0) g_gpu = -1; }\n"
     "        else { aj_fps_alto = 0; aj.fps30 = 1; }\n"
     "        interp_vivo = !aj.fps30;\n"
     "        g_alto_on = aj_fps_alto && interp_vivo;\n"
     "        break;"),
    ("    interp_vivo = !aj.fps30;\n    fprintf(stderr, \"[ventana] cuadros por segundo: %s\\n\", interp_vivo ? \"60 interpolados\" : \"30 (original)\");",
     "    interp_vivo = !aj.fps30;\n"
     "    { const char *a = getenv(\"SM3DL_FPS_ALTO\"); if (a) aj_fps_alto = *a == '1'; }\n"
     "    if (aj_fps_alto) { aj_presentar_gpu = 1; if (!interp_vivo) aj_fps_alto = 0; }\n"
     "    g_alto_on = aj_fps_alto;\n"
     "    gpu_alto_enganchar();\n"
     "    fprintf(stderr, \"[ventana] cuadros por segundo: %s\\n\", aj_fps_alto ? \"monitor (interpolados)\" : interp_vivo ? \"60 interpolados\" : \"30 (original)\");"),
    # en modo monitor el vblank no pinta (lo hace el presentador)
    ("                if (pintar_ya && g_gpu == 1 && aj.unica) { gpu_pintar(); g_cr_pint++; }",
     "                if (g_alto_on && g_gpu == 1 && aj.unica) { /* modo monitor: pinta ventana_presentador */ }\n"
     "                else if (pintar_ya && g_gpu == 1 && aj.unica) { gpu_pintar(); g_cr_pint++; }"),
])
print("ok")
