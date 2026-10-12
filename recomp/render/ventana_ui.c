/* Interfaz del port dibujada POR SOFTWARE sobre el bufer BGRA de la ventana (7 oct), con bordes suavizados y
 * transparencia real (GDI no suaviza contornos ni degradados: se veian dentados y "baratos").
 *   - Texto al estilo del juego: mascara suavizada de GDI (ANTIALIASED_QUALITY) -> contorno por DILATACION, sombra
 *     desplazada y relleno con degradado vertical (como "COURSE CLEAR!"). Las mascaras se cachean.
 *   - Paneles con esquinas redondeadas (distancia con signo), relleno translucido y borde.
 * Fuentes: las del juego vienen RECORTADAS a las letras que usa (MarioFont32 no tiene G H J K Q X Y Z), asi que se
 * usan dos libres (OFL/Apache) del mismo estilo, en extraido\fuentes\ttf: Luckiest Guy (titulos) y Lilita One.
 * Incluido por ventana.c. */
#include <math.h>

enum { UI_TITULO, UI_CUERPO, UI_SIMBOLO };
static const wchar_t *UI_CARA[3] = { L"Luckiest Guy", L"Lilita One", L"Segoe UI Symbol" };
static const wchar_t *UI_RESPALDO[3] = { L"Arial Black", L"Segoe UI Semibold", L"Segoe UI Symbol" };
static int ui_fuente_ok[3];

typedef struct {
    uint32_t arriba, abajo;   /* relleno: degradado vertical 0xRRGGBB */
    uint32_t borde;           /* color del contorno */
    float grosor;             /* contorno en px (0 = sin contorno) */
    float sombra;             /* desplazamiento de la sombra en px (0 = sin sombra) */
    int opacidad;             /* 0..256 */
} UiEstilo;

static uint8_t *ui_px;   /* destino BGRA de arriba a abajo */
static int g_ui_seguir;   /* GPU: anotar en g_ui_sucio la zona que se toca (capa transparente) */
static RECT g_ui_sucio;
static int ui_w, ui_h;

static void ui_cargar_fuentes(void)
{
    static const wchar_t *ARCH[2] = { L"extraido\\fuentes\\ttf\\LuckiestGuy-Regular.ttf",
                                      L"extraido\\fuentes\\ttf\\LilitaOne-Regular.ttf" };
    for (int k = 0; k < 2; k++) ui_fuente_ok[k] = AddFontResourceExW(ARCH[k], FR_PRIVATE, 0) > 0;
    ui_fuente_ok[2] = 1;
    fprintf(stderr, "[ventana] fuentes de interfaz: titulos %s, cuerpo %s\n", ui_fuente_ok[0] ? "Luckiest Guy" : "RESPALDO",
            ui_fuente_ok[1] ? "Lilita One" : "RESPALDO");
}

/* ------------------------------------------------------------------ mascaras de texto (cacheadas) */
typedef struct {
    int fuente, alto, radio;
    wchar_t txt[96];
    int w, h, pad, ancho;   /* ancho = avance del texto */
    uint8_t *cob, *dil;     /* cobertura del texto y su dilatacion (contorno) */
    unsigned uso;
} UiMascara;
#define UI_CACHE 160
static UiMascara ui_cache[UI_CACHE];
static unsigned ui_reloj;

static HFONT ui_crear_fuente(int fuente, int alto)
{
    return CreateFontW(-alto, 0, 0, 0, fuente == UI_SIMBOLO ? FW_BOLD : FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                       ANTIALIASED_QUALITY, 0, ui_fuente_ok[fuente] ? UI_CARA[fuente] : UI_RESPALDO[fuente]);
}

static UiMascara *ui_mascara(int fuente, int alto, int radio, const wchar_t *t)
{
    UiMascara *libre = &ui_cache[0];
    for (int k = 0; k < UI_CACHE; k++) {
        UiMascara *m = &ui_cache[k];
        if (m->cob && m->fuente == fuente && m->alto == alto && m->radio == radio && !wcsncmp(m->txt, t, 95)) {
            m->uso = ++ui_reloj;
            return m;
        }
        if (!m->cob || m->uso < libre->uso) libre = m;
    }
    UiMascara *m = libre;
    free(m->cob);
    free(m->dil);
    memset(m, 0, sizeof *m);
    m->fuente = fuente; m->alto = alto; m->radio = radio;
    wcsncpy(m->txt, t, 95);
    HDC dc = CreateCompatibleDC(NULL);
    HFONT f = ui_crear_fuente(fuente, alto);
    HGDIOBJ vf = SelectObject(dc, f);
    SIZE sz;
    int n = (int)wcslen(m->txt);
    GetTextExtentPoint32W(dc, m->txt, n, &sz);
    m->pad = radio + 3 + alto / 6;   /* las fuentes de dibujo animado se salen un poco de su caja */
    m->ancho = sz.cx;
    m->w = sz.cx + 2 * m->pad;
    m->h = sz.cy + 2 * m->pad;
    BITMAPINFO bi;
    memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader;
    bi.bmiHeader.biWidth = m->w;
    bi.bmiHeader.biHeight = -m->h;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    HGDIOBJ vb = SelectObject(dc, bmp);
    RECT r = { 0, 0, m->w, m->h };
    FillRect(dc, &r, (HBRUSH)GetStockObject(BLACK_BRUSH));
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(255, 255, 255));
    TextOutW(dc, m->pad, m->pad, m->txt, n);
    GdiFlush();
    m->cob = malloc((size_t)m->w * m->h);
    m->dil = malloc((size_t)m->w * m->h);
    const uint8_t *p = bits;
    for (int k = 0; k < m->w * m->h; k++) m->cob[k] = p ? p[4 * k + 1] : 0;
    /* contorno: maximo de la cobertura en un disco de radio 'radio' (con borde suave en el ultimo anillo) */
    for (int y = 0; y < m->h; y++)
        for (int x = 0; x < m->w; x++) {
            int mx = 0;
            for (int j = -radio; j <= radio && mx < 255; j++) {
                int yy = y + j;
                if (yy < 0 || yy >= m->h) continue;
                for (int i = -radio; i <= radio; i++) {
                    int xx = x + i;
                    if (xx < 0 || xx >= m->w) continue;
                    float d = sqrtf((float)(i * i + j * j));
                    if (d > radio + 0.5f) continue;
                    int v = m->cob[yy * m->w + xx];
                    if (d > radio - 0.5f) v = (int)(v * (radio + 0.5f - d));
                    if (v > mx) mx = v;
                }
            }
            m->dil[y * m->w + x] = (uint8_t)mx;
        }
    SelectObject(dc, vb);
    SelectObject(dc, vf);
    DeleteObject(bmp);
    DeleteObject(f);
    DeleteDC(dc);
    m->uso = ++ui_reloj;
    return m;
}

static void ui_mezclar(int x, int y, uint32_t rgb, int a)
{
    if (a <= 0 || x < 0 || y < 0 || x >= ui_w || y >= ui_h) return;
    if (a > 256) a = 256;
    uint8_t *d = ui_px + ((size_t)y * ui_w + x) * 4;
    d[0] = (uint8_t)(((rgb & 0xFF) * a + d[0] * (256 - a)) >> 8);
    d[1] = (uint8_t)((((rgb >> 8) & 0xFF) * a + d[1] * (256 - a)) >> 8);
    d[2] = (uint8_t)((((rgb >> 16) & 0xFF) * a + d[2] * (256 - a)) >> 8);
    d[3] = (uint8_t)((255 * a + d[3] * (256 - a)) >> 8);   /* sobre transparente: premultiplicado */
    if (g_ui_seguir) {
        if (g_ui_sucio.right <= g_ui_sucio.left) SetRect(&g_ui_sucio, x, y, x + 1, y + 1);
        else {
            if (x < g_ui_sucio.left) g_ui_sucio.left = x;
            if (y < g_ui_sucio.top) g_ui_sucio.top = y;
            if (x + 1 > g_ui_sucio.right) g_ui_sucio.right = x + 1;
            if (y + 1 > g_ui_sucio.bottom) g_ui_sucio.bottom = y + 1;
        }
    }
}

static uint32_t ui_lerp(uint32_t a, uint32_t b, float t)
{
    uint32_t r = 0;
    for (int s = 0; s < 24; s += 8) {
        float va = (float)((a >> s) & 0xFF), vb = (float)((b >> s) & 0xFF);
        r |= (uint32_t)(va + (vb - va) * t + 0.5f) << s;
    }
    return r;
}

/* dibuja texto; alin: -1 izquierda, 0 centro, 1 derecha (x es ese borde). y = parte de arriba. Devuelve el ancho. */
static int ui_texto(int fuente, int alto, const wchar_t *t, int x, int y, int alin, const UiEstilo *e)
{
    if (!ui_px || !t[0] || alto < 4) return 0;
    int radio = (int)(e->grosor + 0.5f);
    UiMascara *m = ui_mascara(fuente, alto, radio, t);
    int x0 = (alin < 0 ? x : alin == 0 ? x - m->ancho / 2 : x - m->ancho) - m->pad, y0 = y - m->pad;
    int op = e->opacidad ? e->opacidad : 256;
    /* alto real de la tinta para el degradado */
    int t0 = m->h, t1 = 0;
    for (int yy = 0; yy < m->h; yy++)
        for (int xx = 0; xx < m->w; xx += 2)
            if (m->cob[yy * m->w + xx] > 64) { if (yy < t0) t0 = yy; if (yy > t1) t1 = yy; break; }
    if (t1 <= t0) { t0 = 0; t1 = m->h - 1; }
    int sd = (int)(e->sombra + 0.5f);
    if (sd > 0)
        for (int yy = 0; yy < m->h; yy++)
            for (int xx = 0; xx < m->w; xx++) {
                int v = radio ? m->dil[yy * m->w + xx] : m->cob[yy * m->w + xx];
                if (v) ui_mezclar(x0 + xx + sd / 2 + 1, y0 + yy + sd, 0x000000, v * op * 140 / (255 * 256));
            }
    for (int yy = 0; yy < m->h; yy++) {
        float tt = (float)(yy - t0) / (float)(t1 - t0);
        uint32_t c = ui_lerp(e->arriba, e->abajo, tt < 0 ? 0 : tt > 1 ? 1 : tt);
        for (int xx = 0; xx < m->w; xx++) {
            int k = yy * m->w + xx;
            if (radio && m->dil[k]) ui_mezclar(x0 + xx, y0 + yy, e->borde, m->dil[k] * op / 255);
            if (m->cob[k]) ui_mezclar(x0 + xx, y0 + yy, c, m->cob[k] * op / 255);
        }
    }
    return m->ancho;
}

static int ui_ancho(int fuente, int alto, const wchar_t *t) { return ui_mascara(fuente, alto, 0, t)->ancho; }

/* panel con esquinas redondeadas: relleno 'fondo' con opacidad a_f (0..256) y borde de 'grosor' px */
static void ui_panel(int x, int y, int w, int h, float r, uint32_t fondo, int a_f, uint32_t borde, float grosor)
{
    for (int yy = y; yy < y + h; yy++) {
        if (yy < 0 || yy >= ui_h) continue;
        for (int xx = x; xx < x + w; xx++) {
            if (xx < 0 || xx >= ui_w) continue;
            /* distancia con signo al rectangulo redondeado (negativa adentro) */
            float px = fabsf(xx + 0.5f - (x + w * 0.5f)) - (w * 0.5f - r), py = fabsf(yy + 0.5f - (y + h * 0.5f)) - (h * 0.5f - r);
            float ox = px > 0 ? px : 0, oy = py > 0 ? py : 0;
            float dd = sqrtf(ox * ox + oy * oy) + fminf(fmaxf(px, py), 0.0f) - r;
            if (dd > 0.5f) continue;
            float cub = dd < -0.5f ? 1.0f : 0.5f - dd;   /* cobertura del borde exterior (antialias) */
            ui_mezclar(xx, yy, fondo, (int)(a_f * cub));
            if (grosor > 0) {
                float db = fabsf(dd + grosor * 0.5f) - grosor * 0.5f;   /* banda del borde */
                if (db < 0.5f) ui_mezclar(xx, yy, borde, (int)(256 * fminf(1.0f, 0.5f - db) * cub));
            }
        }
    }
}
