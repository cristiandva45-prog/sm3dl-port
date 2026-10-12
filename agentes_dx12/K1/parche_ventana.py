import os
p = r'C:\Users\usuario\Desktop\Decopilar\sm3dl-port\recomp\render\ventana_gpu.c'
s = open(p, encoding='utf-8').read()
def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a[:70], s.count(a))
    s = s.replace(a, b)
rep('''static double gpu_hz(void)
{
    static double hz;
    static ULONGLONG cuando;
''', '''static double gpu_hz(void)
{
    static double hz, forzado = -1;
    static ULONGLONG cuando;
    if (forzado < 0) {   /* K1 (10 oct), SOLO PRUEBAS: SM3DL_PRES_HZ=<hz> fuerza la rejilla de refrescos (con la ventana
                            oculta DWM dice 60 Hz: M1). No cambia el monitor ni la swap chain, solo la cuenta de t/refresco */
        const char *e = getenv("SM3DL_PRES_HZ");
        forzado = e ? atof(e) : 0;
        if (forzado < 30 || forzado > 500) forzado = 0;
        if (forzado) fprintf(stderr, "[ventana] SM3DL_PRES_HZ: rejilla de refrescos forzada a %.1f Hz (solo pruebas)\\n", forzado);
    }
    if (forzado) return forzado;
''')
rep('''static unsigned g_alto_pres, g_alto_rep;
void ventana_presentador(void);
''', '''static unsigned g_alto_pres, g_alto_rep;
void ventana_presentador(void);
#ifdef SM3DL_CON_D3D12
static int hp_tic(void);
static void hp_soltar_si(void);
static int hp_pedido(void);
static void hp_bloquear(int on);
void raster_hp_publicar(int juego);
static int g_hp_pedido = -1;
#endif
''')
rep('''    { extern void (*gsp_interp_vb)(double *, double *); gsp_interp_vb = gpu_vb; }
}''', '''    { extern void (*gsp_interp_vb)(double *, double *); gsp_interp_vb = gpu_vb; }
#ifdef SM3DL_CON_D3D12
    {   /* K1: candado del tramo + publicar las ranuras (solo con SM3DL_PRES_HILO=1) */
        extern void (*gsp_interp_hp_bloquear)(int);
        extern void (*gsp_interp_hp_publicar)(int);
        if (hp_pedido()) { gsp_interp_hp_bloquear = hp_bloquear; gsp_interp_hp_publicar = raster_hp_publicar; }
    }
#endif
}''')
rep('''    if (w <= 0 || h <= 0) return;
    int dx, dy, dw, dh;
    destino(w, h, &dx, &dy, &dw, &dh);
    LARGE_INTEGER g1_q0''', '''    if (w <= 0 || h <= 0) return;
#ifdef SM3DL_CON_D3D12
    hp_soltar_si();   /* K1: el camino de siempre vuelve a ser el dueno de la swap chain */
#endif
    int dx, dy, dw, dh;
    destino(w, h, &dx, &dy, &dw, &dh);
    LARGE_INTEGER g1_q0''')
rep('''void ventana_presentador(void)
{
    if (!g_alto_on''', '''void ventana_presentador(void)
{
#ifdef SM3DL_CON_D3D12
    if (g_hp_pedido != 0 && hp_tic()) return;   /* K1: presenta el hilo */
#endif
    if (!g_alto_on''')
s += r'''
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
    EnterCriticalSection(&g_hp_cs);
    int r = gsp_interp_alto_ranura();
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
    return 1;
}
#endif
'''
open(p + '.tmp', 'w', encoding='utf-8', newline='\n').write(s)
os.replace(p + '.tmp', p)
print('ok')
