/* Ventana del port (9 oct; menu, pantalla unica, inicio y ajustes 7 oct). La imagen del juego se estira con
 * StretchDIBits a un bufer DIB en memoria; la interfaz (ventana_ui.c) se dibuja POR SOFTWARE encima, con bordes
 * suaves y transparencia; luego BitBlt (sin parpadeo). Aparte del contexto GL oculto del rasterizador. Se crea en la
 * primera presentacion y los mensajes se bombean en cada presentacion (mismo hilo del SO que el juego).
 *
 *   - Pantalla UNICA (la de arriba con el HUD de la de abajo integrado: ventana_hud.c) o DOBLE (como la 3DS).
 *   - TITULO: en vez del "Press A to Start!" de la pantalla de abajo (oculta en modo unico) sale "PULSA CUALQUIER
 *     TECLA" sobre el logo; cualquier tecla, clic o boton = A.
 *   - AJUSTES: clic en la TUERCA (siempre en el titulo; en el juego aparece al mover el mouse y se desvanece) o Esc.
 *     Esc los cierra. PAUSA el juego (se queda dentro de ventana_presentar bombeando mensajes). Pantalla completa
 *     (tambien Alt+Enter), tamano, pantallas, filtro, sincronizacion vertical (DwmFlush), limite de FPS (60/30).
 *     Se guardan en sm3dl_ajustes.ini (carpeta actual). SM3DL_ESCALA=N (1-4) manda sobre el .ini. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xinput.h>
#include <dwmapi.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gsp.h"
#include "ventana.h"

#define LIENZO_W 400
#define LIENZO_H 480
#define ARRIBA_H 240

/* pantalla de abajo (coordenadas 320x240) medidas en capturas del juego */
#define ITEM_CX 160
#define ITEM_CY 127
#define ITEM_R 74
#define BARRA_H 40

static HWND g_v;
static int g_fallo;
static struct { int unica, escala, completa, suave, vsync, fps30, resol, aniso, texhd; } aj = { 0, 2, 0, 0, 0, 0, 1, 8, 1 };
static int aj_presentar_gpu;   /* presentar=gpu en el .ini (ventana_gpu.c) */
static int aj_fps_alto;        /* fps=monitor: tantos cuadros como refresque el monitor (ventana_gpu.c) */
static int g_alto_on;          /* definido en ventana_gpu.c */
static int g_gpu;              /* definido en ventana_gpu.c (-1/0/1) */
static void gpu_pintar(void);
static void gpu_alto_enganchar(void);
static int g_menu, g_sel, g_titulo;
static ULONGLONG g_pulsar_a_hasta;   /* "cualquier tecla" en el titulo = A hasta este instante */
static ULONGLONG g_mouse_visto;      /* ultimo movimiento del mouse: la tuerca aparece y se desvanece */
static uint8_t g_bgra[LIENZO_W * LIENZO_H * 4];         /* las dos pantallas tal cual (DOBLE) */
/* resolucion interna hasta 4x: la de arriba puede llegar en alta (raster_alta) */
#define ALTA_PX (LIENZO_W * 4 * ARRIBA_H * 4)
static uint8_t g_alta_bgra[ALTA_PX * 4];                /* la de arriba en alta, si la hay (g_alta_s > 1) */
static int g_alta_s;
static uint8_t g_unica_bgra[ALTA_PX * 4];               /* la de arriba + lo integrado (UNICA): g_u_w x g_u_h */
static int g_u_w = LIENZO_W, g_u_h = ARRIBA_H, g_u_s = 1;
static uint8_t g_oscuro[ALTA_PX * 4];                   /* fondo oscurecido mientras el menu esta abierto */
int raster_alta(unsigned dir_fisica, unsigned fmt, unsigned stride, unsigned ancho, unsigned alto, const unsigned char **rgba);
void raster_escala(int s);
extern int interp_vivo;   /* interp.c: cuadros intermedios (60 FPS) */
/* T7 (9 oct): texturas. raster_aniso_fijar la define T1 (raster_backend_gl.c); texhd_fijar es de texturas_hd.c. Los
   respaldos 'weak' solo existen para que enlace antes de integrar: el real (fuerte) los reemplaza. */
void raster_aniso_fijar(int n);
void texhd_fijar(int encendido);
void raster_tex_hd_recargar(void);   /* PEDIDO T2: tirar la cache de texturas para re-subirlas (HD <-> original) */
__attribute__((weak)) void raster_aniso_fijar(int n) { (void)n; }
__attribute__((weak)) void raster_tex_hd_recargar(void) { }
static const int ANISO_NIVELES[5] = { 1, 2, 4, 8, 16 };
static HDC g_mem;
static HBITMAP g_bmp;
static uint8_t *g_px;
static int g_mem_w, g_mem_h;
static volatile int g_toque_mouse;
static float g_toque_x, g_toque_y;
static RECT g_rect_tuerca;
static WINDOWPLACEMENT g_lugar = { sizeof(WINDOWPLACEMENT) };
static const DWORD ESTILO_VENTANA = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;

static int alto_lienzo(void) { return aj.unica ? ARRIBA_H : LIENZO_H; }

/* SM3DL_VENTANA_CRONO=1 (7 oct, agente B): cronometros de la presentacion. Cada 600 cuadros (pantalla de abajo)
   imprime ms por cuadro de cada parte: [ventana-crono] */
enum { CR_CONV, CR_ALTA, CR_COPIA_ALTA, CR_TITULO, CR_UNICA, CR_OSCURO, CR_STRETCH, CR_UI, CR_BITBLT, CR_DWM,
       CR_BOMBEAR, CR_TOTAL, CR_N };
static const char *CR_NOMBRE[CR_N] = { "conv", "raster_alta", "copia_alta", "titulo", "unica", "oscuro", "stretch",
                                        "ui", "bitblt", "dwmflush", "bombear", "TOTAL" };
static double g_cr[CR_N];
static unsigned g_cr_pint, g_cr_salt, g_cr_cambio[3];   /* cambios: arriba nativa, abajo, alta */
static int g_cr_on = -1;
static double cr_ahora(void)
{
    static LARGE_INTEGER f;
    LARGE_INTEGER c;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}
/* SM3DL_VENTANA_SALTAR (7 oct, B; por defecto 1): no recomponer ni repintar si el juego no produjo una imagen nueva
   (el juego hace 1 cuadro cada 2 vblanks), el oscurecido del menu una sola vez y la resolucion interna al CERRAR el
   menu. =0: camino viejo. SM3DL_VENTANA_VERIFICAR=1: en cada vblank saltado compone tambien por el camino viejo y
   compara bytes ([ventana-verif]); =2 sabotea la deteccion (ignora los cambios de la pantalla de abajo). */
static int g_saltar = -1, g_verif;
static int g_sucio_comp = 1, g_sucio_pint = 1;   /* la imagen cambio desde la ultima composicion / el ultimo pintado */
static int g_ultimo_con_ui = 1;                   /* el ultimo pintado llevaba interfaz animada (titulo/tuerca) */
static int g_oscuro_listo, g_resol_pend;
static unsigned g_vf_n, g_vf_mal;
static uint8_t *g_vf_copia;
#define CR_INI(v) double v = g_cr_on > 0 ? cr_ahora() : 0
#define CR_FIN(i, v) do { if (g_cr_on > 0) g_cr[i] += cr_ahora() - (v); } while (0)
static void cr_reportar(void)
{
    static unsigned n;
    if (g_cr_on <= 0 || ++n % 600) return;
    char l[600];
    int k = snprintf(l, sizeof l, "[ventana-crono] cuadros=%u pintados=%u saltados=%u cambios(arriba,abajo,alta)=%u,%u,%u ms/cuadro:", n, g_cr_pint,
                     g_cr_salt, g_cr_cambio[0], g_cr_cambio[1], g_cr_cambio[2]);
    for (int i = 0; i < CR_N && k < (int)sizeof l - 40; i++)
        k += snprintf(l + k, sizeof l - k, " %s=%.2f", CR_NOMBRE[i], g_cr[i] * 1000.0 / 600);
    fprintf(stderr, "%s\n", l);
    memset(g_cr, 0, sizeof g_cr);
    g_cr_pint = g_cr_salt = 0;
    memset(g_cr_cambio, 0, sizeof g_cr_cambio);
}

#include "ventana_hud.c"
#include "ventana_ui.c"

/* ------------------------------------------------------------------ ajustes en disco */
#define AJUSTES "sm3dl_ajustes.ini"
static void guardar_ajustes(void)
{
    FILE *f = fopen(AJUSTES, "w");
    if (!f) return;
    fprintf(f, "# ajustes del port (tuerca o Esc)\npantalla=%s\nescala=%d\ncompleta=%d\nfiltro=%s\nvsync=%d\nfps=%d\nresolucion=%d\naniso=%d\ntexturas_hd=%d\n",
            aj.unica ? "unica" : "doble", aj.escala, aj.completa, aj.suave ? "suave" : "nitido", aj.vsync,
            aj_fps_alto ? 0 : aj.fps30 ? 30 : 60, aj.resol, aj.aniso, aj.texhd);
    if (aj_presentar_gpu) fprintf(f, "presentar=gpu\n");
    fclose(f);
}

static void cargar_ajustes(void)
{
    FILE *f = fopen(AJUSTES, "r");
    if (!f) return;
    char l[128];
    while (fgets(l, sizeof l, f)) {
        if (!strncmp(l, "pantalla=", 9)) aj.unica = !strncmp(l + 9, "unica", 5);
        else if (!strncmp(l, "escala=", 7) && atoi(l + 7) >= 1 && atoi(l + 7) <= 4) aj.escala = atoi(l + 7);
        else if (!strncmp(l, "completa=", 9)) aj.completa = atoi(l + 9) != 0;
        else if (!strncmp(l, "filtro=", 7)) aj.suave = !strncmp(l + 7, "suave", 5);
        else if (!strncmp(l, "vsync=", 6)) aj.vsync = atoi(l + 6) != 0;
        else if (!strncmp(l, "fps=", 4)) { aj.fps30 = atoi(l + 4) == 30; aj_fps_alto = !strncmp(l + 4, "monitor", 7) || atoi(l + 4) == 0; }
        else if (!strncmp(l, "resolucion=", 11) && atoi(l + 11) >= 1 && atoi(l + 11) <= 8) aj.resol = atoi(l + 11);
        else if (!strncmp(l, "aniso=", 6)) { int n = atoi(l + 6); if (n == 1 || n == 2 || n == 4 || n == 8 || n == 16) aj.aniso = n; }
        else if (!strncmp(l, "texturas_hd=", 12)) aj.texhd = atoi(l + 12) != 0;
        else if (!strncmp(l, "presentar=", 10)) aj_presentar_gpu = !strncmp(l + 10, "gpu", 3);
    }
    fclose(f);
}

/* ------------------------------------------------------------------ pantalla de titulo */
/* la de abajo del titulo: ~89 % blanca con "Press A to Start!" naranja en las filas 108-133 (capturas reales) */
static int titulo_en_pantalla(void)
{
    int blancos = 0, n = 0, naranja = 0;
    for (int y = 0; y < 240; y += 4)
        for (int x = 0; x < 320; x += 4) {
            const uint8_t *s = px_abajo(x, y);   /* BGRA */
            blancos += s[0] > 225 && s[1] > 225 && s[2] > 225;
            n++;
        }
    if (blancos * 10 < n * 8) return 0;
    for (int y = 104; y <= 136; y += 2)
        for (int x = 0; x < 320; x += 2) {
            const uint8_t *s = px_abajo(x, y);
            naranja += s[2] > 200 && s[1] > 60 && s[1] < 190 && s[0] < 80;
        }
    return naranja >= 30;
}

/* rectangulo de la imagen del juego dentro de la ventana (bandas negras en pantalla completa) */
static void destino(int w, int h, int *dx, int *dy, int *dw, int *dh)
{
    int al = alto_lienzo();
    if ((long long)w * al > (long long)h * LIENZO_W) { *dh = h; *dw = h * LIENZO_W / al; }
    else { *dw = w; *dh = w * al / LIENZO_W; }
    *dx = (w - *dw) / 2;
    *dy = (h - *dh) / 2;
}

/* estilos (colores del juego: amarillo -> naranja de "COURSE CLEAR!", contorno casi negro calido) */
static const UiEstilo E_TITULO = { 0xFFF04A, 0xFF8A0C, 0x1A0E04, 0, 0, 256 };
static const UiEstilo E_BLANCO = { 0xFFFFFF, 0xE8ECF4, 0x10141E, 0, 0, 256 };
static const UiEstilo E_VALOR = { 0xFFE680, 0xFFC23A, 0x10141E, 0, 0, 256 };
static const UiEstilo E_GRIS = { 0x8A8C99, 0x7A7C88, 0x10141E, 0, 0, 256 };
static UiEstilo con(UiEstilo e, float grosor, float sombra, int op) { e.grosor = grosor; e.sombra = sombra; e.opacidad = op; return e; }

/* ------------------------------------------------------------------ menu de ajustes */
enum { F_SECCION, F_OPCION, F_FIJA };
enum { OP_MODO, OP_TAMANO, OP_PANTALLAS, OP_RESOL, OP_ANISO, OP_TEXHD, OP_FILTRO, OP_VSYNC, OP_FPS, OP_VOLVER, OP_N };
static const struct { int tipo, op; const wchar_t *nombre; } FILAS[] = {
    { F_SECCION, -1, L"PANTALLA" },
    { F_OPCION, OP_MODO, L"Modo" },
    { F_OPCION, OP_TAMANO, L"Tamaño de ventana" },
    { F_OPCION, OP_PANTALLAS, L"Pantallas" },
    { F_SECCION, -1, L"GRÁFICOS" },
    { F_OPCION, OP_RESOL, L"Resolución interna" },
    { F_OPCION, OP_ANISO, L"Filtro anisotrópico" },
    { F_OPCION, OP_TEXHD, L"Texturas HD" },
    { F_OPCION, OP_FILTRO, L"Filtro de imagen" },
    { F_OPCION, OP_VSYNC, L"Sincronización vertical" },
    { F_OPCION, OP_FPS, L"Cuadros por segundo" },
    { F_SECCION, -1, L"" },
    { F_OPCION, OP_VOLVER, L"Volver al juego" },
};
#define N_FILAS ((int)(sizeof FILAS / sizeof FILAS[0]))
static const wchar_t *CONTROLES[][2] = {
    { L"Mover", L"W A S D" }, { L"Saltar", L"Espacio" }, { L"Correr / fuego", L"Shift" },
    { L"Agacharse", L"Ctrl · C · Q" }, { L"Usar el ítem", L"E" }, { L"Cámara", L"Flechas" },
    { L"Pausa", L"Enter" }, { L"Ajustes", L"Esc" }, { L"Pantalla completa", L"Alt + Enter" },
};
static RECT g_rect_fila[N_FILAS];

static int fila_activa(int k) { return FILAS[k].tipo == F_OPCION && !(FILAS[k].op == OP_TAMANO && aj.completa); }

static void valor_fila(int op, wchar_t *t, size_t n)
{
    switch (op) {
    case OP_MODO: _snwprintf(t, n, L"%ls", aj.completa ? L"Pantalla completa" : L"Ventana"); break;
    case OP_TAMANO: _snwprintf(t, n, aj.completa ? L"—" : L"%dx", aj.escala); break;
    case OP_PANTALLAS: _snwprintf(t, n, L"%ls", aj.unica ? L"Única (integrada)" : L"Doble (como la 3DS)"); break;
    case OP_RESOL: _snwprintf(t, n, aj.resol == 1 ? L"1x (nativa)" : L"%dx  (%dx%d)", aj.resol, 400 * aj.resol, 240 * aj.resol); break;
    case OP_ANISO: _snwprintf(t, n, aj.aniso == 1 ? L"No" : L"%dx", aj.aniso); break;
    case OP_TEXHD: _snwprintf(t, n, L"%ls", aj.texhd ? L"Sí" : L"No"); break;
    case OP_FILTRO: _snwprintf(t, n, L"%ls", aj.suave ? L"Suave" : L"Nítido"); break;
    case OP_VSYNC: _snwprintf(t, n, L"%ls", aj.vsync ? L"Sí" : L"No"); break;
    case OP_FPS: _snwprintf(t, n, L"%ls", aj_fps_alto ? L"Monitor (interpolados)" : aj.fps30 ? L"30 (original)" : L"60 (interpolados)"); break;
    default: t[0] = 0; break;
    }
}

static void primera_activa(int dir)
{
    for (int k = 0; k < N_FILAS; k++) {
        if (fila_activa(g_sel)) return;
        g_sel = (g_sel + dir + N_FILAS) % N_FILAS;
    }
}

static void dibujar_menu(int dx, int dy, int dw, int dh)
{
    float u = dw / 400.0f;   /* unidad: un pixel de la pantalla de arriba */
    if (!aj.unica) dh /= 2;  /* en modo doble el panel va sobre la de arriba */
    int pw = (int)(376 * u), ph = (int)(232 * u);
    if (ph > dh - (int)(6 * u)) ph = dh - (int)(6 * u);
    int x0 = dx + (dw - pw) / 2, y0 = dy + (dh - ph) / 2;
    ui_panel(x0, y0, pw, ph, 12 * u, 0x141826, 236, 0xFFC400, 2.4f * u);
    UiEstilo et = con(E_TITULO, 2.2f * u, 1.6f * u, 256);
    ui_texto(UI_TITULO, (int)(22 * u), L"AJUSTES", x0 + (int)(13 * u), y0 + (int)(6 * u), -1, &et);
    UiEstilo ep = con(E_GRIS, 0, 0, 256);
    ui_texto(UI_CUERPO, (int)(8 * u), L"juego en pausa", x0 + pw - (int)(13 * u), y0 + (int)(13 * u), 1, &ep);
    /* columna izquierda: ajustes */
    int cx = x0 + (int)(13 * u), cw = (int)(222 * u), fy = y0 + (int)(34 * u), alto_fila = (int)(12 * u);
    UiEstilo es = con(E_TITULO, 1.0f * u, 0, 256);
    for (int k = 0; k < N_FILAS; k++) {
        SetRect(&g_rect_fila[k], 0, 0, 0, 0);
        if (FILAS[k].tipo == F_SECCION) {
            if (FILAS[k].nombre[0]) ui_texto(UI_TITULO, (int)(9.5f * u), FILAS[k].nombre, cx, fy + (int)(1 * u), -1, &es);
            fy += FILAS[k].nombre[0] ? (int)(13 * u) : (int)(5 * u);
            continue;
        }
        RECT fr = { cx - (int)(5 * u), fy, cx + cw, fy + alto_fila };
        g_rect_fila[k] = fr;
        int activa = fila_activa(k), sel = k == g_sel && activa;
        if (sel) ui_panel(fr.left, fr.top, fr.right - fr.left, fr.bottom - fr.top, 6 * u, 0x5A4A10, 230, 0xFFC400, 1.2f * u);
        UiEstilo en = con(!activa ? E_GRIS : E_BLANCO, sel ? 1.1f * u : 0, 0, 256);
        int ty = fy + (int)(1.2f * u);
        ui_texto(UI_CUERPO, (int)(9.5f * u), FILAS[k].nombre, cx + (int)(2 * u), ty, -1, &en);
        wchar_t v[64], vv[80];
        valor_fila(FILAS[k].op, v, 64);
        if (v[0]) {
            if (sel) _snwprintf(vv, 80, L"‹  %ls  ›", v);
            else _snwprintf(vv, 80, L"%ls", v);
            UiEstilo ev = con(!activa ? E_GRIS : E_VALOR, sel ? 1.1f * u : 0, 0, 256);
            ui_texto(UI_CUERPO, (int)(9.5f * u), vv, cx + cw - (int)(7 * u), ty, 1, &ev);
        }
        fy += alto_fila + (int)(1 * u);
    }
    /* columna derecha: controles (referencia) */
    int rx = x0 + (int)(248 * u), ry = y0 + (int)(34 * u);
    ui_panel(rx - (int)(9 * u), ry, (int)(1 * u) + 1, ph - (int)(62 * u), 0, 0x34384A, 256, 0, 0);
    ui_texto(UI_TITULO, (int)(9.5f * u), L"CONTROLES", rx, ry + (int)(1 * u), -1, &es);
    ry += (int)(14 * u);
    UiEstilo ec = con(E_GRIS, 0, 0, 256), ek = con(E_BLANCO, 0, 0, 256);
    ec.arriba = ec.abajo = 0xB8BACB;
    for (size_t k = 0; k < sizeof CONTROLES / sizeof CONTROLES[0]; k++) {
        ui_texto(UI_CUERPO, (int)(8.5f * u), CONTROLES[k][0], rx, ry, -1, &ec);
        ui_texto(UI_CUERPO, (int)(8.5f * u), CONTROLES[k][1], x0 + pw - (int)(13 * u), ry, 1, &ek);
        ry += (int)(12 * u);
    }
    ui_texto(UI_CUERPO, (int)(8 * u), L"Mando: como la 3DS", rx, ry + (int)(4 * u), -1, &ep);
    /* pie */
    ui_texto(UI_CUERPO, (int)(8 * u), L"↑↓ elegir     ←→ / Enter cambiar     Esc volver al juego",
             x0 + pw / 2, y0 + ph - (int)(15 * u), 0, &ep);
}

/* tuerca de ajustes (clic = abrir). opacidad 0..256 */
static void dibujar_tuerca(int dx, int dy, int dw, int dh, int op)
{
    float u = dw / 400.0f;
    (void)dh;
    int t = (int)(19 * u), x = dx + dw - (int)(9 * u), y = dy + (int)(5 * u);
    UiEstilo eg = con(E_TITULO, 1.8f * u, 1.4f * u, op);
    int w = ui_texto(UI_SIMBOLO, t, L"⚙", x, y, 1, &eg);
    SetRect(&g_rect_tuerca, x - w - (int)(6 * u), y - (int)(4 * u), x + (int)(6 * u), y + t + (int)(6 * u));
}

static void dibujar_titulo(int dx, int dy, int dw, int dh)
{
    float u = dw / 400.0f;
    int alto_arriba = aj.unica ? dh : dh / 2;
    double t = (double)GetTickCount64() / 1000.0;
    int op = 150 + (int)(106 * (0.5 + 0.5 * sin(t * 3.2)));   /* late suave */
    UiEstilo e = con(E_TITULO, 2.2f * u, 2.0f * u, op);
    /* el logo del titulo va al centro o abajo a la derecha (alterna): abajo a la izquierda no choca con ninguno */
    ui_texto(UI_TITULO, (int)(19 * u), L"PULSA CUALQUIER TECLA", dx + (int)(dw * 0.30f), dy + (int)(alto_arriba * 0.86f),
             0, &e);
    dibujar_tuerca(dx, dy, dw, dh, 256);
}

/* ------------------------------------------------------------------ ventana / pantalla completa */
static void ajustar_tamano(void)
{
    if (!g_v || aj.completa) return;
    RECT r = { 0, 0, LIENZO_W * aj.escala, alto_lienzo() * aj.escala };
    AdjustWindowRect(&r, ESTILO_VENTANA, FALSE);
    SetWindowPos(g_v, NULL, 0, 0, r.right - r.left, r.bottom - r.top, SWP_NOMOVE | SWP_NOZORDER);
}

static void aplicar_completa(void)
{
    if (!g_v) return;
    if (aj.completa) {
        GetWindowPlacement(g_v, &g_lugar);
        MONITORINFO mi = { sizeof mi };
        GetMonitorInfoW(MonitorFromWindow(g_v, MONITOR_DEFAULTTONEAREST), &mi);
        SetWindowLongW(g_v, GWL_STYLE, WS_POPUP | WS_VISIBLE);
        SetWindowPos(g_v, HWND_TOP, mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right - mi.rcMonitor.left,
                     mi.rcMonitor.bottom - mi.rcMonitor.top, SWP_FRAMECHANGED | SWP_SHOWWINDOW);
    } else {
        SetWindowLongW(g_v, GWL_STYLE, ESTILO_VENTANA | WS_VISIBLE);
        if (g_lugar.length) SetWindowPlacement(g_v, &g_lugar);
        SetWindowPos(g_v, NULL, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED);
        ajustar_tamano();
    }
}

static void cambiar(int op, int dir)
{
    switch (op) {
    case OP_MODO: aj.completa = !aj.completa; aplicar_completa(); break;
    case OP_TAMANO: aj.escala = (aj.escala - 1 + dir + 4) % 4 + 1; ajustar_tamano(); break;
    case OP_PANTALLAS: aj.unica = !aj.unica; if (aj.unica) componer_unica(); ajustar_tamano(); break;
    case OP_RESOL:   /* con SALTAR se aplica al cerrar el menu (raster_escala tarda; el juego esta en pausa igual) */
        aj.resol = (aj.resol - 1 + dir + 8) % 8 + 1;   /* 10 oct: hasta 8x (supersampling en 1080p) */
        if (g_saltar) g_resol_pend = 1; else raster_escala(aj.resol);
        break;
    case OP_ANISO: {
        int i = 0;
        while (i < 4 && ANISO_NIVELES[i] != aj.aniso) i++;
        aj.aniso = ANISO_NIVELES[(i + dir + 5) % 5];
        raster_aniso_fijar(aj.aniso);
        break; }
    case OP_TEXHD: aj.texhd = !aj.texhd; texhd_fijar(aj.texhd); raster_tex_hd_recargar(); break;
    case OP_FILTRO: aj.suave = !aj.suave; break;
    case OP_VSYNC: aj.vsync = !aj.vsync; break;
    case OP_FPS:   /* 30 -> 60 -> monitor -> 30; monitor presenta por la GPU */
        if (aj.fps30) { aj.fps30 = 0; aj_fps_alto = 0; }
        else if (!aj_fps_alto) { aj_fps_alto = 1; aj_presentar_gpu = 1; if (g_gpu == 0) g_gpu = -1; }
        else { aj_fps_alto = 0; aj.fps30 = 1; }
        interp_vivo = !aj.fps30;
        g_alto_on = aj_fps_alto && interp_vivo;
        break;
    case OP_VOLVER: g_menu = 0; return;
    default: return;
    }
    g_oscuro_listo = 0;
    g_sucio_comp = g_sucio_pint = 1;
    guardar_ajustes();
}

static void abrir_menu(void) { g_menu = 1; g_sel = 1; g_oscuro_listo = 0; primera_activa(1); InvalidateRect(g_v, NULL, FALSE); }

static void menu_tecla(WPARAM vk)
{
    if (vk == VK_UP || vk == 'W') { g_sel = (g_sel + N_FILAS - 1) % N_FILAS; primera_activa(-1); }
    else if (vk == VK_DOWN || vk == 'S') { g_sel = (g_sel + 1) % N_FILAS; primera_activa(1); }
    else if (vk == VK_ESCAPE) g_menu = 0;
    else if (vk == VK_LEFT || vk == 'A') cambiar(FILAS[g_sel].op, -1);
    else if (vk == VK_RIGHT || vk == 'D' || vk == VK_RETURN || vk == VK_SPACE) cambiar(FILAS[g_sel].op, 1);
    InvalidateRect(g_v, NULL, FALSE);
}

/* mando en el menu (sondeo con flanco): cruceta/stick navegan, A acepta, B o START cierran */
static void menu_mando(void)
{
    static WORD antes;
    XINPUT_STATE xs;
    if (XInputGetState(0, &xs) != ERROR_SUCCESS) return;
    WORD b = xs.Gamepad.wButtons;
    if (xs.Gamepad.sThumbLY > 20000) b |= XINPUT_GAMEPAD_DPAD_UP;
    if (xs.Gamepad.sThumbLY < -20000) b |= XINPUT_GAMEPAD_DPAD_DOWN;
    if (xs.Gamepad.sThumbLX > 20000) b |= XINPUT_GAMEPAD_DPAD_RIGHT;
    if (xs.Gamepad.sThumbLX < -20000) b |= XINPUT_GAMEPAD_DPAD_LEFT;
    WORD nuevo = b & ~antes;
    antes = b;
    if (nuevo & XINPUT_GAMEPAD_DPAD_UP) menu_tecla(VK_UP);
    if (nuevo & XINPUT_GAMEPAD_DPAD_DOWN) menu_tecla(VK_DOWN);
    if (nuevo & XINPUT_GAMEPAD_DPAD_LEFT) menu_tecla(VK_LEFT);
    if (nuevo & (XINPUT_GAMEPAD_DPAD_RIGHT | XINPUT_GAMEPAD_A)) menu_tecla(VK_RIGHT);
    if (nuevo & (XINPUT_GAMEPAD_B | XINPUT_GAMEPAD_START | XINPUT_GAMEPAD_BACK)) menu_tecla(VK_ESCAPE);
}

/* opacidad de la tuerca en el juego: visible 2 s tras mover el mouse, luego se desvanece en 0,6 s */
static int opacidad_tuerca(void)
{
    ULONGLONG t = GetTickCount64() - g_mouse_visto;
    if (!g_mouse_visto || t > 2600) return 0;
    return t < 2000 ? 256 : (int)(256 * (2600 - t) / 600);
}

/* ------------------------------------------------------------------ pintar */
static void foto_ventana(int w, int h);

static void pintar(HDC dc)
{
    RECT cr;
    GetClientRect(g_v, &cr);
    int w = cr.right, h = cr.bottom;
    if (w <= 0 || h <= 0) return;
    if (!g_mem || w != g_mem_w || h != g_mem_h) {
        if (g_mem) { DeleteObject(g_bmp); DeleteDC(g_mem); }
        g_mem = CreateCompatibleDC(dc);
        BITMAPINFO bd;
        memset(&bd, 0, sizeof bd);
        bd.bmiHeader.biSize = sizeof bd.bmiHeader;
        bd.bmiHeader.biWidth = w;
        bd.bmiHeader.biHeight = -h;   /* de arriba a abajo: g_px[y*w+x] */
        bd.bmiHeader.biPlanes = 1;
        bd.bmiHeader.biBitCount = 32;
        g_bmp = CreateDIBSection(dc, &bd, DIB_RGB_COLORS, (void **)&g_px, NULL, 0);
        SelectObject(g_mem, g_bmp);
        g_mem_w = w;
        g_mem_h = h;
    }
    int dx, dy, dw, dh;
    destino(w, h, &dx, &dy, &dw, &dh);
    if (dw != w || dh != h) { RECT t = { 0, 0, w, h }; FillRect(g_mem, &t, (HBRUSH)GetStockObject(BLACK_BRUSH)); }
    /* fuente: UNICA = g_unica_bgra (g_u_w x g_u_h, en alta si la hay); DOBLE = g_bgra (nativa), y si la de arriba
       llego en alta se pinta aparte encima de su mitad */
    const uint8_t *src = aj.unica ? g_unica_bgra : g_bgra;
    int sw = aj.unica ? g_u_w : LIENZO_W, sh = aj.unica ? g_u_h : LIENZO_H;
    int arriba_alta = !aj.unica && g_alta_s > 1;
    CR_INI(t_osc);
    if (g_menu) {   /* el juego queda de fondo, oscurecido (el juego esta en pausa: con SALTAR se calcula una vez) */
        static uint8_t abajo[LIENZO_W * LIENZO_H * 4];
        if (!g_saltar || !g_oscuro_listo) {
            const uint8_t *o = arriba_alta ? g_alta_bgra : src;
            size_t n = arriba_alta ? (size_t)400 * g_alta_s * 240 * g_alta_s : (size_t)sw * sh;
            for (size_t k = 0; k < n * 4; k++) g_oscuro[k] = (uint8_t)((o[k] * 95) >> 8);
            if (arriba_alta)   /* la de abajo (nativa) se oscurece en su lugar de g_bgra: copia aparte */
                for (size_t k = 0; k < (size_t)LIENZO_W * LIENZO_H * 4; k++) abajo[k] = (uint8_t)((g_bgra[k] * 95) >> 8);
            g_oscuro_listo = 1;
        }
        src = arriba_alta ? abajo : g_oscuro;
    }
    CR_FIN(CR_OSCURO, t_osc);
    CR_INI(t_st);
    BITMAPINFO bi;
    memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader;
    bi.bmiHeader.biWidth = sw;
    bi.bmiHeader.biHeight = -sh;   /* fila 0 arriba */
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    SetStretchBltMode(g_mem, aj.suave ? HALFTONE : COLORONCOLOR);
    if (aj.suave) SetBrushOrgEx(g_mem, 0, 0, NULL);
    StretchDIBits(g_mem, dx, dy, dw, dh, 0, 0, sw, sh, src, &bi, DIB_RGB_COLORS, SRCCOPY);
    if (arriba_alta) {   /* DOBLE con la de arriba en alta: encima de su mitad */
        bi.bmiHeader.biWidth = 400 * g_alta_s;
        bi.bmiHeader.biHeight = -(240 * g_alta_s);
        StretchDIBits(g_mem, dx, dy, dw, dh / 2, 0, 0, 400 * g_alta_s, 240 * g_alta_s, g_menu ? g_oscuro : g_alta_bgra,
                      &bi, DIB_RGB_COLORS, SRCCOPY);
    }
    GdiFlush();   /* desde aca se escribe directo en g_px */
    CR_FIN(CR_STRETCH, t_st);
    CR_INI(t_ui);
    ui_px = g_px;
    ui_w = w;
    ui_h = h;
    SetRect(&g_rect_tuerca, 0, 0, 0, 0);
    g_ultimo_con_ui = 1;
    if (g_menu) dibujar_menu(dx, dy, dw, dh);
    else if (g_titulo) dibujar_titulo(dx, dy, dw, dh);
    else {
        int op = opacidad_tuerca();
        if (op) dibujar_tuerca(dx, dy, dw, dh, op);
        else g_ultimo_con_ui = 0;
    }
    g_sucio_pint = 0;
    CR_FIN(CR_UI, t_ui);
    CR_INI(t_bb);
    if (!dc) return;   /* verificacion de la presentacion por GPU: solo componer en g_px */
    BitBlt(dc, 0, 0, w, h, g_mem, 0, 0, SRCCOPY);
    CR_FIN(CR_BITBLT, t_bb);
    CR_INI(t_dwm);
    /* DwmFlush espera la siguiente composicion del escritorio BLOQUEANDO el unico hilo (el juego). Con SALTAR no se
       llama (medido 7 oct: 2-5 ms/vblank pintando cada vblank, 7-10 ms al pintar solo los cuadros nuevos porque pierde
       la fase). Con DWM activo (siempre en Win10/11) lo pintado por GDI nunca se rasga: el escritorio compone la ultima
       imagen completa; el ritmo ya lo da el vblank emulado. SM3DL_VENTANA_DWMFLUSH=1 lo devuelve. */
    static int dwm = -1;
    if (dwm < 0) { const char *e = getenv("SM3DL_VENTANA_DWMFLUSH"); dwm = !g_saltar || (e && *e == '1'); }
    if (aj.vsync && dwm) DwmFlush();
    CR_FIN(CR_DWM, t_dwm);
    foto_ventana(w, h);
}

/* SM3DL_FOTO_VENTANA=<prefijo> (pruebas): guarda la ventana compuesta como BMP cada 600 cuadros y al abrir el menu */
static void foto_ventana(int w, int h)
{
    static const char *foto = (const char *)1;
    static unsigned n_pint;
    static int fotos_menu;
    if (foto == (const char *)1) foto = getenv("SM3DL_FOTO_VENTANA");
    if (!foto || !*foto) return;
    if (!(++n_pint % 600 == 0 || (g_menu && fotos_menu++ == 3))) return;
    char ruta[300];
    snprintf(ruta, sizeof ruta, "%s_%05u%s.bmp", foto, n_pint, g_menu ? "_menu" : g_titulo ? "_titulo" : "");
    FILE *f = fopen(ruta, "wb");
    if (!f) return;
    BITMAPINFOHEADER bh = { sizeof bh, w, -h, 1, 32, BI_RGB, 0, 0, 0, 0, 0 };
    BITMAPFILEHEADER fh = { 0x4D42, (DWORD)(sizeof fh + sizeof bh + (size_t)w * h * 4), 0, 0, sizeof fh + sizeof bh };
    fwrite(&fh, sizeof fh, 1, f);
    fwrite(&bh, sizeof bh, 1, f);
    fwrite(g_px, 4, (size_t)w * h, f);
    fclose(f);
}

static void pulsar_a(void) { g_pulsar_a_hasta = GetTickCount64() + 160; }

static LRESULT CALLBACK proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    switch (m) {
    case WM_CLOSE:
        fprintf(stderr, "[ventana] cerrada: fin\n");
        fflush(stderr);
        fflush(stdout);
        ExitProcess(0);
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        if (g_gpu == 1 && aj.unica) gpu_pintar(); else pintar(dc);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_ERASEBKGND:
        return 1;   /* todo se pinta por BitBlt: sin borrar, sin parpadeo */
    case WM_SYSKEYDOWN:
        if (w == VK_RETURN) { aj.completa = !aj.completa; aplicar_completa(); guardar_ajustes(); return 0; }   /* Alt+Enter */
        break;
    case WM_KEYDOWN:
        if (g_menu) { menu_tecla(w); return 0; }
        if (w == VK_ESCAPE) { abrir_menu(); return 0; }
        if (g_titulo && !(l & 0x40000000)) { pulsar_a(); return 0; }   /* cualquier tecla (sin autorepeticion) */
        break;
    case WM_SETCURSOR:
        /* en pantalla completa el cursor se esconde junto con la tuerca */
        if (LOWORD(l) == HTCLIENT && aj.completa && !g_menu && !g_titulo && !opacidad_tuerca()) { SetCursor(NULL); return TRUE; }
        break;
    case WM_LBUTTONDOWN:
    case WM_MOUSEMOVE: {
        POINT p = { (short)LOWORD(l), (short)HIWORD(l) };
        static POINT antes = { -1, -1 };
        if (m == WM_MOUSEMOVE && (p.x != antes.x || p.y != antes.y)) { g_mouse_visto = GetTickCount64(); antes = p; }
        if (g_menu) {
            for (int k = 0; k < N_FILAS; k++)
                if (fila_activa(k) && PtInRect(&g_rect_fila[k], p)) {
                    if (g_sel != k) { g_sel = k; InvalidateRect(h, NULL, FALSE); }
                    if (m == WM_LBUTTONDOWN) menu_tecla(VK_RIGHT);
                }
            return 0;
        }
        if (m == WM_LBUTTONDOWN && PtInRect(&g_rect_tuerca, p)) { abrir_menu(); return 0; }
        if (g_titulo && m == WM_LBUTTONDOWN) { pulsar_a(); return 0; }
        /* clic sobre la pantalla de abajo (modo doble) = toque de la pantalla tactil */
        if (!aj.unica && (w & MK_LBUTTON)) {
            RECT cr;
            GetClientRect(h, &cr);
            int dx, dy, dw, dh;
            destino(cr.right, cr.bottom, &dx, &dy, &dw, &dh);
            float x = (p.x - dx) * (float)LIENZO_W / dw - 40.0f, y = (p.y - dy) * (float)LIENZO_H / dh - ARRIBA_H;
            if (x >= 0 && x < 320 && y >= 0 && y < 240) { g_toque_x = x; g_toque_y = y; g_toque_mouse = 1; return 0; }
        }
        g_toque_mouse = 0;
        break;
    }
    case WM_LBUTTONUP:
        g_toque_mouse = 0;
        break;
    }
    return DefWindowProcW(h, m, w, l);
}

static int crear(void)
{
    cargar_ajustes();
    ui_cargar_fuentes();
    const char *s = getenv("SM3DL_ESCALA");
    if (s && atoi(s) >= 1 && atoi(s) <= 4) aj.escala = atoi(s);
    s = getenv("SM3DL_RESOLUCION");   /* pruebas: manda sobre el .ini */
    if (s && atoi(s) >= 1 && atoi(s) <= 8) aj.resol = atoi(s);
    raster_escala(aj.resol);
    /* T7: aniso / texturas HD. SM3DL_ANISO y SM3DL_TEX_HD mandan sobre el .ini (los modulos ya las leen: no pisarlas) */
    { const char *e = getenv("SM3DL_ANISO"); if (!e || !*e) raster_aniso_fijar(aj.aniso); }
    { const char *e = getenv("SM3DL_TEX_HD"); if (!e || !*e) texhd_fijar(aj.texhd); }
    /* el juego corre a 30 FPS nativos: "fps=60" en el .ini = 60 con cuadros intermedios (interp.c, 7 oct).
       SM3DL_INTERP (0/1) manda sobre el .ini (pruebas) */
    s = getenv("SM3DL_INTERP");
    if (s && *s) aj.fps30 = *s != '1';
    interp_vivo = !aj.fps30;
    { const char *a = getenv("SM3DL_FPS_ALTO"); if (a) aj_fps_alto = *a == '1'; }
    if (aj_fps_alto) { aj_presentar_gpu = 1; if (!interp_vivo) aj_fps_alto = 0; }
    g_alto_on = aj_fps_alto;
    gpu_alto_enganchar();
    fprintf(stderr, "[ventana] cuadros por segundo: %s\n", aj_fps_alto ? "monitor (interpolados)" : interp_vivo ? "60 interpolados" : "30 (original)");
    for (int k = 0; k < LIENZO_W * LIENZO_H; k++) {   /* gris oscuro a los lados de la pantalla de abajo */
        g_bgra[4 * k] = g_bgra[4 * k + 1] = g_bgra[4 * k + 2] = 0x20;
        g_bgra[4 * k + 3] = 0xFF;
    }
    SetProcessDPIAware();   /* si no, Windows estira la ventana por DPI y la imagen sale borrosa */
    HINSTANCE ins = GetModuleHandleW(NULL);
    WNDCLASSW wc;
    memset(&wc, 0, sizeof wc);
    wc.style = CS_OWNDC;   /* presentacion por GPU: el contexto GL queda sobre este DC */
    wc.lpfnWndProc = proc;
    wc.hInstance = ins;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = L"sm3dl_ventana";
    RegisterClassW(&wc);
    RECT r = { 0, 0, LIENZO_W * aj.escala, alto_lienzo() * aj.escala };
    AdjustWindowRect(&r, ESTILO_VENTANA, FALSE);
    /* SM3DL_VENTANA_OCULTA=1: pruebas en segundo plano sin aparecer encima de lo que el duenno esta usando */
    const char *oc = getenv("SM3DL_VENTANA_OCULTA");
    int oculta = oc && *oc && *oc != '0';
    g_v = CreateWindowW(L"sm3dl_ventana", L"Super Mario 3D Land — port nativo", ESTILO_VENTANA | (oculta ? 0 : WS_VISIBLE),
                        CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top, NULL, NULL, ins, NULL);
    if (!g_v) { fprintf(stderr, "[ventana] CreateWindow fallo (%lu)\n", GetLastError()); g_fallo = 1; return 0; }
    if (aj.completa && !oculta) aplicar_completa();
    fprintf(stderr, "[ventana] %dx%d (escala %d, pantalla %s%s)\n", LIENZO_W * aj.escala, alto_lienzo() * aj.escala,
            aj.escala, aj.unica ? "unica" : "doble", aj.completa ? ", completa" : "");
    return 1;
}

int ventana_con_foco(void)
{
    return g_v && !g_menu && GetForegroundWindow() == g_v;
}

/* gancho de hid (hid_toque_pc): mouse en la de abajo, o "usar item" (tecla E / clic del stick derecho) */
int ventana_toque(int boton_item, float *x, float *y)
{
    if (g_menu) return 0;
    if (g_toque_mouse) { *x = g_toque_x; *y = g_toque_y; return 1; }
    int tecla_e = ventana_con_foco() && (GetAsyncKeyState('E') & 0x8000);
    if (boton_item || tecla_e) { *x = ITEM_CX; *y = ITEM_CY; return 1; }
    return 0;
}

/* gancho de hid (hid_botones_pc): botones que agrega la ventana ("cualquier tecla" del titulo = A) */
uint32_t ventana_botones(void)
{
    return GetTickCount64() < g_pulsar_a_hasta ? 1u : 0u;   /* bit 0 = A (HID_A) */
}

static void bombear(void)
{
    MSG msg;
    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
}

#include "ventana_gpu.c"

void ventana_presentar(const GspPresentacion *p)
{
    if (g_fallo || (!g_v && !crear())) return;
    if (g_cr_on < 0) { const char *e = getenv("SM3DL_VENTANA_CRONO"); g_cr_on = e && *e && *e != '0'; }
    if (g_saltar < 0) {
        const char *e = getenv("SM3DL_VENTANA_SALTAR");
        g_saltar = !(e && *e == '0');
        e = getenv("SM3DL_VENTANA_VERIFICAR");
        g_verif = e ? atoi(e) : 0;
        if (g_verif && !g_saltar) g_verif = 0;
        fprintf(stderr, "[ventana] saltar cuadros repetidos=%d verificar=%d\n", g_saltar, g_verif);
    }
    CR_INI(t_total);
    if (p->pantalla == 0 || p->pantalla == 1) {
        CR_INI(t_conv);
        uint32_t x0 = p->pantalla ? 40 : 0, y0 = p->pantalla ? 240 : 0, w = p->pantalla ? 320 : 400, h = 240;
        uint32_t dif = 0;   /* != 0 si algun pixel cambio (deteccion de imagen nueva, SALTAR) */
        for (uint32_t y = 0; y < h; y++) {
            uint8_t *d = g_bgra + ((size_t)(y0 + y) * LIENZO_W + x0) * 4;
            if (p->negro || !p->rgba || p->ancho != w || p->alto != h) {
                for (uint32_t x = 0; x < w; x++) dif |= ((const uint32_t *)d)[x];
                memset(d, 0, (size_t)w * 4);
                continue;
            }
            const uint8_t *o = p->rgba + (size_t)y * w * 4;
            uint32_t *d32 = (uint32_t *)d;
            for (uint32_t x = 0; x < w; x++, o += 4) {
                uint32_t v = (uint32_t)o[2] | (uint32_t)o[1] << 8 | (uint32_t)o[0] << 16 | 0xFF000000u;
                dif |= d32[x] ^ v;
                d32[x] = v;
            }
        }
        if (dif) g_cr_cambio[p->pantalla]++;
        /* la de arriba NATIVA cambia medio vblank antes que su copia en alta (raster_alta entrega con 1 vblank de
           retraso): si hay alta, en UNICA la nativa de arriba no se usa y no ensucia (si no, se repinta CADA vblank) */
        if (dif && p->pantalla == 0 && aj.unica && g_alta_s) dif = 0;
        if (dif && !(g_verif == 2 && p->pantalla == 1)) g_sucio_comp = g_sucio_pint = 1;   /* =2: sabotaje */
        CR_FIN(CR_CONV, t_conv);
        if (p->pantalla == 0) {   /* resolucion interna: la de arriba en alta, si el raster la tiene */
            const unsigned char *hi = NULL;
            CR_INI(t_alta);
            g_arr_dir = p->dir_fisica; g_arr_fmt = p->formato & 7u; g_arr_stride = p->stride; g_arr_ok = !p->negro && p->rgba;
            int gpu = aj.unica && gpu_activo() == 1;
            unsigned tex = 0, gen = 0;
            int s = !g_arr_ok ? 0 : gpu ? raster_alta_textura(g_arr_dir, g_arr_fmt, g_arr_stride, 400, 240, &tex, NULL, &gen)
                                       : raster_alta(p->dir_fisica, p->formato & 7u, p->stride, 400, 240, &hi);
            if (gpu) {   /* la imagen no pasa por la CPU: solo marcar que hay una nueva */
                static unsigned gen_antes;
                int capa = s > 1;
                if (capa != g_capa_hud) { g_capa_hud = capa; g_sucio_comp = 1; g_hud_base_sucia = 1; g_hud_subido_w = 0; }
                if (gen != gen_antes) { gen_antes = gen; g_sucio_pint = 1; }
                hi = NULL;
            } else if (g_capa_hud) { g_capa_hud = 0; g_sucio_comp = 1; }
            CR_FIN(CR_ALTA, t_alta);
            int s_antes = g_alta_s;
            g_alta_s = s > 1 && s <= 4 ? s : 0;
            if (g_alta_s != s_antes) g_sucio_comp = g_sucio_pint = 1;
            CR_INI(t_ca);
            if (g_alta_s && hi) {   /* ya viene girada en la GPU y en BGRA con A = 255 */
                size_t n = (size_t)400 * s * 240 * s * 4;
                /* SALTAR: solo copia si cambio (raster_alta devuelve el mismo bufer si el cuadro no cambio) */
                if (!g_saltar || g_alta_s != s_antes || memcmp(g_alta_bgra, hi, n)) {
                    memcpy(g_alta_bgra, hi, n);
                    g_cr_cambio[2]++;
                    g_sucio_comp = g_sucio_pint = 1;
                }
            }
            CR_FIN(CR_COPIA_ALTA, t_ca);
        }
        if (p->pantalla == 1) {   /* cuadro completo: la de abajo llega despues de la de arriba */
            static int racha;
            CR_INI(t_tit);
            int t = titulo_en_pantalla();   /* histeresis de 3 cuadros */
            racha = t == g_titulo ? 0 : racha + 1;
            if (racha >= 3) { g_titulo = t; racha = 0; }
            CR_FIN(CR_TITULO, t_tit);
            CR_INI(t_un);
            if (aj.unica) {
                int vis = hud_histeresis();   /* corre siempre: la histeresis cuenta vblanks, como antes */
                if (!g_saltar || g_sucio_comp || vis) {
                    componer_unica_imagen();
                    g_sucio_comp = 0;
                    g_sucio_pint = 1;
                    g_hud_base_sucia = 1;
                } else if (g_verif) {   /* vblank saltado: el camino viejo tiene que dar EXACTAMENTE lo mismo */
                    size_t n = (size_t)g_u_w * g_u_h * 4;
                    if (!g_vf_copia) g_vf_copia = malloc(sizeof g_unica_bgra);
                    if (g_vf_copia) {
                        memcpy(g_vf_copia, g_unica_bgra, n);
                        componer_unica_imagen();
                        size_t malos = 0;
                        for (size_t k = 0; k < n; k++) malos += g_vf_copia[k] != g_unica_bgra[k];
                        g_vf_n++;
                        if (malos) g_vf_mal++;
                        if (malos && g_vf_mal <= 5)
                            fprintf(stderr, "[ventana-verif] vblank %u: %zu bytes distintos entre lo retenido y el camino viejo\n",
                                    gsp_estadistica()->vblanks, malos);
                        if (g_vf_n % 600 == 0)
                            fprintf(stderr, "[ventana-verif] saltados verificados=%u con diferencias=%u\n", g_vf_n, g_vf_mal);
                    }
                }
            }
            CR_FIN(CR_UNICA, t_un);
            if (1) {   /* (antes "limite de 30": uno de cada dos; el juego ya es de 30, ahora fps30 = sin intermedios) */
                RECT cr;
                GetClientRect(g_v, &cr);
                int pintar_ya = !g_saltar || g_sucio_pint || g_titulo || g_ultimo_con_ui || opacidad_tuerca() ||
                                cr.right != g_mem_w || cr.bottom != g_mem_h;
                if (g_alto_on && g_gpu == 1 && aj.unica) { /* modo monitor: pinta ventana_presentador */ }
                else if (pintar_ya && g_gpu == 1 && aj.unica) { gpu_pintar(); g_cr_pint++; }
                else if (pintar_ya) {
                    HDC dc = GetDC(g_v);
                    pintar(dc);
                    ReleaseDC(g_v, dc);
                    g_cr_pint++;
                } else g_cr_salt++;
            }
        }
    }
    CR_INI(t_bom);
    bombear();
    CR_FIN(CR_BOMBEAR, t_bom);
    CR_FIN(CR_TOTAL, t_total);
    if (p->pantalla == 1) cr_reportar();
    /* SM3DL_PRUEBA_MENU=<vblank> (pruebas sin persona): abre los ajustes en ese cuadro y los cierra 1 s despues */
    static long prueba_menu = -2;
    static ULONGLONG cerrar_prueba;
    if (prueba_menu == -2) { const char *s = getenv("SM3DL_PRUEBA_MENU"); prueba_menu = s ? atol(s) : -1; }
    if (prueba_menu > 0 && gsp_estadistica()->vblanks >= (uint32_t)prueba_menu) {
        prueba_menu = -1;
        abrir_menu();
        cerrar_prueba = GetTickCount64() + 1000;
    }
    /* SM3DL_PRUEBA_CAMBIOS=<vb>:<op>,... (G2, 9 oct; pruebas sin persona): en ese vblank abre los ajustes, aplica el
       cambio por el MISMO camino del menu (cambiar(): resolucion pendiente hasta el cierre, guardar_ajustes) y los
       cierra 1 s despues. op = r1..r4 (resolucion interna) | u (pantalla unica) | d (doble). Ej: 900:r1,1100:r4,1300:u */
    static const char *prueba_cambios = (const char *)1;
    if (prueba_cambios == (const char *)1) prueba_cambios = getenv("SM3DL_PRUEBA_CAMBIOS");
    if (prueba_cambios && *prueba_cambios && !g_menu) {
        char *fin;
        long vb = strtol(prueba_cambios, &fin, 10);
        if (fin != prueba_cambios && *fin == ':' && gsp_estadistica()->vblanks >= (uint32_t)vb) {
            char op = fin[1];
            int r = op == 'r' ? fin[2] - '0' : 0;
            const char *sig = strchr(fin, ',');
            prueba_cambios = sig ? sig + 1 : NULL;
            abrir_menu();
            if (r >= 1 && r <= 8) cambiar(OP_RESOL, r - aj.resol);
            else if ((op == 'u' && !aj.unica) || (op == 'd' && aj.unica)) cambiar(OP_PANTALLAS, 1);
            fprintf(stderr, "[prueba-cambios] vblank %u: %c%c -> resol %d, %s\n", gsp_estadistica()->vblanks, op,
                    r ? fin[2] : ' ', aj.resol, aj.unica ? "unica" : "doble");
            cerrar_prueba = GetTickCount64() + 1000;
        } else if (fin == prueba_cambios || *fin != ':') prueba_cambios = NULL;
    }
    /* menu abierto = juego en PAUSA: todo el juego corre en este hilo (fibras), asi que no volver lo detiene */
    if (g_menu) {
        fprintf(stderr, "[ventana] ajustes abiertos: pausa\n");
        while (g_menu) {
            bombear();
            menu_mando();
            if (g_gpu == 1 && aj.unica) gpu_pintar();
            else {
                HDC dc = GetDC(g_v);   /* pintar directo (una ventana oculta de prueba no recibe WM_PAINT) */
                pintar(dc);
                ReleaseDC(g_v, dc);
            }
            Sleep(16);
            if (cerrar_prueba && GetTickCount64() > cerrar_prueba) { cerrar_prueba = 0; g_menu = 0; }
        }
        if (g_resol_pend) { g_resol_pend = 0; raster_escala(aj.resol); }   /* SALTAR: una sola vez, al cerrar */
        g_sucio_comp = g_sucio_pint = 1;
        fprintf(stderr, "[ventana] ajustes cerrados: sigue\n");
        InvalidateRect(g_v, NULL, FALSE);
    }
}
