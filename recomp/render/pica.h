/* Interprete de listas de comandos de la GPU PICA200 -> estado de registros (paso 5 del port, base del render).
 *
 * Formato de un comando (3dbrew "GPU/Internal Registers"): [parametro0][cabecera] + parametros extra, rellenado a
 * 8 bytes. Cabecera: bits 0-15 registro, 16-19 mascara de bytes, 20-27 cantidad de parametros extra, 31 = modo
 * consecutivo (el extra k va al registro+1+k; si no, todos van al mismo registro).
 *
 * El banco de 0x300 registros guarda el ultimo valor (respetando la mascara de bytes). Algunos registros tienen
 * efecto lateral (como en el hardware / Azahar, que se uso SOLO como referencia de lectura):
 *   - subida de uniforms float del shader (cola empaquetada: 3 palabras = 4 float24, o 4 palabras = 4 float32),
 *     el indice (bits 0-6 de *_FLOATUNIFORM_INDEX) avanza EN el banco;
 *   - codigo y swizzles del shader (el offset avanza en el banco); LUTs de luz y de niebla (idem);
 *   - atributos fijos (FIXEDATTRIB), saltos de lista (CMDBUF_JUMP), FINALIZE (IRQ) y los disparos de dibujo
 *     (DRAWARRAYS / DRAWELEMENTS), que llaman a pica_dibujar() con el estado ya decodificado.
 * Si no hay geometry shader (GEOSTAGE_CONFIG.use_gs != 2 y VSH_COM_MODE = 0), lo que se sube al VS se copia al GS.
 */
#ifndef PICA_H
#define PICA_H

#include <stdint.h>

#define PICA_NUM_REGS 0x300

typedef struct { float x, y, z, w; } PicaVec4;

/* --- vertices --- */
enum { PICA_ATR_BYTE = 0, PICA_ATR_UBYTE = 1, PICA_ATR_SHORT = 2, PICA_ATR_FLOAT = 3 };

typedef struct {
    uint32_t base_fisica;          /* ATTRIBBUFFERS_LOC * 16 */
    uint8_t formato[12];           /* PICA_ATR_* */
    uint8_t componentes[12];       /* 1..4 */
    uint16_t mascara_fijos;        /* bit n = el atributo n sale del valor fijo (no del buffer) */
    uint8_t total_atributos;       /* max_attribute_index + 1 */
    struct {
        uint32_t offset;           /* relativo a base_fisica */
        uint8_t comp[12];          /* 0..11 = atributo; 12..15 = relleno de 4/8/12/16 bytes */
        uint8_t num_comp;          /* component_count */
        uint8_t stride;            /* byte_count */
    } loader[12];
} PicaVertices;

typedef struct {
    uint32_t offset;               /* relativo a la base de atributos */
    uint8_t es_u16;                /* 0 = u8, 1 = u16 */
    uint32_t num_vertices;
    uint32_t vertex_offset;        /* primer vertice en DRAWARRAYS */
    uint8_t topologia;             /* 0 lista, 1 tira, 2 abanico, 3 shader (GS) */
    uint8_t es_elements;           /* 1 = DRAWELEMENTS (con indices), 0 = DRAWARRAYS (lo pone el disparo) */
} PicaIndices;

/* --- shaders --- */
typedef struct {
    PicaVec4 f[96];                /* uniforms float (c0-c95), ya en float32 */
    uint8_t i[4][4];               /* uniforms int i0-i3: x (cuenta), y (inicio), z (paso), w */
    uint16_t b;                    /* uniforms bool b0-b15 */
    uint32_t codigo[4096];         /* memoria de programa */
    uint32_t swizzles[4096];       /* descriptores de operando */
    uint32_t entrada;              /* main_offset (bits 0-15 de *_ENTRYPOINT) */
    uint8_t num_entradas;          /* (INPUTBUFFER_CONFIG & 0xF) + 1 */
    uint8_t permutacion[16];       /* el atributo a va al registro de entrada v[permutacion[a]] (Azahar LoadInput) */
    uint16_t mascara_salida;       /* OUTMAP_MASK */
    /* cola de subida de uniforms (interna) */
    uint32_t cola[4];
    uint32_t n_cola;
} PicaShader;

/* --- etapa de fragmentos --- */
typedef struct {
    uint8_t fuente_rgb[3], fuente_a[3];     /* 0 color vtx, 1 luz difusa, 2 especular, 3-6 tex0-3, D buffer, E const, F previo */
    uint8_t operando_rgb[3], operando_a[3];
    uint8_t comb_rgb, comb_a;               /* 0 REPLACE 1 MOD 2 ADD 3 ADDS 4 LERP 5 SUB 6 DOT3_RGB 7 DOT3_RGBA 8 MULADD 9 ADDMUL */
    uint32_t color;                         /* constante RGBA8 (r en bits 0-7) */
    uint8_t escala_rgb, escala_a;           /* 1, 2 o 4 */
} PicaTev;

typedef struct {
    uint8_t activa;
    uint32_t direccion;                     /* fisica (ADDR1 * 8) */
    uint16_t ancho, alto;
    uint8_t formato;                        /* 0 RGBA8 ... 13 ETC1A4 */
    uint8_t mag_lineal, min_lineal, mip_lineal;
    uint8_t wrap_s, wrap_t;
    uint8_t tipo;                           /* 0 2D, 1 cubo, 2 sombra 2D, 3 proyeccion, 4 sombra cubo, 5 desactivada */
    uint32_t color_borde;
    int16_t lod_bias;                       /* fijo 1.4.8 */
    uint8_t lod_min, lod_max;
} PicaTextura;

typedef struct {
    /* rasterizador */
    uint8_t culling;                        /* 0/3 ninguno, 1 conserva horario (cw), 2 conserva antihorario (ccw) */
    float viewport_ancho, viewport_alto;    /* = 2 * f24(VIEWPORT_WIDTH/HEIGHT) */
    int16_t viewport_x, viewport_y;
    float depth_escala, depth_offset;       /* f24 */
    uint8_t depthmap_activo;
    uint8_t scissor_modo;                   /* 0 off, 1 dentro invertido?, 3 normal */
    uint16_t scissor_x0, scissor_y0, scissor_x1, scissor_y1;

    /* TEV */
    PicaTev tev[6];
    uint8_t tev_buffer_rgb, tev_buffer_a;   /* bit k = la etapa k+1 actualiza el buffer (k = 0..3) */
    uint8_t niebla;                         /* 0 no, 5 niebla, 7 gas */
    uint32_t tev_buffer_color;

    /* operaciones de fragmento */
    uint8_t modo_fragmento;                 /* 0 normal, 3 gas, 4 sombra */
    uint8_t blend_activo;                   /* 1 = blend, 0 = logic op */
    uint8_t blend_eq_rgb, blend_eq_a;       /* 0 add 1 sub 2 revsub 3 min 4 max */
    uint8_t blend_src_rgb, blend_dst_rgb, blend_src_a, blend_dst_a;  /* 0..14 */
    uint8_t logic_op;
    uint32_t blend_color;
    uint8_t alpha_test, alpha_func, alpha_ref;
    uint8_t stencil_test, stencil_func, stencil_ref, stencil_wmask, stencil_imask;
    uint8_t stencil_fail, stencil_zfail, stencil_zpass;
    uint8_t depth_test, depth_func, depth_write;
    uint8_t color_mask;                     /* bit0 r, 1 g, 2 b, 3 a */

    /* framebuffer */
    uint32_t color_dir, depth_dir;          /* fisicas */
    uint8_t color_formato;                  /* 0 RGBA8, 1 RGB8, 2 RGB5A1, 3 RGB565, 4 RGBA4 */
    uint8_t depth_formato;                  /* 0 D16, 2 D24, 3 D24S8 */
    uint16_t fb_ancho, fb_alto;
    uint8_t fb_flip;
    uint8_t color_lectura, color_escritura, depth_lectura, depth_escritura;

    /* texturas */
    PicaTextura tex[3];
    uint8_t tex2_usa_coord1;

    /* luz de fragmento */
    uint8_t luz_activa;                     /* LIGHTING_ENABLE0 */
    uint8_t num_luces;                      /* (LIGHTING_NUM_LIGHTS & 7) + 1 */
    uint32_t luz_lut[24][256];
    uint32_t niebla_lut[128];
    uint32_t luz_lut_ver, niebla_lut_ver;   /* suben cuando una escritura de LUT CAMBIA un valor (el rasterizador re-sube) */

    /* vertices, shaders, atributos fijos */
    PicaVertices vtx;
    PicaIndices idx;
    PicaShader vs, gs;
    PicaVec4 atr_fijo[16];
    uint32_t cola_fijo[3];
    uint32_t n_cola_fijo;
    uint8_t usa_gs;
    /* modo inmediato (FIXEDATTRIB indice 15): si inm_n > 0 el dibujo es un triangulo suelto cuyas entradas ya
       vienen aqui (inm[v][a] = atributo a del vertice v, antes de la permutacion), no del buffer de vertices */
    PicaVec4 inm[3][16];
    uint32_t inm_n;
    uint32_t inm_triangulos;                /* contador (pruebas) */

    /* contadores (para GSP y pruebas) */
    uint32_t dibujos;                       /* disparos de DRAWARRAYS / DRAWELEMENTS */
    uint32_t irq_p3d;                       /* FINALIZE que dispararon la IRQ P3D */
    uint32_t comandos;                      /* escrituras de registro procesadas */
    uint32_t errores;                       /* cabeceras invalidas, lista que se sale, memoria no mapeada */
} PicaEstado;

typedef struct {
    uint32_t reg[PICA_NUM_REGS];
    PicaEstado e;
    /* SELLOS (P2, 10 oct): cada vez que una escritura CAMBIA un dato de un grupo, el grupo recibe un numero NUEVO de un
       contador global de 64 bits que nunca se repite (pica.c). Viajan DENTRO de 'pica' junto con su dato: la
       re-ejecucion del modo Monitor (interp.c memcpy de 'pica') restaura dato y sello a la vez, asi que sello igual =>
       contenido igual. 0 = desconocido (el rasterizador recalcula). Fuera de PicaEstado a proposito: el estado FALSO
       de la cinta de H1 copia [0, luz_lut) de PicaEstado y aqui no toca nada. */
    uint64_t sello_vs;         /* vs.codigo[0..511] (lo que hashea vs_para) */
    uint64_t sello_frag;       /* registros de la clave de fragmento: TEV (C0-C2, C4 de cada etapa), 1C2-1C4, 1C6, 1D0-1D2 */
    uint64_t sello_lut[24];    /* contenido de luz_lut[t] */
} Pica;

extern Pica pica;

/* traduce una direccion fisica del 3DS a memoria del anfitrion (NULL si no esta); lo pone el integrador */
extern const uint8_t *(*pica_memoria)(uint32_t dir_fisica, uint32_t tam);

/* interfaz acordada con el agente E (gsp.h): ejecuta la lista de comandos en dir_fisica (tam en bytes) */
void pica_ejecutar(uint32_t dir_fisica, uint32_t tam);
/* lo mismo sobre memoria del anfitrion (pruebas); devuelve 1 si termino por FINALIZE con autostop */
int pica_ejecutar_palabras(const uint32_t *palabras, uint32_t n);
/* deja banco y estado en cero */
void pica_reiniciar(void);
/* escribe un registro como lo haria un comando (mascara de 4 bits); expuesto para pruebas */
void pica_escribir(uint32_t reg, uint32_t valor, uint32_t mascara);
/* rehace los campos decodificados de PicaEstado desde el banco (lo llama pica_ejecutar al final y antes de dibujar) */
void pica_decodificar(void);
/* float24 del PICA (1 signo, 7 exponente con sesgo 63, 16 mantisa) -> float32 */
float pica_f24(uint32_t v);
/* float16 (1.5.10) y float31 (1.7.23) del PICA -> float32 */
float pica_f16(uint32_t v);
float pica_f31(uint32_t v);
/* float20 (1.7.12) del PICA (atenuacion por distancia de la luz) */
float pica_f20(uint32_t v);

/* callback del disparo de dibujo; vacio por ahora (pica_dibujar.c) */
void pica_dibujar(const PicaEstado *e);

#endif
