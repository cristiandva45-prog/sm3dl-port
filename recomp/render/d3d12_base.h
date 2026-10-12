/* BASE DE DIRECT3D 12 (paso 3 del plan D3D12, 8 oct noche; plan en agentes_dx12\BRIEF_COMUN.md).
 * Lo minimo comun que usara el backend d3d12 de raster_backend.h (agente A) y la presentacion:
 *   - dispositivo en la GPU de alto rendimiento (IDXGIFactory6::EnumAdapterByGpuPreference), capa de depuracion con
 *     SM3DL_D3D_DEBUG=1;
 *   - cola directa + N_CUADROS listas/allocators en vuelo, fence por cuadro;
 *   - swap chain FLIP_DISCARD de 3 buffers con FRAME_LATENCY_WAITABLE_OBJECT (latencia maxima 1) y ALLOW_TEARING si
 *     el sistema lo soporta (vsync apagado sin tearing bloqueado; con vsync, intervalo 1). Ventana sin bordes a
 *     pantalla completa = "independent flip" (no SetFullscreenState: ese modo pierde el objeto de espera);
 *   - anillo de SUBIDA (vertices, constantes: memoria UPLOAD mapeada, se recicla por cuadro con la fence);
 *   - anillo de descriptores CBV/SRV/UAV visible al shader + monton de RTV/DSV en CPU;
 *   - estadisticas de presentacion (DXGI_FRAME_STATISTICS: refrescos perdidos), para medir el ritmo.
 * Todo en C con COBJMACROS; WIDL_C_INLINE_WRAPPERS arregla las funciones que devuelven estructuras
 * (GetCPUDescriptorHandleForHeapStart & co.: en C el ABI es por puntero oculto). */
#ifndef D3D12_BASE_H
#define D3D12_BASE_H
#define COBJMACROS
#define WIDL_C_INLINE_WRAPPERS
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <stdint.h>

#define D3D_N_CUADROS 3   /* buffers de la swap chain */
#define D3D_N_ALLOC 16    /* allocators en el pool: cada vaciado usa uno y lo libera su fence */
#define D3D_N_MARCAS 64   /* marcas de los anillos (inicio de cada tramo vaciado + su fence) */

/* LISTA CONTINUA (8 oct noche, para el backend del raster): el raster no dibuja "por cuadro": graba en UNA lista que
   se abre sola (d3d_lista) y se manda a la GPU cuando hace falta (d3d_vaciar: sin esperar; antes de una lectura, al
   presentar). Cada vaciado deja una MARCA {inicio de su tramo en los anillos, fence}: los anillos se reciclan hasta
   el inicio de la marca mas vieja que la GPU no termino. */
typedef struct { uint64_t subida, srv, smp, fence; } D3dMarca;

typedef struct {
    ID3D12Device *dev;
    IDXGIFactory6 *fab;
    IDXGIAdapter1 *adaptador;
    ID3D12CommandQueue *cola;
    ID3D12CommandAllocator *pool[D3D_N_ALLOC];
    uint64_t pool_fence[D3D_N_ALLOC];               /* libre cuando la fence llega a esto */
    int alloc_actual, lista_abierta;
    ID3D12GraphicsCommandList *lista;
    ID3D12Fence *fence;
    HANDLE fence_ev;
    uint64_t fence_val;
    D3dMarca marca[D3D_N_MARCAS];
    int marca_ini, marca_n;
    uint64_t seg_subida, seg_srv, seg_smp;          /* inicio del tramo actual (desde el ultimo vaciado) */
    IDXGISwapChain3 *sc;
    HANDLE sc_espera;                               /* objeto de latencia (NULL si no hay swap chain) */
    ID3D12Resource *atras[D3D_N_CUADROS];
    ID3D12DescriptorHeap *rtv_heap;                 /* RTV de los buffers de la swap chain (+ libres para el raster) */
    UINT rtv_paso, rtv_libre, rtv_max;
    ID3D12DescriptorHeap *dsv_heap;
    UINT dsv_paso, dsv_libre, dsv_max;
    ID3D12DescriptorHeap *srv_heap;                 /* visible al shader, usado como anillo */
    UINT srv_paso, srv_max;
    uint64_t srv_pos;
    ID3D12DescriptorHeap *smp_heap;                 /* muestreadores visibles (tope de D3D12: 2.048), anillo */
    UINT smp_paso, smp_max;
    uint64_t smp_pos;
    ID3D12Resource *subida;                         /* anillo UPLOAD */
    uint8_t *subida_cpu;
    uint64_t subida_gpu, subida_tam, subida_pos;
    HWND hwnd;
    int w, h, cuadro, tearing, abierto, en_cuadro;  /* cuadro = indice del buffer de atras en uso */
    char nombre_gpu[128];
    /* ritmo */
    UINT ult_present_count, ult_refresh_count;
    uint32_t presentados, perdidos;
} D3dBase;

extern D3dBase g_d3d;

/* hwnd NULL = sin swap chain (solo dispositivo: render fuera de pantalla, pruebas). 1 = bien. */
int d3d_iniciar(HWND hwnd, int w, int h);
void d3d_cerrar(void);
int d3d_redimensionar(int w, int h);
/* la lista abierta (la abre con un allocator libre del pool si hacia falta) */
ID3D12GraphicsCommandList *d3d_lista(void);
/* manda lo grabado a la GPU SIN esperar; devuelve el valor de fence que marca su fin (0 si no habia nada) */
uint64_t d3d_vaciar(void);
void d3d_esperar_valor(uint64_t v);
int d3d_valor_listo(uint64_t v);
/* buffer de atras: espera el objeto de latencia (si se pide) y lo pasa a RENDER_TARGET en la lista */
int d3d_atras_empezar(int esperar_latencia);
/* lo pasa a PRESENT, vacia y presenta (vsync 1 = intervalo 1; 0 = inmediato, con tearing si se puede) */
int d3d_atras_presentar(int vsync);
/* compatibilidad (pruebas): con swap chain = atras_empezar + lista; sin ella = lista */
ID3D12GraphicsCommandList *d3d_empezar_cuadro(int esperar_latencia);
D3D12_CPU_DESCRIPTOR_HANDLE d3d_rtv_atras(void);
int d3d_terminar_cuadro(int vsync);
void d3d_esperar_gpu(void);
/* n muestreadores consecutivos del anillo visible */
int d3d_smp_reservar(UINT n, D3D12_CPU_DESCRIPTOR_HANDLE *cpu, D3D12_GPU_DESCRIPTOR_HANDLE *gpu);
/* anillo de subida: 'tam' bytes alineados a 'alin' (constantes: 256). Devuelve puntero CPU y direccion GPU. */
void *d3d_subir(uint64_t tam, uint64_t alin, uint64_t *gpu_va);
/* n descriptores consecutivos del anillo visible: handle CPU (para escribir) y GPU (para la tabla) */
int d3d_srv_reservar(UINT n, D3D12_CPU_DESCRIPTOR_HANDLE *cpu, D3D12_GPU_DESCRIPTOR_HANDLE *gpu);
D3D12_CPU_DESCRIPTOR_HANDLE d3d_rtv_nuevo(void);   /* descriptores fijos para render targets / profundidad */
D3D12_CPU_DESCRIPTOR_HANDLE d3d_dsv_nuevo(void);
void d3d_barrera(ID3D12GraphicsCommandList *l, ID3D12Resource *r, D3D12_RESOURCE_STATES antes, D3D12_RESOURCE_STATES despues);

#endif
