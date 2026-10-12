/* Prueba del interprete PICA: ejecuta los casos de un .bin (los arma tools\pica_volcar_estado.py) y vuelca el
 * estado decodificado en texto; el script lo compara contra su modelo en Python.
 *
 * Formato del .bin: "PICA" + n_casos, y por caso: n_palabras, palabras (lista de comandos), n_mem, y n_mem bloques
 * (dir_fisica, n_palabras, palabras) que el gancho pica_memoria sirve (para los saltos CMDBUF_JUMP).
 * Uso: prueba_pica.exe casos.bin > salida.txt
 */
#include "pica.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t bitsf(float f) {
    uint32_t b;
    memcpy(&b, &f, 4);
    return b;
}

static uint32_t fnv(const uint32_t *p, size_t n) {
    uint32_t h = 2166136261u;
    for (size_t k = 0; k < n; k++)
        for (int j = 0; j < 4; j++) {
            h ^= (p[k] >> (8 * j)) & 0xFF;
            h *= 16777619u;
        }
    return h;
}

static void volcar_shader(const char *nom, const PicaShader *s) {
    printf("%s entrada=%u nent=%u omask=%04X b=%04X perm=", nom, s->entrada, s->num_entradas, s->mascara_salida, s->b);
    for (int k = 0; k < 16; k++)
        printf("%X", s->permutacion[k]);
    printf(" i=");
    for (int k = 0; k < 4; k++)
        printf("%02X%02X%02X%02X ", s->i[k][0], s->i[k][1], s->i[k][2], s->i[k][3]);
    printf("cod=%08X swz=%08X\n", fnv(s->codigo, 4096), fnv(s->swizzles, 4096));
    for (int k = 0; k < 96; k++) {
        const PicaVec4 *v = &s->f[k];
        if (bitsf(v->x) | bitsf(v->y) | bitsf(v->z) | bitsf(v->w))
            printf("%s c%d %08X %08X %08X %08X\n", nom, k, bitsf(v->x), bitsf(v->y), bitsf(v->z), bitsf(v->w));
    }
}

static void volcar(const PicaEstado *e) {
    printf("rast cull=%u vp=%08X,%08X xy=%d,%d dz=%08X,%08X dmap=%u sc=%u %u,%u,%u,%u\n", e->culling,
           bitsf(e->viewport_ancho), bitsf(e->viewport_alto), e->viewport_x, e->viewport_y, bitsf(e->depth_escala),
           bitsf(e->depth_offset), e->depthmap_activo, e->scissor_modo, e->scissor_x0, e->scissor_y0, e->scissor_x1,
           e->scissor_y1);
    for (int k = 0; k < 6; k++) {
        const PicaTev *t = &e->tev[k];
        printf("tev%d src=%X%X%X/%X%X%X op=%X%X%X/%X%X%X comb=%X/%X k=%08X esc=%u/%u\n", k, t->fuente_rgb[0],
               t->fuente_rgb[1], t->fuente_rgb[2], t->fuente_a[0], t->fuente_a[1], t->fuente_a[2], t->operando_rgb[0],
               t->operando_rgb[1], t->operando_rgb[2], t->operando_a[0], t->operando_a[1], t->operando_a[2],
               t->comb_rgb, t->comb_a, t->color, t->escala_rgb, t->escala_a);
    }
    printf("buf niebla=%u rgb=%X a=%X color=%08X\n", e->niebla, e->tev_buffer_rgb, e->tev_buffer_a, e->tev_buffer_color);
    printf("frag modo=%u blend=%u eq=%u/%u f=%u,%u,%u,%u lop=%u bc=%08X at=%u,%u,%u st=%u,%u,%u,%02X,%02X op=%u,%u,%u "
           "dt=%u,%u,%u cm=%X\n",
           e->modo_fragmento, e->blend_activo, e->blend_eq_rgb, e->blend_eq_a, e->blend_src_rgb, e->blend_dst_rgb,
           e->blend_src_a, e->blend_dst_a, e->logic_op, e->blend_color, e->alpha_test, e->alpha_func, e->alpha_ref,
           e->stencil_test, e->stencil_func, e->stencil_ref, e->stencil_wmask, e->stencil_imask, e->stencil_fail,
           e->stencil_zfail, e->stencil_zpass, e->depth_test, e->depth_func, e->depth_write, e->color_mask);
    printf("fb c=%08X d=%08X fmt=%u/%u %ux%u flip=%u rw=%u%u%u%u\n", e->color_dir, e->depth_dir, e->color_formato,
           e->depth_formato, e->fb_ancho, e->fb_alto, e->fb_flip, e->color_lectura, e->color_escritura,
           e->depth_lectura, e->depth_escritura);
    for (int k = 0; k < 3; k++) {
        const PicaTextura *t = &e->tex[k];
        printf("tex%d act=%u dir=%08X %ux%u fmt=%u filt=%u%u%u wrap=%u,%u tipo=%u borde=%08X lod=%d,%u,%u\n", k,
               t->activa, t->direccion, t->ancho, t->alto, t->formato, t->mag_lineal, t->min_lineal, t->mip_lineal,
               t->wrap_s, t->wrap_t, t->tipo, t->color_borde, t->lod_bias, t->lod_min, t->lod_max);
    }
    printf("luz act=%u n=%u tex2c1=%u lut=%08X niebla=%08X\n", e->luz_activa, e->num_luces, e->tex2_usa_coord1,
           fnv(&e->luz_lut[0][0], 24 * 256), fnv(e->niebla_lut, 128));
    const PicaVertices *v = &e->vtx;
    printf("vtx base=%08X fijos=%03X total=%u fmt=", v->base_fisica, v->mascara_fijos, v->total_atributos);
    for (int k = 0; k < 12; k++)
        printf("%u%u", v->formato[k], v->componentes[k]);
    printf("\n");
    for (int k = 0; k < 12; k++) {
        if (!v->loader[k].offset && !v->loader[k].stride && !v->loader[k].num_comp)
            continue;
        printf("loader%d off=%08X stride=%u n=%u comp=", k, v->loader[k].offset, v->loader[k].stride,
               v->loader[k].num_comp);
        for (int j = 0; j < 12; j++)
            printf("%X", v->loader[k].comp[j]);
        printf("\n");
    }
    printf("idx off=%08X u16=%u nv=%u voff=%u topo=%u gs=%u\n", e->idx.offset, e->idx.es_u16, e->idx.num_vertices,
           e->idx.vertex_offset, e->idx.topologia, e->usa_gs);
    volcar_shader("vs", &e->vs);
    volcar_shader("gs", &e->gs);
    for (int k = 0; k < 16; k++) {
        const PicaVec4 *f = &e->atr_fijo[k];
        if (bitsf(f->x) | bitsf(f->y) | bitsf(f->z) | bitsf(f->w))
            printf("fijo%d %08X %08X %08X %08X\n", k, bitsf(f->x), bitsf(f->y), bitsf(f->z), bitsf(f->w));
    }
}

void pica_dibujar(const PicaEstado *e) {
    printf("== dibujo %u\n", e->dibujos);
    volcar(e);
}

/* memoria simulada para los saltos */
static struct { uint32_t dir, n; uint32_t *p; } mem[16];
static int n_mem;

static const uint8_t *memoria(uint32_t dir, uint32_t tam) {
    for (int k = 0; k < n_mem; k++)
        if (dir >= mem[k].dir && dir + tam <= mem[k].dir + 4 * mem[k].n)
            return (const uint8_t *)mem[k].p + (dir - mem[k].dir);
    return 0;
}

static uint32_t leer(FILE *f) {
    uint32_t v = 0;
    if (fread(&v, 4, 1, f) != 1) {
        fprintf(stderr, "archivo corto\n");
        exit(2);
    }
    return v;
}

static uint32_t *leer_n(FILE *f, uint32_t n) {
    uint32_t *p = malloc(4 * (size_t)n + 4);
    if (n && fread(p, 4, n, f) != n) {
        fprintf(stderr, "archivo corto\n");
        exit(2);
    }
    return p;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "uso: prueba_pica casos.bin\n");
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f)
        return 2;
    if (leer(f) != 0x41434950u) { /* "PICA" */
        fprintf(stderr, "no es un .bin de casos\n");
        return 2;
    }
    uint32_t casos = leer(f);
    pica_memoria = memoria;
    for (uint32_t c = 0; c < casos; c++) {
        uint32_t n = leer(f);
        uint32_t *pal = leer_n(f, n);
        n_mem = (int)leer(f);
        for (int k = 0; k < n_mem; k++) {
            mem[k].dir = leer(f);
            mem[k].n = leer(f);
            mem[k].p = leer_n(f, mem[k].n);
        }
        pica_reiniciar();
        int fin = pica_ejecutar_palabras(pal, n);
        printf("=== caso %u fin=%d dib=%u irq=%u cmds=%u err=%u\n", c, fin, pica.e.dibujos, pica.e.irq_p3d,
               pica.e.comandos, pica.e.errores);
        for (int r = 0; r < PICA_NUM_REGS; r++)
            if (pica.reg[r])
                printf("r%03X=%08X\n", r, pica.reg[r]);
        volcar(&pica.e);
        printf("--- fin caso %u\n", c);
        free(pal);
        for (int k = 0; k < n_mem; k++)
            free(mem[k].p);
    }
    fclose(f);
    return 0;
}
