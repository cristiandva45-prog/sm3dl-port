/* Disparo de dibujo del interprete PICA. Ver pica.h.
   8 oct: CENSO (SM3DL_CENSO_DIBUJOS=1): agrupa los dibujos por (programa de vertex shader, render target,
   topologia) y lo imprime cada 600 dibujos, para dimensionar el rasterizador antes de escribirlo. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pica.h"

static uint32_t fnv(const uint32_t *p, size_t n)
{
    uint32_t h = 2166136261u;
    for (size_t k = 0; k < n; k++) { h ^= p[k]; h *= 16777619u; }
    return h;
}

typedef struct { uint32_t prog, entrada, color, topo, w, h, n, vmax, permfmt; } Grupo;
static Grupo g_grupos[256];
static int g_n;
static uint32_t g_total;

/* rasterizador (raster_gl.c lo engancha con raster_iniciar; NULL = sin rasterizar) */
void (*pica_raster)(const PicaEstado *e);
/* interpolacion de cuadros (interp.c, prototipo): si esta puesto, cada dibujo pasa por ahi (NULL = camino normal) */
void (*pica_interp)(PicaEstado *e);

/* ESTUDIO DE INTERPOLACION (7 oct noche, >60 FPS): SM3DL_ESTUDIO_INTERP=<archivo> vuelca, para los dibujos entre el
   vblank SM3DL_ESTUDIO_DESDE (def. 1800) y +SM3DL_ESTUDIO_CUADROS vblanks (def. 40), un registro por dibujo: huella
   (programa, entrada, RT, buffers, texturas), uniforms float del VS y un hash de los vertices que usa. Sirve para
   medir si los dibujos de un cuadro se emparejan con los del siguiente y que uniforms cambian (matrices). */
#include "gsp.h"
typedef struct {
    uint32_t vblank, swaps, prog, entrada, color_dir, base, idx_off, nv, voff, es_el, topo, tex[3], vhash, vbytes, usa_gs, b;
    float f[96][4];
} RegEstudio;
static void estudio(const PicaEstado *e)
{
    static FILE *f;
    static int estado = -1;
    static uint32_t desde, hasta;
    if (estado < 0) {
        const char *a = getenv("SM3DL_ESTUDIO_INTERP");
        estado = a && *a ? 1 : 0;
        if (!estado) return;
        f = fopen(a, "wb");
        const char *d = getenv("SM3DL_ESTUDIO_DESDE"), *c = getenv("SM3DL_ESTUDIO_CUADROS");
        desde = d ? (uint32_t)atoi(d) : 1800;
        hasta = desde + (c ? (uint32_t)atoi(c) : 40);
        if (!f) estado = 0;
    }
    if (!estado) return;
    const GspEstadistica *g = gsp_estadistica();
    if (g->vblanks < desde) return;
    if (g->vblanks >= hasta) { fclose(f); estado = 0; fprintf(stderr, "[estudio] listo\n"); return; }
    RegEstudio r;
    memset(&r, 0, sizeof r);
    r.vblank = g->vblanks; r.swaps = g->swaps;
    r.prog = fnv(e->vs.codigo, 512) ^ fnv(e->vs.swizzles, 128);
    r.entrada = e->vs.entrada; r.color_dir = e->color_dir; r.base = e->vtx.base_fisica;
    r.idx_off = e->idx.offset; r.nv = e->idx.num_vertices; r.voff = e->idx.vertex_offset;
    r.es_el = e->idx.es_elements; r.topo = e->idx.topologia; r.usa_gs = e->usa_gs; r.b = e->vs.b;
    for (int k = 0; k < 3; k++) r.tex[k] = e->tex[k].activa ? e->tex[k].direccion : 0;
    memcpy(r.f, e->vs.f, sizeof r.f);
    /* rango de vertices usado: max indice + 1 */
    uint32_t vmax = e->idx.vertex_offset + e->idx.num_vertices;
    if (e->idx.es_elements && pica_memoria) {
        const uint8_t *ix = pica_memoria(e->vtx.base_fisica + e->idx.offset, e->idx.num_vertices * (e->idx.es_u16 ? 2 : 1));
        vmax = 0;
        if (ix)
            for (uint32_t k = 0; k < e->idx.num_vertices; k++) {
                uint32_t v = e->idx.es_u16 ? ((const uint16_t *)ix)[k] : ix[k];
                if (v + 1 > vmax) vmax = v + 1;
            }
    }
    uint32_t h = 2166136261u;
    for (int l = 0; l < 12 && pica_memoria; l++) {
        if (!e->vtx.loader[l].num_comp || !e->vtx.loader[l].stride) continue;
        uint32_t n = vmax * e->vtx.loader[l].stride;
        const uint8_t *p = pica_memoria(e->vtx.base_fisica + e->vtx.loader[l].offset, n);
        if (!p) continue;
        for (uint32_t k = 0; k < n; k++) { h ^= p[k]; h *= 16777619u; }
        r.vbytes += n;
    }
    r.vhash = h;
    fwrite(&r, sizeof r, 1, f);
}

void pica_dibujar(const PicaEstado *e)
{
    static int censo = -1;
    {   /* SM3DL_ORDEN_DIBUJOS=1 + SM3DL_INTERP_ORDEN: cuenta dibujos por RT entre operaciones (ojo derecho) */
        static int od = -1;
        if (od < 0) od = getenv("SM3DL_ORDEN_DIBUJOS") != NULL;
        if (od) {
            static uint32_t ult_rt, n;
            const GspEstadistica *g = gsp_estadistica();
            static uint32_t ult_tr;
            if (g->transfers != ult_tr || e->color_dir != ult_rt) {
                if (n && g->vblanks > 2000 && g->vblanks < 2006) fprintf(stderr, "[orden-dib] %u dibujos al RT 0x%08X (transfers hechos %u)\n", n, ult_rt, ult_tr);
                n = 0; ult_rt = e->color_dir; ult_tr = g->transfers;
            }
            n++;
        }
    }
    estudio(e);
    if (gsp_ojo_derecho && e->viewport_alto >= 399.0f) return;   /* un solo ojo (gsp.h): el derecho no se ve */
    if (pica_interp) pica_interp((PicaEstado *)e);   /* interpolacion de cuadros (interp.c): graba y llama al raster */
    else if (pica_raster) pica_raster(e);
    if (censo < 0) censo = getenv("SM3DL_CENSO_DIBUJOS") != NULL;
    if (!censo) return;
    /* el programa se identifica por su codigo (los primeros 512 descriptores alcanzan para distinguir los 7 DVLB) */
    uint32_t prog = fnv(e->vs.codigo, 512) ^ fnv(e->vs.swizzles, 128);
    uint32_t topo = e->idx.topologia, color = e->color_dir;
    int k;
    for (k = 0; k < g_n; k++)
        if (g_grupos[k].prog == prog && g_grupos[k].entrada == e->vs.entrada && g_grupos[k].color == color
            && g_grupos[k].topo == topo) break;
    if (k == g_n && g_n < 256) {
        g_grupos[k].prog = prog; g_grupos[k].entrada = e->vs.entrada; g_grupos[k].color = color;
        g_grupos[k].topo = topo; g_grupos[k].w = e->fb_ancho; g_grupos[k].h = e->fb_alto;
        g_grupos[k].permfmt = e->vtx.total_atributos;
        g_n++;
    }
    if (k == g_n - 1 && g_grupos[k].n == 0) {   /* grupo nuevo: volcar su programa y un ejemplo de estado */
        char r[96];
        snprintf(r, sizeof r, "recomp\\arranque\\vs_%08X.bin", prog);
        FILE *f = fopen(r, "wb");
        if (f) { fwrite(e->vs.codigo, 4, 4096, f); fwrite(e->vs.swizzles, 4, 4096, f); fclose(f); }
        fprintf(stderr, "[censo] nuevo prog %08X: entrada %u, entradas %u, perm", prog, e->vs.entrada, e->vs.num_entradas);
        for (int j = 0; j < 16; j++) fprintf(stderr, " %X", e->vs.permutacion[j]);
        fprintf(stderr, ", omask %04X, fijos %03X, base %08X fmt", e->vs.mascara_salida, e->vtx.mascara_fijos,
                e->vtx.base_fisica);
        for (int j = 0; j < 12; j++) fprintf(stderr, " %u/%u", e->vtx.formato[j], e->vtx.componentes[j]);
        fprintf(stderr, "\n");
    }
    if (k < 256) {
        g_grupos[k].n++;
        if (e->idx.num_vertices > g_grupos[k].vmax) g_grupos[k].vmax = e->idx.num_vertices;
    }
    if (++g_total % 600 == 0) {
        fprintf(stderr, "[censo] %u dibujos, %d grupos (prog, entrada, render target, topologia):\n", g_total, g_n);
        for (k = 0; k < g_n; k++)
            fprintf(stderr, "[censo]   prog %08X e%u rt %08X %ux%u topo %u atrib %u: %u dibujos, hasta %u vertices\n",
                    g_grupos[k].prog, g_grupos[k].entrada, g_grupos[k].color, g_grupos[k].w, g_grupos[k].h,
                    g_grupos[k].topo, g_grupos[k].permfmt, g_grupos[k].n, g_grupos[k].vmax);
    }
}
