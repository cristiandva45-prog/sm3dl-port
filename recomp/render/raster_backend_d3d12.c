/* BACKEND DIRECT3D 12 DEL RASTERIZADOR (8 oct noche; plan en agentes_dx12\BRIEF_COMUN.md, interfaz en raster_backend.h).
 * Se incluye al FINAL de raster_gl.c (como raster_backend_gl.c): ve logr, AVISO_UNA_VEZ, etc. de la capa comun. Para no
 * chocar con los static de la capa comun ni del backend GL (mismo archivo de compilacion), TODO lo de aqui y de las
 * partes lleva el prefijo dx_ / DX_.
 * Se apoya en modulos compilados aparte (compilar.py): d3d12_base.c (dispositivo, swap chain, LISTA CONTINUA con pool
 * de allocators y vaciado sin espera, anillos de subida/descriptores/muestreadores), d3d12_recursos.c (texturas, RT,
 * D24S8 en dos planos, lecturas con fence, cache de PSO en disco) y d3d12_presentador.c (base escalada + capas).
 * Shaders: DXIL precompilado por la cadena del agente B (GLSL -> SPIR-V -> HLSL -> DXIL), buscado por hash del TEXTO.
 *
 * PARTES (cada una de UN autor; ver agentes_dx12\BRIEF_BACKEND.md):
 *   raster_d3d12_recursos.inc  (agente C): iniciar/contexto, texturas + mips, muestreadores, RT, limpiar, reducir,
 *                                          leer, copiar, lecturas asincronas, girar, ventana, capas, presentar, crono.
 *   raster_d3d12_dibujo.inc    (agente D): shaders/programas (cache DXIL), constantes, destino, estado -> PSO,
 *                                          vertices (floats y crudos), dibujar (abanico -> lista).
 * Este archivo: las estructuras COMPARTIDAS, el estado comun y la tabla. Cambiarlas = coordinar (sesion principal). */
#include "d3d12_presentador.h"   /* trae d3d12_recursos.h y d3d12_base.h */

/* ---------------------------------------------------------------- objetos de la interfaz
   El backend GL define struct RbTex & co. en este MISMO archivo de compilacion: aqui son tipos propios (DxTex...) y los
   punteros de la interfaz se convierten en la frontera con DX_TEX(p) etc. (la capa comun nunca mira adentro). */
typedef struct DxTex {
    D3dTextura t;          /* t.fmt: formato DXGI; mips en t.res (MipLevels = niveles) */
    int fmt;               /* RB_FMT_* */
    int niveles, banderas;
} DxTex;
typedef struct DxRT {
    D3dTextura color;      /* RGBA8 (render target + SRV) */
    D3dTextura ds;         /* D24S8 si con_ds (ds.res == NULL si no) */
    int w, h, con_ds, banderas;
} DxRT;
typedef struct DxEtapa {
    int tipo;              /* RB_ETAPA_* */
    void *dxil;            /* bytecode (contenedor DXBC firmado) */
    size_t n;
    uint32_t hash;         /* FNV-1a del texto (= nombre en la cache de B) */
    char nombre[64];
} DxEtapa;
typedef struct DxProg {
    DxEtapa *vs, *fs, *gs; /* gs NULL si no hay */
    uint32_t hv, hf;
    uint64_t clave;        /* parte del programa en la clave del PSO */
} DxProg;
typedef struct DxLectura {
    D3dLectura l;
    int fmt;
    int emitida;
    uint8_t *copia;        /* lectura_mapear: copia en CPU (el D3dLectura se lee de una vez) */
    size_t cap;
} DxLectura;

#define DX_TEX(p) ((DxTex *)(void *)(p))
#define DX_RT(p) ((DxRT *)(void *)(p))
#define DX_ETAPA(p) ((DxEtapa *)(void *)(p))
#define DX_PROG(p) ((DxProg *)(void *)(p))
#define DX_LEC(p) ((DxLectura *)(void *)(p))

/* ---------------------------------------------------------------- estado comun del backend */
#define DX_UNIDADES 4      /* t0..t2 texturas PICA, t3 LUTs de luz */
static struct {
    int estado;                            /* 0 sin iniciar, 1 listo, -1 fallo (no se reintenta) */
    ID3D12RootSignature *rs;               /* firma raiz del raster: b0..b3 CBV raiz, tabla t0..t3, tabla s0..s3 */
    /* lo fijado por la capa comun para el proximo dibujo */
    DxRT *destino;                         /* NULL = buffer de atras de la ventana */
    D3D12_VIEWPORT vp;
    RbEstado est;
    int est_valido;
    DxProg *prog;
    uint64_t cb_va[4];                     /* direccion GPU de cada bloque de constantes (anillo de subida) */
    DxTex *tex[DX_UNIDADES];
    RbMuestreador mues[DX_UNIDADES];
    int mues_valido[DX_UNIDADES];
    D3D12_VERTEX_BUFFER_VIEW vb;           /* vertices del proximo dibujo (anillo de subida) */
    int vb_crudos;                         /* 1: layout crudo (input layout por dibujo); 0: 16 x float4 */
    uint32_t vb_layout_hash;               /* para la clave del PSO con layout crudo */
    D3D12_INPUT_ELEMENT_DESC vb_elems[16];
    int vb_nelems;
    int sab;                               /* SM3DL_BACKEND_SABOTAJE */
    /* ventana */
    HWND hwnd;
    int ventana_w, ventana_h, en_ventana;
} dx;

/* ---------------------------------------------------------------- las partes */
#include "raster_d3d12_recursos.inc"
#include "raster_d3d12_dibujo.inc"

/* ---------------------------------------------------------------- la tabla */
static const RasterBackend RB_D3D12 = {
    "d3d12",
    dx_iniciar, dx_listo, dx_contexto_actual, dx_es_actual, dx_hacer_actual_dc, dx_ultimo_error,
    dx_etapa_compilar, dx_etapa_destruir, dx_prog_cargar_cache, dx_prog_enlazar, dx_prog_guardar_cache, dx_prog_destruir,
    dx_prog_usar, dx_constantes,
    dx_tex_crear, dx_tex_destruir, dx_tex_subir, dx_tex_cargar_mips, dx_tex_enlazar,
    dx_rt_crear, dx_rt_destruir, dx_rt_subir, dx_rt_limpiar, dx_rt_reducir, dx_rt_leer, dx_rt_leer_ventana, dx_copiar,
    dx_rt_id_nativo, dx_rt_volcar_bgra,
    dx_lectura_crear, dx_lectura_destruir, dx_lectura_emitir, dx_lectura_lista, dx_lectura_esperar, dx_lectura_cerrar,
    dx_lectura_mapa_persistente, dx_lectura_mapear, dx_lectura_desmapear,
    dx_fijar_destino, dx_fijar_estado, dx_vertices_crudos, dx_vertices_floats, dx_dibujar,
    dx_girar, dx_ventana_empezar, dx_pres_capa, dx_presentar,
    dx_gpu_crono_ini, dx_gpu_crono_fin, dx_gpu_crono_leer,
};

const RasterBackend *rb_d3d12_obtener(void) { return &RB_D3D12; }
