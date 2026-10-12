/* RECURSOS D3D12 (pasos 4-6 del plan, 8 oct noche): utilidades que el backend d3d12 usara sin importar la forma
 * final de raster_backend.h (agente A).
 *   - Textura: 2D, opcionalmente render target o profundidad/stencil (D24S8), con su SRV en un descriptor fijo de
 *     CPU (se copia al anillo visible al dibujar) y estado actual seguido a mano (barreras minimas).
 *   - Subida de una region: datos de CPU -> anillo UPLOAD (pitch alineado a 256) -> CopyTextureRegion.
 *   - LECTURA DE VUELTA ASINCRONA (reemplaza los glReadPixels): copia a un buffer READBACK + valor de fence; se
 *     recoge despues (d3d_leer_listo / d3d_leer_esperar) sin vaciar la GPU entera.
 *   - Cache de PSO en disco (ID3D12PipelineLibrary, "sesion_juego\\pso_cache.bin"): un PSO por clave de estado;
 *     si el driver cambio, la libreria se descarta y se rearma sola (como la cache de programas GL). */
#ifndef D3D12_RECURSOS_H
#define D3D12_RECURSOS_H
#include "d3d12_base.h"

typedef struct {
    ID3D12Resource *res;
    DXGI_FORMAT fmt;
    int w, h, rt, ds;
    D3D12_RESOURCE_STATES estado;
    D3D12_CPU_DESCRIPTOR_HANDLE rtv, dsv, srv;   /* srv: en un monton de CPU (no visible) para copiar al anillo */
    int niveles;           /* niveles de mip del recurso (C2, 9 oct; d3d_tex_crear deja 1) */
} D3dTextura;

/* rt = render target (color), ds = profundidad/stencil (fmt se ignora: D24_UNORM_S8_UINT) */
int d3d_tex_crear(D3dTextura *t, DXGI_FORMAT fmt, int w, int h, int rt, int ds);
void d3d_tex_liberar(D3dTextura *t);   /* espera a que la GPU suelte el recurso (diferido por fence) */
void d3d_tex_estado(ID3D12GraphicsCommandList *l, D3dTextura *t, D3D12_RESOURCE_STATES e);
/* sube la region (x, y, w, h) desde 'datos' (filas de 'pitch' bytes, de arriba hacia abajo) */
int d3d_tex_subir(ID3D12GraphicsCommandList *l, D3dTextura *t, int x, int y, int w, int h, const void *datos, int pitch);

/* MIPS (agente C2, 9 oct): textura muestreable (sin RT/DS) con 'niveles' niveles de mip (1..16; se recorta al maximo
   que admite el tamano); el SRV abarca todos. Nivel k = max(1, w>>k) x max(1, h>>k). Queda en COPY_DEST. 1 = bien. */
int d3d_tex_crear_mips(D3dTextura *t, DXGI_FORMAT fmt, int w, int h, int niveles);
/* sube la region (x, y, w, h) del NIVEL 'nivel' (coordenadas de ese nivel). intercambiar_rb = 1 cambia los bytes 0 y 2
   de cada texel al copiar (RGBA8 <-> BGRA8, solo formatos de 4 bytes). Regiones grandes van en tiras (el anillo de
   subida admite hasta 1/4 de su tamano por reserva). Si el anillo tuvo que vaciar la lista para hacer lugar, la reabre
   (d3d_lista) antes de grabar: 'l' debe ser la lista continua (g_d3d.lista). Estado final: el de d3d_tex_subir. */
int d3d_tex_subir_nivel(ID3D12GraphicsCommandList *l, D3dTextura *t, int nivel, int x, int y, int w, int h,
                        const void *datos, int pitch, int intercambiar_rb);

typedef struct {
    ID3D12Resource *buf;
    uint64_t fence;        /* listo cuando la fence llega a este valor (lo pone d3d_leer_marcar) */
    int w, h;
    UINT pitch;            /* pitch del buffer (alineado a 256) */
    int bpp;
    int ds;                /* profundidad: plano 0 (z en 32 bits) + plano 1 (stencil R8) detras; se juntan en D24S8 */
    uint64_t off_stencil, cap;   /* cap: tamano del buffer de lectura */
    UINT pitch_stencil;
} D3dLectura;
/* encola la copia de (x, y, w, h) de t a la lectura (crea/reutiliza el buffer). Llamar d3d_leer_marcar() DESPUES de
   ejecutar la lista (d3d_terminar_cuadro o d3d_ejecutar) para saber cuando esta lista. */
int d3d_leer_encolar(ID3D12GraphicsCommandList *l, D3dTextura *t, int x, int y, int w, int h, D3dLectura *lec);
void d3d_leer_marcar(D3dLectura *lec, uint64_t valor_fence);
int d3d_leer_listo(const D3dLectura *lec);
/* espera y copia a 'dst' (filas de dst_pitch, de arriba hacia abajo). 1 = bien */
int d3d_leer_esperar(D3dLectura *lec, void *dst, int dst_pitch);
void d3d_leer_liberar(D3dLectura *lec);

/* ejecutar la lista abierta FUERA del ritmo de presentacion (cargas, pruebas): cierra, ejecuta, senala y la reabre.
   Devuelve el valor de fence de lo ejecutado. */
uint64_t d3d_ejecutar(ID3D12GraphicsCommandList *l);
/* d3d_esperar_valor: en d3d12_base.h */

/* PSO con cache en disco. 'clave' identifica el estado completo (hash del backend). */
int d3d_pso_cache_abrir(const char *ruta);
void d3d_pso_cache_guardar(void);
ID3D12PipelineState *d3d_pso_obtener(uint64_t clave, const D3D12_GRAPHICS_PIPELINE_STATE_DESC *desc);
void d3d_pso_estadisticas(unsigned *de_disco, unsigned *creados, double *ms_creando);

#endif
