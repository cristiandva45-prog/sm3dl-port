/* Interprete de listas de comandos PICA200 -> estado de registros. Ver pica.h.
 * Referencia de lectura: 3dbrew (GPU/Internal Registers) y Azahar video_core/pica (GPLv2: nada copiado literal).
 *
 * Sabotajes de prueba (prueba_pica):
 *   -DPICA_SABOTAJE_MASCARA  ignora la mascara de bytes (escribe la palabra entera)
 *   -DPICA_SABOTAJE_F24      sesgo del exponente float24 en 64 en vez de 63
 */
#include "pica.h"

#include <string.h>

Pica pica;
const uint8_t *(*pica_memoria)(uint32_t dir_fisica, uint32_t tam) = 0;

/* P2 (10 oct): fuente de los sellos de pica.h. Nunca se reinicia ni vuelve atras (vive FUERA de 'pica': la
   restauracion de interp.c no la toca), asi que un sello nuevo jamas coincide con uno ya repartido. */
static uint64_t g_sello;
#ifdef P2_SABOTAJE_SIN_SELLO   /* solo agentes_dx12\P2\prueba_p2.c: sella una vez y nunca mas (= no marcar sucio) */
static inline uint64_t sello_nuevo(void) { return g_sello ? g_sello : ++g_sello; }
#else
static inline uint64_t sello_nuevo(void) { return ++g_sello; }
#endif
/* registros que entran en clave_frag (raster_gl.c): C0-C2 y C4 de las 6 etapas TEV, 1C2-1C4, 1C6, 1D0-1D2 */
static inline int reg_de_clave_frag(uint32_t reg) {
    if (reg >= 0x0C0 && reg < 0x100) {
        uint32_t b = reg & ~7u, o = reg & 7u;
        return (b == 0x0C0 || b == 0x0C8 || b == 0x0D0 || b == 0x0D8 || b == 0x0F0 || b == 0x0F8) && o != 3 && o <= 4;
    }
    return (reg >= 0x1C2 && reg <= 0x1C4) || reg == 0x1C6 || (reg >= 0x1D0 && reg <= 0x1D2);
}

/* registros con efecto lateral */
enum {
    R_FINALIZE = 0x010, R_IRQ_CMP = 0x020, R_IRQ_AUTOSTOP = 0x034,
    R_FOG_LUT_INDEX = 0x0E6, R_FOG_LUT_DATA0 = 0x0E8,
    R_LUT_INDEX = 0x1C5, R_LUT_DATA0 = 0x1C8,
    R_GEOSTAGE = 0x229, R_DRAWARRAYS = 0x22E, R_DRAWELEMENTS = 0x22F,
    R_MAX_ATRIB = 0x242, R_TOPOLOGIA = 0x25E, R_REINICIAR_PRIM = 0x25F,
    R_FIX_INDEX = 0x232, R_FIX_DATA0 = 0x233,
    R_CMDBUF_SIZE0 = 0x238, R_CMDBUF_ADDR0 = 0x23A, R_CMDBUF_JUMP0 = 0x23C,
    R_VSH_COM_MODE = 0x244,
    R_GSH = 0x280, R_VSH = 0x2B0
};
/* desplazamientos dentro del bloque de un shader (GSH 0x280 / VSH 0x2B0) */
enum {
    S_BOOL = 0x00, S_INT0 = 0x01, S_INPUT_CFG = 0x09, S_ENTRADA = 0x0A, S_PERM_LO = 0x0B, S_PERM_HI = 0x0C,
    S_OUTMASK = 0x0D, S_UNI_INDEX = 0x10, S_UNI_DATA0 = 0x11, S_COD_INDEX = 0x1B, S_COD_DATA0 = 0x1C,
    S_SWZ_INDEX = 0x25, S_SWZ_DATA0 = 0x26
};

static uint32_t expandir(uint32_t m) {
#ifdef PICA_SABOTAJE_MASCARA
    (void)m;
    return 0xFFFFFFFFu;
#else
    return (m & 1 ? 0xFFu : 0) | (m & 2 ? 0xFF00u : 0) | (m & 4 ? 0xFF0000u : 0) | (m & 8 ? 0xFF000000u : 0);
#endif
}

static float de_bits(uint32_t b) {
    float f;
    memcpy(&f, &b, 4);
    return f;
}

/* float con M bits de mantisa y E de exponente -> float32, sin perdida (los denormales se renormalizan:
 * en float32 caben como normales; el ALU del PICA los aplana, eso es asunto del shader, no del dato). */
static float pica_float(uint32_t v, int M, int E) {
#ifdef PICA_SABOTAJE_F24
    const int sesgo = 127 - ((1 << (E - 1)) - 1) - (M == 16 ? 1 : 0);
#else
    const int sesgo = 127 - ((1 << (E - 1)) - 1);
#endif
    const uint32_t emask = (1u << E) - 1, mmask = (1u << M) - 1;
    uint32_t signo = ((v >> (M + E)) & 1u) << 31;
    int32_t e = (int32_t)((v >> M) & emask);
    uint32_t m = v & mmask, r;
    if (e == 0 && m == 0) {
        r = signo;                                   /* +-0 */
    } else if (e == 0) {                             /* denormal -> normal en float32 */
        e = sesgo + 1;
        while (!(m & (1u << M))) {
            e--;
            m <<= 1;
        }
        r = signo | ((uint32_t)e << 23) | ((m & mmask) << (23 - M));
    } else if ((uint32_t)e == emask) {
        r = signo | (0xFFu << 23) | (m << (23 - M)); /* inf / NaN (la mantisa se conserva) */
    } else {
        r = signo | ((uint32_t)(sesgo + e) << 23) | (m << (23 - M));
    }
    return de_bits(r);
}

float pica_f24(uint32_t v) { return pica_float(v & 0xFFFFFFu, 16, 7); }
float pica_f16(uint32_t v) { return pica_float(v & 0xFFFFu, 10, 5); }
float pica_f31(uint32_t v) { return pica_float(v & 0x7FFFFFFFu, 23, 7); }
float pica_f20(uint32_t v) { return pica_float(v & 0xFFFFFu, 12, 7); }

/* 3 palabras empaquetadas -> 4 float24 (w x y z repartidos como en el hardware: w arriba de la palabra 0) */
static PicaVec4 desempacar_f24(const uint32_t c[3]) {
    PicaVec4 r;
    r.x = pica_f24(c[2] & 0xFFFFFFu);
    r.y = pica_f24(((c[1] & 0xFFFFu) << 8) | (c[2] >> 24));
    r.z = pica_f24(((c[0] & 0xFFu) << 16) | (c[1] >> 16));
    r.w = pica_f24(c[0] >> 8);
    return r;
}

static int sin_gs(void) {
    return (pica.reg[R_VSH_COM_MODE] & 1) == 0 && (pica.reg[R_GEOSTAGE] & 3) != 2;
}

/* ---------------- subidas al shader ---------------- */
static void uniform_float(PicaShader *s, uint32_t base, uint32_t valor, int espejo) {
    uint32_t *ireg = &pica.reg[base + S_UNI_INDEX];
    const int f32 = (*ireg >> 31) & 1;
    s->cola[s->n_cola++] = valor;
    if (s->n_cola < (f32 ? 4u : 3u))
        return;
    s->n_cola = 0;
    PicaVec4 v;
    if (f32) { /* la palabra 0 es w */
        v.w = de_bits(s->cola[0]);
        v.z = de_bits(s->cola[1]);
        v.y = de_bits(s->cola[2]);
        v.x = de_bits(s->cola[3]);
    } else {
        v = desempacar_f24(s->cola);
    }
    uint32_t idx = *ireg & 0x7F;
    if (idx >= 96)
        return; /* el juego puede mandar 0x7F: el hardware lo ignora */
    s->f[idx] = v;
    if (espejo)
        pica.e.gs.f[idx] = v;
    *ireg = (*ireg & ~0x7Fu) | ((idx + 1) & 0x7F);
}

static void palabra_codigo(PicaShader *s, uint32_t base, uint32_t valor, int espejo, int swz) {
    uint32_t *oreg = &pica.reg[base + (swz ? S_SWZ_INDEX : S_COD_INDEX)];
    uint32_t lim = swz ? 4096u : (base == R_VSH ? 512u : 4096u);
    uint32_t off = *oreg;
    if (off >= lim) {
        pica.e.errores++;
        return;
    }
    /* P2: sello del codigo del VS solo si la palabra CAMBIA y cae en lo que hashea vs_para (0..511) */
    if (!swz && s == &pica.e.vs && off < 512 && s->codigo[off] != valor) pica.sello_vs = sello_nuevo();
    (swz ? s->swizzles : s->codigo)[off] = valor;
    if (espejo)
        (swz ? pica.e.gs.swizzles : pica.e.gs.codigo)[off] = valor;
    *oreg = off + 1;
}

static void shader_especial(uint32_t reg, uint32_t valor) {
    const int es_vs = reg >= R_VSH;
    const uint32_t base = es_vs ? R_VSH : R_GSH;
    PicaShader *s = es_vs ? &pica.e.vs : &pica.e.gs;
    const int espejo = es_vs && sin_gs();
    const uint32_t k = reg - base;
    if (k == S_BOOL) {
        s->b = (uint16_t)(pica.reg[reg] & 0xFFFF);
        if (espejo)
            pica.e.gs.b = s->b;
    } else if (k >= S_INT0 && k < S_INT0 + 4) {
        uint32_t v = pica.reg[reg];
        for (int j = 0; j < 4; j++) {
            s->i[k - S_INT0][j] = (uint8_t)(v >> (8 * j));
            if (espejo)
                pica.e.gs.i[k - S_INT0][j] = s->i[k - S_INT0][j];
        }
    } else if (k == S_OUTMASK) {
        if (espejo)
            pica.reg[R_GSH + S_OUTMASK] = pica.reg[reg];
    } else if (k >= S_UNI_DATA0 && k < S_UNI_DATA0 + 8) {
        uniform_float(s, base, valor, espejo);
    } else if (k >= S_COD_DATA0 && k < S_COD_DATA0 + 8) {
        palabra_codigo(s, base, valor, espejo, 0);
    } else if (k >= S_SWZ_DATA0 && k < S_SWZ_DATA0 + 8) {
        palabra_codigo(s, base, valor, espejo, 1);
    }
}

static int es_especial_shader(uint32_t reg) {
    if (reg < R_GSH || reg >= R_VSH + 0x30)
        return 0;
    uint32_t k = (reg - R_GSH) % 0x30;
    return k == S_BOOL || (k >= S_INT0 && k < S_INT0 + 4) || (k == S_OUTMASK && reg >= R_VSH) ||
           (k >= S_UNI_DATA0 && k < S_UNI_DATA0 + 8) || (k >= S_COD_DATA0 && k < S_COD_DATA0 + 8) ||
           (k >= S_SWZ_DATA0 && k < S_SWZ_DATA0 + 8);
}

/* ---------------- lista en curso ---------------- */
static struct {
    const uint32_t *p;
    uint32_t n, k;
    int parar, saltar;
    const uint32_t *nuevo_p;
    uint32_t nuevo_n;
} lista;

/* ---------------- modo inmediato (FIXEDATTRIB indice 15) ----------------
 * Como Azahar pica_core.cpp SubmitImmediate/DrawImmediate + primitive_assembly.cpp (solo lectura): cada triple de
 * FIXEDATTRIB_DATA es un atributo del vertice en curso; al llegar al atributo max_input_attrib_index (0x242) el
 * vertice esta completo y entra al ensamblador de primitivas (lista / tira / abanico, 0x25E); cada triangulo
 * formado se dibuja en el acto (pica_dibujar con e->inm_n = 3). Escribir FIXEDATTRIB_INDEX, la topologia o
 * RESTART_PRIMITIVE reinicia el ensamblador. */
static struct {
    PicaVec4 vtx[16];          /* atributos del vertice en curso */
    uint32_t actual;
    PicaVec4 buf[2][16];       /* los 2 vertices que guarda el ensamblador */
    uint32_t indice, listo;
} inm;

static void inm_reiniciar(void) {
    inm.actual = 0;
    inm.indice = 0;
    inm.listo = 0;
}

static void inm_triangulo(const PicaVec4 *a, const PicaVec4 *b, const PicaVec4 *c) {
    PicaEstado *e = &pica.e;
    memcpy(e->inm[0], a, sizeof e->inm[0]);
    memcpy(e->inm[1], b, sizeof e->inm[1]);
    memcpy(e->inm[2], c, sizeof e->inm[2]);
    e->dibujos++;
    e->inm_triangulos++;
    pica_decodificar();
    e->idx.es_elements = 0;
    e->inm_n = 3;
    pica_dibujar(e);
    e->inm_n = 0;
}

static void inm_atributo(PicaVec4 v) {
    uint32_t max = pica.reg[R_MAX_ATRIB] & 0xF;
    inm.vtx[inm.actual & 15] = v;
    if (inm.actual < max) {
        inm.actual++;
        return;
    }
    inm.actual = 0;
    uint32_t topo = (pica.reg[R_TOPOLOGIA] >> 8) & 3;
    if (topo == 0 || topo == 3) {             /* lista (o "shader" sin GS: igual) */
        if (inm.indice < 2) {
            memcpy(inm.buf[inm.indice++], inm.vtx, sizeof inm.vtx);
        } else {
            inm.indice = 0;
            inm_triangulo(inm.buf[0], inm.buf[1], inm.vtx);
        }
        return;
    }
    if (inm.listo)
        inm_triangulo(inm.buf[0], inm.buf[1], inm.vtx);
    memcpy(inm.buf[inm.indice], inm.vtx, sizeof inm.vtx);
    inm.listo |= inm.indice == 1;
    inm.indice = topo == 1 ? !inm.indice : 1;  /* tira alterna, abanico conserva el vertice 0 */
}

static void especial(uint32_t reg, uint32_t valor) {
    PicaEstado *e = &pica.e;
    switch (reg) {
    case R_FINALIZE: {
        uint32_t a = pica.reg[R_FINALIZE], b = pica.reg[R_IRQ_CMP];
        if (((a ^ b) & 0xFF) == 0 || ((a ^ b) & 0xFF00) == 0 || ((a ^ b) & 0xFF0000) == 0 ||
            ((a ^ b) & 0xFF000000u) == 0) {
            e->irq_p3d++;
            if (pica.reg[R_IRQ_AUTOSTOP] & 1)
                lista.parar = 1;
        }
        return;
    }
    case R_FOG_LUT_DATA0: case R_FOG_LUT_DATA0 + 1: case R_FOG_LUT_DATA0 + 2: case R_FOG_LUT_DATA0 + 3:
    case R_FOG_LUT_DATA0 + 4: case R_FOG_LUT_DATA0 + 5: case R_FOG_LUT_DATA0 + 6: case R_FOG_LUT_DATA0 + 7: {
        uint32_t *ir = &pica.reg[R_FOG_LUT_INDEX];
        uint32_t i = *ir & 0xFFFF;
        if (e->niebla_lut[i % 128] != valor) {
            e->niebla_lut[i % 128] = valor;
            e->niebla_lut_ver++;
        }
        *ir = (*ir & ~0xFFFFu) | ((i + 1) & 0xFFFF);
        return;
    }
    case R_LUT_DATA0: case R_LUT_DATA0 + 1: case R_LUT_DATA0 + 2: case R_LUT_DATA0 + 3:
    case R_LUT_DATA0 + 4: case R_LUT_DATA0 + 5: case R_LUT_DATA0 + 6: case R_LUT_DATA0 + 7: {
        uint32_t *ir = &pica.reg[R_LUT_INDEX];
        uint32_t i = *ir & 0xFF, t = (*ir >> 8) & 0x1F;
        if (t < 24) {
            if (e->luz_lut[t][i] != valor) {   /* el juego re-escribe las mismas tablas en cada material */
                e->luz_lut[t][i] = valor;
                e->luz_lut_ver++;
                pica.sello_lut[t] = sello_nuevo();
            }
        }
        else
            e->errores++;
        *ir = (*ir & ~0xFFu) | ((i + 1) & 0xFF);
        return;
    }
    case R_FIX_INDEX:
        e->n_cola_fijo = 0;
        inm_reiniciar();
        return;
    case R_TOPOLOGIA:
    case R_REINICIAR_PRIM:
        inm.listo = 0;
        inm.indice = 0;
        return;
    case R_FIX_DATA0: case R_FIX_DATA0 + 1: case R_FIX_DATA0 + 2: {
        e->cola_fijo[e->n_cola_fijo++] = valor;
        if (e->n_cola_fijo < 3)
            return;
        e->n_cola_fijo = 0;
        uint32_t *ir = &pica.reg[R_FIX_INDEX];
        uint32_t i = *ir & 0xF;
        if (i < 15) {
            e->atr_fijo[i] = desempacar_f24(e->cola_fijo);
            *ir = (*ir & ~0xFu) | (i + 1);
        } else {
            inm_atributo(desempacar_f24(e->cola_fijo));
        }
        return;
    }
    case R_DRAWARRAYS:
    case R_DRAWELEMENTS:
        e->dibujos++;
        pica_decodificar();
        e->idx.es_elements = reg == R_DRAWELEMENTS;
        pica_dibujar(e);
        return;
    case R_CMDBUF_JUMP0:
    case R_CMDBUF_JUMP0 + 1: {
        uint32_t c = reg - R_CMDBUF_JUMP0;
        uint32_t dir = (pica.reg[R_CMDBUF_ADDR0 + c] & 0x0FFFFFFFu) * 8;
        uint32_t tam = (pica.reg[R_CMDBUF_SIZE0 + c] & 0xFFFFFu) * 8;
        const uint8_t *m = pica_memoria ? pica_memoria(dir, tam) : 0;
        if (!m) {
            e->errores++;
            lista.parar = 1;
            return;
        }
        lista.saltar = 1;
        lista.nuevo_p = (const uint32_t *)m;
        lista.nuevo_n = tam / 4;
        return;
    }
    default:
        if (es_especial_shader(reg))
            shader_especial(reg, valor);
        return;
    }
}

void pica_escribir(uint32_t reg, uint32_t valor, uint32_t mascara) {
    if (reg >= PICA_NUM_REGS) {
        pica.e.errores++;
        return;
    }
    uint32_t m = expandir(mascara);
    uint32_t nuevo = (pica.reg[reg] & ~m) | (valor & m);
    if (nuevo != pica.reg[reg] && reg_de_clave_frag(reg)) pica.sello_frag = sello_nuevo();
    pica.reg[reg] = nuevo;
    pica.e.comandos++;
    /* los datos de subida (uniforms, codigo, LUTs) van crudos, como los toma el hardware/Azahar */
    especial(reg, valor);
}

static void correr(void) {
    while (!lista.parar) {
        if (lista.saltar) {
            lista.saltar = 0;
            lista.p = lista.nuevo_p;
            lista.n = lista.nuevo_n;
            lista.k = 0;
        }
        if (lista.k + 2 > lista.n)
            break;
        uint32_t p0 = lista.p[lista.k], cab = lista.p[lista.k + 1];
        uint32_t reg = cab & 0xFFFF, masc = (cab >> 16) & 0xF, extra = (cab >> 20) & 0xFF, cons = cab >> 31;
        uint32_t total = 2 + extra;
        if (lista.k + total > lista.n) {
            pica.e.errores++;
            break;
        }
        const uint32_t *ex = &lista.p[lista.k + 2];
        lista.k += total + (total & 1);
        pica_escribir(reg, p0, masc);
        for (uint32_t j = 0; j < extra && !lista.parar && !lista.saltar; j++)
            pica_escribir(cons ? reg + 1 + j : reg, ex[j], masc);
    }
}

int pica_ejecutar_palabras(const uint32_t *palabras, uint32_t n) {
    memset(&lista, 0, sizeof lista);
    lista.p = palabras;
    lista.n = n;
    correr();
    int r = lista.parar;
    pica_decodificar();
    return r;
}

void pica_ejecutar(uint32_t dir_fisica, uint32_t tam) {
    const uint8_t *m = pica_memoria ? pica_memoria(dir_fisica, tam) : 0;
    if (!m) {
        pica.e.errores++;
        return;
    }
    pica_ejecutar_palabras((const uint32_t *)m, tam / 4);
}

void pica_reiniciar(void) {
    memset(&pica, 0, sizeof pica);
    inm_reiniciar();
}

/* ---------------- decodificacion del banco ---------------- */
static uint8_t bits(uint32_t v, int lo, int n) { return (uint8_t)((v >> lo) & ((1u << n) - 1)); }

static void dec_shader(PicaShader *s, uint32_t base) {
    const uint32_t *r = &pica.reg[base];
    s->entrada = r[S_ENTRADA] & 0xFFFF;
    s->num_entradas = (uint8_t)((r[S_INPUT_CFG] & 0xF) + 1);
    for (int k = 0; k < 8; k++) {
        s->permutacion[k] = bits(r[S_PERM_LO], 4 * k, 4);
        s->permutacion[8 + k] = bits(r[S_PERM_HI], 4 * k, 4);
    }
    s->mascara_salida = (uint16_t)(r[S_OUTMASK] & 0xFFFF);
}

static void dec_textura(PicaTextura *t, int activa, uint32_t borde, uint32_t dim, uint32_t param, uint32_t lod,
                        uint32_t dir, uint32_t tipo) {
    t->activa = (uint8_t)activa;
    t->color_borde = borde;
    t->alto = dim & 0x7FF;
    t->ancho = (dim >> 16) & 0x7FF;
    t->mag_lineal = bits(param, 1, 1);
    t->min_lineal = bits(param, 2, 1);
    t->wrap_t = bits(param, 8, 3);
    t->wrap_s = bits(param, 12, 3);
    t->mip_lineal = bits(param, 24, 1);
    t->tipo = bits(param, 28, 3);
    t->lod_bias = (int16_t)((int32_t)(lod << 19) >> 19);
    t->lod_max = bits(lod, 16, 4);
    t->lod_min = bits(lod, 24, 4);
    t->direccion = (dir & 0x0FFFFFFFu) * 8;
    t->formato = bits(tipo, 0, 4);
}

void pica_decodificar(void) {
    const uint32_t *r = pica.reg;
    PicaEstado *e = &pica.e;
    static const uint8_t escala[4] = {1, 2, 4, 1};
    static const uint16_t tev_base[6] = {0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8};

    e->culling = bits(r[0x040], 0, 2);
    e->viewport_ancho = 2.0f * pica_f24(r[0x041]);
    e->viewport_alto = 2.0f * pica_f24(r[0x043]);
    e->depth_escala = pica_f24(r[0x04D]);
    e->depth_offset = pica_f24(r[0x04E]);
    e->scissor_modo = bits(r[0x065], 0, 2);
    e->scissor_x0 = r[0x066] & 0x3FF;
    e->scissor_y0 = (r[0x066] >> 16) & 0x3FF;
    e->scissor_x1 = r[0x067] & 0x3FF;
    e->scissor_y1 = (r[0x067] >> 16) & 0x3FF;
    e->viewport_x = (int16_t)((int32_t)(r[0x068] << 22) >> 22);
    e->viewport_y = (int16_t)((int32_t)(r[0x068] << 6) >> 22);
    e->depthmap_activo = bits(r[0x06D], 0, 1);

    for (int k = 0; k < 6; k++) {
        const uint32_t *t = &r[tev_base[k]];
        PicaTev *v = &e->tev[k];
        for (int j = 0; j < 3; j++) {
            v->fuente_rgb[j] = bits(t[0], 4 * j, 4);
            v->fuente_a[j] = bits(t[0], 16 + 4 * j, 4);
            v->operando_rgb[j] = bits(t[1], 4 * j, 4);
            v->operando_a[j] = bits(t[1], 12 + 4 * j, 3);
        }
        v->comb_rgb = bits(t[2], 0, 4);
        v->comb_a = bits(t[2], 16, 4);
        v->color = t[3];
        v->escala_rgb = escala[t[4] & 3];
        v->escala_a = escala[(t[4] >> 16) & 3];
    }
    e->niebla = bits(r[0x0E0], 0, 3);
    e->tev_buffer_rgb = bits(r[0x0E0], 8, 4);
    e->tev_buffer_a = bits(r[0x0E0], 12, 4);
    e->tev_buffer_color = r[0x0FD];

    e->modo_fragmento = bits(r[0x100], 0, 2);
    e->blend_activo = bits(r[0x100], 8, 1);
    e->blend_eq_rgb = bits(r[0x101], 0, 3);
    e->blend_eq_a = bits(r[0x101], 8, 3);
    e->blend_src_rgb = bits(r[0x101], 16, 4);
    e->blend_dst_rgb = bits(r[0x101], 20, 4);
    e->blend_src_a = bits(r[0x101], 24, 4);
    e->blend_dst_a = bits(r[0x101], 28, 4);
    e->logic_op = bits(r[0x102], 0, 4);
    e->blend_color = r[0x103];
    e->alpha_test = bits(r[0x104], 0, 1);
    e->alpha_func = bits(r[0x104], 4, 3);
    e->alpha_ref = bits(r[0x104], 8, 8);
    e->stencil_test = bits(r[0x105], 0, 1);
    e->stencil_func = bits(r[0x105], 4, 3);
    e->stencil_wmask = bits(r[0x105], 8, 8);
    e->stencil_ref = bits(r[0x105], 16, 8);
    e->stencil_imask = bits(r[0x105], 24, 8);
    e->stencil_fail = bits(r[0x106], 0, 3);
    e->stencil_zfail = bits(r[0x106], 4, 3);
    e->stencil_zpass = bits(r[0x106], 8, 3);
    e->depth_test = bits(r[0x107], 0, 1);
    e->depth_func = bits(r[0x107], 4, 3);
    e->color_mask = bits(r[0x107], 8, 4);
    e->depth_write = bits(r[0x107], 12, 1);

    e->color_lectura = (r[0x112] & 0xF) != 0;
    e->color_escritura = (r[0x113] & 0xF) != 0;
    e->depth_lectura = (r[0x114] & 3) != 0;
    e->depth_escritura = (r[0x115] & 3) != 0;
    e->depth_formato = bits(r[0x116], 0, 2);
    e->color_formato = bits(r[0x117], 16, 3);
    e->depth_dir = (r[0x11C] & 0x0FFFFFFFu) * 8;
    e->color_dir = (r[0x11D] & 0x0FFFFFFFu) * 8;
    e->fb_ancho = r[0x11E] & 0x7FF;
    e->fb_alto = (uint16_t)(((r[0x11E] >> 12) & 0x3FF) + 1);
    e->fb_flip = bits(r[0x11E], 24, 1);

    dec_textura(&e->tex[0], r[0x080] & 1, r[0x081], r[0x082], r[0x083], r[0x084], r[0x085], r[0x08E]);
    dec_textura(&e->tex[1], (r[0x080] >> 1) & 1, r[0x091], r[0x092], r[0x093], r[0x094], r[0x095], r[0x096]);
    dec_textura(&e->tex[2], (r[0x080] >> 2) & 1, r[0x099], r[0x09A], r[0x09B], r[0x09C], r[0x09D], r[0x09E]);
    e->tex2_usa_coord1 = bits(r[0x080], 13, 1);

    e->luz_activa = bits(r[0x08F], 0, 1);
    e->num_luces = (uint8_t)((r[0x1C2] & 7) + 1);

    PicaVertices *v = &e->vtx;
    v->base_fisica = (r[0x200] & 0x1FFFFFFEu) * 8; /* bits 1-28 * 16 */
    for (int k = 0; k < 12; k++) {
        uint32_t w = k < 8 ? r[0x201] : r[0x202];
        int s = 4 * (k & 7);
        v->formato[k] = bits(w, s, 2);
        v->componentes[k] = (uint8_t)(bits(w, s + 2, 2) + 1);
        const uint32_t *l = &r[0x203 + 3 * k];
        v->loader[k].offset = l[0] & 0x0FFFFFFFu;
        for (int j = 0; j < 8; j++)
            v->loader[k].comp[j] = bits(l[1], 4 * j, 4);
        for (int j = 0; j < 4; j++)
            v->loader[k].comp[8 + j] = bits(l[2], 4 * j, 4);
        v->loader[k].stride = bits(l[2], 16, 8);
        v->loader[k].num_comp = bits(l[2], 28, 4);
    }
    v->mascara_fijos = (uint16_t)((r[0x202] >> 16) & 0xFFF);
    v->total_atributos = (uint8_t)(bits(r[0x202], 28, 4) + 1);

    e->idx.offset = r[0x227] & 0x0FFFFFFFu;
    e->idx.es_u16 = (uint8_t)(r[0x227] >> 31);
    e->idx.num_vertices = r[0x228];
    e->idx.vertex_offset = r[0x22A];
    e->idx.topologia = bits(r[0x25E], 8, 2);

    e->usa_gs = !sin_gs();
    dec_shader(&e->vs, R_VSH);
    dec_shader(&e->gs, R_GSH);
}
