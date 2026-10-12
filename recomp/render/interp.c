/* Interpolacion de cuadros (>30 FPS nativos) — 7 oct noche. Ver reportes\interpolacion.md.
 *
 * Estudio (SM3DL_ESTUDIO_INTERP, tools\estudio_interp.py): el juego corre a 30 FPS; el 99,4 % de los dibujos de un
 * cuadro se emparejan con los del siguiente por su HUELLA (programa, buffers, texturas, RT) y el 100 % de los
 * emparejados usa los MISMOS vertices: toda la animacion viaja en los uniforms del vertex shader. Un cuadro intermedio
 * = re-ejecutar las operaciones de GPU del cuadro C con los uniforms de cada dibujo mezclados con los de su pareja en
 * el cuadro anterior.
 *
 * Este archivo guarda, por cuadro, la tabla (huella, uniforms) de cada dibujo y, durante una re-ejecucion, reemplaza
 * los uniforms de cada dibujo por mezcla(pareja, actual, t) y los RESTAURA despues (los uniforms persisten entre
 * dibujos: si no se restauran, el siguiente dibujo mezclaria sobre lo ya mezclado).
 * gsp_interp.inc decide los cuadros, hace la re-ejecucion y presenta el intermedio.
 *
 * Interruptor: interp_vivo (menu de ajustes "Cuadros: 60 interpolados", sm3dl_ajustes.ini "interpolar=1", o
 * SM3DL_INTERP=1). Con interp_vivo = 0 y sin SM3DL_REPETIR no se graba nada: el camino de siempre.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stddef.h>
#include "pica.h"

extern void (*pica_raster)(const PicaEstado *e);
extern void (*pica_interp)(PicaEstado *e);
extern void (*gsp_interp_cerrar)(void);
extern void (*gsp_interp_repetir)(int modo, float t);
extern void (*gsp_interp_lista)(const uint32_t *p, uint32_t n);
extern int (*gsp_interp_rapido_listo)(void);   /* H1: cinta de intermedios (gsp_interp.inc) */
extern void (*gsp_interp_rapido_op)(int k);
extern void (*gsp_interp_rapido_cifras)(char *b, size_t n);
void raster_cinta_cifras(char *b, size_t n);
extern void (*gsp_interp_cuenta)(uint32_t *emparejados, uint32_t *sueltos);
extern void (*gsp_interp_alta)(uint32_t sal, int restaurar);
extern int *gsp_interp_vivo;
extern void (*gsp_interp_diag)(int on, int excluir);
extern int (*gsp_interp_diag_n)(void);
extern void (*gsp_interp_diag_linea)(FILE *f, int k, uint32_t px, int x0, int y0, int x1, int y1);
void raster_alta_instantanea(uint32_t sal, int restaurar);

int interp_vivo;            /* 1 = presentar cuadros intermedios (60 FPS) */
static int g_prueba;        /* SM3DL_REPETIR: prueba de laboratorio (graba aunque interp_vivo = 0) */

static Pica g_copia_pica;   /* el estado PICA del juego se guarda antes de re-ejecutar y se restaura despues */
static void lista(const uint32_t *p, uint32_t n) { pica_ejecutar_palabras(p, n); }

#define MAX_DIB 2048
typedef struct { uint32_t h; PicaVec4 f[96]; } Dib;
static Dib *g_tab[3];        /* rotan por cuadro: g_ord[0] = dos atras, [1] = anterior, [2] = el que se esta grabando */
static int g_n[3], g_ord[3] = { 0, 1, 2 };
static uint8_t g_usado[MAX_DIB];
static uint8_t g_usado_a[MAX_DIB];   /* PARPADEO (10 oct): candidatas de A ya tomadas en esta re-ejecucion */
static uint32_t g_dos_atras, g_tex_mezcla;
/* modo: 0 grabar; 1 re-ejecutar mezclando contra g_ord[0] (prueba: C contra A); 3 mezclando contra g_ord[1]
   (en vivo: C contra B); 2 re-ejecutar SIN mezclar */
static int g_modo;
static float g_t;
static uint32_t g_emparejados, g_sueltos, g_sin_mezcla, g_vetados, g_saltos;

static uint32_t fnv(const uint32_t *p, size_t n, uint32_t h)
{
    for (size_t k = 0; k < n; k++) { h ^= p[k]; h *= 16777619u; }
    return h;
}

/* H1 (cinta de intermedios D3D12): estado falso armado por rapido_op(); su huella y su programa son los grabados */
static PicaEstado *g_rap_e;
static uint32_t g_rap_h;
static const void *g_rap_prog;
static uint32_t huella(const PicaEstado *e)
{
    if (e == g_rap_e) return g_rap_h;
    uint32_t h = fnv(e->vs.codigo, 512, 2166136261u);
    h = fnv(e->vs.swizzles, 128, h);
    uint32_t v[12] = { e->vs.entrada, e->color_dir, e->vtx.base_fisica, e->idx.offset, e->idx.num_vertices,
                       e->idx.vertex_offset, e->tex[0].activa ? e->tex[0].direccion : 0,
                       e->tex[1].activa ? e->tex[1].direccion : 0, e->tex[2].activa ? e->tex[2].direccion : 0,
                       e->idx.topologia, e->usa_gs, 0 };
    return fnv(v, 12, h);
}

/* ---- SEMANTICA (8 oct, tras la prueba del dueno en W2-2: el pozo de veneno se veia mal SOLO a 60) ----
   Los DVLB del juego traen el NOMBRE de cada uniform (WrldMtx, ViewMtx, ProjMtx, TexMtx0, UnivReg = huesos...).
   tools\gen_interp_programas.py genera interp_programas.h: por programa, la clase de cada registro c0-c95:
     0 OBJETO (matriz del objeto, huesos, colores): se mezcla solo si el dibujo tiene pareja segura;
     1 CAMARA (ViewMtx/ProjMtx): se mezcla SIEMPRE, tambien en dibujos sin pareja (particulas, repetidos): asi todo
       lo 3D sigue a la camara a 60 FPS aunque su objeto vaya a 30;
     2 REAL (TexMtx/TexTran/UV): animacion de textura, NUNCA se mezcla (la causa probable del veneno: su
       desplazamiento de textura se mezclaba y la regla de saltos solo cubria vueltas de ~1);
     3 TIEMPO (particulas): se mezcla si avanza; si vuelve atras (ciclo), real;
     4 sin nombre: mezcla ciega con la regla de saltos (lo de antes).
   Programa desconocido (no esta en la tabla): todo como antes. SM3DL_INTERP_SEMANTICA=0 vuelve al camino viejo. */
#include "interp_programas.h"

typedef struct { uint32_t clave; const InterpPrograma *p; } CacheProg;
static CacheProg g_cache[64];
static const InterpPrograma *programa(const PicaEstado *e)
{
    if (e == g_rap_e) return (const InterpPrograma *)g_rap_prog;
    uint32_t clave = fnv(e->vs.codigo, 16, 2166136261u) ^ (e->vs.entrada * 2654435761u) ^ 1u;
    CacheProg *c = &g_cache[clave & 63];
    if (c->clave == clave) return c->p;
    const InterpPrograma *r = NULL;
    for (int k = 0; k < N_INTERP_PROGRAMAS && !r; k++)
        if (g_programas[k].main == e->vs.entrada && !memcmp(g_programas[k].cod, e->vs.codigo, sizeof g_programas[k].cod))
            r = &g_programas[k];
    c->clave = clave;
    c->p = r;
    return r;
}

/* camaras de cada cuadro: los valores distintos de los registros de CAMARA (con su forma: primer registro + cuantos) */
#define MAX_CAM 16
typedef struct { uint8_t r0, n; PicaVec4 v[8]; } Cam;
static Cam g_cams[3][MAX_CAM];
static int g_ncam[3];
static uint32_t g_solo_cam, g_cortes, g_reconocidos, g_desconocidos, g_tex_real;

/* ---- diagnostico F9 (8 oct): por dibujo de la re-ejecucion, su decision y sus uniforms de B (pareja) y C ---- */
typedef struct { const char *prog; int dec, prof, cam, st, stw, stop; uint32_t h; PicaVec4 a[96], c[96]; } DiagDib;
#define MAX_DIAG 1024
static DiagDib *g_diag;
static int g_ndiag, g_diag_on, g_excluir = -1, g_idx;
static void diag_reg(int idx, const InterpPrograma *p, int dec, int cam, const PicaEstado *e, const PicaVec4 *a, const PicaVec4 *c)
{
    if (!g_diag_on || idx >= MAX_DIAG) return;
    if (!g_diag && !(g_diag = calloc(MAX_DIAG, sizeof *g_diag))) return;
    DiagDib *d = &g_diag[idx];
    d->prog = p ? p->nombre : "?";
    d->dec = dec; d->prof = e->depth_test; d->cam = cam; d->h = huella(e);
    d->st = e->stencil_test; d->stw = e->stencil_wmask;
    d->stop = e->stencil_fail | e->stencil_zfail << 4 | e->stencil_zpass << 8;
    memcpy(d->c, c, sizeof d->c);
    if (a) memcpy(d->a, a, sizeof d->a); else memcpy(d->a, c, sizeof d->a);
    if (idx + 1 > g_ndiag) g_ndiag = idx + 1;
}
static void diag_modo(int on, int excluir) { g_diag_on = on; g_excluir = excluir; if (on) g_ndiag = 0; }
static int diag_n(void) { return g_ndiag; }
static const char *DEC[] = { "2D-sin-mezcla", "sin-pareja", "repetido-vetado", "MEZCLADO" };
static void diag_linea(FILE *f, int k, uint32_t px, int x0, int y0, int x1, int y1)
{
    if (k >= g_ndiag || !g_diag) return;
    const DiagDib *d = &g_diag[k];
    fprintf(f, "dibujo %3d  %-40s %-16s prof=%d cam=%d stencil=%d/%02X/%03X huella=%08X  pantalla: %6u px", k, d->prog, DEC[d->dec], d->prof, d->cam, d->st, d->stw, d->stop, d->h, px);
    if (px) fprintf(f, " en x %d-%d y %d-%d", x0, x1, y0, y1);
    fprintf(f, "\n");
    if (!px && !d->st) return;   /* H2: las pasadas de stencil (sombras) con sus uniforms aunque no muevan pixeles */
    const InterpPrograma *p = NULL;
    for (int j = 0; j < N_INTERP_PROGRAMAS; j++) if (g_programas[j].nombre == d->prog) p = &g_programas[j];
    for (int r = 0; r < 96; r++) {
        const PicaVec4 *a = &d->a[r], *c = &d->c[r];
        if (!memcmp(a, c, sizeof *a)) continue;
        fprintf(f, "    c%-2d clase %d  B (%10.5f %10.5f %10.5f %10.5f)  C (%10.5f %10.5f %10.5f %10.5f)\n", r, p ? p->clase[r] : 9,
                a->x, a->y, a->z, a->w, c->x, c->y, c->z, c->w);
    }
}

static int regs_camara(const InterpPrograma *p, uint8_t *r0)
{
    int n = 0;
    for (int k = 0; k < 96; k++)
        if (p->clase[k] == 1) { if (!n) *r0 = (uint8_t)k; n++; }
    return n > 8 ? 8 : n;   /* contiguos en todos los programas del juego (c86-c92, o c0-c3) */
}

static void grabar_camara(const PicaEstado *e, const InterpPrograma *p, int t)
{
    uint8_t r0 = 0;
    int n = regs_camara(p, &r0);
    if (!n || !e->depth_test) return;
    for (int j = 0; j < g_ncam[t]; j++) {
        Cam *c = &g_cams[t][j];
        if (c->r0 == r0 && c->n == n && !memcmp(c->v, &e->vs.f[r0], n * sizeof(PicaVec4))) return;
    }
    if (g_ncam[t] >= MAX_CAM) return;
    Cam *c = &g_cams[t][g_ncam[t]++];
    c->r0 = r0;
    c->n = (uint8_t)n;
    memcpy(c->v, &e->vs.f[r0], n * sizeof(PicaVec4));
}

/* pone en e la camara mezclada: la de este dibujo (exacta en el cuadro actual) con la MAS CERCANA del anterior.
   Un corte de camara (cambio grande) no se mezcla. Devuelve 1 si cambio algo. */
static int mezclar_camara(PicaEstado *e, const InterpPrograma *p, int r, int cur, float t)
{
    uint8_t r0 = 0;
    int n = regs_camara(p, &r0);
    if (!n) return 0;
    int esta = 0;
    for (int j = 0; j < g_ncam[cur] && !esta; j++) {
        const Cam *c = &g_cams[cur][j];
        esta = c->r0 == r0 && c->n == n && !memcmp(c->v, &e->vs.f[r0], n * sizeof(PicaVec4));
    }
    if (!esta) return 0;
    const Cam *mejor = NULL;
    double dm = 1e300, mag = 0;
    const float *y = &e->vs.f[r0].x;
    for (int j = 0; j < g_ncam[r]; j++) {
        const Cam *c = &g_cams[r][j];
        if (c->r0 != r0 || c->n != n) continue;
        double d = 0;
        for (int q = 0; q < n * 4; q++) d += fabs((double)(&c->v[0].x)[q] - (double)y[q]);
        if (d < dm) { dm = d; mejor = c; }
    }
    if (!mejor) return 0;
    for (int q = 0; q < n * 4; q++) mag += fabs((double)y[q]);
    if (dm > 0.25 * mag) { g_cortes++; return 0; }
    const float *a = &mejor->v[0].x;
    float *o = &e->vs.f[r0].x;
    for (int q = 0; q < n * 4; q++) o[q] = a[q] + (y[q] - a[q]) * t;
    return 1;
}


static uint32_t g_mat_mezcladas, g_mat_grandes, g_huesos_real;
/* o, a (pareja = cuadro anterior), c (actual): 3 filas de una matriz 3x4 (xyz = fila de la 3x3, w = traslacion) */
static void mezclar_matriz(PicaVec4 *o, const PicaVec4 *a, const PicaVec4 *c, float t)
{
    double dif = 0, na = 0, nc = 0;
    for (int i = 0; i < 3; i++) {
        const float *x = &a[i].x, *y = &c[i].x;
        for (int j = 0; j < 3; j++) {
            double d = (double)y[j] - x[j];
            dif += d * d;
            na += (double)x[j] * x[j];
            nc += (double)y[j] * y[j];
        }
        o[i].w = a[i].w + (c[i].w - a[i].w) * t;
    }
    double n = na > nc ? na : nc;
    /* rotacion pura: |R1-R2|^2 = 4(1-cos th) y |R|^2 = 3 -> 0,36 * 3 = 1,08 = th ~ 43 grados */
    if (n <= 0 || dif > 0.36 * n) {
        for (int i = 0; i < 3; i++) { o[i].x = c[i].x; o[i].y = c[i].y; o[i].z = c[i].z; }
        g_mat_grandes++;
        return;
    }
    float m[3][3];
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) m[i][j] = (&a[i].x)[j] + ((&c[i].x)[j] - (&a[i].x)[j]) * t;
    for (int j = 0; j < 3; j++) {
        double la = 0, lc = 0, lm = 0;
        for (int i = 0; i < 3; i++) {
            la += (double)(&a[i].x)[j] * (&a[i].x)[j];
            lc += (double)(&c[i].x)[j] * (&c[i].x)[j];
            lm += (double)m[i][j] * m[i][j];
        }
        la = sqrt(la); lc = sqrt(lc); lm = sqrt(lm);
        if (lm > 1e-12) {
            float s = (float)((la + (lc - la) * t) / lm);
            for (int i = 0; i < 3; i++) m[i][j] *= s;
        }
    }
    for (int i = 0; i < 3; i++) { o[i].x = m[i][0]; o[i].y = m[i][1]; o[i].z = m[i][2]; }
    g_mat_mezcladas++;
}


static uint32_t g_part_mezcladas, g_part_reales, g_ambiguas, g_stencil;
#define MAX_PART 32
/* o = salida (ya con los valores reales de C en las casillas de particula), a = pareja (cuadro anterior), c = actual */
static void mezclar_particulas(PicaVec4 *o, const PicaVec4 *a, const PicaVec4 *c, const uint8_t *clase, float t)
{
    int ini = -1, n = 0;
    for (int q = 0; q < 96; q++)
        if (clase[q] == 6) { if (ini < 0) ini = q; n++; }
    int np = n / 3;
    if (ini < 0 || np <= 0) return;
    if (np > MAX_PART) np = MAX_PART;
    int de_c[MAX_PART], de_a[MAX_PART];
    for (int lado = 0; lado < 2; lado++) {
        const PicaVec4 *x = lado ? a : c, *y = lado ? c : a;
        int *sal = lado ? de_a : de_c;
        for (int k = 0; k < np; k++) {
            double mejor = 1e300;
            sal[k] = -1;
            const PicaVec4 *p = &x[ini + 3 * k];
            for (int j = 0; j < np; j++) {
                const PicaVec4 *q = &y[ini + 3 * j];
                double dx = (double)p[0].w - q[0].w, dy = (double)p[1].w - q[1].w, dz = (double)p[2].w - q[2].w;
                double d = dx * dx + dy * dy + dz * dz;
                if (d < mejor) { mejor = d; sal[k] = j; }
            }
        }
    }
    for (int k = 0; k < np; k++) {
        int j = de_c[k];
        if (j >= 0 && de_a[j] == k) { mezclar_matriz(&o[ini + 3 * k], &a[ini + 3 * j], &c[ini + 3 * k], t); g_part_mezcladas++; }
        else g_part_reales++;
    }
}

/* SOMBRAS, modo 2 (H2, 9 oct; SM3DL_INTERP_SOMBRA_CAMARA=2, PRUEBA): pareja del OBJETO de una pasada de stencil que
   no depende del orden ni de g_usado. Las copias de un volumen (7-14 por grupo en el 1-1) tienen uniforms IDENTICOS;
   la pareja normal las vetaba por "ambiguas" (mejor == segunda) salvo la ultima, que quedaba sola y se mezclaba: las
   pasadas dejaban de cancelarse (8 oct). Aca: la candidata de B con la misma huella mas cercana; "ambigua" solo si hay
   OTRA candidata con uniforms DISTINTOS a menos del doble de distancia. Mismas entradas -> misma respuesta para todas
   las copias de C. NULL = sin pareja segura (la pasada queda con solo la camara). */
static void dibujo(PicaEstado *e);
/* ---- CINTA DE INTERMEDIOS (H1, 10 oct; MECANISMO, no reglas: ver agentes_dx12\H1.md) ----
   En D3D12 un intermedio del modo Monitor ya no re-ejecuta las listas PICA por la capa comun: gsp_interp.inc llama a
   rapido_op(k) por cada lista k del cuadro y aqui se re-arma, por cada dibujo j que esa lista hizo en el cuadro REAL,
   un PicaEstado FALSO con lo grabado (campos de fragmento/estado [0, luz_lut) + vs.f/b/i/entrada/salidas + vertices e
   indices; huella y programa = los grabados) y se pasa por el MISMO dibujo() de siempre: las reglas de mezcla (H2 y
   las de antes) deciden igual que en la re-ejecucion. Su pica_raster(e) final va a raster_cinta_dibujar(j, e->vs.f):
   el backend re-emite lo que grabo con b0 = esos registros. Si una regla nueva lee OTRO campo de PicaEstado, hay que
   copiarlo en rap_grabar (si no, aqui vale 0): por eso existe SM3DL_D3D12_REPETIR_VERIFICAR (gsp_interp.inc). */
extern int gsp_interp_op_actual;   /* gsp_interp.inc: operacion del cuadro (lista) que se esta ejecutando; -1 = no grabada */
extern int raster_cinta_j;         /* raster_gl.c */
void raster_cinta_empezar(void);
int raster_cinta_lista(int n);
void raster_cinta_dibujar(int j, const float *c);
#define RAP_PREF offsetof(PicaEstado, luz_lut)
typedef struct {
    int op;
    const InterpPrograma *prog;
    uint16_t vs_b, vs_masc;
    uint8_t vs_i[4][4];
    uint32_t vs_entrada, inm_n;
    uint8_t usa_gs;
    PicaVertices vtx;
    PicaIndices idx;
    uint8_t pre[RAP_PREF];
} DibRap;
static DibRap *g_rap;
static int g_rap_mal, g_rap_cur, g_rap_j;
static void rap_grabar(const PicaEstado *e, int j)
{
    if (!g_rap && !(g_rap = calloc(MAX_DIB, sizeof *g_rap))) { g_rap_mal = 1; return; }
    DibRap *d = &g_rap[j];
    d->op = gsp_interp_op_actual;
    if (d->op < 0) g_rap_mal = 1;   /* lista sin grabar (o fuera de gsp): el cuadro no se puede re-emitir por lista */
    d->prog = programa(e);
    d->vs_b = e->vs.b; d->vs_masc = e->vs.mascara_salida;
    memcpy(d->vs_i, e->vs.i, sizeof d->vs_i);
    d->vs_entrada = e->vs.entrada;
    d->inm_n = e->inm_n;
    d->usa_gs = e->usa_gs;
    d->vtx = e->vtx;
    d->idx = e->idx;
    memcpy(d->pre, e, RAP_PREF);
}
/* SM3DL_H1_TRAZA=1 (diagnostico de H1): registros que recibe pica_raster en cada dibujo de la re-ejecucion */
static int g_tz_on = -1, g_tz_k, g_tz_n[2], g_tz_lado;
static float g_tz_t[2];
static PicaVec4 (*g_tz)[2][96];
static void (*g_tz_orig)(const PicaEstado *e);
static void tz_anotar(const PicaEstado *e)
{
    if (g_tz && g_tz_k < MAX_DIB) memcpy(g_tz[g_tz_k][g_tz_lado], e->vs.f, sizeof e->vs.f);
    g_tz_k++;
}
static int g_tz_huella_mal, g_tz_entrada_mal, g_tz_ent_k;
static void dibujo(PicaEstado *e);
/* lo que la re-ejecucion le entrega a dibujo() ANTES de mezclar vs lo grabado en tiempo real (H1, SM3DL_H1_TRAZA) */
static void tz_interp(PicaEstado *e)
{
    int cur = g_ord[2];
    if (g_tz_ent_k < g_n[cur] && memcmp(e->vs.f, g_tab[cur][g_tz_ent_k].f, sizeof e->vs.f)) g_tz_entrada_mal++;
    g_tz_ent_k++;
    dibujo(e);
}
static void tz_raster(const PicaEstado *e)
{
    int cur = g_ord[2];   /* la huella que ve la re-ejecucion vs la grabada en tiempo real (con la que se eligen parejas) */
    if (g_tz_k < g_n[cur] && huella(e) != g_tab[cur][g_tz_k].h) g_tz_huella_mal++;
    tz_anotar(e);
    if (g_tz_orig) g_tz_orig(e);
}
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
    if (g_tz_n[0] != g_tz_n[1]) { if (avisos++ < 40) fprintf(stderr, "[h1-traza] dibujos: re-ejecucion %d, cinta %d\n", g_tz_n[0], g_tz_n[1]); return; }
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
            fprintf(stderr, "\n");
        }
    }
    if (avisos++ < 40) fprintf(stderr, "[h1-traza] t=%.2f: %d de %d dibujos con registros distintos; huella de la re-ejecucion != grabada en %d, registros de ENTRADA (antes de mezclar) != grabados en %d\n", g_tz_t[0], malos, g_tz_n[0], g_tz_huella_mal, g_tz_entrada_mal);
    g_tz_huella_mal = g_tz_entrada_mal = 0;
}
/* 1 si el cuadro actual (C) se puede re-emitir por la cinta (lo pregunta repetir_cuadro al empezar cada intermedio) */
static int rapido_listo(void)
{
    if (g_rap_mal || !g_rap || g_n[g_ord[2]] <= 0) return 0;
    if (!g_rap_e && !(g_rap_e = calloc(1, sizeof *g_rap_e))) return 0;
    g_rap_cur = 0;
    int ok = raster_cinta_lista(g_n[g_ord[2]]);
    if (ok && g_tz_on > 0) {   /* la re-ejecucion de siempre de este mismo intermedio no se envolvio: deshacer */
        if (pica_raster == tz_raster) pica_raster = g_tz_orig;
        tz_empezar(g_t, 1);
    }
    return ok;
}
/* los dibujos que la lista k del cuadro hizo, en orden (las listas saltadas no se re-emiten: como en la re-ejecucion) */
static void rapido_op(int k)
{
    int cur = g_ord[2], n = g_n[cur];
    while (g_rap_cur < n && g_rap[g_rap_cur].op < k) g_rap_cur++;
    void (*orig)(const PicaEstado *) = pica_raster;
    pica_raster = rap_raster;
    PicaEstado *e = g_rap_e;
    for (; g_rap_cur < n && g_rap[g_rap_cur].op == k; g_rap_cur++) {
        const DibRap *d = &g_rap[g_rap_cur];
        memcpy(e, d->pre, RAP_PREF);
        memcpy(e->vs.f, g_tab[cur][g_rap_cur].f, sizeof e->vs.f);
        e->vs.b = d->vs_b; e->vs.mascara_salida = d->vs_masc;
        memcpy(e->vs.i, d->vs_i, sizeof d->vs_i);
        e->vs.entrada = d->vs_entrada;
        e->inm_n = d->inm_n;
        e->usa_gs = d->usa_gs;
        e->vtx = d->vtx;
        e->idx = d->idx;
        g_rap_h = g_tab[cur][g_rap_cur].h;
        g_rap_prog = d->prog;
        g_rap_j = g_rap_cur;
        dibujo(e);
    }
    pica_raster = orig;
}

static uint32_t g_stencil_cam, g_stencil_obj;
static const PicaVec4 *pareja_sombra(const PicaEstado *e, int r, const PicaVec4 *actual)
{
    uint32_t h = huella(e);
    const float *y = &actual[0].x;
    int jb = -1;
    double mejor = 1e300;
    for (int j = 0; j < g_n[r]; j++) {
        if (g_tab[r][j].h != h) continue;
        double d = 0;
        const float *x = &g_tab[r][j].f[0].x;
        for (int c = 0; c < 96 * 4; c++) d += fabs((double)x[c] - (double)y[c]);
        if (d < mejor) { mejor = d; jb = j; }
    }
    if (jb < 0) return NULL;
    const PicaVec4 *b = g_tab[r][jb].f;
    for (int j = 0; j < g_n[r]; j++) {
        if (g_tab[r][j].h != h || !memcmp(g_tab[r][j].f, b, sizeof g_tab[r][j].f)) continue;
        double d = 0;
        const float *x = &g_tab[r][j].f[0].x;
        for (int c = 0; c < 96 * 4; c++) d += fabs((double)x[c] - (double)y[c]);
        if (mejor > 0.5 * d) return NULL;
    }
    return b;
}

static void dibujo(PicaEstado *e)
{
    static int semantica = -1;
    if (semantica < 0) { const char *s = getenv("SM3DL_INTERP_SEMANTICA"); semantica = !(s && *s == '0'); }
    if (g_modo == 0) {
        int jc = -1;   /* H1: numero de este dibujo en el cuadro (la cinta D3D12 lo graba con ese indice) */
        if (interp_vivo || g_prueba) {
            int t = g_ord[2];
            if (g_n[t] < MAX_DIB) {
                jc = g_n[t];
                g_tab[t][g_n[t]].h = huella(e);
                memcpy(g_tab[t][g_n[t]].f, e->vs.f, sizeof e->vs.f);
                g_n[t]++;
            } else g_rap_mal = 1;
            if (semantica) {
                const InterpPrograma *p = programa(e);
                if (p) { g_reconocidos++; grabar_camara(e, p, t); } else g_desconocidos++;
            }
        }
        if (jc >= 0) rap_grabar(e, jc);
        raster_cinta_j = jc;
        if (pica_raster) pica_raster(e);
        raster_cinta_j = -1;
        return;
    }
    if (g_modo == 2) {
        if (pica_raster) pica_raster(e);
        return;
    }
    int idx = g_idx++;
    if (idx == 0) {   /* H2: contadores de sombras por re-ejecucion (sin tocar repetir(), que es del mecanismo) */
        static int informar = -1;
        if (informar < 0) informar = getenv("SM3DL_REPETIR") != NULL;
        if (informar && (g_stencil_cam || g_stencil_obj))
            fprintf(stderr, "[interp-sombra] re-ejecucion anterior: %u pasadas de stencil con camara mezclada, %u con objeto mezclado (modo 2)\n", g_stencil_cam, g_stencil_obj);
        g_stencil_cam = g_stencil_obj = 0;
    }
    static int cercano = -1, mezclar_2d = -1, repetidos = -1, saltos = -1;
    if (cercano < 0) {
        const char *s = getenv("SM3DL_INTERP_CERCANO"), *m = getenv("SM3DL_INTERP_2D");
        const char *rp = getenv("SM3DL_INTERP_REPETIDOS"), *sl = getenv("SM3DL_INTERP_SALTOS");
        cercano = !(s && *s == '0');   /* por defecto SI: medido 300 cuadros, ~1.600 px del real vs ~1.950 por orden */
        mezclar_2d = m && *m == '1';
        repetidos = rp ? atoi(rp) : 2;
        saltos = !(sl && *sl == '0');
    }
    /* HUD / 2D (sin prueba de profundidad): NO se mezcla. Los iconos del HUD comparten malla y atlas (misma huella)
       y se emparejaban cruzados: el reloj salia como cabeza de Luigi (vblank 2061). El HUD a 30 FPS no se nota.
       SM3DL_INTERP_2D=1 los mezcla igual (para comparar). */
    if (!e->depth_test && !mezclar_2d) {
        g_sin_mezcla++;
        diag_reg(idx, semantica ? programa(e) : NULL, 0, 0, e, NULL, e->vs.f);
        if (pica_raster) pica_raster(e);
        return;
    }
    static PicaVec4 guardado[96];
    memcpy(guardado, e->vs.f, sizeof guardado);
    const InterpPrograma *prog = semantica ? programa(e) : NULL;
    int r = g_ord[g_modo == 1 ? 0 : 1], cur = g_ord[2];
    /* Pareja: entre las libres con la misma huella, la de uniforms MAS PARECIDOS (SM3DL_INTERP_CERCANO=0 = la primera
       en orden de aparicion). Medido 7 oct con la metrica por pixel en 300 cuadros con movimiento: intermedio a ~1.600
       px visibles del real por cercania vs ~1.950 por orden (sin interpolar ~4.100). */
    uint32_t h = huella(e);
    int k = g_n[r];
    double mejor = 1e300, segundo = 1e300, d_orden = -1, d_otro = 1e300;
    const float *y = &e->vs.f[0].x;
    for (int j = 0; j < g_n[r]; j++) {
        if (g_usado[j] || g_tab[r][j].h != h) continue;
        double d = 0;
        const float *x = &g_tab[r][j].f[0].x;
        for (int c = 0; c < 96 * 4; c++) d += fabs((double)x[c] - (double)y[c]);
        if (!cercano) {
            if (k == g_n[r]) { k = j; d_orden = d; }      /* pareja por orden: la primera libre */
            else if (d < d_otro) d_otro = d;              /* la mejor de las OTRAS candidatas */
        } else if (d < mejor) { segundo = mejor; mejor = d; k = j; }
        else if (d < segundo) segundo = d;
    }
    int sin_pareja = k == g_n[r], vetado = 0;
    if (sin_pareja) g_sueltos++;
    else {
        g_usado[k] = 1;
        g_emparejados++;
        /* OBJETOS REPETIDOS (pasto, monedas, particulas: misma huella): si el juego los reordena, la pareja por orden
           es OTRO objeto. Si otra candidata se parece claramente mas que la de orden, el objeto no se mezcla. */
        if (d_orden >= 0 && d_otro < 0.5 * d_orden) { g_vetados++; sin_pareja = 1; vetado = 1; }
        /* AMBIGUA (8 oct, nubes del veneno): con varias candidatas iguales, si la mejor no es claramente mejor que la
           segunda (menos de la mitad), la pareja puede ser OTRO objeto: no se mezcla (solo la camara) */
        else if (cercano && mejor > 0 && segundo < 1e300 && mejor > 0.5 * segundo) { g_vetados++; g_ambiguas++; sin_pareja = 1; vetado = 1; }
        /* PARTICULAS (confirmado por el dueno): un grupo repetido solo se mezcla si tiene la MISMA cantidad de copias
           en los dos cuadros. SM3DL_INTERP_REPETIDOS=0: los repetidos nunca se mezclan; =1: sin esta regla. */
        else if (repetidos != 1) {
            int nr = 0, nc = 0;
            for (int j = 0; j < g_n[r]; j++) nr += g_tab[r][j].h == h;
            for (int j = 0; j < g_n[cur]; j++) nc += g_tab[cur][j].h == h;
            if ((nr > 1 || nc > 1) && (repetidos == 0 || nr != nc)) { g_vetados++; sin_pareja = 1; vetado = 1; }
        }
    }
    /* PARPADEO (10 oct, el dueno a 144: "cuando me pegan siento que el juego regresa a 30"; Mario invencible se dibuja
       un cuadro si y otro no). Un objeto SIN ninguna candidata en B (no se dibujo en el cuadro anterior) iba real, a 30,
       y la camara lo sigue. Ahora se busca en A (dos cuadros atras) y se mezcla de A a C con t' = (1+t)/2 (A=0, B=1,
       C=2; el intermedio esta en 1+t). Solo modo 3 (Monitor), sin stencil, pareja clara (la mejor < mitad de la
       segunda) y la misma cantidad de copias de esa huella en A y en C. SM3DL_INTERP_DOS_ATRAS=1 lo enciende. */
    const PicaVec4 *a_dos = NULL;
    if (k == g_n[r] && g_modo == 3 && !e->stencil_test && idx != g_excluir) {
        static int dos_atras = -1;
        if (dos_atras < 0) { const char *s = getenv("SM3DL_INTERP_DOS_ATRAS"); dos_atras = s && *s == '1'; }
        int ra = g_ord[0];
        if (dos_atras && ra != cur && ra != r) {
            int ka = -1, na = 0, nc = 0;
            double ma = 1e300, sa = 1e300;
            for (int j = 0; j < g_n[ra]; j++) {
                if (g_tab[ra][j].h != h) continue;
                na++;
                if (g_usado_a[j]) continue;
                double d = 0;
                const float *x = &g_tab[ra][j].f[0].x;
                for (int c = 0; c < 96 * 4; c++) d += fabs((double)x[c] - (double)y[c]);
                if (d < ma) { sa = ma; ma = d; ka = j; }
                else if (d < sa) sa = d;
            }
            for (int j = 0; j < g_n[cur]; j++) nc += g_tab[cur][j].h == h;
            if (ka >= 0 && na == nc && (sa >= 1e300 || ma <= 0.5 * sa)) { g_usado_a[ka] = 1; a_dos = g_tab[ra][ka].f; g_dos_atras++; }
        }
    }
    /* SOMBRAS (8 oct, sombra de Mario rara solo a 60 en W2-1): los volumenes de sombra son pasadas de STENCIL que
       suman y restan (ops 3/4, varias copias por volumen); si una pasada se mezcla y su compañera no, no se cancelan
       y quedan restos. Todo dibujo que ESCRIBE stencil va igual: objeto real, solo la camara mezclada. */
    /* Y la pasada que LEE el stencil para oscurecer (primitive_renderer, wvp combinado: sin camara aparte) tiene que
       calzar con los volumenes: todo lo que use stencil va COMPLETO real (la sombra a 30, pero entera). */
    /* SOMBRAS Y CAMARA (H2, 9 oct; el dueno en Monitor 144 Hz: "las sombras vibran un poquito mientras me muevo, quieto
       no"). Con la regla de arriba la sombra se proyectaba con la camara REAL y el resto de la escena con la MEZCLADA:
       en cada intermedio el volumen quedaba (1-t) de paso de camara atras -> diente de sierra a 30 Hz contra el piso
       (quieto: las dos camaras coinciden y no se ve). Lo que rompia la sombra el 8 oct NO era la camara sino el OBJETO
       mezclado en unas pasadas y en otras no (6 de 7 copias vetadas, la ultima -con una sola candidata libre- mezclada).
       Regla nueva por SEMANTICA: en todo dibujo con stencil_test el objeto va REAL y se mezclan SOLO los registros de
       clase CAMARA (ProjMtx c86-89 / ViewMtx c90-92 por nombre del DVLE) con mezclar_camara: es la misma cuenta para
       todas las pasadas del cuadro (camara exacta de C + la mas cercana de B), asi que se siguen cancelando igual.
       Desensamblado Shader_008F2C#3 (volumenes): posicion = c86-89 * c90-92 * (c0-2 o huesos) * v; NormMtx c3-5 solo
       va a las normales (dp3) -> con c86-92 la sombra sigue a la camara entera. La pasada que oscurece
       (primitive_renderer, `wvp` combinado, sin clase CAMARA) es 2D (prof=0, pantalla completa) o no tiene camara
       aparte: queda real, como hoy.
       SM3DL_INTERP_SOMBRA_CAMARA: 0 = lo del 8 oct (todo real, POR DEFECTO); 1 = solo camara; 2 = PRUEBA: tambien el
       objeto, con una pareja que no depende del orden (pareja_sombra: todas las copias identicas reciben la misma). */
    const PicaVec4 *a_sombra = NULL;
    if (e->stencil_test) {
        static int sombra_cam = -1;
        if (sombra_cam < 0) { const char *s = getenv("SM3DL_INTERP_SOMBRA_CAMARA"); sombra_cam = s && *s ? atoi(s) : 0; }   /* default 0 hasta que el dueño elija 1 o 2 jugando (principal, 10 oct) */
        g_stencil++;
        if (sombra_cam == 2 && prog && idx != g_excluir) a_sombra = pareja_sombra(e, r, guardado);
        if (!a_sombra) {
            int cam = sombra_cam >= 1 && idx != g_excluir && prog && mezclar_camara(e, prog, r, cur, g_t);
            g_stencil_cam += cam;
            diag_reg(idx, prog, 1, cam, e, NULL, guardado);
            if (pica_raster) pica_raster(e);
            memcpy(e->vs.f, guardado, sizeof guardado);
            return;
        }
        g_stencil_obj++;   /* modo 2 con pareja segura: sigue abajo como un dibujo emparejado, contra a_sombra */
    }
    if (sin_pareja && !a_sombra && !a_dos) {
        /* sin pareja segura: el objeto va en su posicion real, pero la CAMARA si se mezcla (si el programa se conoce) */
        int cam = idx != g_excluir && prog && mezclar_camara(e, prog, r, cur, g_t);
        g_solo_cam += cam;
        diag_reg(idx, prog, vetado ? 2 : 1, cam, e, vetado ? g_tab[r][k].f : NULL, guardado);
        if (pica_raster) pica_raster(e);
        memcpy(e->vs.f, guardado, sizeof guardado);
        return;
    }
    const PicaVec4 *a = a_sombra ? a_sombra : a_dos ? a_dos : g_tab[r][k].f;
    diag_reg(idx, prog, 3, 1, e, a, guardado);
    if (idx == g_excluir) { if (pica_raster) pica_raster(e); return; }   /* diagnostico: este dibujo, real */
    float t = a_dos ? 0.5f * (1.0f + g_t) : g_t;   /* PARPADEO: de A a C */
    /* FLECHAS (10 oct, piso del jefe del barco a 144: la textura avanzaba a 30). La animacion de textura (clase 2) iba
       siempre real. Con SM3DL_INTERP_TEXTURA=1 se mezcla si el paso es chico (<= 0,25); un desplazamiento que DA LA
       VUELTA (0,98 -> 0,02) se mezcla por el camino corto (d - round(d)), igual porque la textura se repite. Un
       salto mayor (cambio de animacion) sigue real. Solo dibujos con pareja (no en las sombras de stencil). */
    static int tex_mezcla = -1;
    if (tex_mezcla < 0) { const char *s = getenv("SM3DL_INTERP_TEXTURA"); tex_mezcla = s && *s == '1'; }
    const float *pa = &a[0].x, *pc = &guardado[0].x;
    float *po = &e->vs.f[0].x;
    for (int j = 0; j < 96 * 4; j++) {
        float d = pc[j] - pa[j], m = fabsf(pa[j]) > fabsf(pc[j]) ? fabsf(pa[j]) : fabsf(pc[j]);
        int cl = prog ? prog->clase[j >> 2] : 4;
        if (cl == 2) {
            if (tex_mezcla && !a_sombra && d != 0) {
                /* la vuelta solo en traslaciones (columna w de TexMtx, o TexTran c19): una escala/giro no "da la vuelta" */
                int tras = (j & 3) == 3 || (j >> 2) == 19;
                float dd = fabsf(d) <= 0.25f ? d : tras ? d - roundf(d) : d;
                if (fabsf(dd) <= 0.25f) { po[j] = pc[j] - dd * (1.0f - t); g_tex_mezcla++; continue; }
            }
            po[j] = pc[j]; g_tex_real += d != 0; continue;
        }
        if (cl == 6) { po[j] = pc[j]; continue; }                          /* particula: abajo, por cercania */                          /* animacion de textura: real */
        if (cl == 3) { po[j] = d >= 0 ? pa[j] + d * t : pc[j]; continue; } /* tiempo: real si dio la vuelta */
        /* SALTOS (7 oct), solo para registros sin nombre: un valor que DA LA VUELTA (0,98 -> 0,02) toma el real.
           Medido 7 oct: la regla amplia congelaba 12 % de los valores y empeoraba; queda solo la vuelta de ~1. */
        if (cl == 4 && saltos && m <= 1.5f && fabsf(d) >= 0.6f && fabsf(d) <= 1.4f) { po[j] = pc[j]; g_saltos++; }
        else po[j] = pa[j] + d * t;
    }
    static int matrices = -1;
    if (matrices < 0) { const char *s = getenv("SM3DL_INTERP_MATRICES"); matrices = !(s && *s == '0'); }
    static int particulas = -1;
    /* por defecto NO (8 oct): medido en el 1-1, las particulas se mueven por cuadro casi lo mismo que la distancia
       entre ellas (5-12 u): la pareja por cercania es ambigua. Van en su posicion real; la camara si se mezcla.
       SM3DL_INTERP_PARTICULAS=1 prueba la pareja por cercania mutua. */
    if (particulas < 0) { const char *s = getenv("SM3DL_INTERP_PARTICULAS"); particulas = s && *s == '1'; }
    if (prog && particulas) mezclar_particulas(e->vs.f, a, guardado, prog->clase, t);
    if (prog && matrices) {
        int con_piel = (e->vs.b & prog->piel) != 0, en_cuat = (e->vs.b & prog->quat) != 0;
        for (int q = 0; q < 96; q++)
            if (prog->clase[q] == 5 && !con_piel) { e->vs.f[q] = guardado[q]; g_huesos_real++; }
        for (int q = 0; q + 2 < 96; q++) {
            if (!prog->bloque[q]) continue;
            if (prog->clase[q] == 5 && (!con_piel || en_cuat)) continue;   /* sin esqueleto: real; cuaterniones: valor por valor */
            if (prog->clase[q] == 2) continue;
            mezclar_matriz(&e->vs.f[q], &a[q], &guardado[q], t);
        }
    }
    if (pica_raster) pica_raster(e);
    memcpy(e->vs.f, guardado, sizeof guardado);
}

/* fin de un cuadro del juego: la actual pasa a ser la anterior; la mas vieja se recicla */
static void cerrar(void)
{
    int viejo = g_ord[0];
    g_ord[0] = g_ord[1];
    g_ord[1] = g_ord[2];
    g_ord[2] = viejo;
    g_n[viejo] = 0;
    g_rap_mal = 0;              /* H1: cinta del cuadro nuevo */
    raster_cinta_empezar();
    g_ncam[viejo] = 0;
}

/* modo 1/2/3: empieza una re-ejecucion (guarda el estado PICA); 0: la termina (lo restaura) */
static void repetir(int modo, float t)
{
    static int informar = -1;
    if (informar < 0) informar = getenv("SM3DL_REPETIR") != NULL;
    if (modo) {
        memcpy(&g_copia_pica, &pica, sizeof pica);
        g_modo = modo;
        g_t = t;
        g_idx = 0;
        tz_empezar(t, 0);   /* H1: SM3DL_H1_TRAZA */
        if (g_tz_on > 0 && pica_raster != tz_raster) { g_tz_orig = pica_raster; pica_raster = tz_raster; }
        if (g_tz_on > 0) { pica_interp = tz_interp; g_tz_ent_k = 0; }
        memset(g_usado, 0, sizeof g_usado);
        memset(g_usado_a, 0, sizeof g_usado_a);
        g_dos_atras = g_tex_mezcla = 0;
        g_emparejados = g_sueltos = g_sin_mezcla = g_vetados = g_saltos = g_solo_cam = g_cortes = g_tex_real = g_mat_mezcladas = g_mat_grandes = g_huesos_real = g_part_mezcladas = g_part_reales = g_ambiguas = g_stencil = 0;
    } else {
        if (informar && g_modo != 2)
            fprintf(stderr, "[interp] re-ejecucion t=%.2f: %u dibujos emparejados (%u 2D sin mezclar, %u repetidos dudosos sin mezclar), %u sin pareja, %u valores que saltan; %u solo con camara mezclada, %u cortes de camara, %u valores de textura animada sin mezclar, matrices %u mezcladas como rotacion y %u con giro grande (real), %u huesos de objetos sin esqueleto (real), particulas %u mezcladas y %u sin pareja mutua, %u parejas ambiguas, %u de stencil (sombras) reales; programas %u conocidos %u no\n",
                    g_t, g_emparejados, g_sin_mezcla, g_vetados, g_sueltos, g_saltos, g_solo_cam, g_cortes, g_tex_real, g_mat_mezcladas, g_mat_grandes, g_huesos_real, g_part_mezcladas, g_part_reales, g_ambiguas, g_stencil, g_reconocidos, g_desconocidos);
        if (informar && g_modo != 2 && (g_dos_atras || g_tex_mezcla))
            fprintf(stderr, "[interp] t=%.2f: %u dibujos mezclados desde A (parpadeo), %u valores de textura animada mezclados\n", g_t, g_dos_atras, g_tex_mezcla);
        if (pica_raster == tz_raster) pica_raster = g_tz_orig;   /* H1: SM3DL_H1_TRAZA */
        if (pica_interp == tz_interp) pica_interp = dibujo;
        tz_terminar();
        g_modo = 0;
        memcpy(&pica, &g_copia_pica, sizeof pica);
    }
}

static void cuenta(uint32_t *emp, uint32_t *sue) { *emp = g_emparejados; *sue = g_sueltos; }

/* detector de destellos a 4x: la misma imagen en alta que recibe la ventana (raster_alta reusa su bufer si no cambio) */
extern int (*gsp_interp_leer_alta)(uint32_t dir, uint32_t fmt, uint32_t stride, const uint8_t **bgra);
int raster_alta(uint32_t dir_fisica, uint32_t fmt, uint32_t stride, uint32_t ancho, uint32_t alto, const uint8_t **rgba);
static int leer_alta(uint32_t dir, uint32_t fmt, uint32_t stride, const uint8_t **bgra)
{
    return raster_alta(dir, fmt, stride, 400, 240, bgra);
}

__attribute__((constructor)) static void enganchar(void)
{
    const char *s = getenv("SM3DL_REPETIR"), *v = getenv("SM3DL_INTERP");
    g_prueba = s && *s;
    interp_vivo = v && *v == '1';
    for (int k = 0; k < 3; k++) g_tab[k] = calloc(MAX_DIB, sizeof(Dib));
    if (!g_tab[0] || !g_tab[1] || !g_tab[2]) { interp_vivo = 0; return; }
    pica_interp = dibujo;
    gsp_interp_cerrar = cerrar;
    gsp_interp_repetir = repetir;
    gsp_interp_lista = lista;
    gsp_interp_rapido_listo = rapido_listo;   /* H1 */
    gsp_interp_rapido_op = rapido_op;
    gsp_interp_rapido_cifras = raster_cinta_cifras;
    gsp_interp_cuenta = cuenta;
    gsp_interp_alta = raster_alta_instantanea;
    gsp_interp_vivo = &interp_vivo;
    gsp_interp_leer_alta = leer_alta;
    gsp_interp_diag = diag_modo;
    gsp_interp_diag_n = diag_n;
    gsp_interp_diag_linea = diag_linea;
}
