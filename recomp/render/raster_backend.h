/* INTERFAZ DE BACKEND DEL RASTERIZADOR (8 oct 2026, agente A de la tanda D3D12, paso 1 del plan de 9).
 *
 * raster_gl.c  = capa COMUN: decodifica el estado de la PICA200 (registros, TEV, blend, profundidad/stencil, texturas,
 *                LUTs de luz y niebla, vertices, tijera, render targets, lecturas de vuelta hacia la memoria del 3DS,
 *                cache de programas por clave) y SOLO habla con la GPU a traves de esta tabla de funciones.
 * raster_backend_gl.c = backend OpenGL 4.5 (el de siempre, comportamiento identico; es el de REFERENCIA para comparar
 *                el futuro backend D3D12 pixel a pixel). Se incluye con #include al FINAL de raster_gl.c: por eso la capa
 *                comun no ve ni un simbolo de GL (si lo usara, no compila).
 * Seleccion: SM3DL_BACKEND=gl (default) | d3d12 (hoy un stub: avisa "no implementado" y cae a gl).
 *
 * DECISIONES DE DISENO (pensadas para D3D12, no un envoltorio 1:1 de GL):
 *  1. ESTADO INMUTABLE TIPO PSO. Todo el estado de fragmentos/rasterizador va en UNA estructura plana (RbEstado: cull,
 *     clip, profundidad, stencil, mascara de color, blend/logic op). El backend la compara con la anterior (hash) y la
 *     traduce a glEnable/... (GL) o a un D3D12_GRAPHICS_PIPELINE_STATE_DESC de una cache (D3D12). La combinacion
 *     (RbProg + RbEstado + formato de los RT + layout de vertices + topologia) es la clave del PSO. NO hay "setters"
 *     sueltos. La tijera de la PICA NO es estado de GPU: la hace el shader (RbCbFragmento.tijera*).
 *  2. CONSTANT BUFFERS, NO UNIFORMS SUELTOS. Los ~60 glUniform* del raster se agrupan en 4 bloques con layout de
 *     cbuffer (arrays densos rellenos a multiplo de 4 elementos = int4/uint4/float4[] en HLSL; todos los tamanos son
 *     multiplos de 16 bytes): RbCbVertice (b0), RbCbFragmento (b1), RbCbNiebla (b2), RbCbLuz (b3). El GL los reparte en
 *     glUniform* (mismos nombres que consumen los shaders GLSL); D3D12 hace memcpy a un anillo de upload y apunta un
 *     root CBV. Los campos son los MISMOS valores que antes se pasaban uno a uno.
 *  3. DESCRIPTORES. Una "tabla" fija por dibujo: texturas t0..t2 (texturas PICA 0-2), t3 (LUTs de luz, RG32F 256 x
 *     LUT_FILAS) con muestreadores s0..s3; las unidades GL 0-3 son los mismos numeros. tex_enlazar(unidad, tex, muestreador)
 *     cubre SRV + sampler. Las unidades 5 (giro de la pantalla en alta) y la de las capas son internas del backend.
 *  4. LECTURAS ASINCRONAS CON FENCE. RbLectura = buffer de readback + fence (PBO+glFenceSync / buffer READBACK + ID3D12Fence).
 *     El flujo es siempre: lectura_emitir (copia GPU->buffer y señala) ... lectura_lista / lectura_esperar ...
 *     lectura_cerrar (consume la fence) -> lectura_mapear / lectura_desmapear. Reemplaza los 15 glReadPixels: los
 *     sincronos son rt_leer (emitir + esperar), los diferidos usan RbLectura.
 *  5. PASES. fijar_destino(rt, viewport) = OMSetRenderTargets + RSSetViewports. rt_limpiar = ClearRenderTargetView /
 *     ClearDepthStencilView. copiar() = copia/escalado/volteo entre superficies (D3D12: pasada de blit o CopyTexture
 *     cuando los rectangulos coinciden). NULL como superficie = back buffer de la ventana.
 *  6. SHADERS. El backend recibe FUENTE (GLSL 4.50 generado en vivo por la capa comun + FRAG_UBER de raster_uber.c +
 *     GEOM_FLIP) mas una CLAVE (hash del texto, hv/hf). El backend GL compila el texto. El backend D3D12 (agente B,
 *     paso 2) mira PRIMERO su cache por clave de bytecode DXIL ya traducido (GLSL -> SPIR-V -> HLSL/DXIL fuera de linea
 *     o al vuelo) y solo si falta traduce. Convenciones que B debe respetar en el HLSL:
 *       - VS: texto = un .vert de extraido\shaders\glsl\ (generado por tools\shader_glsl.py; `#version 330 core`, entradas
 *         `layout(location = k) in vec4 vK` = registro de entrada v[K] de la PICA, K = 0..15, uniforms pica_c[96] /
 *         pica_i[4] / pica_b[16] como `bool`) envuelto por raster_gl.c:envolver_vert (#version 450, main -> pica_vmain, y
 *         VERT_ENVOLTORIO de raster_uber.c que agrega omap[24], clip_on, clip_coef y las salidas). Salidas por el bloque
 *         V {color, tc01, tc2w, quat, view} + gl_ClipDistance[0] (solo se lee si RbEstado.clip_dist).
 *         gl_Position = (x, y, -z, w): la z de clip queda en [0, w] (glClipControl ZERO_TO_ONE = convencion D3D). 
 *         D3D12 (agente B, 8 oct): el HLSL del VS emite (x, -y, -z, w) -> la fila r del RT D3D12 = la fila r del GL
 *         (la 0 = la de ABAJO de la PICA): lecturas de vuelta, tijera y z NO cambian; viewport normal (sin altura
 *         negativa) y FrontCounterClockwise = FALSE. RbEstado.cull = 1 descarta las caras "de frente" (antihorarias
 *         con y hacia arriba en la PICA), 2 las de reverso. Ver agentes_dx12\B.md, "Coordenadas".
 *         CLAVE: la capa comun identifica cada programa por (hv, hf, gs) = hash FNV del TEXTO final del VS, del FS y si lleva GS
 *         (prog_cargar_cache / prog_guardar_cache la reciben); un backend D3D12 puede usar la misma terna como nombre de su
 *         cache de bytecode/PSO. Para el VS el texto sale de (fnv512 del codigo PICA + entrada) -> programas.tsv.
 *       - GS (solo si hay luz): GEOM_FLIP, triangulos -> triangulos, voltea el cuaternion por cara.
 *       - FS: texto = `#version 450 core` + definiciones de especializacion (tev[6] y luces como `const`; claves en
 *         clave_frag) + FRAG_UBER de raster_uber.c. Salida unica `salida` (float4, RT0). Texturas: tex0..tex2 (unidades
 *         0-2), luz_luts (unidad 3, RG32F), cada una con su muestreador. Si el fragment shader es especializado, los
 *         campos tev/luz_* de los bloques son redundantes (el texto los fija como constantes) pero se siguen mandando.
 *         Constantes: ver RbCb*; el nombre GLSL de cada campo esta en el comentario del campo.
 *     La capa comun construye UN fragment shader por clave de TEV (especializado por constantes; ~150 programas en una
 *     partida normal) o el uber por uniforms (SM3DL_RASTER_UBER=1); no hay nada que cambiar para D3D12 ahi.
 *  7. TOPOLOGIA: 0 lista de triangulos, 1 tira, 2 ABANICO. D3D12 no tiene abanico: el backend lo convierte a lista de
 *     indices (la capa comun ya manda indices cuando los hay; con arrays el backend genera los indices).
 *  8. DEFERRED vs INMEDIATO: el backend GL ejecuta en el momento de la llamada. El D3D12 podra grabar en una command
 *     list y enviarla al esperar una fence, al presentar o en un futuro vaciar() (flush); por eso las lecturas son lectura_emitir/esperar y
 *     no hay ninguna funcion que devuelva datos de GPU sin pasar por una RbLectura o rt_leer.
 *  9. Todo texto de error se loguea por el backend con logr (prefijo [raster]). Las funciones que pueden fallar
 *     devuelven NULL/0; la capa comun decide si reintenta o se salta el dibujo (igual que antes).
 */
#ifndef RASTER_BACKEND_H
#define RASTER_BACKEND_H

#include <stddef.h>
#include <stdint.h>

/* ---------------------------------------------------------------- objetos opacos */
typedef struct RbTex RbTex;           /* textura 2D muestreable (juego, LUTs, capas de la interfaz) */
typedef struct RbRT RbRT;             /* superficie RGBA8 que se puede dibujar/copiar/leer (+ D24S8 si con_ds) */
typedef struct RbEtapa RbEtapa;       /* shader compilado de una etapa (VS, FS o GS) */
typedef struct RbProg RbProg;         /* VS + FS (+ GS) enlazados; en D3D12: el juego de bytecodes + root signature */
typedef struct RbLectura RbLectura;   /* buffer de lectura de vuelta + fence */

/* ---------------------------------------------------------------- enumeraciones */
enum { RB_FMT_RGBA8, RB_FMT_BGRA8, RB_FMT_RG32F };                      /* de texturas y de lecturas */
enum { RB_TEX_NEAREST = 1, RB_TEX_LINEAR_CLAMP = 2 };                   /* banderas de tex_crear */
enum { RB_RT_NEAREST = 1 };                                             /* banderas de rt_crear (filtro de la textura de color) */
enum { RB_LIMPIAR_COLOR = 1, RB_LIMPIAR_DS = 2 };
enum { RB_ETAPA_VS, RB_ETAPA_FS, RB_ETAPA_GS };
enum { RB_BLOQUE_V, RB_BLOQUE_F, RB_BLOQUE_NIEBLA, RB_BLOQUE_LUZ };     /* b0..b3 */
enum { RB_TOPO_LISTA, RB_TOPO_TIRA, RB_TOPO_ABANICO };
/* categorias de los cronometros de GPU (SM3DL_A_CRONO) */
enum { RB_GQ_DIB, RB_GQ_LIGAR, RB_GQ_COPIAR, RB_GQ_GIRO, RB_GQ_SUBIR, RB_GQ_N };
/* funciones de comparacion = codificacion PICA (profundidad y stencil) */
enum { RB_CMP_NEVER, RB_CMP_ALWAYS, RB_CMP_EQUAL, RB_CMP_NOTEQUAL, RB_CMP_LESS, RB_CMP_LEQUAL, RB_CMP_GREATER,
       RB_CMP_GEQUAL };

/* ---------------------------------------------------------------- estado de pipeline (inmutable, tipo PSO) */
/* Todos los enteros usan la codificacion de los registros de la PICA (los mismos indices que PicaEstado), asi la capa
   comun no traduce nada y cada backend tiene su tabla:
     factor de blend 0..15 (ZERO ONE SRC_COLOR 1-SRC_COLOR DST_COLOR 1-DST_COLOR SRC_ALPHA 1-SRC_ALPHA DST_ALPHA
       1-DST_ALPHA CONST_COLOR 1-CONST_COLOR CONST_ALPHA 1-CONST_ALPHA SRC_ALPHA_SATURATE ONE)
     ecuacion 0..7 (ADD SUB REVSUB MIN MAX ADD ADD ADD)   logic_op 0..15 (CLEAR AND AND_REVERSE COPY SET COPY_INVERTED
       NOOP INVERT NAND OR NOR XOR EQUIV AND_INVERTED OR_REVERSE OR_INVERTED)
     stencil op 0..7 (KEEP ZERO REPLACE INCR DECR INVERT INCR_WRAP DECR_WRAP) */
typedef struct {
    uint8_t cull;            /* 0 ninguno, 1 descarta caras de frente, 2 descarta caras de reverso (ver nota 6) */
    uint8_t clip_dist;       /* 1: el VS escribe gl_ClipDistance[0] (plano de recorte de la PICA) */
    uint8_t depth_func;      /* RB_CMP_*; sin prueba de profundidad = RB_CMP_ALWAYS (la prueba NUNCA se apaga) */
    uint8_t depth_write;     /* ya combinado con depth_escritura */
    uint8_t stencil_on;      /* solo con D24S8 */
    uint8_t stencil_func, stencil_ref, stencil_imask, stencil_fail, stencil_zfail, stencil_zpass;
    uint8_t stencil_wmask;   /* ya combinado con depth_escritura (0 si no se escribe) */
    uint8_t color_mask;      /* bit0 R, bit1 G, bit2 B, bit3 A; ya combinado con color_escritura */
    uint8_t blend_on;        /* 1: blend; 0: logic op */
    uint8_t eq_rgb, eq_a, src_rgb, dst_rgb, src_a, dst_a;
    uint8_t logic_op;
    uint32_t blend_color;    /* RGBA8, r en los bits 0-7 */
} RbEstado;

/* ---------------------------------------------------------------- muestreador de una textura PICA */
typedef struct {
    uint8_t mag_lineal, min_lineal;
    uint8_t mip;             /* 0 sin mipmaps (1 nivel), 1 mip mas cercano, 2 mip lineal */
    uint8_t wrap_s, wrap_t;  /* PICA: 0 ClampToEdge 1 ClampToBorder 2 Repeat 3 Mirror 4 ClampToEdge2 5 ClampToBorder2 6-7 Repeat */
    uint8_t lod_min, lod_max;
    int16_t lod_bias;        /* 1.4.8 fijo: sesgo = lod_bias / 256 */
    uint32_t color_borde;    /* RGBA8, r en los bits 0-7 */
} RbMuestreador;

/* ---------------------------------------------------------------- bloques de constantes (layout de cbuffer) */
/* Arrays densos: HLSL los declara como int4/uint4/float4 de n/4 elementos. */
typedef struct {                 /* b0: etapa de vertices; ~1.8 KB */
    float   c[96][4];            /* pica_c: registros float del VS (96 x vec4) */
    int32_t i[4][4];             /* pica_i: enteros del VS (x, y y z con signo de 8 bits ya extendido) */
    int32_t b[16];               /* pica_b: bools del VS (0/1)  -> int4 b4[4] */
    int32_t omap[24];            /* omap: semantica -> registro*4+componente de o[]; -1 = sin mapear -> int4 omap4[6] */
    int32_t clip_on, _p0[3];     /* clip_on */
    float   clip_coef[4];        /* clip_coef */
} RbCbVertice;

typedef struct {                 /* b1: etapa de fragmentos */
    uint32_t tev[6][4];          /* tev: por etapa {fuentes, operandos, combinador, escala} crudos (r[base+0,1,2,4]) */
    uint32_t tev_const[8];       /* tev_const[6] usados: color constante de cada etapa -> uint4[2] */
    uint32_t tev_buf, tev_upd, _p0[2];   /* tev_buf (0x0FD), tev_upd (0x0E0) */
    int32_t  tex_modo[4];        /* tex_modo: xyz = unidades 0-2: 0 apagada, 1 muestrear, 2 direccion 0; w = tex2 usa coord1 */
    int32_t  tex0_proy;          /* tex0_proy */
    int32_t  alfa_func;          /* alfa_func (-1 = sin alpha test) */
    int32_t  alfa_ref;           /* alfa_ref */
    int32_t  wbuffer;            /* wbuffer */
    float    z_escala, z_offset; /* z_escala, z_offset */
    int32_t  tijera_modo, _p1;   /* tijera_modo: 0 apagada, 1 descarta lo de dentro, 3 descarta lo de fuera */
    int32_t  tijera[4];          /* tijera: x0, y0, x1+1, y1+1 en pixeles del RT (ya multiplicada por la escala interna) */
    int32_t  niebla, niebla_flip;/* niebla, niebla_flip */
    uint32_t niebla_color, _p2;  /* niebla_color */
} RbCbFragmento;

typedef struct {                 /* b2: LUT de niebla; solo se sube si RbCbFragmento.niebla */
    float lut[128][2];           /* niebla_lut: (valor, diferencia) -> float4[64] */
} RbCbNiebla;

typedef struct {                 /* una luz de la PICA (en orden de ranura 0x1D9) */
    float esp0[4], esp1[4], dif[4], amb[4];   /* luz[k].esp0 esp1 dif amb (rgb en xyz, w = 0) */
    float pos[4], spot[4];                    /* luz[k].pos spot */
    float da_escala, da_sesgo;                /* luz[k].da_escala da_sesgo */
    int32_t num, cfg;                         /* luz[k].num (luz fisica) cfg */
} RbLuz;
typedef struct {                 /* b3: luces; si luz_on == 0 el resto NO se lee */
    int32_t  luz_on, luz_n, luz_mues, _p0;    /* luz_on luz_n luz_mues */
    uint32_t luz_c0, luz_c1, luz_abs, luz_ent;/* luz_c0 luz_c1 luz_abs luz_ent */
    uint32_t luz_esc, _p1[3];                 /* luz_esc */
    float    luz_amb[4];                      /* luz_amb (rgb) */
    int32_t  luz_fila[24];                    /* luz_fila: fila de la textura de LUTs de cada tabla -> int4[6] */
    RbLuz    luz[8];                          /* solo las primeras luz_n se leen */
} RbCbLuz;

/* ---------------------------------------------------------------- vertices */
/* Camino NATIVO: los bloques de los 12 loaders de la PICA se suben TAL CUAL (un solo buffer 'datos') y la GPU convierte.
   layout[loc] (loc = registro de entrada v[loc] del VS, 0..15): 0 = valor constante cte[loc]; si no
       0x80000000 | (n_componentes << 24) | (tipo << 20) | (loader << 16) | offset_en_el_vertice
   con tipo 0 BYTE, 1 UBYTE, 2 SHORT, 3 FLOAT, SIN normalizar (el entero se convierte tal cual a float). Los componentes
   que faltan salen (0,0,0,1). bind_off/bind_stride: donde empieza el loader j dentro de 'datos' y su stride. */
typedef struct {
    uint32_t layout[16];
    float    cte[16][4];
    uint32_t bind_off[12], bind_stride[12];
    uint16_t bind_mask;          /* bit j: el loader j tiene datos */
    const uint8_t *datos;
    uint32_t bytes;
} RbVerticesCrudos;

/* ---------------------------------------------------------------- giro de la pantalla en alta */
typedef struct {                 /* texel(x,y) = o + A * pixel(X,Y) sobre la copia en alta; ver raster_gl.c "Giro" */
    int ws, hs;                  /* tamano de la imagen girada (destino) */
    int W, H;                    /* tamano de la copia en alta (origen) */
    int s;                       /* escala interna */
    int ox, oy, a00, a01, a10, a11;
} RbGiro;

/* ---------------------------------------------------------------- la tabla */
typedef struct RasterBackend {
    const char *nombre;

    /* --- ciclo de vida / contexto --- */
    int  (*iniciar)(void);                 /* crea dispositivo/contexto la primera vez; 1 si esta listo (no reintenta si fallo) */
    int  (*listo)(void);                   /* 1 si iniciar() tuvo exito */
    int  (*contexto_actual)(void);         /* deja el contexto de GPU actual en este hilo; 0 si no se puede */
    int  (*es_actual)(void);               /* 1 si ya es el actual (sin forzar nada) */
    int  (*hacer_actual_dc)(void *hdc);    /* el contexto sobre el DC de la ventana visible (pixel format incluido) */
    unsigned (*ultimo_error)(void);        /* codigo de error pendiente de la GPU (diagnostico), 0 = ninguno */

    /* --- shaders --- */
    RbEtapa *(*etapa_compilar)(int tipo, const char *src, const char *nombre);
    void     (*etapa_destruir)(RbEtapa *e);
    /* cache de programas enlazados en disco (hv/hf = hash del TEXTO del VS/FS, gs = 0/1) */
    RbProg  *(*prog_cargar_cache)(uint32_t hv, uint32_t hf, int gs, int *rechazado);
    RbProg  *(*prog_enlazar)(RbEtapa *vs, RbEtapa *fs, RbEtapa *gs /* o NULL */, const char *nombre);
    void     (*prog_guardar_cache)(RbProg *p, uint32_t hv, uint32_t hf, int gs);
    void     (*prog_destruir)(RbProg *p);
    void     (*prog_usar)(RbProg *p);
    void     (*constantes)(RbProg *p, int bloque, const void *datos);  /* tras prog_usar(p) */

    /* --- texturas --- */
    RbTex   *(*tex_crear)(int w, int h, int fmt, int banderas);
    void     (*tex_destruir)(RbTex *t);
    void     (*tex_subir)(RbTex *t, int x, int y, int w, int h, int fmt, int fila_px /* 0 = compacta */, const void *datos);
    /* textura del juego con mipmaps: 'existente' se reusa (o NULL = nueva); devuelve la textura. niveles puede ser 0
       (nada que subir: la textura queda sin contenido). rgba[k] = nivel k, RGBA8, (w>>k) x (h>>k). */
    RbTex   *(*tex_cargar_mips)(RbTex *existente, int w, int h, int niveles, const uint8_t *const *rgba);
    void     (*tex_enlazar)(int unidad, RbTex *t /* NULL: solo selecciona la unidad */, const RbMuestreador *m /* o NULL */);

    /* --- superficies --- */
    RbRT    *(*rt_crear)(int w, int h, int con_ds, int banderas);
    void     (*rt_destruir)(RbRT *rt);
    void     (*rt_subir)(RbRT *rt, int x, int y, int w, int h, const void *rgba);
    void     (*rt_limpiar)(RbRT *rt, int mascara, const float color[4], double z, int stencil);
    RbRT    *(*rt_reducir)(RbRT *rt, int w, int h);                 /* copia reducida (lineal) a w x h; devuelve la superficie a leer */
    int      (*rt_leer)(RbRT *rt, int w, int h, int fmt, void *dst);/* lectura SINCRONA de (0,0,w,h); fila 0 = ABAJO */
    int      (*rt_leer_ventana)(int w, int h, void *bgra);           /* idem del back buffer de la ventana */
    void     (*copiar)(RbRT *dst /* NULL = ventana */, RbRT *src, int sx0, int sy0, int sx1, int sy1,
                       int dx0, int dy0, int dx1, int dy1, int lineal);   /* dx1 < dx0 / dy1 < dy0 voltea */
    unsigned (*rt_id_nativo)(RbRT *rt);                              /* id de la textura de color en el API (solo para la API publica) */
    int      (*rt_volcar_bgra)(RbRT *rt, int w, int h, void *dst);   /* diagnostico: lee la textura de color en BGRA */

    /* --- lecturas de vuelta asincronas --- */
    RbLectura *(*lectura_crear)(void);
    void       (*lectura_destruir)(RbLectura *l);
    /* emite la copia de (0,0,w,h) de 'rt' al buffer de 'l' y senala la fence. persistente: buffer mapeado siempre
       (cero copia); *persistente_ok dice si se pudo (si no, el llamador deja de pedirlo). Devuelve 1, o 2 si el
       almacenamiento persistente se REHIZO (los punteros que dio lectura_mapa_persistente antes quedan invalidos). */
    int        (*lectura_emitir)(RbLectura *l, RbRT *rt, int w, int h, int fmt, int persistente, int *persistente_ok);
    int        (*lectura_lista)(RbLectura *l);                       /* 1 si la fence ya se cumplio (sin esperar) */
    int        (*lectura_esperar)(RbLectura *l, uint64_t ns);        /* 0 solo si se agoto 'ns' (0 = sondeo) */
    void       (*lectura_cerrar)(RbLectura *l);                      /* consume la fence */
    const uint8_t *(*lectura_mapa_persistente)(RbLectura *l);        /* puntero fijo si es persistente, si no NULL */
    const uint8_t *(*lectura_mapear)(RbLectura *l, size_t bytes);    /* lectura no persistente */
    void       (*lectura_desmapear)(RbLectura *l);

    /* --- pase de dibujo --- */
    void (*fijar_destino)(RbRT *rt, int vx, int vy, int vw, int vh);
    void (*fijar_estado)(const RbEstado *e);
    int  (*vertices_crudos)(const RbVerticesCrudos *v);              /* 0 = no se pudo: usar vertices_floats */
    void (*vertices_floats)(const float *v, uint32_t nv);            /* nv vertices x 16 registros x 4 floats */
    void (*dibujar)(int topologia, uint32_t n, const uint32_t *indices /* NULL = n vertices seguidos */);

    /* --- operaciones internas del presentador / pantalla en alta --- */
    int  (*girar)(RbRT *dst, RbRT *alta, const RbGiro *g);           /* triangulo de pantalla completa con la afin; 0 si falla */
    void (*ventana_empezar)(int w, int h);                           /* back buffer: viewport, estado limpio, negro */
    int  (*pres_capa)(RbTex *capa, int x0, int y0, int x1, int y1, int lineal, int vw, int vh);
    int  (*presentar)(void *hdc, int intervalo);                     /* SwapBuffers / Present */

    /* --- cronometros de GPU (SM3DL_A_CRONO) --- */
    void (*gpu_crono_ini)(int cat);
    void (*gpu_crono_fin)(void);
    void (*gpu_crono_leer)(double seg[RB_GQ_N], uint32_t n[RB_GQ_N], uint32_t *perdidas);
} RasterBackend;

const RasterBackend *rb_gl_obtener(void);

#endif
