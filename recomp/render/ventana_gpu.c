/* PRESENTACION POR GPU (8 oct, paso hacia >60 FPS). Incluido por ventana.c antes de ventana_presentar.
 * En vez de bajar la pantalla de arriba en alta a la CPU (6 MB a 4x), componerla con GDI y pintarla con StretchDIBits:
 *   1. la imagen del juego va directo de su textura (raster_alta_textura) al framebuffer de la ventana (blit);
 *   2. el HUD integrado se compone en la CPU sobre una capa TRANSPARENTE (mezclar acumula alfa premultiplicado) y
 *      se sube solo la zona que cambio;
 *   3. la interfaz (titulo, tuerca, menu) igual, en una capa del tamano de la ventana;
 *   4. SwapBuffers con wglSwapIntervalEXT (vsync real del monitor).
 * Se activa con SM3DL_PRESENTAR=gpu (o presentar=gpu en sm3dl_ajustes.ini). Solo pantalla UNICA; sin eso, GDI.
 * SM3DL_PRES_VERIFICAR=1: cada 120 presentaciones compara lo presentado con el camino GDI del MISMO cuadro.
 * SM3DL_PRES_VERIFICAR=2: sabotaje (imagen y HUD 3 px corridos): la verificacion tiene que verlo. */
int raster_alta_textura(unsigned dir_fisica, unsigned fmt, unsigned stride, unsigned ancho, unsigned alto,
                        unsigned *tex_gl, int *s, unsigned *gen);
int raster_gl_hacer_actual(void *hdc);
int raster_pres_empezar(int w, int h);
int raster_pres_base(int r, int x0, int y0, int x1, int y1, int lineal);
int raster_pres_subir(int c, const uint8_t *bgra, int w, int h, int x0, int y0, int x1, int y1);
int raster_pres_capa(int c, int x0, int y0, int x1, int y1, int lineal);
int raster_pres_mostrar(void *hdc, int intervalo);
int raster_pres_leer(uint8_t *bgra, int w, int h);
int raster_pres_listo(int w, int h);

static int g_gpu = -1;          /* -1 sin decidir, 0 GDI, 1 GPU */
static HDC g_gpu_dc;
static uint32_t g_arr_dir, g_arr_fmt, g_arr_stride;
static int g_arr_ok;
static uint8_t *g_ui_capa;
static int g_ui_cw, g_ui_ch;
static RECT g_ui_previo;
static RECT g_hud_previo;
static int g_hud_subido_w, g_hud_subido_h, g_hud_base_sucia = 1;
static unsigned g_gpu_n, g_gpu_verif_n, g_gpu_verif_mal;

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
    static double hz, forzado = -1;
    static ULONGLONG cuando;
    if (forzado < 0) {   /* K1 (10 oct), SOLO PRUEBAS: SM3DL_PRES_HZ=<hz> fuerza la rejilla de refrescos (con la ventana
                            oculta DWM dice 60 Hz: M1). No cambia el monitor ni la swap chain, solo la cuenta de t/refresco */
        const char *e = getenv("SM3DL_PRES_HZ");
        forzado = e ? atof(e) : 0;
        if (forzado < 30 || forzado > 500) forzado = 0;
        if (forzado) fprintf(stderr, "[ventana] SM3DL_PRES_HZ: rejilla de refrescos forzada a %.1f Hz (solo pruebas)\n", forzado);
    }
    if (forzado) return forzado;
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
/* el refresco EN CURSO = (ahora - fase) / periodo. qpcVBlank de DWM solo da la fase: a pantalla completa (flip
   independiente) DWM no compone y qpcVBlank se queda quieto (8 oct: se veia a ~2 FPS esperando que cambiara) */
static long long g_vb_fase, g_vb_periodo;
static ULONGLONG g_vb_cuando;
static void gpu_vb_actualizar(void)
{
    if (g_vb_periodo && GetTickCount64() - g_vb_cuando <= 1000) return;
    LARGE_INTEGER f;
    QueryPerformanceFrequency(&f);
    g_vb_periodo = (long long)((double)f.QuadPart / gpu_hz());
    DWM_TIMING_INFO ti;
    memset(&ti, 0, sizeof ti);
    ti.cbSize = sizeof ti;
    if (g_vb_periodo > 0 && DwmGetCompositionTimingInfo(NULL, &ti) == S_OK && ti.qpcVBlank)
        g_vb_fase = (long long)(ti.qpcVBlank % (unsigned long long)g_vb_periodo);
    g_vb_cuando = GetTickCount64();
}
/* para gsp_interp.inc: la misma rejilla de refrescos en ms (QPC * 1000 / f, como alto_ms) */
static void gpu_vb(double *fase_ms, double *periodo_ms)
{
    gpu_vb_actualizar();
    LARGE_INTEGER f;
    QueryPerformanceFrequency(&f);
    *fase_ms = (double)g_vb_fase * 1000.0 / (double)f.QuadPart;
    *periodo_ms = (double)g_vb_periodo * 1000.0 / (double)f.QuadPart;
}
#ifdef SM3DL_CON_D3D12
static int hp_tic(void);
static void hp_soltar_si(void);
static int hp_pedido(void);
static void hp_bloquear(int on);
void raster_hp_publicar(int juego);
static int g_hp_pedido = -1;
#endif
static void gpu_alto_enganchar(void)
{
    gsp_interp_guardar = gpu_guardar;
    gsp_interp_alto = &g_alto_on;
    gsp_interp_hz = gpu_hz;
    { extern void (*gsp_interp_tic)(void); gsp_interp_tic = ventana_presentador; }
    { extern void (*gsp_interp_vb)(double *, double *); gsp_interp_vb = gpu_vb; }
#ifdef SM3DL_CON_D3D12
    {   /* K1: candado del tramo + publicar las ranuras (solo con SM3DL_PRES_HILO=1) */
        extern void (*gsp_interp_hp_bloquear)(int);
        extern void (*gsp_interp_hp_publicar)(int);
        if (hp_pedido()) { gsp_interp_hp_bloquear = hp_bloquear; gsp_interp_hp_publicar = raster_hp_publicar; }
    }
#endif
}
static unsigned g_alto_pres, g_alto_rep;
void ventana_presentador(void);

static void rect_unir(RECT *a, const RECT *b)
{
    if (b->right <= b->left || b->bottom <= b->top) return;
    if (a->right <= a->left || a->bottom <= a->top) { *a = *b; return; }
    if (b->left < a->left) a->left = b->left;
    if (b->top < a->top) a->top = b->top;
    if (b->right > a->right) a->right = b->right;
    if (b->bottom > a->bottom) a->bottom = b->bottom;
}

static int gpu_pedido(void)
{
    const char *e = getenv("SM3DL_PRESENTAR");
    if (e) return !strcmp(e, "gpu");
    return aj_presentar_gpu;
}

/* decide una vez (cuando el raster ya tiene contexto): deja el contexto GL sobre el DC de la ventana */
static int gpu_activo(void)
{
    if (g_gpu >= 0) return g_gpu;
    if (!gpu_pedido()) { g_gpu = 0; return 0; }
    if (!g_gpu_dc) g_gpu_dc = GetDC(g_v);   /* clase CS_OWNDC: el mismo DC para siempre */
    if (!raster_gl_hacer_actual(g_gpu_dc)) return 0;   /* el raster aun no tiene contexto: probar en el proximo */
    g_gpu = 1;
    fprintf(stderr, "[ventana] presentacion por GPU (SwapBuffers, vsync %s)\n", aj.vsync ? "del monitor" : "apagado");
    return 1;
}

/* el HUD sobre transparente: lo llama componer_unica_imagen en vez de copiar la imagen de base */
static void gpu_hud_limpiar(void)
{
    static int w_antes, h_antes;
    if (g_u_w != w_antes || g_u_h != h_antes) {
        memset(g_unica_bgra, 0, (size_t)g_u_w * g_u_h * 4);
        w_antes = g_u_w; h_antes = g_u_h;
        SetRect(&g_hud_previo, 0, 0, g_u_w, g_u_h);   /* subir entera */
    } else {
        for (int y = g_hud_previo.top; y < g_hud_previo.bottom; y++)
            memset(g_unica_bgra + ((size_t)y * g_u_w + g_hud_previo.left) * 4, 0, (size_t)(g_hud_previo.right - g_hud_previo.left) * 4);
    }
    SetRectEmpty(&g_hud_sucio);
}

static void gpu_pintar_ranura(int ranura)
{
    RECT cr;
    GetClientRect(g_v, &cr);
    int w = cr.right, h = cr.bottom;
    if (w <= 0 || h <= 0) return;
#ifdef SM3DL_CON_D3D12
    hp_soltar_si();   /* K1: el camino de siempre vuelve a ser el dueno de la swap chain */
#endif
    int dx, dy, dw, dh;
    destino(w, h, &dx, &dy, &dw, &dh);
    LARGE_INTEGER g1_q0, g1_q1, g1_q2, g1_q3;
    QueryPerformanceCounter(&g1_q0);
    raster_pres_empezar(w, h);
    QueryPerformanceCounter(&g1_q1);
    unsigned tex = 0, gen = 0;
    int s = 0;
    int alta = ranura >= 0 ? g_capa_hud
             : g_capa_hud && g_arr_ok && raster_alta_textura(g_arr_dir, g_arr_fmt, g_arr_stride, 400, 240, &tex, &s, &gen) > 1;
    static int verif = -1;
    if (verif < 0) { const char *e = getenv("SM3DL_PRES_VERIFICAR"); verif = e ? atoi(e) : 0; }
    int corr = verif == 2 ? 3 : 0;   /* sabotaje */
    if (alta) {
        raster_pres_base(ranura, dx + corr, dy, dx + dw + corr, dy + dh, aj.suave);   /* corr: sabotaje de la verificacion */
        /* HUD: subir lo que cambio (lo de antes + lo de ahora) */
        RECT r = g_hud_previo;
        rect_unir(&r, &g_hud_sucio);
        if (g_hud_subido_w != g_u_w || g_hud_subido_h != g_u_h) { SetRect(&r, 0, 0, g_u_w, g_u_h); g_hud_subido_w = g_u_w; g_hud_subido_h = g_u_h; }
        if (r.right > r.left) raster_pres_subir(0, g_unica_bgra, g_u_w, g_u_h, r.left, r.top, r.right, r.bottom);
        g_hud_previo = g_hud_sucio;
        SetRectEmpty(&g_hud_sucio);
        if (g_hud_visible) raster_pres_capa(0, dx + corr, dy, dx + dw + corr, dy + dh, aj.suave);
    } else {   /* sin alta (1x): la imagen ya compuesta en la CPU (chica: 400x240) va entera como base opaca */
        if (g_hud_base_sucia || g_hud_subido_w != g_u_w || g_hud_subido_h != g_u_h) {
            raster_pres_subir(0, g_unica_bgra, g_u_w, g_u_h, 0, 0, g_u_w, g_u_h);
            g_hud_subido_w = g_u_w; g_hud_subido_h = g_u_h;
            SetRect(&g_hud_previo, 0, 0, g_u_w, g_u_h);
        }
        raster_pres_capa(0, dx, dy, dx + dw, dy + dh, aj.suave);
    }
    g_hud_base_sucia = 0;
    /* interfaz: capa del tamano de la ventana; se borra lo de la vez pasada y se sube lo que cambio */
    if (!g_ui_capa || g_ui_cw != w || g_ui_ch != h) {
        free(g_ui_capa);
        g_ui_capa = calloc((size_t)w * h, 4);
        g_ui_cw = w; g_ui_ch = h;
        SetRect(&g_ui_previo, 0, 0, w, h);
        if (!g_ui_capa) { g_ui_cw = g_ui_ch = 0; return; }
    } else {
        for (int y = g_ui_previo.top; y < g_ui_previo.bottom; y++)
            memset(g_ui_capa + ((size_t)y * w + g_ui_previo.left) * 4, 0, (size_t)(g_ui_previo.right - g_ui_previo.left) * 4);
    }
    SetRectEmpty(&g_ui_sucio);
    ui_px = g_ui_capa;
    ui_w = w;
    ui_h = h;
    g_ui_seguir = 1;
    SetRect(&g_rect_tuerca, 0, 0, 0, 0);
    g_ultimo_con_ui = 1;
    if (g_menu) {   /* fondo oscurecido: como el GDI (x 95/256) = negro con alfa 161 encima */
        for (size_t k = 0; k < (size_t)w * h; k++) { g_ui_capa[4 * k] = g_ui_capa[4 * k + 1] = g_ui_capa[4 * k + 2] = 0; g_ui_capa[4 * k + 3] = 161; }
        SetRect(&g_ui_sucio, 0, 0, w, h);
        dibujar_menu(dx, dy, dw, dh);
    } else if (g_titulo) dibujar_titulo(dx, dy, dw, dh);
    else {
        int op = opacidad_tuerca();
        if (op) dibujar_tuerca(dx, dy, dw, dh, op);
        else g_ultimo_con_ui = 0;
    }
    g_ui_seguir = 0;
    RECT r = g_ui_previo;
    rect_unir(&r, &g_ui_sucio);
    if (r.right > r.left) raster_pres_subir(1, g_ui_capa, w, h, r.left, r.top, r.right, r.bottom);
    g_ui_previo = g_ui_sucio;
    if (g_ui_sucio.right > g_ui_sucio.left) raster_pres_capa(1, 0, 0, w, h, 0);
    g_sucio_pint = 0;
    g_gpu_n++;
    if (verif && ranura < 0 && g_gpu_n % 120 == 60 && alta && !g_menu) {
        /* lo presentado vs el camino GDI del MISMO cuadro (pintar con dc NULL = sin BitBlt, deja el resultado en g_px) */
        uint8_t *gl_px = malloc((size_t)w * h * 4);
        const unsigned char *hi = NULL;
        int s2 = raster_alta(g_arr_dir, g_arr_fmt, g_arr_stride, 400, 240, &hi);
        if (gl_px && s2 == s && hi) {
            raster_pres_leer(gl_px, w, h);
            memcpy(g_alta_bgra, hi, (size_t)400 * s * 240 * s * 4);
            g_capa_hud = 0;
            componer_unica_imagen();
            pintar(NULL);
            g_capa_hud = 1;
            g_hud_base_sucia = 1;
            SetRect(&g_hud_previo, 0, 0, g_u_w, g_u_h);
            componer_unica_imagen();   /* vuelve a dejar el HUD sobre transparente */
            uint32_t malos = 0, grandes = 0;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++) {
                    const uint8_t *a = gl_px + ((size_t)(h - 1 - y) * w + x) * 4, *b = g_px + ((size_t)y * w + x) * 4;
                    int m = 0;
                    for (int c = 0; c < 3; c++) { int d = abs(a[c] - b[c]); if (d > m) m = d; }
                    malos += m > 8;
                    grandes += m > 64;
                }
            const char *vol = getenv("SM3DL_PRES_VOLCAR");   /* carpeta: g<n>.raw (GPU, fila 0 abajo) y c<n>.raw (GDI) */
            if (vol && *vol && g_gpu_verif_n >= 13 && g_gpu_verif_n < 16) {
                char ruta[400];
                snprintf(ruta, sizeof ruta, "%s\\g%u_%dx%d.raw", vol, g_gpu_verif_n, w, h);
                FILE *fv = fopen(ruta, "wb");
                if (fv) { fwrite(gl_px, 4, (size_t)w * h, fv); fclose(fv); }
                snprintf(ruta, sizeof ruta, "%s\\c%u_%dx%d.raw", vol, g_gpu_verif_n, w, h);
                fv = fopen(ruta, "wb");
                if (fv) { fwrite(g_px, 4, (size_t)w * h, fv); fclose(fv); }
            }
            g_gpu_verif_n++;
            /* calibrado 8 oct (1-1, 1200x720): lo legitimo (muestreo distinto al reducir, en los bordes) da <= 0,5 %
               muy distintos; el sabotaje de 3 px da >= 1,5 %. Umbral 1 %. */
            if (grandes * 100u > (uint32_t)w * h) g_gpu_verif_mal++;
            fprintf(stderr, "[pres-verif] presentacion %u: %u px distintos (>8 niveles) y %u muy distintos (>64) de %d contra GDI; malas %u de %u\n",
                    g_gpu_n, malos, grandes, w * h, g_gpu_verif_mal, g_gpu_verif_n);
        }
        free(gl_px);
    }
    {   /* SM3DL_PRES_SECUENCIA=<presentacion>: vuelca 12 presentaciones SEGUIDAS (s<k>_r<ranura>_WxH.raw) en SM3DL_PRES_VOLCAR */
        static long desde = -2;
        if (desde == -2) { const char *e = getenv("SM3DL_PRES_SECUENCIA"); desde = e ? atol(e) : -1; }
        const char *vol = getenv("SM3DL_PRES_VOLCAR");
        if (desde >= 0 && vol && g_gpu_n >= (unsigned)desde && g_gpu_n < (unsigned)desde + 12) {
            uint8_t *px = malloc((size_t)w * h * 4);
            if (px) {
                raster_pres_leer(px, w, h);
                char ruta[400];
                snprintf(ruta, sizeof ruta, "%s\\s%02u_r%d_%dx%d.raw", vol, g_gpu_n - (unsigned)desde, ranura, w, h);
                FILE *fv = fopen(ruta, "wb");
                if (fv) { fwrite(px, 4, (size_t)w * h, fv); fclose(fv); }
                free(px);
            }
        }
    }
    {   /* G1 (9 oct) SM3DL_PRES_VIDEO=<carpeta>, SM3DL_PRES_VIDEO_DESDE=<p1>[,<p2>...] (presentaciones), _N=<cuantas> (180):
           rafagas de lo PRESENTADO (el buffer de atras justo antes de mostrar), a media resolucion, v<k>_<n>_WxH.raw
           (BGRA, fila 0 ABAJO) -> tools: agentes_dx12\G1\video.py. La lectura es SINCRONA: cambia el ritmo; medir aparte */
        static int on = -1, nd, nv; static long desde[8]; static char dir[300];
        if (on < 0) {
            const char *c = getenv("SM3DL_PRES_VIDEO"), *d = getenv("SM3DL_PRES_VIDEO_DESDE"), *nn = getenv("SM3DL_PRES_VIDEO_N");
            on = c && *c && d && *d;
            if (on) {
                snprintf(dir, sizeof dir, "%s", c);
                for (const char *q = d; *q && nd < 8; ) { desde[nd++] = atol(q); while (*q && *q != ',') q++; if (*q) q++; }
                nv = nn ? atoi(nn) : 180;
            }
        }
        for (int i = 0; on && i < nd; i++)
            if (g_gpu_n >= (unsigned)desde[i] && g_gpu_n < (unsigned)(desde[i] + nv)) {
                uint8_t *px = malloc((size_t)w * h * 4), *m = malloc((size_t)(w / 2) * (h / 2) * 4);
                if (px && m && raster_pres_leer(px, w, h)) {
                    for (int y = 0; y < h / 2; y++)
                        for (int x = 0; x < w / 2; x++) memcpy(m + ((size_t)y * (w / 2) + x) * 4, px + ((size_t)(2 * y) * w + 2 * x) * 4, 4);
                    char ruta[400];
                    snprintf(ruta, sizeof ruta, "%s\\v%d_%04u_r%06u_%dx%d.raw", dir, i, g_gpu_n - (unsigned)desde[i], g_alto_pres, w / 2, h / 2);
                    FILE *fv = fopen(ruta, "wb");
                    if (fv) { fwrite(m, 4, (size_t)(w / 2) * (h / 2), fv); fclose(fv); }
                }
                free(px); free(m);
            }
    }
    QueryPerformanceCounter(&g1_q2);
    raster_pres_mostrar(g_gpu_dc, aj.vsync ? 1 : 0);
    QueryPerformanceCounter(&g1_q3);
    {   /* G1 (9 oct): cuanto bloquea presentar el hilo del planificador (empezar = espera de latencia en D3D12) */
        static double s_emp, s_pin, s_mos, m_emp, m_mos; static unsigned n;
        LARGE_INTEGER f; QueryPerformanceFrequency(&f);
        double k = 1000.0 / (double)f.QuadPart, e = (g1_q1.QuadPart - g1_q0.QuadPart) * k,
               pi = (g1_q2.QuadPart - g1_q1.QuadPart) * k, mo = (g1_q3.QuadPart - g1_q2.QuadPart) * k;
        s_emp += e; s_pin += pi; s_mos += mo;
        if (e > m_emp) m_emp = e;
        if (mo > m_mos) m_mos = mo;
        if (++n % 600 == 0) {
            fprintf(stderr, "[pres-crono] %u presentaciones: empezar %.2f ms (peor %.1f), componer %.2f ms, mostrar %.2f ms (peor %.1f)\n",
                    n, s_emp / 600, m_emp, s_pin / 600, s_mos / 600, m_mos);
            s_emp = s_pin = s_mos = m_emp = m_mos = 0;
        }
    }
}

static void gpu_pintar(void) { gpu_pintar_ranura(g_alto_on ? gsp_interp_alto_ranura() : -1); }

/* tic de 2 ms (enchufes.c): en modo monitor presenta UNA vez por refresco, justo despues de cada uno (DWM) */
void ventana_presentador(void)
{
#ifdef SM3DL_CON_D3D12
    if (g_hp_pedido != 0 && hp_tic()) return;   /* K1: presenta el hilo */
#endif
    if (!g_alto_on || g_gpu != 1 || !aj.unica || g_menu || !g_v) return;
    static long long ult_vblank;
    LARGE_INTEGER q;
    QueryPerformanceCounter(&q);
    gpu_vb_actualizar();
    if (g_vb_periodo <= 0) return;
    long long vb = (q.QuadPart - g_vb_fase) / g_vb_periodo;
    if (vb == ult_vblank) return;   /* ya se presento en este refresco */
    int r = gsp_interp_alto_ranura();
    static int r_antes = -2;
    static double t0_antes;
    if (r == r_antes && !g_sucio_pint && !g_ultimo_con_ui && !g_titulo) { ult_vblank = vb; g_alto_pres++; g_alto_rep++; return; }   /* nada nuevo */
    {   /* G1 (9 oct): este tic corre en el hilo del juego; si la swap chain todavia no acepta otra imagen (D3D12: objeto
           de latencia), NO esperar: probar en el proximo tic (2 ms). Antes la espera (~4 ms por refresco en el titulo)
           dejaba al juego casi parado = imagen congelada. SM3DL_PRES_BLOQUEAR=1 = lo de antes (comparar/sabotaje). */
        static int bloquear = -1;
        static unsigned no_listo;
        if (bloquear < 0) { const char *e = getenv("SM3DL_PRES_BLOQUEAR"); bloquear = e && *e == '1'; }
        RECT cr;
        GetClientRect(g_v, &cr);
        if (!bloquear && !raster_pres_listo(cr.right, cr.bottom)) {
            if (++no_listo % 2000 == 0) fprintf(stderr, "[alto-pres] %u tics sin presentar: la swap chain aun no aceptaba imagen\n", no_listo);
            return;
        }
    }
    ult_vblank = vb;
    g_alto_pres++;
    r_antes = r;
    (void)t0_antes;
    gpu_pintar_ranura(r);
    if (g_alto_pres % 1440 == 0)
        fprintf(stderr, "[alto-pres] %u refrescos (%.0f Hz): %u con imagen repetida (%.1f %%)\n", g_alto_pres, gpu_hz(), g_alto_rep,
                100.0 * g_alto_rep / g_alto_pres);
}

/* ---- K1 (10 oct, paso 7 D3D12): HILO DE PRESENTACION del modo Monitor (SM3DL_PRES_HILO=1, solo --d3d12; apagado =
   nada de esto corre). El hilo (raster_d3d12_hilo.inc) espera el objeto de latencia, elige la ranura del refresco
   (hp_elegir: gsp_interp_alto_ranura bajo g_hp_cs, el mismo candado que toma alto_cerrar SOLO para leer/publicar el
   tramo) y presenta. Este hilo (el del juego) ya no presenta: en su tic de 2 ms solo compone el HUD y la interfaz en la
   CPU, como siempre, y publica las zonas que cambiaron (raster_hp_capa). Menu, 1x (sin capa de HUD) o cualquier
   gpu_pintar del camino de siempre (WM_PAINT, menu) -> raster_hp_soltar() y vuelve lo de antes. */
#ifdef SM3DL_CON_D3D12
int raster_hp_disponible(void);
int raster_hp_activo(void);
int raster_hp_parado_solo(void);
int raster_hp_tomar(int w, int h, int vsync, int (*elegir)(void));
void raster_hp_soltar(void);
void raster_hp_capa(int c, const uint8_t *bgra, int w, int h, int x0, int y0, int x1, int y1);
void raster_hp_marco(int bx0, int by0, int bx1, int by1, int lineal, int hud_vis, int hx0, int hy0, int hx1, int hy1,
                     int ui_vis, int ux0, int uy0, int ux1, int uy1);
static CRITICAL_SECTION g_hp_cs;
static int g_hp_ya, g_hp_ui_vis;
static int hp_pedido(void)
{
    if (g_hp_pedido < 0) {
        const char *e = getenv("SM3DL_PRES_HILO");
        g_hp_pedido = e && *e == '1';
        if (g_hp_pedido) InitializeCriticalSection(&g_hp_cs);
    }
    return g_hp_pedido;
}
static void hp_bloquear(int on) { if (on) EnterCriticalSection(&g_hp_cs); else LeaveCriticalSection(&g_hp_cs); }
static int hp_elegir(void)
{
    extern double gsp_interp_alto_adelanto;
    EnterCriticalSection(&g_hp_cs);
    double fase, per;
    gpu_vb(&fase, &per);
    gsp_interp_alto_adelanto = per > 1.0 ? 0.5 * per : 0;   /* el refresco cuyo borde esta mas cerca (ver gsp_interp.inc) */
    if (per > 1.0) {   /* diagnostico: en que parte del refresco (rejilla DWM) suelta el objeto de latencia */
        static unsigned hist[10], n;
        LARGE_INTEGER q, f;
        QueryPerformanceCounter(&q);
        QueryPerformanceFrequency(&f);
        double x = ((double)q.QuadPart * 1000.0 / (double)f.QuadPart - fase) / per;
        int b = (int)((x - floor(x)) * 10.0);
        hist[b < 0 ? 0 : b > 9 ? 9 : b]++;
        if (++n % 1440 == 0) {
            fprintf(stderr, "[pres-hilo-fase] %u: fraccion del refresco al elegir (decimos 0-9): %u %u %u %u %u %u %u %u %u %u\n", n,
                    hist[0], hist[1], hist[2], hist[3], hist[4], hist[5], hist[6], hist[7], hist[8], hist[9]);
            memset(hist, 0, sizeof hist);
        }
    }
    int r = gsp_interp_alto_ranura();
    gsp_interp_alto_adelanto = 0;
    LeaveCriticalSection(&g_hp_cs);
    return r;
}
/* las capas del camino que retoma (hilo o el de siempre) estan viejas: la proxima subida va ENTERA */
static void hp_forzar_capas(void)
{
    g_hud_subido_w = g_hud_subido_h = 0;
    if (g_ui_cw > 0) SetRect(&g_ui_previo, 0, 0, g_ui_cw, g_ui_ch);
    g_hp_ya = 1;
}
static void hp_soltar_si(void)
{
    if (g_hp_pedido > 0 && (raster_hp_activo() || raster_hp_parado_solo())) { raster_hp_soltar(); hp_forzar_capas(); }
}
/* lo de gpu_pintar_ranura que es CPU (HUD sobre transparente + interfaz), publicado en vez de subido */
static void hp_componer(int w, int h)
{
    int ui = g_titulo || g_ultimo_con_ui || opacidad_tuerca();
    int algo = g_hp_ya || g_sucio_pint || g_hud_sucio.right > g_hud_sucio.left || ui;
    if (!algo) return;
    static long long ult;
    LARGE_INTEGER q, f;
    QueryPerformanceCounter(&q);
    QueryPerformanceFrequency(&f);
    if (!g_hp_ya && (q.QuadPart - ult) * 1000 < 4 * f.QuadPart) return;   /* tope ~250 composiciones/s */
    ult = q.QuadPart;
    g_hp_ya = 0;
    int dx, dy, dw, dh;
    destino(w, h, &dx, &dy, &dw, &dh);
    RECT r = g_hud_previo;
    rect_unir(&r, &g_hud_sucio);
    if (g_hud_subido_w != g_u_w || g_hud_subido_h != g_u_h) { SetRect(&r, 0, 0, g_u_w, g_u_h); g_hud_subido_w = g_u_w; g_hud_subido_h = g_u_h; }
    if (r.right > r.left) raster_hp_capa(0, g_unica_bgra, g_u_w, g_u_h, r.left, r.top, r.right, r.bottom);
    g_hud_previo = g_hud_sucio;
    SetRectEmpty(&g_hud_sucio);
    g_hud_base_sucia = 0;
    if (ui || g_ui_previo.right > g_ui_previo.left) {   /* interfaz: igual que gpu_pintar_ranura (sin menu: el menu suelta el hilo) */
        if (!g_ui_capa || g_ui_cw != w || g_ui_ch != h) {
            free(g_ui_capa);
            g_ui_capa = calloc((size_t)w * h, 4);
            g_ui_cw = w; g_ui_ch = h;
            SetRect(&g_ui_previo, 0, 0, w, h);
            if (!g_ui_capa) { g_ui_cw = g_ui_ch = 0; return; }
        } else {
            for (int y = g_ui_previo.top; y < g_ui_previo.bottom; y++)
                memset(g_ui_capa + ((size_t)y * w + g_ui_previo.left) * 4, 0, (size_t)(g_ui_previo.right - g_ui_previo.left) * 4);
        }
        SetRectEmpty(&g_ui_sucio);
        ui_px = g_ui_capa;
        ui_w = w;
        ui_h = h;
        g_ui_seguir = 1;
        SetRect(&g_rect_tuerca, 0, 0, 0, 0);
        g_ultimo_con_ui = 1;
        if (g_titulo) dibujar_titulo(dx, dy, dw, dh);
        else {
            int op = opacidad_tuerca();
            if (op) dibujar_tuerca(dx, dy, dw, dh, op);
            else g_ultimo_con_ui = 0;
        }
        g_ui_seguir = 0;
        RECT u = g_ui_previo;
        rect_unir(&u, &g_ui_sucio);
        if (u.right > u.left) raster_hp_capa(1, g_ui_capa, w, h, u.left, u.top, u.right, u.bottom);
        g_ui_previo = g_ui_sucio;
        g_hp_ui_vis = g_ui_sucio.right > g_ui_sucio.left;
    }
    raster_hp_marco(dx, dy, dx + dw, dy + dh, aj.suave, g_hud_visible, dx, dy, dx + dw, dy + dh, g_hp_ui_vis, 0, 0, w, h);
    g_sucio_pint = 0;
}
/* tic del juego: 1 = el hilo presenta (no hacer nada mas aqui) */
static int hp_tic(void)
{
    if (!hp_pedido() || !raster_hp_disponible()) return 0;
    int quiere = g_alto_on && g_gpu == 1 && aj.unica && !g_menu && g_v && g_capa_hud;
    if (!quiere || raster_hp_parado_solo()) { hp_soltar_si(); return 0; }
    RECT cr;
    GetClientRect(g_v, &cr);
    if (!raster_hp_activo()) {
        if (hp_elegir() < 0) return 0;   /* todavia ningun tramo: el camino de siempre */
        hp_forzar_capas();
        if (!raster_hp_tomar(cr.right, cr.bottom, aj.vsync ? 1 : 0, hp_elegir)) return 0;
    }
    hp_componer(cr.right, cr.bottom);
    {   /* lo grabado por el juego a la GPU de a poco (ver raster_hp_vaciar), como maximo cada 1,5 ms */
        void raster_hp_vaciar(void);
        static long long ult;
        LARGE_INTEGER q, f;
        QueryPerformanceCounter(&q);
        QueryPerformanceFrequency(&f);
        if ((q.QuadPart - ult) * 2000 >= 3 * f.QuadPart) { ult = q.QuadPart; raster_hp_vaciar(); }
    }
    return 1;
}
#endif
