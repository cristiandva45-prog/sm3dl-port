/* Llenado de la memoria compartida de hid:USER desde la PC. Ver hid.h. */
#include "hid.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

_Static_assert(offsetof(HidShm, pad.e) == 0x28, "pad.e");
_Static_assert(offsetof(HidShm, touch) == 0xA8, "touch");
_Static_assert(offsetof(HidShm, accel) == 0x108, "accel");
_Static_assert(offsetof(HidShm, giro) == 0x158, "giro");
_Static_assert(sizeof(HidShm) == 0x238, "tamano");

#define CIRC_MAX 0x9A        /* valor del circle pad a fondo */
#define CIRC_UMBRAL 40       /* radio a partir del cual cuenta como direccion digital */

void hid_iniciar(HidShm *m, HidEstado *s)
{
    memset(m, 0, sizeof *m);
    memset(s, 0, sizeof *s);
}

static uint32_t direccion(int x, int y)
{
    /* sectores de 60 grados con solape: diagonal = dos direcciones (tan 30 / tan 60) */
    uint32_t d = 0;
    if (x * x + y * y <= CIRC_UMBRAL * CIRC_UMBRAL)
        return 0;
    float t = x ? fabsf((float)y / (float)x) : 0.0f;
    if (x != 0 && t < 1.7320508f)
        d |= x > 0 ? HID_CIRC_DERECHA : HID_CIRC_IZQUIERDA;
    if (x == 0 || t > 0.57735027f)
        d |= y > 0 ? HID_CIRC_ARRIBA : HID_CIRC_ABAJO;
    return d;
}

int hid_muestrear(HidShm *m, HidEstado *s, const HidEntradaPC *e, int64_t ticks)
{
    /* stick -> circle pad: escala al rango del 3DS y promedio de 3 muestras como el hardware */
    int nx = (int)lroundf(fmaxf(-1.0f, fminf(1.0f, e->stick_x)) * CIRC_MAX);
    int ny = (int)lroundf(fmaxf(-1.0f, fminf(1.0f, e->stick_y)) * CIRC_MAX);
    int16_t cx = (int16_t)((nx + s->viejo_x[0] + s->viejo_x[1]) / 3);
    int16_t cy = (int16_t)((ny + s->viejo_y[0] + s->viejo_y[1]) / 3);
    s->viejo_x[0] = s->viejo_x[1]; s->viejo_x[1] = (int16_t)nx;
    s->viejo_y[0] = s->viejo_y[1]; s->viejo_y[1] = (int16_t)ny;

    uint32_t est = (e->botones & 0x0FFFFFFFu) | direccion(cx, cy);
    m->pad.actual = est;
    m->pad.indice = s->sig_pad;
    s->sig_pad = (s->sig_pad + 1) % 8;
    uint32_t viejo = m->pad.e[(m->pad.indice + 7) % 8].actual;
    HidPadEntrada *p = &m->pad.e[m->pad.indice];
    p->actual = est;
    p->altas = (est ^ viejo) & est;
    p->bajas = (est ^ viejo) & viejo;
    p->cx = cx;
    p->cy = cy;
    if (m->pad.indice == 0) {
        m->pad.ticks_prev = m->pad.ticks;
        m->pad.ticks = ticks;
    }

    m->touch.indice = s->sig_touch;
    s->sig_touch = (s->sig_touch + 1) % 8;
    HidTouchEntrada *t = &m->touch.e[m->touch.indice];
    t->x = (uint16_t)(e->touch_x * 320.0f);
    t->y = (uint16_t)(e->touch_y * 240.0f);
    t->valido = e->tocando ? 1u : 0u;
    if (m->touch.indice == 0) {
        m->touch.ticks_prev = m->touch.ticks;
        m->touch.ticks = ticks;
    }
    return 1;
}

#ifdef _WIN32
#include <windows.h>
#include <xinput.h>

static int tecla(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }

/* GetAsyncKeyState lee el teclado aunque la ventana activa sea otra: con ventana propia, el integrador pone aqui
   "la ventana del juego tiene el foco" (9 oct). NULL = leer siempre (pruebas). */
int (*hid_teclado_activo)(void);
/* toque de la pantalla de abajo desde el PC (7 oct): la ventana resuelve mouse / tecla del item; boton_item = 1 si
   el mando pide "usar item de reserva" (clic del stick derecho). Devuelve 1 y x,y en pixeles 320x240 si hay toque. */
int (*hid_toque_pc)(int boton_item, float *x, float *y);
/* botones que agrega la ventana (p. ej. "pulsa cualquier tecla" del titulo = A); se suman siempre */
uint32_t (*hid_botones_pc)(void);

void hid_leer_pc(HidEntradaPC *e)
{
    /* teclado de PC (7 oct, a pedido del duenno): WASD = circle pad, Espacio = A (saltar), Shift = Y (correr /
       bola de fuego), Ctrl o C = R (agacharse), Q = L, Enter = Start, Tab = Select, flechas = cruceta (camara).
       E = usar el item de reserva (toque de la pantalla de abajo: lo resuelve la ventana, hid_toque_pc). */
    memset(e, 0, sizeof *e);
    if (hid_teclado_activo && !hid_teclado_activo()) goto mando;
    static const struct { int vk; uint32_t b; } mapa[] = {
        {VK_SPACE, HID_A}, {VK_LSHIFT, HID_Y}, {VK_RSHIFT, HID_Y}, {VK_LCONTROL, HID_R}, {'C', HID_R},
        {'Q', HID_L}, {VK_RETURN, HID_START}, {VK_TAB, HID_SELECT}, {VK_UP, HID_ARRIBA}, {VK_DOWN, HID_ABAJO},
        {VK_LEFT, HID_IZQUIERDA}, {VK_RIGHT, HID_DERECHA},
    };
    for (size_t k = 0; k < sizeof mapa / sizeof mapa[0]; k++)
        if (tecla(mapa[k].vk))
            e->botones |= mapa[k].b;
    e->stick_x = (float)(tecla('D') - tecla('A'));
    e->stick_y = (float)(tecla('W') - tecla('S'));
    if (e->stick_x && e->stick_y) { e->stick_x *= 0.7071f; e->stick_y *= 0.7071f; }   /* diagonal: misma rapidez */

mando:;
    XINPUT_STATE xs;
    if (XInputGetState(0, &xs) == ERROR_SUCCESS) {
        WORD b = xs.Gamepad.wButtons;
        /* posiciones como en el 3DS: A del 3DS a la derecha = B del mando Xbox */
        if (b & XINPUT_GAMEPAD_B) e->botones |= HID_A;
        if (b & XINPUT_GAMEPAD_A) e->botones |= HID_B;
        if (b & XINPUT_GAMEPAD_Y) e->botones |= HID_X;
        if (b & XINPUT_GAMEPAD_X) e->botones |= HID_Y;
        if (b & XINPUT_GAMEPAD_LEFT_SHOULDER) e->botones |= HID_L;
        if (b & XINPUT_GAMEPAD_RIGHT_SHOULDER) e->botones |= HID_R;
        if (b & XINPUT_GAMEPAD_START) e->botones |= HID_START;
        if (b & XINPUT_GAMEPAD_BACK) e->botones |= HID_SELECT;
        if (b & XINPUT_GAMEPAD_DPAD_UP) e->botones |= HID_ARRIBA;
        if (b & XINPUT_GAMEPAD_DPAD_DOWN) e->botones |= HID_ABAJO;
        if (b & XINPUT_GAMEPAD_DPAD_LEFT) e->botones |= HID_IZQUIERDA;
        if (b & XINPUT_GAMEPAD_DPAD_RIGHT) e->botones |= HID_DERECHA;
        float sx = xs.Gamepad.sThumbLX / 32767.0f, sy = xs.Gamepad.sThumbLY / 32767.0f;
        float r = sqrtf(sx * sx + sy * sy);
        const float muerta = XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE / 32767.0f;
        if (r > muerta) {  /* zona muerta radial, reescalada para que fuera de ella vaya de 0 a 1 */
            float k = fminf(1.0f, (r - muerta) / (1.0f - muerta)) / r;
            e->stick_x = sx * k;
            e->stick_y = sy * k;
        }
    }
    {
        int item = XInputGetState(0, &xs) == ERROR_SUCCESS && (xs.Gamepad.wButtons & XINPUT_GAMEPAD_RIGHT_THUMB);
        float tx, ty;
        if (hid_botones_pc) e->botones |= hid_botones_pc();
        if (hid_toque_pc && hid_toque_pc(item, &tx, &ty)) {
            e->tocando = 1;
            e->touch_x = tx / 320.0f;
            e->touch_y = ty / 240.0f;
        }
    }
}
#endif

/* ------------------------------------------------------------------ entrada por guion (agente P, 10 oct)
 * SM3DL_GUION=<archivo>: lineas "<vblank> <botones> [duracion_vblanks]" (duracion por defecto 6).
 *   botones: A B X Y L R START SELECT ARRIBA ABAJO IZQUIERDA DERECHA (o UP DOWN LEFT RIGHT),
 *            CARRIBA CABAJO CIZQUIERDA CDERECHA (circle pad a fondo), combinables con '+' (p.ej. A+B, ABAJO+R),
 *            "TOQUE x y" (pantalla de abajo en pixeles 320x240), "STICK x y" (circle pad, -1..1), "NADA".
 *   '#' empieza un comentario. Se SUMA al teclado/mando y cuenta aunque la ventana no tenga el foco. */
#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>

typedef struct { uint32_t vb, dur, botones; int toque; float tx, ty, sx, sy; int stick; } HidPaso;
static HidPaso *g_pasos;
static int g_npasos, g_guion_cargado;

static int nombre_boton(const char *t, uint32_t *b)
{
    static const struct { const char *n; uint32_t b; } m[] = {
        {"A", HID_A}, {"B", HID_B}, {"X", HID_X}, {"Y", HID_Y}, {"L", HID_L}, {"R", HID_R},
        {"START", HID_START}, {"SELECT", HID_SELECT}, {"ARRIBA", HID_ARRIBA}, {"ABAJO", HID_ABAJO},
        {"IZQUIERDA", HID_IZQUIERDA}, {"DERECHA", HID_DERECHA}, {"UP", HID_ARRIBA}, {"DOWN", HID_ABAJO},
        {"LEFT", HID_IZQUIERDA}, {"RIGHT", HID_DERECHA}, {"CARRIBA", HID_CIRC_ARRIBA}, {"CABAJO", HID_CIRC_ABAJO},
        {"CIZQUIERDA", HID_CIRC_IZQUIERDA}, {"CDERECHA", HID_CIRC_DERECHA}, {"NADA", 0},
    };
    for (size_t k = 0; k < sizeof m / sizeof m[0]; k++)
        if (!strcmp(t, m[k].n)) { *b |= m[k].b; return 1; }
    return 0;
}

int hid_guion_cargar(const char *ruta)
{
    FILE *f = fopen(ruta, "r");
    g_guion_cargado = 1;
    if (!f) { fprintf(stderr, "[guion] no abre %s\n", ruta); return -1; }
    char l[256];
    int nl = 0, cap = 0;
    while (fgets(l, sizeof l, f)) {
        nl++;
        char *c = strchr(l, '#');
        if (c) *c = 0;
        for (char *q = l; *q; q++) *q = (char)toupper((unsigned char)*q);
        char tok[4][64];
        int n = sscanf(l, "%63s %63s %63s %63s", tok[0], tok[1], tok[2], tok[3]);
        if (n < 2) continue;
        HidPaso p;
        memset(&p, 0, sizeof p);
        p.vb = (uint32_t)strtoul(tok[0], NULL, 10);
        p.dur = 6;
        if (!strcmp(tok[1], "TOQUE") || !strcmp(tok[1], "STICK")) {
            if (n < 4) { fprintf(stderr, "[guion] linea %d: faltan x y\n", nl); continue; }
            float x = strtof(tok[2], NULL), y = strtof(tok[3], NULL);
            if (tok[1][0] == 'T') { p.toque = 1; p.tx = x / 320.0f; p.ty = y / 240.0f; }
            else { p.stick = 1; p.sx = x; p.sy = y; }
            char extra[64];   /* duracion opcional tras x y */
            if (sscanf(l, "%*s %*s %*s %*s %63s", extra) == 1) p.dur = (uint32_t)strtoul(extra, NULL, 10);
        } else {
            char *s = tok[1], *mas;
            int ok = 1;
            do {
                mas = strchr(s, '+');
                if (mas) *mas = 0;
                if (!nombre_boton(s, &p.botones)) { fprintf(stderr, "[guion] linea %d: boton desconocido '%s'\n", nl, s); ok = 0; }
                s = mas + 1;
            } while (mas);
            if (!ok) continue;
            if (n >= 3) p.dur = (uint32_t)strtoul(tok[2], NULL, 10);
        }
        if (g_npasos == cap) { cap = cap ? 2 * cap : 64; g_pasos = realloc(g_pasos, (size_t)cap * sizeof *g_pasos); }
        g_pasos[g_npasos++] = p;
    }
    fclose(f);
    fprintf(stderr, "[guion] %s: %d pasos\n", ruta, g_npasos);
    return g_npasos;
}

/* SM3DL_GRABAR=<archivo> (7 oct): graba lo que el duenno juega (teclado/mando REAL, antes del guion) en el mismo
 * formato de guion, para repetir su recorrido en turbo. Dos codificadores por tramos: botones y stick (cuantizado
 * a 0,05 para no escribir una linea por cada temblor del mando). Se escribe al cambiar, con fflush. */
void hid_grabar(const HidEntradaPC *e, uint32_t vblank)
{
    static FILE *f;
    static int ini;
    static uint32_t b_ant, b_desde, s_desde;
    static int sx_ant, sy_ant;
    if (!ini) {
        const char *r = getenv("SM3DL_GRABAR");
        ini = 1;
        if (r && *r && (f = fopen(r, "w")))
            fprintf(f, "# grabado por SM3DL_GRABAR: vblank BOTONES duracion | vblank STICK x y duracion\n");
    }
    if (!f) return;
    static const struct { const char *n; uint32_t b; } m[] = {
        {"A", HID_A}, {"B", HID_B}, {"X", HID_X}, {"Y", HID_Y}, {"L", HID_L}, {"R", HID_R}, {"START", HID_START},
        {"SELECT", HID_SELECT}, {"ARRIBA", HID_ARRIBA}, {"ABAJO", HID_ABAJO}, {"IZQUIERDA", HID_IZQUIERDA},
        {"DERECHA", HID_DERECHA},
    };
    uint32_t b = e->botones & 0x0FFFFFFFu;
    if (b != b_ant) {
        if (b_ant && vblank > b_desde) {
            char t[160] = "";
            for (size_t k = 0; k < sizeof m / sizeof m[0]; k++)
                if (b_ant & m[k].b) { if (*t) strcat(t, "+"); strcat(t, m[k].n); }
            fprintf(f, "%u %s %u\n", b_desde, t, vblank - b_desde);
        }
        b_ant = b;
        b_desde = vblank;
        fflush(f);
    }
    int sx = (int)(e->stick_x * 20.0f + (e->stick_x >= 0 ? 0.5f : -0.5f));
    int sy = (int)(e->stick_y * 20.0f + (e->stick_y >= 0 ? 0.5f : -0.5f));
    if (sx != sx_ant || sy != sy_ant) {
        if ((sx_ant || sy_ant) && vblank > s_desde)
            fprintf(f, "%u STICK %.2f %.2f %u\n", s_desde, sx_ant / 20.0, sy_ant / 20.0, vblank - s_desde);
        sx_ant = sx;
        sy_ant = sy;
        s_desde = vblank;
        fflush(f);
    }
}

void hid_guion_aplicar(HidEntradaPC *e, uint32_t vblank)
{
    if (!g_guion_cargado) {
        const char *r = getenv("SM3DL_GUION");
        g_guion_cargado = 1;
        if (r && *r) hid_guion_cargar(r);
    }
    static uint32_t ultimo_aviso = 0xFFFFFFFFu;
    for (int k = 0; k < g_npasos; k++) {
        HidPaso *p = &g_pasos[k];
        if (vblank < p->vb || vblank >= p->vb + p->dur) continue;
        e->botones |= p->botones & 0x0FFFFFFFu;
        if (p->botones & 0xF0000000u) {   /* hid_muestrear deriva los bits del circle pad del stick: pasar por ahi */
            e->stick_x = (float)(!!(p->botones & HID_CIRC_DERECHA) - !!(p->botones & HID_CIRC_IZQUIERDA));
            e->stick_y = (float)(!!(p->botones & HID_CIRC_ARRIBA) - !!(p->botones & HID_CIRC_ABAJO));
        }
        if (p->toque) { e->tocando = 1; e->touch_x = p->tx; e->touch_y = p->ty; }
        if (p->stick) { e->stick_x = p->sx; e->stick_y = p->sy; }
        if (ultimo_aviso != (uint32_t)k && vblank == p->vb) {   /* un aviso por paso, al empezar */
            ultimo_aviso = (uint32_t)k;
            fprintf(stderr, "[guion] vblank %u: paso %d botones=0x%08X%s\n", vblank, k, p->botones,
                    p->toque ? " (toque)" : p->stick ? " (stick)" : "");
        }
    }
}
