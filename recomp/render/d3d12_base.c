/* BASE DE DIRECT3D 12 — ver d3d12_base.h. Se enlaza con -ld3d12 -ldxgi -ldxguid. */
#include "d3d12_base.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

D3dBase g_d3d;

#define FALLA(hr, que) do { if (FAILED(hr)) { fprintf(stderr, "[d3d12] %s fallo (0x%08lX)\n", que, (unsigned long)(hr)); return 0; } } while (0)

static int crear_dispositivo(void)
{
    HRESULT hr;
    if (getenv("SM3DL_D3D_DEBUG")) {
        ID3D12Debug *dbg = NULL;
        if (SUCCEEDED(D3D12GetDebugInterface(&IID_ID3D12Debug, (void **)&dbg))) {
            ID3D12Debug_EnableDebugLayer(dbg);
            ID3D12Debug_Release(dbg);
            fprintf(stderr, "[d3d12] capa de depuracion activa\n");
        }
    }
    hr = CreateDXGIFactory2(getenv("SM3DL_D3D_DEBUG") ? DXGI_CREATE_FACTORY_DEBUG : 0, &IID_IDXGIFactory6, (void **)&g_d3d.fab);
    FALLA(hr, "CreateDXGIFactory2 (IDXGIFactory6)");
    /* la GPU de alto rendimiento primero (la NVIDIA en un portatil con MUX/Optimus); la integrada solo si se pide */
    DXGI_GPU_PREFERENCE pref = getenv("SM3DL_GPU_INTEGRADA") ? DXGI_GPU_PREFERENCE_MINIMUM_POWER : DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE;
    for (UINT i = 0;; i++) {
        IDXGIAdapter1 *a = NULL;
        if (FAILED(IDXGIFactory6_EnumAdapterByGpuPreference(g_d3d.fab, i, pref, &IID_IDXGIAdapter1, (void **)&a))) break;
        DXGI_ADAPTER_DESC1 d;
        IDXGIAdapter1_GetDesc1(a, &d);
        if (!(d.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) &&
            SUCCEEDED(D3D12CreateDevice((IUnknown *)a, D3D_FEATURE_LEVEL_11_0, &IID_ID3D12Device, (void **)&g_d3d.dev))) {
            g_d3d.adaptador = a;
            WideCharToMultiByte(CP_UTF8, 0, d.Description, -1, g_d3d.nombre_gpu, sizeof g_d3d.nombre_gpu, NULL, NULL);
            fprintf(stderr, "[d3d12] dispositivo: %s (%llu MB de video)\n", g_d3d.nombre_gpu,
                    (unsigned long long)(d.DedicatedVideoMemory >> 20));
            return 1;
        }
        IDXGIAdapter1_Release(a);
    }
    fprintf(stderr, "[d3d12] ninguna GPU acepto D3D12 (nivel 11_0)\n");
    return 0;
}

static ID3D12DescriptorHeap *heap(D3D12_DESCRIPTOR_HEAP_TYPE tipo, UINT n, int visible, UINT *paso)
{
    D3D12_DESCRIPTOR_HEAP_DESC d = { tipo, n, visible ? D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE : D3D12_DESCRIPTOR_HEAP_FLAG_NONE, 0 };
    ID3D12DescriptorHeap *h = NULL;
    if (FAILED(ID3D12Device_CreateDescriptorHeap(g_d3d.dev, &d, &IID_ID3D12DescriptorHeap, (void **)&h))) return NULL;
    *paso = ID3D12Device_GetDescriptorHandleIncrementSize(g_d3d.dev, tipo);
    return h;
}

static int buffers_atras(void)
{
    for (int k = 0; k < D3D_N_CUADROS; k++) {
        HRESULT hr = IDXGISwapChain3_GetBuffer(g_d3d.sc, k, &IID_ID3D12Resource, (void **)&g_d3d.atras[k]);
        FALLA(hr, "GetBuffer");
        D3D12_CPU_DESCRIPTOR_HANDLE h = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(g_d3d.rtv_heap);
        h.ptr += (SIZE_T)k * g_d3d.rtv_paso;   /* los primeros D3D_N_CUADROS RTV son de la swap chain */
        ID3D12Device_CreateRenderTargetView(g_d3d.dev, g_d3d.atras[k], NULL, h);
    }
    return 1;
}

static int crear_swap_chain(HWND hwnd, int w, int h)
{
    BOOL tear = FALSE;
    IDXGIFactory5 *f5 = NULL;
    if (SUCCEEDED(IDXGIFactory6_QueryInterface(g_d3d.fab, &IID_IDXGIFactory5, (void **)&f5))) {
        if (FAILED(IDXGIFactory5_CheckFeatureSupport(f5, DXGI_FEATURE_PRESENT_ALLOW_TEARING, &tear, sizeof tear))) tear = FALSE;
        IDXGIFactory5_Release(f5);
    }
    g_d3d.tearing = tear ? 1 : 0;
    DXGI_SWAP_CHAIN_DESC1 d;
    memset(&d, 0, sizeof d);
    d.Width = (UINT)w; d.Height = (UINT)h;
    d.Format = DXGI_FORMAT_B8G8R8A8_UNORM;   /* la UI y el HUD se componen en BGRA (como el camino GL) */
    d.SampleDesc.Count = 1;
    d.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    d.BufferCount = D3D_N_CUADROS;
    d.Scaling = DXGI_SCALING_NONE;
    d.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
    d.AlphaMode = DXGI_ALPHA_MODE_IGNORE;
    d.Flags = DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT | (g_d3d.tearing ? DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING : 0);
    IDXGISwapChain1 *sc1 = NULL;
    HRESULT hr = IDXGIFactory6_CreateSwapChainForHwnd(g_d3d.fab, (IUnknown *)g_d3d.cola, hwnd, &d, NULL, NULL, &sc1);
    FALLA(hr, "CreateSwapChainForHwnd");
    IDXGIFactory6_MakeWindowAssociation(g_d3d.fab, hwnd, DXGI_MWA_NO_ALT_ENTER);   /* pantalla completa = ventana sin bordes */
    hr = IDXGISwapChain1_QueryInterface(sc1, &IID_IDXGISwapChain3, (void **)&g_d3d.sc);
    IDXGISwapChain1_Release(sc1);
    FALLA(hr, "IDXGISwapChain3");
    IDXGISwapChain3_SetMaximumFrameLatency(g_d3d.sc, 1);
    g_d3d.sc_espera = IDXGISwapChain3_GetFrameLatencyWaitableObject(g_d3d.sc);
    g_d3d.w = w; g_d3d.h = h;
    if (!buffers_atras()) return 0;
    fprintf(stderr, "[d3d12] swap chain %dx%d flip-discard x%d, latencia 1, tearing %s\n", w, h, D3D_N_CUADROS,
            g_d3d.tearing ? "permitido" : "no soportado");
    return 1;
}

int d3d_iniciar(HWND hwnd, int w, int h)
{
    if (g_d3d.abierto) return 1;
    memset(&g_d3d, 0, sizeof g_d3d);
    if (!crear_dispositivo()) return 0;
    HRESULT hr;
    D3D12_COMMAND_QUEUE_DESC cd = { D3D12_COMMAND_LIST_TYPE_DIRECT, 0, D3D12_COMMAND_QUEUE_FLAG_NONE, 0 };
    hr = ID3D12Device_CreateCommandQueue(g_d3d.dev, &cd, &IID_ID3D12CommandQueue, (void **)&g_d3d.cola);
    FALLA(hr, "CreateCommandQueue");
    for (int k = 0; k < D3D_N_ALLOC; k++) {
        hr = ID3D12Device_CreateCommandAllocator(g_d3d.dev, D3D12_COMMAND_LIST_TYPE_DIRECT, &IID_ID3D12CommandAllocator, (void **)&g_d3d.pool[k]);
        FALLA(hr, "CreateCommandAllocator");
    }
    hr = ID3D12Device_CreateCommandList(g_d3d.dev, 0, D3D12_COMMAND_LIST_TYPE_DIRECT, g_d3d.pool[0], NULL,
                                        &IID_ID3D12GraphicsCommandList, (void **)&g_d3d.lista);
    FALLA(hr, "CreateCommandList");
    ID3D12GraphicsCommandList_Close(g_d3d.lista);
    hr = ID3D12Device_CreateFence(g_d3d.dev, 0, D3D12_FENCE_FLAG_NONE, &IID_ID3D12Fence, (void **)&g_d3d.fence);
    FALLA(hr, "CreateFence");
    g_d3d.fence_ev = CreateEventA(NULL, FALSE, FALSE, NULL);
    /* descriptores: RTV/DSV fijos (swap chain + render targets del raster: a 4x el juego usa decenas), y el anillo
       visible al shader (por cuadro: ~1.400 dibujos x 3 texturas + LUTs, con holgura) */
    g_d3d.rtv_max = 1024; g_d3d.dsv_max = 256; g_d3d.srv_max = 65536;
    g_d3d.rtv_heap = heap(D3D12_DESCRIPTOR_HEAP_TYPE_RTV, g_d3d.rtv_max, 0, &g_d3d.rtv_paso);
    g_d3d.dsv_heap = heap(D3D12_DESCRIPTOR_HEAP_TYPE_DSV, g_d3d.dsv_max, 0, &g_d3d.dsv_paso);
    g_d3d.srv_heap = heap(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV, g_d3d.srv_max, 1, &g_d3d.srv_paso);
    g_d3d.smp_max = 2048;   /* tope de D3D12 para un monton de muestreadores visible */
    g_d3d.smp_heap = heap(D3D12_DESCRIPTOR_HEAP_TYPE_SAMPLER, g_d3d.smp_max, 1, &g_d3d.smp_paso);
    if (!g_d3d.rtv_heap || !g_d3d.dsv_heap || !g_d3d.srv_heap || !g_d3d.smp_heap) { fprintf(stderr, "[d3d12] CreateDescriptorHeap fallo\n"); return 0; }
    g_d3d.rtv_libre = D3D_N_CUADROS;
    /* anillo de subida: 64 MB (vertices de un cuadro a 4x ~ unos MB + constantes de ~1.400 dibujos x 256 B) */
    g_d3d.subida_tam = 64ull << 20;
    D3D12_HEAP_PROPERTIES hp = { D3D12_HEAP_TYPE_UPLOAD, D3D12_CPU_PAGE_PROPERTY_UNKNOWN, D3D12_MEMORY_POOL_UNKNOWN, 1, 1 };
    D3D12_RESOURCE_DESC rd;
    memset(&rd, 0, sizeof rd);
    rd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    rd.Width = g_d3d.subida_tam; rd.Height = 1; rd.DepthOrArraySize = 1; rd.MipLevels = 1;
    rd.Format = DXGI_FORMAT_UNKNOWN; rd.SampleDesc.Count = 1; rd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    hr = ID3D12Device_CreateCommittedResource(g_d3d.dev, &hp, D3D12_HEAP_FLAG_NONE, &rd, D3D12_RESOURCE_STATE_GENERIC_READ,
                                              NULL, &IID_ID3D12Resource, (void **)&g_d3d.subida);
    FALLA(hr, "anillo de subida");
    D3D12_RANGE nada = { 0, 0 };
    hr = ID3D12Resource_Map(g_d3d.subida, 0, &nada, (void **)&g_d3d.subida_cpu);
    FALLA(hr, "Map del anillo");
    g_d3d.subida_gpu = ID3D12Resource_GetGPUVirtualAddress(g_d3d.subida);
    g_d3d.hwnd = hwnd;
    if (hwnd && !crear_swap_chain(hwnd, w, h)) return 0;
    g_d3d.abierto = 1;
    return 1;
}

int d3d_redimensionar(int w, int h)
{
    if (!g_d3d.sc || (w == g_d3d.w && h == g_d3d.h) || w <= 0 || h <= 0) return 1;
    d3d_esperar_gpu();
    for (int k = 0; k < D3D_N_CUADROS; k++) if (g_d3d.atras[k]) { ID3D12Resource_Release(g_d3d.atras[k]); g_d3d.atras[k] = NULL; }
    HRESULT hr = IDXGISwapChain3_ResizeBuffers(g_d3d.sc, D3D_N_CUADROS, (UINT)w, (UINT)h, DXGI_FORMAT_B8G8R8A8_UNORM,
                                               DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT | (g_d3d.tearing ? DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING : 0));
    FALLA(hr, "ResizeBuffers");
    g_d3d.w = w; g_d3d.h = h;
    return buffers_atras();
}

void d3d_barrera(ID3D12GraphicsCommandList *l, ID3D12Resource *r, D3D12_RESOURCE_STATES antes, D3D12_RESOURCE_STATES despues)
{
    if (antes == despues) return;
    D3D12_RESOURCE_BARRIER b;
    memset(&b, 0, sizeof b);
    b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    b.Transition.pResource = r;
    b.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    b.Transition.StateBefore = antes;
    b.Transition.StateAfter = despues;
    ID3D12GraphicsCommandList_ResourceBarrier(l, 1, &b);
}

/* ---- lista continua + pool de allocators ---- */
int d3d_valor_listo(uint64_t v) { return !v || ID3D12Fence_GetCompletedValue(g_d3d.fence) >= v; }

void d3d_esperar_valor(uint64_t v)
{
    if (v && ID3D12Fence_GetCompletedValue(g_d3d.fence) < v) {
        ID3D12Fence_SetEventOnCompletion(g_d3d.fence, v, g_d3d.fence_ev);
        WaitForSingleObject(g_d3d.fence_ev, INFINITE);
    }
}

ID3D12GraphicsCommandList *d3d_lista(void)
{
    if (!g_d3d.lista) return NULL;
    if (g_d3d.lista_abierta) return g_d3d.lista;
    /* un allocator libre (su fence ya paso); si no hay, se espera al mas viejo */
    int k = -1;
    uint64_t hecho = ID3D12Fence_GetCompletedValue(g_d3d.fence), viejo = UINT64_MAX;
    for (int i = 0; i < D3D_N_ALLOC && k < 0; i++) if (g_d3d.pool_fence[i] <= hecho) k = i;
    if (k < 0) {
        for (int i = 0; i < D3D_N_ALLOC; i++) if (g_d3d.pool_fence[i] < viejo) { viejo = g_d3d.pool_fence[i]; k = i; }
        d3d_esperar_valor(viejo);
    }
    ID3D12CommandAllocator_Reset(g_d3d.pool[k]);
    ID3D12GraphicsCommandList_Reset(g_d3d.lista, g_d3d.pool[k], NULL);
    ID3D12DescriptorHeap *h[2] = { g_d3d.srv_heap, g_d3d.smp_heap };
    ID3D12GraphicsCommandList_SetDescriptorHeaps(g_d3d.lista, 2, h);
    g_d3d.alloc_actual = k;
    g_d3d.lista_abierta = 1;
    return g_d3d.lista;
}

static void marcas_recoger(void)
{
    uint64_t hecho = ID3D12Fence_GetCompletedValue(g_d3d.fence);
    while (g_d3d.marca_n && g_d3d.marca[g_d3d.marca_ini].fence <= hecho) {
        g_d3d.marca_ini = (g_d3d.marca_ini + 1) % D3D_N_MARCAS;
        g_d3d.marca_n--;
    }
}

uint64_t d3d_vaciar(void)
{
    if (!g_d3d.lista_abierta) return g_d3d.fence_val;
    ID3D12GraphicsCommandList_Close(g_d3d.lista);
    ID3D12CommandList *l = (ID3D12CommandList *)g_d3d.lista;
    ID3D12CommandQueue_ExecuteCommandLists(g_d3d.cola, 1, &l);
    uint64_t v = ++g_d3d.fence_val;
    ID3D12CommandQueue_Signal(g_d3d.cola, g_d3d.fence, v);
    g_d3d.pool_fence[g_d3d.alloc_actual] = v;
    g_d3d.lista_abierta = 0;
    /* marca del tramo que se acaba de mandar */
    marcas_recoger();
    if (g_d3d.marca_n == D3D_N_MARCAS) {   /* llena: esperar la mas vieja */
        d3d_esperar_valor(g_d3d.marca[g_d3d.marca_ini].fence);
        marcas_recoger();
    }
    D3dMarca *m = &g_d3d.marca[(g_d3d.marca_ini + g_d3d.marca_n) % D3D_N_MARCAS];
    m->subida = g_d3d.seg_subida; m->srv = g_d3d.seg_srv; m->smp = g_d3d.seg_smp; m->fence = v;
    g_d3d.marca_n++;
    g_d3d.seg_subida = g_d3d.subida_pos; g_d3d.seg_srv = g_d3d.srv_pos; g_d3d.seg_smp = g_d3d.smp_pos;
    return v;
}

void d3d_esperar_gpu(void) { if (g_d3d.cola) d3d_esperar_valor(d3d_vaciar()); }

/* el inicio de lo que la GPU todavia puede estar leyendo en un anillo (que = 0 subida, 1 srv, 2 smp) */
static uint64_t limite_anillo(int que)
{
    marcas_recoger();
    if (g_d3d.marca_n) { D3dMarca *m = &g_d3d.marca[g_d3d.marca_ini]; return que == 0 ? m->subida : que == 1 ? m->srv : m->smp; }
    return que == 0 ? g_d3d.seg_subida : que == 1 ? g_d3d.seg_srv : g_d3d.seg_smp;
}

/* reserva en un anillo de posiciones MONOTONAS: si no entra al final, salta a la vuelta siguiente; si alcanza lo que
   la GPU todavia lee, vacia y espera (no deberia pasar; se avisa) */
static uint64_t anillo_reservar(int que, uint64_t *pos, uint64_t tam_anillo, uint64_t n, uint64_t alin, const char *nombre)
{
    uint64_t p = (*pos + alin - 1) / alin * alin;
    uint64_t off = p % tam_anillo;
    if (off + n > tam_anillo) { p += tam_anillo - off; off = 0; }
    if (p + n - limite_anillo(que) > tam_anillo) {
        static int avisos;
        if (avisos++ < 5) fprintf(stderr, "[d3d12] anillo de %s lleno: se espera a la GPU\n", nombre);
        d3d_esperar_gpu();
        if (p + n - limite_anillo(que) > tam_anillo)   /* lo grabado sin vaciar ya ocupa todo: imposible */
            fprintf(stderr, "[d3d12] anillo de %s: la reserva de %llu no entra\n", nombre, (unsigned long long)n);
    }
    *pos = p + n;
    return off;
}

void *d3d_subir(uint64_t tam, uint64_t alin, uint64_t *gpu_va)
{
    if (!g_d3d.subida || tam > g_d3d.subida_tam / 4) return NULL;
    if (alin < 16) alin = 16;
    uint64_t off = anillo_reservar(0, &g_d3d.subida_pos, g_d3d.subida_tam, tam, alin, "subida");
    if (gpu_va) *gpu_va = g_d3d.subida_gpu + off;
    return g_d3d.subida_cpu + off;
}

static int heap_reservar(int que, ID3D12DescriptorHeap *h, uint64_t *pos, UINT max, UINT paso, UINT n,
                         D3D12_CPU_DESCRIPTOR_HANDLE *cpu, D3D12_GPU_DESCRIPTOR_HANDLE *gpu, const char *nombre)
{
    if (!h || n == 0 || n > max / 4) return 0;
    uint64_t p = anillo_reservar(que, pos, max, n, 1, nombre);
    D3D12_CPU_DESCRIPTOR_HANDLE c = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(h);
    D3D12_GPU_DESCRIPTOR_HANDLE g = ID3D12DescriptorHeap_GetGPUDescriptorHandleForHeapStart(h);
    c.ptr += (SIZE_T)p * paso;
    g.ptr += (UINT64)p * paso;
    if (cpu) *cpu = c;
    if (gpu) *gpu = g;
    return 1;
}
int d3d_srv_reservar(UINT n, D3D12_CPU_DESCRIPTOR_HANDLE *cpu, D3D12_GPU_DESCRIPTOR_HANDLE *gpu)
{ return heap_reservar(1, g_d3d.srv_heap, &g_d3d.srv_pos, g_d3d.srv_max, g_d3d.srv_paso, n, cpu, gpu, "descriptores"); }
int d3d_smp_reservar(UINT n, D3D12_CPU_DESCRIPTOR_HANDLE *cpu, D3D12_GPU_DESCRIPTOR_HANDLE *gpu)
{ return heap_reservar(2, g_d3d.smp_heap, &g_d3d.smp_pos, g_d3d.smp_max, g_d3d.smp_paso, n, cpu, gpu, "muestreadores"); }

/* ---- buffer de atras ---- */
static void anotar_ritmo(int vsync)
{
    DXGI_FRAME_STATISTICS fs;
    if (FAILED(IDXGISwapChain3_GetFrameStatistics(g_d3d.sc, &fs))) return;   /* falla hasta el primer flip y en ventana compuesta a veces */
    if (g_d3d.ult_present_count && vsync) {
        UINT dp = fs.PresentCount - g_d3d.ult_present_count, dr = fs.PresentRefreshCount - g_d3d.ult_refresh_count;
        if (dp && dr > dp) g_d3d.perdidos += dr - dp;   /* refrescos sin imagen nueva entre dos presentaciones vistas */
    }
    g_d3d.ult_present_count = fs.PresentCount;
    g_d3d.ult_refresh_count = fs.PresentRefreshCount;
}

int d3d_atras_empezar(int esperar_latencia)
{
    if (!g_d3d.sc || g_d3d.en_cuadro) return 0;
    /* objeto de latencia: se libera cuando la swap chain puede aceptar otra imagen = empezar lo mas cerca posible de
       cuando se va a ver (no bloquear en Present). Tope 100 ms para no colgar si la ventana se oculta. */
    if (esperar_latencia && g_d3d.sc_espera) WaitForSingleObjectEx(g_d3d.sc_espera, 100, TRUE);
    g_d3d.cuadro = (int)IDXGISwapChain3_GetCurrentBackBufferIndex(g_d3d.sc);
    ID3D12GraphicsCommandList *l = d3d_lista();
    if (!l) return 0;
    d3d_barrera(l, g_d3d.atras[g_d3d.cuadro], D3D12_RESOURCE_STATE_PRESENT, D3D12_RESOURCE_STATE_RENDER_TARGET);
    g_d3d.en_cuadro = 1;
    return 1;
}

int d3d_atras_presentar(int vsync)
{
    if (!g_d3d.en_cuadro) return 0;
    d3d_barrera(d3d_lista(), g_d3d.atras[g_d3d.cuadro], D3D12_RESOURCE_STATE_RENDER_TARGET, D3D12_RESOURCE_STATE_PRESENT);
    d3d_vaciar();
    g_d3d.en_cuadro = 0;
    HRESULT hr = IDXGISwapChain3_Present(g_d3d.sc, vsync ? 1 : 0, (!vsync && g_d3d.tearing) ? DXGI_PRESENT_ALLOW_TEARING : 0);
    g_d3d.presentados++;
    anotar_ritmo(vsync);
    if (g_d3d.presentados % 1440 == 0)
        fprintf(stderr, "[d3d12] %u presentaciones, %u refrescos sin imagen nueva\n", g_d3d.presentados, g_d3d.perdidos);
    if (FAILED(hr)) { fprintf(stderr, "[d3d12] Present fallo (0x%08lX)\n", (unsigned long)hr); return 0; }
    return 1;
}

ID3D12GraphicsCommandList *d3d_empezar_cuadro(int esperar_latencia)
{
    if (!g_d3d.abierto) return NULL;
    if (g_d3d.sc && !d3d_atras_empezar(esperar_latencia)) return NULL;
    return d3d_lista();
}

int d3d_terminar_cuadro(int vsync)
{
    if (g_d3d.sc) return d3d_atras_presentar(vsync);
    d3d_vaciar();
    return 1;
}

D3D12_CPU_DESCRIPTOR_HANDLE d3d_rtv_atras(void)
{
    D3D12_CPU_DESCRIPTOR_HANDLE h = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(g_d3d.rtv_heap);
    h.ptr += (SIZE_T)g_d3d.cuadro * g_d3d.rtv_paso;
    return h;
}

D3D12_CPU_DESCRIPTOR_HANDLE d3d_rtv_nuevo(void)
{
    D3D12_CPU_DESCRIPTOR_HANDLE h = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(g_d3d.rtv_heap);
    if (g_d3d.rtv_libre >= g_d3d.rtv_max) { fprintf(stderr, "[d3d12] sin RTV libres\n"); h.ptr = 0; return h; }
    h.ptr += (SIZE_T)(g_d3d.rtv_libre++) * g_d3d.rtv_paso;
    return h;
}

D3D12_CPU_DESCRIPTOR_HANDLE d3d_dsv_nuevo(void)
{
    D3D12_CPU_DESCRIPTOR_HANDLE h = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(g_d3d.dsv_heap);
    if (g_d3d.dsv_libre >= g_d3d.dsv_max) { fprintf(stderr, "[d3d12] sin DSV libres\n"); h.ptr = 0; return h; }
    h.ptr += (SIZE_T)(g_d3d.dsv_libre++) * g_d3d.dsv_paso;
    return h;
}

void d3d_cerrar(void)
{
    if (!g_d3d.dev) return;
    d3d_esperar_gpu();
    for (int k = 0; k < D3D_N_CUADROS; k++) {
        if (g_d3d.atras[k]) ID3D12Resource_Release(g_d3d.atras[k]);
    }
    for (int k = 0; k < D3D_N_ALLOC; k++) if (g_d3d.pool[k]) ID3D12CommandAllocator_Release(g_d3d.pool[k]);
    if (g_d3d.smp_heap) ID3D12DescriptorHeap_Release(g_d3d.smp_heap);
    if (g_d3d.subida) ID3D12Resource_Release(g_d3d.subida);
    if (g_d3d.srv_heap) ID3D12DescriptorHeap_Release(g_d3d.srv_heap);
    if (g_d3d.dsv_heap) ID3D12DescriptorHeap_Release(g_d3d.dsv_heap);
    if (g_d3d.rtv_heap) ID3D12DescriptorHeap_Release(g_d3d.rtv_heap);
    if (g_d3d.sc_espera) CloseHandle(g_d3d.sc_espera);   /* 9 oct (C1): el objeto de latencia es un HANDLE propio */
    if (g_d3d.sc) IDXGISwapChain3_Release(g_d3d.sc);
    if (g_d3d.lista) ID3D12GraphicsCommandList_Release(g_d3d.lista);
    if (g_d3d.fence) ID3D12Fence_Release(g_d3d.fence);
    if (g_d3d.cola) ID3D12CommandQueue_Release(g_d3d.cola);
    if (g_d3d.fence_ev) CloseHandle(g_d3d.fence_ev);
    if (g_d3d.adaptador) IDXGIAdapter1_Release(g_d3d.adaptador);
    if (g_d3d.fab) IDXGIFactory6_Release(g_d3d.fab);
    ID3D12Device_Release(g_d3d.dev);
    memset(&g_d3d, 0, sizeof g_d3d);
}
