/* Servicio gsp::Gpu (HLE) del port nativo. Ver gsp.h. Reimplementado en C a partir de la LECTURA de Azahar
 * (GPLv2: no se copio codigo). Sabotajes para la prueba: compilar con -DSABOTAJE=n (ver prueba_gsp.c). */
#include "gsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#ifndef SABOTAJE
#define SABOTAJE 0
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;

GspPicaFn gsp_pica;
void (*gsp_antes_de_leer)(uint32_t fisica, uint32_t tam);
void (*gsp_tras_fill)(uint32_t ini, uint32_t fin, uint32_t valor, uint32_t control);
int (*gsp_transfer_diferido)(uint32_t ent, uint32_t sal, const GspTransfer *t, uint32_t te, uint32_t ts);
void (*gsp_antes_de_escribir)(uint32_t fisica, uint32_t tam);
int gsp_presentando;
/* P1 (10 oct): avisos para la cache de texturas del raster (textura_para deja de re-hashear lo que no cambio).
   gsp_tras_escribir: TODA escritura de memoria hecha por la GPU emulada (copiar_fisica/copiar_virtual con escribir =
   fills, transfers, texcopy, DMA, bajadas de RT, copias de la re-ejecucion) + las escrituras de CPU que el juego avisa
   como en el 3DS real (Flush/InvalidateDataCache 0x08/0x09 y el GX 5 CacheFlush). Las escrituras de CPU sin aviso van
   directo a memoria (rt_pagina) y nadie las ve: para esas el raster re-valida una vez por cuadro (gsp_cuadro_tex).
   gsp_cuadro_tex: +1 en la DisplayTransfer de abajo (la que cierra el cuadro), NO en las re-ejecuciones del 144. */
void (*gsp_tras_escribir)(uint32_t fisica, uint32_t tam);
uint32_t gsp_cuadro_tex;

static GspAnfitrion A;
static GspEstadistica E;

/* ======================================================================= memoria compartida */
#define SHM_TAM          0x1000u
#define MAX_HILOS        4u
#define NADIE            0xFFFFFFFFu
#define COLA_SLOTS       0x34u
#define COLA_UMBRAL_PDC  0x20u
#define OFF_FB_UPDATE    0x200u
#define OFF_CMD_BUF      0x800u

static u8 *g_shm;
static u32 g_shm_handle;
static int g_primera = 1;

typedef struct {
    int usada;
    u32 sesion;
    u32 hilo;          /* id de hilo GSP (0..3) */
    int registrada;
    u32 evento;
} Sesion;
static Sesion g_ses[MAX_HILOS];

/* ======================================================================= registros */
#define N_GPU 0x800u   /* palabras desde 0x1EF00000 (la PICA llega a 0x732) */
#define N_LCD 0x400u   /* palabras desde 0x1ED02000 */
static u32 g_gpu[N_GPU];
static u32 g_lcd[N_LCD];

/* offsets en bytes desde 0x1EF00000 */
#define R_FILL(i)        (0x10u + (i) * 0x10u)       /* +0 ini, +4 fin, +8 valor, +C control */
#define R_FB(p)          (0x400u + (p) * 0x100u)     /* +68 izq1, +6C izq2, +70 formato, +78 select, +90 stride, +94/+98 der */
#define R_DT             0xC00u                      /* +0 ent, +4 sal, +8 tam sal, +C tam ent, +10 flags, +18 disparo, +20.. texcopy */
#define R_CMDBUF         0x18E0u                     /* +0/+4 tam/8, +8/+C dir/8, +10/+14 disparo */
/* offsets en bytes desde 0x1ED02000 */
#define L_FILL_ARRIBA    0x204u
#define L_FILL_ABAJO     0xA04u

#define GPU(off) g_gpu[(off) >> 2]

static void logf_(const char *fmt, ...)
{
    char b[256];
    va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
    if (A.log) A.log(b); else fprintf(stderr, "%s\n", b);
}

/* ======================================================================= direcciones */
uint32_t gsp_virtual_a_fisica(uint32_t v)
{
#if SABOTAJE == 5
    if (v >= 0x14000000u && v < 0x1C000000u) return v;                       /* lineal sin traducir */
#else
    if (v >= 0x14000000u && v < 0x1C000000u) return v - 0x14000000u + 0x20000000u;   /* heap lineal -> FCRAM */
#endif
    if (v >= 0x30000000u && v < 0x38000000u) return v - 0x30000000u + 0x20000000u;   /* heap lineal nuevo */
    if (v >= 0x1F000000u && v < 0x1F600000u) return v - 0x1F000000u + 0x18000000u;   /* VRAM */
    if (v >= 0x1FF00000u && v < 0x1FF80000u) return v;                               /* RAM del DSP */
    return 0;
}

uint32_t gsp_fisica_a_virtual(uint32_t f)
{
    if (f >= 0x20000000u && f < 0x28000000u) return f - 0x20000000u + 0x14000000u;
    if (f >= 0x18000000u && f < 0x18600000u) return f - 0x18000000u + 0x1F000000u;
    if (f >= 0x1FF00000u && f < 0x1FF80000u) return f;
    return 0;
}

static u8 *host_fis(u32 f)
{
    u32 v = gsp_fisica_a_virtual(f);
    if (!v || !A.puntero) return NULL;
    return A.puntero(v);
}

const uint8_t *gsp_fisica_a_host(uint32_t fisica, uint32_t tam)
{
    u8 *p0 = host_fis(fisica);
    if (!p0) return NULL;
    for (u32 o = 0x1000u - (fisica & 0xFFFu); o < tam; o += 0x1000u) {
        u8 *p = host_fis(fisica + o);
        if (p != p0 + o) return NULL;
    }
    return p0;
}

static int copiar_fisica(u32 fisica, u8 *buf, u32 tam, int escribir)
{
    u32 hecho = 0;
    if (escribir && gsp_tras_escribir) gsp_tras_escribir(fisica, tam);   /* P1 */
    while (hecho < tam) {
        u32 a = fisica + hecho;
        u32 trozo = 0x1000u - (a & 0xFFFu);
        if (trozo > tam - hecho) trozo = tam - hecho;
        u8 *p = host_fis(a);
        if (!p) return -1;
        if (escribir) memcpy(p, buf + hecho, trozo); else memcpy(buf + hecho, p, trozo);
        hecho += trozo;
    }
    return 0;
}
int gsp_leer_fisica(uint32_t fisica, void *dst, uint32_t tam) { return copiar_fisica(fisica, dst, tam, 0); }
int gsp_escribir_fisica(uint32_t fisica, const void *src, uint32_t tam) { return copiar_fisica(fisica, (u8 *)src, tam, 1); }

/* P1: aviso de escritura por direccion VIRTUAL (DMA, flush de cache): las regiones visibles por la GPU son lineales */
void gsp_cpu_escribio(uint32_t v, uint32_t tam)
{
    if (!gsp_tras_escribir || !tam) return;
    u32 f = gsp_virtual_a_fisica(v);
    if (f) gsp_tras_escribir(f, tam);
}

static int copiar_virtual(u32 v, u8 *buf, u32 tam, int escribir)
{
    u32 hecho = 0;
    if (escribir) gsp_cpu_escribio(v, tam);   /* P1 */
    while (hecho < tam) {
        u32 a = v + hecho;
        u32 trozo = 0x1000u - (a & 0xFFFu);
        if (trozo > tam - hecho) trozo = tam - hecho;
        u8 *p = A.puntero ? A.puntero(a) : NULL;
        if (!p) return -1;
        if (escribir) memcpy(p, buf + hecho, trozo); else memcpy(buf + hecho, p, trozo);
        hecho += trozo;
    }
    return 0;
}

/* ======================================================================= pixeles */
int gsp_bytes_pixel(int fmt)
{
    switch (fmt) {
    case GSP_RGBA8: return 4;
    case GSP_RGB8: return 3;
    case GSP_RGB565: case GSP_RGB5A1: case GSP_RGBA4: return 2;
    default: return 0;
    }
}

static u8 de5(u32 v) { return (u8)((v << 3) | (v >> 2)); }
static u8 de6(u32 v) { return (u8)((v << 2) | (v >> 4)); }
static u8 de4(u32 v) { return (u8)((v << 4) | v); }

void gsp_decodificar_pixel(int fmt, const uint8_t *p, uint8_t c[4])
{
    u32 h = (u32)p[0] | ((u32)p[1] << 8);
    switch (fmt) {
    case GSP_RGBA8: c[0] = p[3]; c[1] = p[2]; c[2] = p[1]; c[3] = p[0]; break;      /* en memoria: A B G R */
    case GSP_RGB8: c[0] = p[2]; c[1] = p[1]; c[2] = p[0]; c[3] = 255; break;        /* en memoria: B G R */
    case GSP_RGB565: c[0] = de5((h >> 11) & 31); c[1] = de6((h >> 5) & 63); c[2] = de5(h & 31); c[3] = 255; break;
    case GSP_RGB5A1: c[0] = de5((h >> 11) & 31); c[1] = de5((h >> 6) & 31); c[2] = de5((h >> 1) & 31);
                     c[3] = (h & 1) ? 255 : 0; break;
    case GSP_RGBA4: c[0] = de4((h >> 12) & 15); c[1] = de4((h >> 8) & 15); c[2] = de4((h >> 4) & 15); c[3] = de4(h & 15); break;
    default: c[0] = c[1] = c[2] = c[3] = 0; break;
    }
}

void gsp_codificar_pixel(int fmt, const uint8_t c[4], uint8_t *p)
{
    u32 h;
    switch (fmt) {
    case GSP_RGBA8: p[0] = c[3]; p[1] = c[2]; p[2] = c[1]; p[3] = c[0]; return;
    case GSP_RGB8: p[0] = c[2]; p[1] = c[1]; p[2] = c[0]; return;
#if SABOTAJE == 3
    case GSP_RGB565: h = ((u32)(c[0] >> 3) << 11) | ((u32)(c[1] >> 3) << 5) | (c[2] >> 3); break;   /* verde a 5 bits */
#else
    case GSP_RGB565: h = ((u32)(c[0] >> 3) << 11) | ((u32)(c[1] >> 2) << 5) | (c[2] >> 3); break;
#endif
    case GSP_RGB5A1: h = ((u32)(c[0] >> 3) << 11) | ((u32)(c[1] >> 3) << 6) | ((u32)(c[2] >> 3) << 1) | (c[3] >> 7); break;
    case GSP_RGBA4: h = ((u32)(c[0] >> 4) << 12) | ((u32)(c[1] >> 4) << 8) | ((u32)(c[2] >> 4) << 4) | (c[3] >> 4); break;
    default: return;
    }
    p[0] = (u8)h; p[1] = (u8)(h >> 8);
}

/* indice Morton dentro del mosaico 8x8: bits x0 y0 x1 y1 x2 y2 (x en los pares, y en los impares) */
static u32 morton8(u32 x, u32 y)
{
    u32 i = 0;
    for (u32 b = 0; b < 3; b++) {
#if SABOTAJE == 1
        i |= ((y >> b) & 1u) << (2 * b);          /* x e y cambiados */
        i |= ((x >> b) & 1u) << (2 * b + 1);
#else
        i |= ((x >> b) & 1u) << (2 * b);
        i |= ((y >> b) & 1u) << (2 * b + 1);
#endif
    }
    return i;
}

uint32_t gsp_offset_morton(uint32_t x, uint32_t y, uint32_t ancho, uint32_t bpp)
{
    /* mosaicos de 8x8 de izquierda a derecha; filas de mosaicos de arriba abajo (en orden de memoria) */
    return (morton8(x & 7u, y & 7u) + (x & ~7u) * 8u) * bpp + (y & ~7u) * ancho * bpp;
}

/* ======================================================================= DisplayTransfer / TextureCopy / MemoryFill */
#define T_VOLTEAR(f)   ((f) & 1u)
#define T_LINEAL(f)    (((f) >> 1) & 1u)
#define T_RECORTE(f)   (((f) >> 2) & 1u)
#define T_NOSWZ(f)     (((f) >> 5) & 1u)
#define T_FMT_E(f)     (((f) >> 8) & 7u)
#define T_FMT_S(f)     (((f) >> 12) & 7u)
#define T_ESCALA(f)    (((f) >> 24) & 3u)

static u32 dt_desplazamiento(const GspTransfer *t)
{
    /* voltear + recortar desplaza la salida (el hardware lo hace sesgado y hay juegos que dependen de eso) */
    u32 f = t->flags;
    if (T_VOLTEAR(f) && T_RECORTE(f) && t->ancho_entrada > t->ancho_salida && t->alto_salida > 0)
        return (t->ancho_entrada - t->ancho_salida) * (t->alto_salida - 1) * (u32)gsp_bytes_pixel((int)T_FMT_S(f));
    return 0;
}

void gsp_display_transfer_tam(const GspTransfer *t, uint32_t *te, uint32_t *ts)
{
    u32 f = t->flags, esc = T_ESCALA(f);
    u32 hs = esc != 0, vs = esc == 2;
    *te = t->ancho_entrada * t->alto_entrada * (u32)gsp_bytes_pixel((int)T_FMT_E(f));
    *ts = dt_desplazamiento(t) + (t->ancho_salida >> hs) * (t->alto_salida >> vs) * (u32)gsp_bytes_pixel((int)T_FMT_S(f));
}

int gsp_display_transfer(const uint8_t *entrada, uint8_t *salida, const GspTransfer *t)
{
    u32 f = t->flags, esc = T_ESCALA(f);
    int fe = (int)T_FMT_E(f), fs = (int)T_FMT_S(f);
    u32 be = (u32)gsp_bytes_pixel(fe), bs = (u32)gsp_bytes_pixel(fs);
    if (!be || !bs) return -1;
    if (!t->ancho_entrada || !t->alto_entrada || !t->ancho_salida || !t->alto_salida) return -1;
    if (esc > 2) return -1;
    if (T_LINEAL(f) && esc != 0) return -1;
    u32 hs = esc != 0, vs = esc == 2;
    u32 aw = t->ancho_salida >> hs, ah = t->alto_salida >> vs;
    u32 te, ts;
    gsp_display_transfer_tam(t, &te, &ts);
    salida += dt_desplazamiento(t);
    ts -= dt_desplazamiento(t);

    for (u32 y = 0; y < ah; y++) {
        for (u32 x = 0; x < aw; x++) {
            u32 ix = x << hs, iy = y << vs;
#if SABOTAJE == 6
            u32 oy = y;                                       /* volteo ignorado */
#else
            u32 oy = T_VOLTEAR(f) ? ah - y - 1 : y;
#endif
            u32 so, dof;
            if (T_LINEAL(f)) {
                so = (ix + iy * t->ancho_entrada) * be;
                dof = T_NOSWZ(f) ? (x + oy * aw) * bs : gsp_offset_morton(x, oy, aw, bs);
            } else {
                so = gsp_offset_morton(ix, iy, t->ancho_entrada, be);
                dof = T_NOSWZ(f) ? gsp_offset_morton(x, oy, aw, bs) : (x + oy * aw) * bs;
            }
            u32 vecinos = esc == 1 ? 1 : esc == 2 ? 3 : 0;
            if (so + (vecinos + 1) * be > te || dof + bs > ts) continue;   /* fuera de rango: no se toca */
            u8 c[4], d[4];
            gsp_decodificar_pixel(fe, entrada + so, c);
            if (vecinos) {
                u32 s[4] = { c[0], c[1], c[2], c[3] };
                for (u32 k = 1; k <= vecinos; k++) {
                    gsp_decodificar_pixel(fe, entrada + so + k * be, d);
                    for (int j = 0; j < 4; j++) s[j] += d[j];
                }
                for (int j = 0; j < 4; j++) c[j] = (u8)(s[j] / (vecinos + 1));
            }
            gsp_codificar_pixel(fs, c, salida + dof);
        }
    }
    return 0;
}

/* recorre el TextureCopy: si ent/sal no son NULL copia; devuelve por puntero los bytes que alcanza en cada lado */
static void texcopy(const u8 *ent, u8 *sal, u32 tam, u32 re, u32 rs, u32 *te, u32 *ts)
{
    u32 resto = tam & ~15u;
    u32 hue_e = (re >> 16) * 16u, hue_s = (rs >> 16) * 16u;
    u32 an_e = hue_e == 0 ? resto : (re & 0xFFFFu) * 16u;   /* hueco 0 = contiguo aunque el ancho sea 0 */
    u32 an_s = hue_s == 0 ? resto : (rs & 0xFFFFu) * 16u;
    u32 pe = 0, ps = 0;
    *te = *ts = 0;
    if (!resto || !an_e || !an_s) return;
    u32 qe = an_e, qs = an_s;
    while (resto) {
        u32 n = qe < qs ? qe : qs;
        if (resto < n) n = resto;
        if (ent && sal) memcpy(sal + ps, ent + pe, n);
        pe += n; ps += n; qe -= n; qs -= n; resto -= n;
        if (pe > *te) *te = pe;
        if (ps > *ts) *ts = ps;
        if (!qe) { qe = an_e; pe += hue_e; }
        if (!qs) { qs = an_s; ps += hue_s; }
    }
}
void gsp_texture_copy(const uint8_t *e, uint8_t *s, uint32_t tam, uint32_t re, uint32_t rs)
{
    u32 a, b;
    texcopy(e, s, tam, re, rs, &a, &b);
}
void gsp_texture_copy_tam(uint32_t tam, uint32_t re, uint32_t rs, uint32_t *te, uint32_t *ts)
{
    texcopy(NULL, NULL, tam, re, rs, te, ts);
}

void gsp_memory_fill(uint8_t *ini, uint8_t *fin, uint32_t valor, uint32_t control)
{
    if (fin <= ini) return;
    if ((control >> 8) & 1u) {                       /* 24 bits: r,g,b en los bytes 0,1,2 del valor */
        for (u8 *p = ini; p < fin; p += 3)
            for (int k = 0; k < 3 && p + k < fin; k++) p[k] = (u8)(valor >> (8 * k));
    } else if ((control >> 9) & 1u) {
        for (u8 *p = ini; p + 4 <= fin; p += 4) memcpy(p, &valor, 4);
    } else {
        u16 v = (u16)valor;
        for (u8 *p = ini; p + 2 <= fin; p += 2) memcpy(p, &v, 2);
    }
}

/* ======================================================================= interrupciones */
static Sesion *sesion_de_hilo(u32 hilo)
{
    for (u32 i = 0; i < MAX_HILOS; i++)
        if (g_ses[i].usada && g_ses[i].hilo == hilo) return &g_ses[i];
    return NULL;
}

static void aprender_ojo_derecho(u32 izq, u32 der);   /* un solo ojo: mas abajo */

/* lee la info de framebuffer del hilo: si esta "dirty" (o forzado) la aplica a los registros y limpia la marca */
static void aplicar_fb_update(u32 hilo, u32 pantalla)
{
    u8 *u = g_shm + OFF_FB_UPDATE + (2u * hilo + pantalla) * 0x40u;
#if SABOTAJE != 2                                             /* sabotaje 2: marca ignorada, se aplica siempre */
    if (!(u[1] & 1u)) return;
#endif
    u32 info[7];
    memcpy(info, u + 4 + (u[0] & 1u) * 0x1Cu, sizeof info);
    u[1] &= (u8)~1u;
    u32 fb = R_FB(pantalla);
    u32 izq = gsp_virtual_a_fisica(info[1]), der = gsp_virtual_a_fisica(info[2]);
    if (pantalla == 0) aprender_ojo_derecho(izq, der);
    if (info[0] == 0) { GPU(fb + 0x68) = izq; GPU(fb + 0x94) = der; }
    else              { GPU(fb + 0x6C) = izq; GPU(fb + 0x98) = der; }
    GPU(fb + 0x90) = info[3];
    GPU(fb + 0x70) = info[4];
    GPU(fb + 0x78) = info[5];
    E.swaps++;
}

/* ======================================================================= un solo ojo (7 oct, idea del dueno)
   Cada cuadro: [limpiar + dibujar ojo IZQUIERDO -> transfer a un fb izquierdo] [limpiar + dibujar ojo DERECHO (los
   mismos 132 dibujos) -> transfer a un fb derecho] [limpiar + dibujar ABAJO -> transfer de abajo]. El port solo
   muestra el izquierdo: el derecho es la mitad del trabajo 3D tirada. Salvaguardas:
   - los fb derechos se APRENDEN de lo que el juego configura (info[2] del swap), no se adivinan;
   - solo se saltan dibujos de la pantalla de ARRIBA (viewport de 400) y solo si el cuadro anterior fue estereo;
   - si tras saltar llega una transfer que NO es al ojo derecho, se apaga el salto 120 cuadros y se avisa. */
int gsp_ojo_derecho;
static u32 g_der[4];
static int g_nder, g_un_ojo = -1, g_estereo_previo, g_der_en_cuadro, g_enfriar;
static u32 g_der_saltadas, g_der_avisos;

static void aprender_ojo_derecho(u32 izq, u32 der)
{
    if (!der || der == izq) return;
    for (int k = 0; k < g_nder; k++) if (g_der[k] == der) return;
    if (g_nder < 4) g_der[g_nder++] = der;
}

static int es_fb_derecho(u32 sal)
{
    for (int k = 0; k < g_nder; k++) if (g_der[k] == sal) return 1;
    return 0;
}

static int un_ojo_activo(void)
{
    if (g_un_ojo < 0) { const char *s = getenv("SM3DL_UN_OJO"); g_un_ojo = !(s && *s == '0'); }
    return g_un_ojo && !g_enfriar;
}

static void interrupcion_hilo(int id, u32 hilo)
{
    Sesion *s = sesion_de_hilo(hilo);
    if (!s || !s->registrada || !g_shm) return;
    u8 *q = g_shm + hilo * 0x40u;   /* +0 indice, +1 cuenta, +2 error, +3 config, +4/+8 PDC perdidos, +C slots */
    int pdc = id == GSP_INT_PDC0 || id == GSP_INT_PDC1;
    int encolar = 1;
    if (pdc) {
        if (q[3] & 1u) encolar = 0;                       /* el hilo pidio ignorar los PDC */
        else if (q[1] >= COLA_UMBRAL_PDC) {
            u32 *perdidos = (u32 *)(q + (id == GSP_INT_PDC0 ? 4 : 8));
            (*perdidos)++;
            encolar = 0;
        }
    }
    if (encolar) {
        if (q[1] >= COLA_SLOTS) q[2] = 1;                 /* cola llena */
        else {
#if SABOTAJE == 4
            u32 sig = (u32)q[0] + q[1];                   /* sin vuelta al principio */
#else
            u32 sig = ((u32)q[0] + q[1]) % COLA_SLOTS;
#endif
            q[0x0C + sig] = (u8)id;
            q[1]++;
            if (A.senalar_evento) A.senalar_evento(s->evento);
        }
    }
    if (pdc) aplicar_fb_update(hilo, id == GSP_INT_PDC0 ? 0u : 1u);
}

#include "gsp_interp.inc"

void gsp_interrupcion(int id)
{
    if (!g_shm || g_repitiendo) return;   /* re-ejecucion de un cuadro (interpolacion): el juego no se entera */
    if (id == GSP_INT_PDC0 || id == GSP_INT_PDC1) {
        for (u32 h = 0; h < MAX_HILOS; h++) interrupcion_hilo(id, h);
        return;
    }
    if (E.hilo_con_derechos == NADIE) return;
    interrupcion_hilo(id, E.hilo_con_derechos);
}

/* ======================================================================= motores (por registros, como el hardware) */
static void ejecutar_fill(u32 i, int intr)
{
    u32 b = R_FILL(i);
    u32 ctl = GPU(b + 0xC);
    if (!(ctl & 1u)) return;
    op_regs((u8)(2u + i), b, 4);
    u32 ini = GPU(b) * 8u, fin = GPU(b + 4) * 8u;
    if (fin > ini && fin - ini <= 0x08000000u) {
        if (gsp_antes_de_escribir) gsp_antes_de_escribir(ini, fin - ini);
        u8 *buf = malloc(fin - ini);
        if (buf && gsp_leer_fisica(ini, buf, fin - ini) == 0) {
            if (E.fills < 6) logf_("MemoryFill 0x%08X-0x%08X valor 0x%08X control 0x%08X", ini, fin, GPU(b + 8), ctl);
            gsp_memory_fill(buf, buf + (fin - ini), GPU(b + 8), ctl);
            gsp_escribir_fisica(ini, buf, fin - ini);
            if (gsp_tras_fill) gsp_tras_fill(ini, fin, GPU(b + 8), ctl);
        } else logf_("[gsp] MemoryFill fuera de memoria: 0x%08X-0x%08X", ini, fin);
        free(buf);
    }
    E.fills++;
    if (ini != 0 && intr >= 0) gsp_interrupcion(intr == 0 ? GSP_INT_PSC0 : GSP_INT_PSC1);
    GPU(b + 0xC) = (ctl & ~1u) | 2u;   /* disparo a 0, "terminado" a 1 */
}

static void ejecutar_transfer(void)
{
    if (!(GPU(R_DT + 0x18) & 1u)) return;
    op_regs(4, R_DT, 11);
    u32 ent = GPU(R_DT) * 8u, sal = GPU(R_DT + 4) * 8u, flags = GPU(R_DT + 0x10);
    u32 te, ts, es_display = 0;
    int poner_der = 0;
    if ((flags >> 3) & 1u) {
        u32 tam = GPU(R_DT + 0x20), re = GPU(R_DT + 0x24), rs = GPU(R_DT + 0x28);
        gsp_texture_copy_tam(tam, re, rs, &te, &ts);
        if (gsp_antes_de_leer && te) gsp_antes_de_leer(ent, te);
        if (gsp_antes_de_escribir && ts) gsp_antes_de_escribir(sal, ts);
        u8 *a = te ? malloc(te) : NULL, *b = ts ? malloc(ts) : NULL;
        if (a && b && gsp_leer_fisica(ent, a, te) == 0 && gsp_leer_fisica(sal, b, ts) == 0) {
            gsp_texture_copy(a, b, tam, re, rs);
            gsp_escribir_fisica(sal, b, ts);
        } else if (te) logf_("[gsp] TextureCopy fuera de memoria: 0x%08X -> 0x%08X", ent, sal);
        free(a); free(b);
        E.texcopies++;
    } else {
        GspTransfer t;
        es_display = 1;
        u32 rs = GPU(R_DT + 8), re = GPU(R_DT + 0xC);
        t.ancho_entrada = re & 0xFFFFu; t.alto_entrada = re >> 16;
        t.ancho_salida = rs & 0xFFFFu; t.alto_salida = rs >> 16;
        t.flags = flags;
        gsp_display_transfer_tam(&t, &te, &ts);
        /* un solo ojo: la transfer del ojo derecho no se hace (nadie la ve) */
        int es_der = es_fb_derecho(sal), arriba = t.ancho_salida == 240u && t.alto_salida == 400u;
        if (es_der) {
            g_der_en_cuadro = 1;
            int saltar = gsp_ojo_derecho;
            gsp_ojo_derecho = 0;
            if (saltar) {
                E.transfers++;
                if (++g_der_saltadas % 1800 == 0) logf_("[un-ojo] %u transfers del ojo derecho saltadas", g_der_saltadas);
                goto transfer_hecho;
            }
        } else if (gsp_ojo_derecho) {   /* se esperaba el ojo derecho y llego otra cosa: no saltar por un rato */
            gsp_ojo_derecho = 0;
            g_enfriar = 120;
            if (g_der_avisos++ < 5)
                fprintf(stderr, "[un-ojo] AVISO: tras el ojo izquierdo llego una transfer a 0x%08X (no es ojo derecho): salto apagado 120 cuadros\n", sal);
        }
        if (!arriba && !es_der) {   /* la de abajo cierra el cuadro */
            if (!g_repitiendo) gsp_cuadro_tex++;   /* P1: frontera de re-validacion de texturas (no en intermedios) */
            g_estereo_previo = g_der_en_cuadro;
            g_der_en_cuadro = 0;
            if (g_enfriar) g_enfriar--;
        }
        poner_der = arriba && !es_der && g_estereo_previo && un_ojo_activo();
        if (gsp_transfer_diferido && te && ts && gsp_transfer_diferido(ent, sal, &t, te, ts)) {
            E.transfers++;
            goto transfer_hecho;
        }
        if (gsp_antes_de_leer && te) gsp_antes_de_leer(ent, te);
        if (gsp_antes_de_escribir && ts) gsp_antes_de_escribir(sal, ts);
        u8 *a = te ? malloc(te) : NULL, *b = ts ? malloc(ts) : NULL;
        if (a && b && gsp_leer_fisica(ent, a, te) == 0 && gsp_leer_fisica(sal, b, ts) == 0) {
            if (E.transfers < 4)
                logf_("DisplayTransfer 0x%08X -> 0x%08X flags 0x%08X entrada %ux%u salida %ux%u bytes0 %02X%02X%02X%02X",
                      ent, sal, flags, t.ancho_entrada, t.alto_entrada, t.ancho_salida, t.alto_salida, a[0], a[1], a[2], a[3]);
            if (gsp_display_transfer(a, b, &t) == 0) gsp_escribir_fisica(sal, b, ts);
            else logf_("[gsp] DisplayTransfer no soportado: flags 0x%08X", flags);
        } else if (te) logf_("[gsp] DisplayTransfer fuera de memoria: 0x%08X -> 0x%08X", ent, sal);
        free(a); free(b);
        E.transfers++;
    transfer_hecho:;
        if (poner_der) gsp_ojo_derecho = 1;   /* lo que se dibuje hasta la proxima transfer es el ojo derecho */
    }
    GPU(R_DT + 0x18) &= ~1u;
    gsp_interrupcion(GSP_INT_PPF);
    if (es_display && ts) quizas_cerrar_cuadro(sal, ts);
}

static void ejecutar_lista(u32 canal)
{
    if (!GPU(R_CMDBUF + 0x10 + 4 * canal)) return;
    u32 dir = GPU(R_CMDBUF + 8 + 4 * canal) * 8u, tam = GPU(R_CMDBUF + 4 * canal) * 8u;
    E.listas++;
    op_lista(dir, tam);
    if (gsp_pica) gsp_pica(dir, tam);
    else if (E.listas <= 8) logf_("[gsp] lista PICA 0x%08X (%u bytes) sin interprete", dir, tam);
    GPU(R_CMDBUF + 0x10 + 4 * canal) = 0;
    gsp_interrupcion(GSP_INT_P3D);
}

uint32_t gsp_leer_reg(uint32_t d)
{
    if (d >= GSP_REG_GPU_BASE && d < GSP_REG_GPU_BASE + N_GPU * 4) return g_gpu[(d - GSP_REG_GPU_BASE) >> 2];
    if (d >= GSP_REG_LCD_BASE && d < GSP_REG_LCD_BASE + N_LCD * 4) return g_lcd[(d - GSP_REG_LCD_BASE) >> 2];
    return 0;
}

void gsp_escribir_reg(uint32_t d, uint32_t v)
{
    if (d >= GSP_REG_LCD_BASE && d < GSP_REG_LCD_BASE + N_LCD * 4) { g_lcd[(d - GSP_REG_LCD_BASE) >> 2] = v; return; }
    if (!(d >= GSP_REG_GPU_BASE && d < GSP_REG_GPU_BASE + N_GPU * 4)) {
        logf_("[gsp] escritura a registro desconocido 0x%08X = 0x%08X", d, v);
        return;
    }
    u32 off = d - GSP_REG_GPU_BASE;
    g_gpu[off >> 2] = v;
    if (off == R_FILL(0) + 0xC) ejecutar_fill(0, 0);
    else if (off == R_FILL(1) + 0xC) ejecutar_fill(1, 1);
    else if (off == R_DT + 0x18) ejecutar_transfer();
    else if (off == R_CMDBUF + 0x10) ejecutar_lista(0);
    else if (off == R_CMDBUF + 0x14) ejecutar_lista(1);
}

/* ======================================================================= cola GX */
static void comando_gx(const u32 *c)
{
    u32 id = c[0] & 0xFFu;
    switch (id) {
    case 0: {                                             /* RequestDma: copia virtual -> virtual */
        u32 tam = c[3];
        u8 *buf = tam ? malloc(tam) : NULL;
        if (buf && copiar_virtual(c[1], buf, tam, 0) == 0) copiar_virtual(c[2], buf, tam, 1);
        else if (tam) logf_("[gsp] DMA fuera de memoria: 0x%08X -> 0x%08X (%u)", c[1], c[2], tam);
        free(buf);
        E.dmas++;
        gsp_interrupcion(GSP_INT_DMA);
        break;
    }
    case 1:                                               /* ProcessCommandList */
        GPU(R_CMDBUF) = c[2] >> 3;
        GPU(R_CMDBUF + 8) = gsp_virtual_a_fisica(c[1]) >> 3;
        gsp_escribir_reg(GSP_REG_GPU_BASE + R_CMDBUF + 0x10, 1);
        break;
    case 2: {                                             /* MemoryFill: dos buffers; con los dos, solo PSC0 */
        int ambos = c[1] != 0 && c[4] != 0;
        if (c[1]) {
            GPU(R_FILL(0)) = gsp_virtual_a_fisica(c[1]) >> 3;
            GPU(R_FILL(0) + 4) = gsp_virtual_a_fisica(c[3]) >> 3;
            GPU(R_FILL(0) + 8) = c[2];
            GPU(R_FILL(0) + 0xC) = c[7] & 0xFFFFu;
            ejecutar_fill(0, ambos ? -1 : 0);
        }
        if (c[4]) {
            GPU(R_FILL(1)) = gsp_virtual_a_fisica(c[4]) >> 3;
            GPU(R_FILL(1) + 4) = gsp_virtual_a_fisica(c[6]) >> 3;
            GPU(R_FILL(1) + 8) = c[5];
            GPU(R_FILL(1) + 0xC) = c[7] >> 16;
            ejecutar_fill(1, ambos ? 0 : 1);
        }
        break;
    }
    case 3:                                               /* DisplayTransfer */
        GPU(R_DT) = gsp_virtual_a_fisica(c[1]) >> 3;
        GPU(R_DT + 4) = gsp_virtual_a_fisica(c[2]) >> 3;
        GPU(R_DT + 0xC) = c[3];
        GPU(R_DT + 8) = c[4];
        GPU(R_DT + 0x10) = c[5];
        gsp_escribir_reg(GSP_REG_GPU_BASE + R_DT + 0x18, 1);
        break;
    case 4:                                               /* TextureCopy */
        GPU(R_DT) = gsp_virtual_a_fisica(c[1]) >> 3;
        GPU(R_DT + 4) = gsp_virtual_a_fisica(c[2]) >> 3;
        GPU(R_DT + 0x20) = c[3];
        GPU(R_DT + 0x24) = c[4];
        GPU(R_DT + 0x28) = c[5];
        GPU(R_DT + 0x10) = c[6];
        gsp_escribir_reg(GSP_REG_GPU_BASE + R_DT + 0x18, 1);
        break;
    case 5:                                               /* CacheFlush: no hay caches que vaciar */
        for (int k = 0; k < 3; k++) if (c[1 + 2 * k]) gsp_cpu_escribio(c[1 + 2 * k], c[2 + 2 * k]);   /* P1: la CPU escribio ahi */
        break;
    default:
        logf_("[gsp] comando GX desconocido %u", id);
        break;
    }
}

void gsp_procesar_cola(void)
{
    if (!g_shm || E.hilo_con_derechos == NADIE) return;
    u8 *b = g_shm + OFF_CMD_BUF + E.hilo_con_derechos * 0x200u;
    /* cabecera: byte0 indice, byte1 cantidad, byte2 estado, byte3 "parar"; comandos desde +0x20 */
    while (b[1]) {
        if (b[3]) { b[2] = 1; break; }
        if (b[2] == 1) break;
        u32 c[8];
        memcpy(c, b + 0x20 + (u32)(b[0] % 15u) * 0x20u, sizeof c);
        b[1]--;
        b[0] = (u8)((b[0] + 1u) % 15u);
        comando_gx(c);
        if ((c[0] >> 16) & 0xFFu) b[2] = 1;               /* el comando pedia parar despues */
    }
}

/* ======================================================================= presentacion */
void gsp_framebuffer_a_rgba(const uint8_t *fb, int fmt, uint32_t stride, uint32_t ancho, uint32_t alto, uint8_t *rgba)
{
    u32 bpp = (u32)gsp_bytes_pixel(fmt);
    /* el LCD esta girado: cada "fila" de memoria (stride) es una COLUMNA de la pantalla, de abajo hacia arriba */
    for (u32 y = 0; y < alto; y++)
        for (u32 x = 0; x < ancho; x++) {
            u8 *o = rgba + (y * ancho + x) * 4u;
            if (!bpp) { o[0] = o[1] = o[2] = 0; o[3] = 255; continue; }
            gsp_decodificar_pixel(fmt, fb + x * stride + (alto - 1u - y) * bpp, o);
            o[3] = 255;
        }
}

static u8 g_img[2][400 * 240 * 4];

static void presentar(u32 p)
{
    if (!A.presentar) return;
    GspPresentacion r;
    memset(&r, 0, sizeof r);
    u32 b = R_FB(p);
    u32 sel = GPU(b + 0x78) & 1u;
    r.pantalla = (int)p;
    r.dir_fisica = sel ? GPU(b + 0x6C) : GPU(b + 0x68);
    r.formato = GPU(b + 0x70);
    r.stride = GPU(b + 0x90);
    r.ancho = p == 0 ? 400u : 320u;
    r.alto = 240u;
    u32 relleno = g_lcd[(p == 0 ? L_FILL_ARRIBA : L_FILL_ABAJO) >> 2];
    r.negro = (relleno >> 24) & 1u;
    int fmt = (int)(r.formato & 7u);
    u32 bpp = (u32)gsp_bytes_pixel(fmt);
    if (r.negro) {
        for (u32 i = 0; i < r.ancho * r.alto; i++) {
            u8 *o = g_img[p] + i * 4u;
            o[0] = (u8)relleno; o[1] = (u8)(relleno >> 8); o[2] = (u8)(relleno >> 16); o[3] = 255;
        }
        r.rgba = g_img[p];
    } else if (bpp && r.stride >= 240u * bpp && r.dir_fisica) {
        u32 tam = (r.ancho - 1u) * r.stride + 240u * bpp;
        u8 *fb = malloc(tam);
        gsp_presentando = 1;
        if (gsp_antes_de_leer) gsp_antes_de_leer(r.dir_fisica, tam);
        gsp_presentando = 0;
        if (fb && gsp_leer_fisica(r.dir_fisica, fb, tam) == 0) {
            gsp_framebuffer_a_rgba(fb, fmt, r.stride, r.ancho, r.alto, g_img[p]);
            r.rgba = g_img[p];
        }
        free(fb);
    }
    E.presentaciones++;
    A.presentar(&r);
}

void gsp_vblank(void)
{
    E.vblanks++;
    gsp_interrupcion(GSP_INT_PDC0);
    gsp_interrupcion(GSP_INT_PDC1);
    presentar(0);
    presentar(1);
    vivo_vblank();   /* interpolacion en vivo: tras mostrar el intermedio, vuelve la imagen real (gsp_interp.inc) */
}

/* ======================================================================= IPC */
static Sesion *sesion(u32 id)
{
    for (u32 i = 0; i < MAX_HILOS; i++)
        if (g_ses[i].usada && g_ses[i].sesion == id) return &g_ses[i];
    /* sesion nueva: primer id de hilo libre (como el GSP real, al conectar) */
    for (u32 h = 0; h < MAX_HILOS; h++) {
        if (sesion_de_hilo(h)) continue;
        for (u32 i = 0; i < MAX_HILOS; i++)
            if (!g_ses[i].usada) {
                memset(&g_ses[i], 0, sizeof g_ses[i]);
                g_ses[i].usada = 1; g_ses[i].sesion = id; g_ses[i].hilo = h;
                return &g_ses[i];
            }
    }
    return NULL;
}

#define RES_REG_RANGO     0xE0E02A01u
#define RES_REG_ALINEADO  0xE0E02BF2u
#define RES_REG_TAMANO    0xE0E02BECu
#define RES_PRIMERA_INIT  0x00002A07u

static void responder(u32 *cmd, u32 id, u32 normales, u32 traducidos, u32 res)
{
    cmd[0] = (id << 16) | (normales << 6) | traducidos;
    cmd[1] = res;
}

static u32 validar_regs(u32 dir, u32 tam)
{
    if ((dir & 3u) || dir >= 0x420000u) return RES_REG_RANGO;
    if (tam > 0x80u) return RES_REG_TAMANO;
    if (tam & 3u) return RES_REG_ALINEADO;
    return 0;
}

void gsp_ipc(uint32_t *cmd, uint32_t id_sesion)
{
    u32 cab = cmd[0], id = cab >> 16;
    Sesion *s = sesion(id_sesion);
    if (!s) { logf_("[gsp] demasiadas sesiones"); responder(cmd, id, 1, 0, 0xD8E0080Au); return; }

    switch (id) {
    case 0x01:                                            /* WriteHWRegs(dir, tam, buffer estatico) */
    case 0x02: {                                          /* WriteHWRegsWithMask(dir, tam, datos, mascaras) */
        u32 dir = cmd[1], tam = cmd[2], dat = cmd[4], msk = id == 2 ? cmd[6] : 0;
        u32 r = validar_regs(dir, tam);
        if (!r) {
            for (u32 o = 0; o < tam; o += 4) {
                u32 v = 0, m = 0xFFFFFFFFu;
                if (copiar_virtual(dat + o, (u8 *)&v, 4, 0)) { r = RES_REG_RANGO; break; }
                if (id == 2 && copiar_virtual(msk + o, (u8 *)&m, 4, 0)) { r = RES_REG_RANGO; break; }
                u32 d = 0x1EB00000u + dir + o;
                gsp_escribir_reg(d, (gsp_leer_reg(d) & ~m) | (v & m));
            }
        }
        responder(cmd, id, 1, 0, r);
        return;
    }
    case 0x04: {                                          /* ReadHWRegs(dir, tam) -> buffer estatico 0 */
        u32 dir = cmd[1], tam = cmd[2] > 0x80u ? 0x80u : cmd[2];
        u32 r = ((dir & 3u) || dir >= 0x420000u) ? RES_REG_RANGO : (tam & 3u) ? RES_REG_ALINEADO : 0;
        if (r) { responder(cmd, id, 1, 0, r); return; }
        u32 destino = cmd[0x40 + 1];                      /* TLS+0x180: descriptor y direccion del buffer 0 */
        for (u32 o = 0; o < tam; o += 4) {
            u32 v = gsp_leer_reg(0x1EB00000u + dir + o);
            copiar_virtual(destino + o, (u8 *)&v, 4, 1);
        }
        responder(cmd, id, 1, 2, 0);
        cmd[2] = (tam << 14) | 2u;
        cmd[3] = destino;
        return;
    }
    case 0x08: case 0x09:                                 /* Flush/InvalidateDataCache: no hay cache */
        gsp_cpu_escribio(cmd[1], cmd[2]);                 /* P1: (dir, tam) que la CPU acaba de escribir */
        responder(cmd, id, 1, 0, 0);
        return;
    case 0x0B: {                                          /* SetLcdForceBlack(bool) */
        u32 v = (cmd[1] & 0xFFu) ? (1u << 24) : 0;
        g_lcd[L_FILL_ARRIBA >> 2] = v;
        g_lcd[L_FILL_ABAJO >> 2] = v;
        E.forzar_negro = v != 0;
        responder(cmd, id, 1, 0, 0);
        return;
    }
    case 0x0C:                                            /* TriggerCmdReqQueue */
        gsp_procesar_cola();
        responder(cmd, id, 1, 0, 0);
        return;
    case 0x13: {                                          /* RegisterInterruptRelayQueue(flags, evento) */
        if (!g_shm) {
            if (!A.crear_shm) { responder(cmd, id, 1, 0, 0xD8E0080Au); return; }
            g_shm_handle = A.crear_shm(SHM_TAM, &g_shm);
        }
        s->evento = cmd[3];
        s->registrada = 1;
        responder(cmd, id, 2, 2, g_primera ? RES_PRIMERA_INIT : 0);
        g_primera = 0;
        cmd[2] = s->hilo;
        cmd[3] = 0;                                       /* descriptor: copiar 1 handle */
        cmd[4] = g_shm_handle;
        return;
    }
    case 0x14:                                            /* UnregisterInterruptRelayQueue */
        s->registrada = 0; s->evento = 0;
        responder(cmd, id, 1, 0, 0);
        return;
    case 0x16:                                            /* AcquireRight(flags, proceso) */
    case 0x0F:                                            /* TryAcquireRight(proceso) */
        if (E.hilo_con_derechos == NADIE) E.hilo_con_derechos = s->hilo;
        responder(cmd, id, 1, 0, 0);
        return;
    case 0x17:                                            /* ReleaseRight */
        if (E.hilo_con_derechos == s->hilo) E.hilo_con_derechos = NADIE;
        responder(cmd, id, 1, 0, 0);
        return;
    case 0x18: {                                          /* ImportDisplayCaptureInfo -> 2 x {izq, der, formato, stride} */
        responder(cmd, id, 9, 0, 0);
        for (u32 p = 0; p < 2; p++) {
            u32 b = R_FB(p), sel = GPU(b + 0x78) & 1u;
            cmd[2 + p * 4] = gsp_fisica_a_virtual(sel ? GPU(b + 0x6C) : GPU(b + 0x68));
            cmd[3 + p * 4] = gsp_fisica_a_virtual(sel ? GPU(b + 0x98) : GPU(b + 0x94));
            cmd[4 + p * 4] = GPU(b + 0x70);
            cmd[5 + p * 4] = GPU(b + 0x90);
        }
        return;
    }
    default:                                              /* SaveVramSysArea, RestoreVramSysArea, SetInternalPriorities... */
        responder(cmd, id, 1, 0, 0);
        return;
    }
}

void gsp_iniciar(const GspAnfitrion *a)
{
    memset(&A, 0, sizeof A);
    if (a) A = *a;
    memset(&E, 0, sizeof E);
    E.hilo_con_derechos = NADIE;
    memset(g_ses, 0, sizeof g_ses);
    memset(g_gpu, 0, sizeof g_gpu);
    memset(g_lcd, 0, sizeof g_lcd);
    g_shm = NULL; g_shm_handle = 0; g_primera = 1;
}

const GspEstadistica *gsp_estadistica(void) { return &E; }
