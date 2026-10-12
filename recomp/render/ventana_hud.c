/* HUD integrado de la pantalla UNICA (7 oct): barra de estado sin su fondo + circulo del item, sacados de la
 * pantalla de abajo. Incluido por ventana.c (usa g_bgra, g_unica_bgra de g_u_w x g_u_h a escala g_u_s, g_alta_bgra, ITEM_*, BARRA_H). */

/* ------------------------------------------------------------------ pantalla unica */
/* PRESENTACION POR GPU (ventana_gpu.c): con g_capa_hud el HUD se compone sobre TRANSPARENTE y se anota la zona */
static int g_capa_hud;
static RECT g_hud_sucio;
static void gpu_hud_limpiar(void);
/* mezcla src sobre dst con alfa a (0..256); el alfa de dst acumula (sobre transparente queda premultiplicado) */
static void mezclar(uint8_t *d, const uint8_t *s, int a)
{
    for (int c = 0; c < 3; c++) d[c] = (uint8_t)((s[c] * a + d[c] * (256 - a)) >> 8);
    d[3] = (uint8_t)((255 * a + d[3] * (256 - a)) >> 8);
    if (g_capa_hud) {
        size_t i = (size_t)(d - g_unica_bgra) / 4;
        RECT p = { (LONG)(i % (size_t)g_u_w), (LONG)(i / (size_t)g_u_w), 0, 0 };
        p.right = p.left + 1; p.bottom = p.top + 1;
        if (g_hud_sucio.right <= g_hud_sucio.left) g_hud_sucio = p;
        else {
            if (p.left < g_hud_sucio.left) g_hud_sucio.left = p.left;
            if (p.top < g_hud_sucio.top) g_hud_sucio.top = p.top;
            if (p.right > g_hud_sucio.right) g_hud_sucio.right = p.right;
            if (p.bottom > g_hud_sucio.bottom) g_hud_sucio.bottom = p.bottom;
        }
    }
}

/* pixel de la pantalla de abajo (x,y en 320x240) desde el lienzo doble, promediando 2x2 si se reduce */
static void muestra_abajo(float x, float y, float paso, uint8_t *o)
{
    int acc[3] = { 0, 0, 0 }, n = 0;
    float h = paso > 1.0f ? paso * 0.25f : 0.0f;
    for (int j = 0; j < 2; j++)
        for (int i = 0; i < 2; i++) {
            int sx = (int)(x + (i ? h : -h)), sy = (int)(y + (j ? h : -h));
            if (sx < 0 || sx >= 320 || sy < 0 || sy >= 240) continue;
            const uint8_t *s = g_bgra + ((size_t)(ARRIBA_H + sy) * LIENZO_W + 40 + sx) * 4;
            acc[0] += s[0]; acc[1] += s[1]; acc[2] += s[2]; n++;
        }
    if (!n) n = 1;
    o[0] = (uint8_t)(acc[0] / n); o[1] = (uint8_t)(acc[1] / n); o[2] = (uint8_t)(acc[2] / n);
}

/* Pega un recorte de la barra de estado SIN su fondo verde (chroma key por "verdor" = g - max(r,b): el fondo es
   (82,255,82) ~173 y se aclara hacia abajo; texto blanco/negro, monedas y Mario quedan cerca de 0 o negativos).
   Los elementos ya traen el estilo del HUD de arriba (borde, sombra): sin el fondo parecen nativos.
   (sx0,sy0,sw,sh) en la de abajo; (dx,dy) en la de arriba; k = escala. */
/* 7 oct: el color de la barra CAMBIA por mundo (W1 verde 82,255,82; W2 amarillo 255,227,107...): el fondo se toma
   en cada cuadro, fila por fila, del hueco entre las monedas estrella y las vidas (x 215..240), y el recorte quita
   ESE color (distancia maxima por canal). Antes buscaba verde y en el W2 el HUD entero desaparecia. */
static const uint8_t *px_abajo(int x, int y) { return g_bgra + ((size_t)(ARRIBA_H + y) * LIENZO_W + 40 + x) * 4; }
static uint8_t g_fondo[BARRA_H][3];
/* 7 oct (2): el fondo se mide en los BORDES de la barra (x 1-3 y 316-318), que nunca tienen contenido. Antes se
   media en x 215-240 y con 10+ vidas el bloque "Mario x11" se corre a la izquierda y cae ahi: el fondo salia mal y
   no se quitaba nada (recuadros amarillos en el W2-2, visto por el duenno). */
static void medir_fondo_barra(void)
{
    static const int XS[6] = { 1, 2, 3, 316, 317, 318 };
    for (int y = 0; y < BARRA_H; y++) {
        int acc[3] = { 0, 0, 0 };
        for (int k = 0; k < 6; k++) {
            const uint8_t *s = g_bgra + ((size_t)(ARRIBA_H + y) * LIENZO_W + 40 + XS[k]) * 4;
            acc[0] += s[0]; acc[1] += s[1]; acc[2] += s[2];
        }
        for (int c = 0; c < 3; c++) g_fondo[y][c] = (uint8_t)(acc[c] / 6);
    }
}

static int dist_fondo(int x, int y)
{
    const uint8_t *s = px_abajo(x, y), *f = g_fondo[y < 0 ? 0 : y >= BARRA_H ? BARRA_H - 1 : y];
    int d = 0;
    for (int c = 0; c < 3; c++) { int e = abs(s[c] - f[c]); if (e > d) d = e; }
    return d;
}

/* columna x de la barra con contenido (contorno o texto) en las filas del HUD */
static int columna_ocupada(int x)
{
    for (int y = 7; y <= 33; y++)
        if (dist_fondo(x, y) > 70) return 1;
    return 0;
}

/* desde una columna ocupada, avanza en 'dir' hasta 10 columnas vacias seguidas (o el tope): extremo del bloque */
static int extremo_bloque(int x, int dir, int tope)
{
    int ultimo = x, vacias = 0;
    for (int c = x; dir < 0 ? c >= tope : c <= tope; c += dir) {
        if (columna_ocupada(c)) { ultimo = c; vacias = 0; }
        else if (++vacias >= 10) break;
    }
    return ultimo;
}

/* Quita el fondo por INUNDACION desde el borde del recorte (como el balde de pintura): solo se borra el fondo
   conectado con el borde, asi el interior de numeros y monedas (rodeados de contorno oscuro) queda aunque sea del
   mismo color que la barra (el "9" amarillo de las vidas sobre la barra amarilla del W2 se desteñia). Los bordes
   del fondo tocados por la inundacion dan alfa parcial segun la distancia de color (antialias). */
#define REC_MAX 128
static void pegar_sin_fondo(int sx0, int sy0, int sw, int sh, int dx, int dy, float k)
{
    /* resolucion interna: el destino mide 400s x 240s; posiciones y escala en pixeles nativos se multiplican */
    dx *= g_u_s; dy *= g_u_s; k *= g_u_s;
    static uint8_t alfa[REC_MAX * 48];
    static int16_t pila[REC_MAX * 48 * 2];
    if (sw > REC_MAX || sh > 48) return;
    memset(alfa, 255, (size_t)sw * sh);
    int np = 0;
    for (int x = 0; x < sw; x++) { pila[np++] = (int16_t)(x); pila[np++] = 0; pila[np++] = (int16_t)x; pila[np++] = (int16_t)(sh - 1); }
    for (int y = 0; y < sh; y++) { pila[np++] = 0; pila[np++] = (int16_t)y; pila[np++] = (int16_t)(sw - 1); pila[np++] = (int16_t)y; }
    while (np > 0 && np < (int)(sizeof pila / sizeof pila[0]) - 8) {
        int y = pila[--np], x = pila[--np];
        if (x < 0 || x >= sw || y < 0 || y >= sh || alfa[y * sw + x] != 255) continue;
        int d = dist_fondo(sx0 + x, sy0 + y);
        if (d > 70) continue;   /* contorno o contenido: la inundacion se detiene */
        alfa[y * sw + x] = (uint8_t)(d <= 30 ? 0 : (d - 30) * 254 / 40);   /* fondo (0) o borde suave */
        if (d <= 30) { pila[np++] = (int16_t)(x + 1); pila[np++] = (int16_t)y; pila[np++] = (int16_t)(x - 1); pila[np++] = (int16_t)y;
                       pila[np++] = (int16_t)x; pila[np++] = (int16_t)(y + 1); pila[np++] = (int16_t)x; pila[np++] = (int16_t)(y - 1); }
    }
    int w = (int)(sw * k + 0.5f), h = (int)(sh * k + 0.5f);
    float paso = 1.0f / k, hh = paso * 0.25f;
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            int X = dx + x, Y = dy + y;
            if (X < 0 || X >= g_u_w || Y < 0 || Y >= g_u_h) continue;
            int acc[3] = { 0, 0, 0 }, aa = 0;   /* promedio 2x2 ponderado por alfa */
            for (int j = 0; j < 2; j++)
                for (int i = 0; i < 2; i++) {
                    int rx = (int)((x + 0.5f) * paso + (i ? hh : -hh)), ry = (int)((y + 0.5f) * paso + (j ? hh : -hh));
                    if (rx < 0 || rx >= sw || ry < 0 || ry >= sh) continue;
                    int a = alfa[ry * sw + rx];
                    const uint8_t *s = px_abajo(sx0 + rx, sy0 + ry);
                    acc[0] += s[0] * a; acc[1] += s[1] * a; acc[2] += s[2] * a; aa += a;
                }
            if (!aa) continue;
            uint8_t px[3] = { (uint8_t)(acc[0] / aa), (uint8_t)(acc[1] / aa), (uint8_t)(acc[2] / aa) };
            mezclar(g_unica_bgra + ((size_t)Y * g_u_w + X) * 4, px, aa * 256 / (4 * 255));
        }
}

/* 1 si la pantalla de abajo esta mostrando el HUD de juego: las filas 1-3 de la barra son fondo verde puro
   (82,255,82). En cinematicas, menus o pausa la de abajo es negra u otra cosa: ahi no se integra nada (si no,
   salia un circulo y una barra NEGROS encima de la escena; visto por el duenno en la cinematica del final del W1). */
/* HUD de juego = filas 1-3 de UN SOLO color saturado (el de la barra del mundo, sea cual sea) y debajo de la barra
   el fondo claro a cuadros (fila 46, a la izquierda del circulo). Descarta mapas (gris), cinematicas (negro) y la
   cortina de transicion (amarilla de arriba a abajo). */
static int hud_en_pantalla(void)
{
    int m[3] = { 0, 0, 0 }, n = 0;
    for (int y = 1; y <= 3; y++)
        for (int x = 2; x < 318; x += 4) { const uint8_t *s = px_abajo(x, y); m[0] += s[0]; m[1] += s[1]; m[2] += s[2]; n++; }
    for (int c = 0; c < 3; c++) m[c] /= n;
    int mx = m[0] > m[1] ? m[0] : m[1], mn = m[0] < m[1] ? m[0] : m[1];
    if (m[2] > mx) mx = m[2];
    if (m[2] < mn) mn = m[2];
    if (mx - mn < 80) return 0;   /* no saturado: gris, blanco o negro */
    int iguales = 0;
    for (int y = 1; y <= 3; y++)
        for (int x = 2; x < 318; x += 4) {
            const uint8_t *s = px_abajo(x, y);
            iguales += abs(s[0] - m[0]) < 25 && abs(s[1] - m[1]) < 25 && abs(s[2] - m[2]) < 25;
        }
    if (iguales * 10 < n * 8) return 0;
    int claros = 0, total = 0;
    for (int y = 46; y <= 48; y++)
        for (int x = 4; x < 70; x += 3) {
            const uint8_t *s = px_abajo(x, y);
            claros += s[0] > 180 && s[1] > 180 && s[2] > 180;
            total++;
        }
    return claros * 10 >= total * 8;
}

/* histeresis del HUD: 4 cuadros seguidos para aparecer o desaparecer (sin parpadeo en transiciones). Va APARTE de la
   composicion (7 oct, B): corre en cada vblank aunque la composicion se salte; devuelve 1 si cambio la visibilidad. */
static int g_hud_visible, g_hud_racha;
static int hud_histeresis(void)
{
    int ahora = hud_en_pantalla();
    g_hud_racha = ahora == g_hud_visible ? 0 : g_hud_racha + 1;
    if (g_hud_racha >= 4) { g_hud_visible = ahora; g_hud_racha = 0; return 1; }
    return 0;
}

/* la composicion en si (deterministica: depende de g_bgra, g_alta_bgra, g_alta_s y g_hud_visible) */
static void componer_unica_imagen(void)
{
    /* la de arriba: en alta si la hay (resolucion interna), si no la nativa */
    g_u_s = g_alta_s > 1 ? g_alta_s : 1;
    g_u_w = LIENZO_W * g_u_s;
    g_u_h = ARRIBA_H * g_u_s;
    if (g_capa_hud) gpu_hud_limpiar();   /* GPU: la imagen va aparte; aqui solo el HUD */
    else memcpy(g_unica_bgra, g_u_s > 1 ? g_alta_bgra : g_bgra, (size_t)g_u_w * g_u_h * 4);
    if (!g_hud_visible) return;
    medir_fondo_barra();
    /* barra de estado, desarmada e integrada al HUD de arriba (tamano de los numeros de monedas y reloj):
       - Mario x vidas: arriba a la izquierda, debajo del contador de monedas;
       - mundo (W1-3) + monedas estrella: arriba al centro. */
    const float k = 0.62f;
    /* Mario x vidas: el bloque crece a la izquierda con 2 digitos ("x11" empieza en ~228): extension real */
    int v1 = 318;
    while (v1 > 212 && !columna_ocupada(v1)) v1--;
    int v0 = extremo_bloque(v1, -1, 212);
    pegar_sin_fondo(v0 - 2, 5, v1 - v0 + 5, 31, 4, 26, 0.7f);
    /* mundo ("W1-3", "W2-2", "S1-1"...): desde la izquierda */
    int m0 = 1;
    while (m0 < 100 && !columna_ocupada(m0)) m0++;
    int m1 = extremo_bloque(m0, 1, 110);
    int ancho = (int)((206 - m0) * k);
    pegar_sin_fondo(m0 - 2, 5, m1 - m0 + 5, 31, (LIENZO_W - ancho) / 2, 3, k);
    pegar_sin_fondo(115, 5, 92, 31, (LIENZO_W - ancho) / 2 + (int)((115 - 6) * k) - 6, 3, k);   /* monedas estrella */
    /* circulo del item: diametro 2*ITEM_R a 64 px, recortado en circulo con borde suave, esquina de abajo a la izq. */
    const int dd = 64 * g_u_s;
    const float ki = (float)dd / (2 * ITEM_R);
    int ix = 5 * g_u_s, iy = g_u_h - dd - 5 * g_u_s;
    for (int y = 0; y < dd; y++)
        for (int x = 0; x < dd; x++) {
            float dx = x + 0.5f - dd / 2.0f, dy = y + 0.5f - dd / 2.0f, r = dd / 2.0f;
            float dist = dx * dx + dy * dy;
            if (dist > r * r) continue;
            int a = dist > (r - 1.5f) * (r - 1.5f) ? 120 : 245;
            uint8_t px[3];
            muestra_abajo(ITEM_CX + dx / ki, ITEM_CY + dy / ki, 1.0f / ki, px);
            mezclar(g_unica_bgra + ((size_t)(iy + y) * g_u_w + ix + x) * 4, px, a);
        }
}

/* camino de siempre: histeresis + composicion en la misma llamada */
static void componer_unica(void)
{
    hud_histeresis();
    componer_unica_imagen();
}
