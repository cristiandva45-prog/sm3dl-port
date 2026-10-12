/* RECURSOS D3D12 — ver d3d12_recursos.h */
#include "d3d12_recursos.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- monton de SRV en CPU (fijos por textura; se copian al anillo visible con CopyDescriptorsSimple) ---- */
static ID3D12DescriptorHeap *g_srv_cpu;
static UINT g_srv_cpu_paso, g_srv_cpu_libre, g_srv_cpu_max = 16384;
static UINT g_srv_cpu_huecos[16384], g_srv_cpu_nhuecos;   /* indices devueltos por texturas liberadas */

static D3D12_CPU_DESCRIPTOR_HANDLE srv_cpu_nuevo(UINT *indice)
{
    D3D12_CPU_DESCRIPTOR_HANDLE h = { 0 };
    if (!g_srv_cpu) {
        D3D12_DESCRIPTOR_HEAP_DESC d = { D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV, g_srv_cpu_max, D3D12_DESCRIPTOR_HEAP_FLAG_NONE, 0 };
        if (FAILED(ID3D12Device_CreateDescriptorHeap(g_d3d.dev, &d, &IID_ID3D12DescriptorHeap, (void **)&g_srv_cpu))) return h;
        g_srv_cpu_paso = ID3D12Device_GetDescriptorHandleIncrementSize(g_d3d.dev, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    }
    UINT i;
    if (g_srv_cpu_nhuecos) i = g_srv_cpu_huecos[--g_srv_cpu_nhuecos];
    else if (g_srv_cpu_libre < g_srv_cpu_max) i = g_srv_cpu_libre++;
    else { fprintf(stderr, "[d3d12] sin SRV de CPU libres\n"); return h; }
    h = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(g_srv_cpu);
    h.ptr += (SIZE_T)i * g_srv_cpu_paso;
    *indice = i;
    return h;
}

/* ---- RTV/DSV reciclados (C2, 9 oct; PEDIDO de C4): d3d_rtv_nuevo/d3d_dsv_nuevo de d3d12_base solo avanzan (1.024 RTV,
   256 DSV) y la capa comun recrea sus RT al cambiar la resolucion interna: ~256 recreaciones con D24S8 agotaban el
   monton. Los de las texturas liberadas vuelven aqui y se reusan EN EL ACTO: un RTV/DSV es de CPU y D3D12 lo lee al
   GRABAR (OMSetRenderTargets / Clear*View copian el descriptor), asi que una lista ya grabada no depende de el. ---- */
static D3D12_CPU_DESCRIPTOR_HANDLE g_rtv_huecos[1024], g_dsv_huecos[256];
static UINT g_rtv_nhuecos, g_dsv_nhuecos;
static D3D12_CPU_DESCRIPTOR_HANDLE rtv_tomar(void) { return g_rtv_nhuecos ? g_rtv_huecos[--g_rtv_nhuecos] : d3d_rtv_nuevo(); }
static D3D12_CPU_DESCRIPTOR_HANDLE dsv_tomar(void) { return g_dsv_nhuecos ? g_dsv_huecos[--g_dsv_nhuecos] : d3d_dsv_nuevo(); }

/* ---- liberacion diferida: el recurso vive hasta que la GPU paso la fence del cuadro en que se solto ---- */
typedef struct { ID3D12Resource *r; uint64_t fence; } Diferido;
static Diferido g_dif[4096];
static int g_ndif;
static void diferidos_recoger(void)
{
    uint64_t hecho = ID3D12Fence_GetCompletedValue(g_d3d.fence);
    int j = 0;
    for (int i = 0; i < g_ndif; i++) {
        if (g_dif[i].fence <= hecho) ID3D12Resource_Release(g_dif[i].r);
        else g_dif[j++] = g_dif[i];
    }
    g_ndif = j;
}
static void soltar(ID3D12Resource *r)
{
    if (!r) return;
    diferidos_recoger();
    if (g_ndif >= (int)(sizeof g_dif / sizeof g_dif[0])) { d3d_esperar_gpu(); diferidos_recoger(); }
    g_dif[g_ndif].r = r;
    g_dif[g_ndif].fence = g_d3d.fence_val + 1;   /* lo que se ejecute despues de ahora ya no lo usa */
    g_ndif++;
}

static UINT bytes_por_pixel(DXGI_FORMAT f)
{
    switch (f) {
    case DXGI_FORMAT_R8G8B8A8_UNORM: case DXGI_FORMAT_B8G8R8A8_UNORM: case DXGI_FORMAT_R32_FLOAT:
    case DXGI_FORMAT_D24_UNORM_S8_UINT: case DXGI_FORMAT_R32_UINT: case DXGI_FORMAT_R16G16_FLOAT: return 4;
    case DXGI_FORMAT_R32G32_FLOAT: case DXGI_FORMAT_R16G16B16A16_FLOAT: return 8;
    case DXGI_FORMAT_R32G32B32A32_FLOAT: return 16;
    case DXGI_FORMAT_R8_UNORM: return 1;
    case DXGI_FORMAT_R8G8_UNORM: case DXGI_FORMAT_R16_FLOAT: case DXGI_FORMAT_B5G6R5_UNORM: return 2;
    default: return 4;
    }
}

/* niveles de mip que admite w x h (hasta que ambos lados llegan a 1) */
static int niveles_max(int w, int h)
{
    int n = 1;
    while ((w > 1 || h > 1) && n < 16) { w >>= 1; h >>= 1; n++; }
    return n;
}

static int tex_crear_n(D3dTextura *t, DXGI_FORMAT fmt, int w, int h, int rt, int ds, int niveles)
{
    memset(t, 0, sizeof *t);
    if (w <= 0 || h <= 0) return 0;
    if (niveles < 1 || rt || ds) niveles = 1;
    if (niveles > niveles_max(w, h)) niveles = niveles_max(w, h);
    if (ds) fmt = DXGI_FORMAT_D24_UNORM_S8_UINT;
    D3D12_HEAP_PROPERTIES hp = { D3D12_HEAP_TYPE_DEFAULT, D3D12_CPU_PAGE_PROPERTY_UNKNOWN, D3D12_MEMORY_POOL_UNKNOWN, 1, 1 };
    D3D12_RESOURCE_DESC d;
    memset(&d, 0, sizeof d);
    d.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    d.Width = (UINT64)w; d.Height = (UINT)h; d.DepthOrArraySize = 1; d.MipLevels = (UINT16)niveles;
    /* profundidad con formato TYPELESS para poder leerla tambien como textura (el juego copia el z a veces) */
    d.Format = ds ? DXGI_FORMAT_R24G8_TYPELESS : fmt;
    d.SampleDesc.Count = 1;
    d.Layout = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    d.Flags = rt ? D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET : ds ? D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL : D3D12_RESOURCE_FLAG_NONE;
    D3D12_CLEAR_VALUE cv;
    memset(&cv, 0, sizeof cv);
    cv.Format = fmt;
    if (ds) { cv.DepthStencil.Depth = 1.0f; cv.DepthStencil.Stencil = 0; }
    D3D12_RESOURCE_STATES e0 = rt ? D3D12_RESOURCE_STATE_RENDER_TARGET : ds ? D3D12_RESOURCE_STATE_DEPTH_WRITE : D3D12_RESOURCE_STATE_COPY_DEST;
    HRESULT hr = ID3D12Device_CreateCommittedResource(g_d3d.dev, &hp, D3D12_HEAP_FLAG_NONE, &d, e0, (rt || ds) ? &cv : NULL,
                                                      &IID_ID3D12Resource, (void **)&t->res);
    if (FAILED(hr)) { fprintf(stderr, "[d3d12] textura %dx%d fmt %d fallo (0x%08lX)\n", w, h, fmt, (unsigned long)hr); return 0; }
    t->fmt = fmt; t->w = w; t->h = h; t->rt = rt; t->ds = ds; t->estado = e0; t->niveles = niveles;
    if (rt) {
        t->rtv = rtv_tomar();
        if (!t->rtv.ptr) { ID3D12Resource_Release(t->res); memset(t, 0, sizeof *t); return 0; }   /* sin RTV: no crear con NULL */
        ID3D12Device_CreateRenderTargetView(g_d3d.dev, t->res, NULL, t->rtv);
    }
    if (ds) {
        D3D12_DEPTH_STENCIL_VIEW_DESC dv;
        memset(&dv, 0, sizeof dv);
        dv.Format = DXGI_FORMAT_D24_UNORM_S8_UINT;
        dv.ViewDimension = D3D12_DSV_DIMENSION_TEXTURE2D;
        t->dsv = dsv_tomar();
        if (!t->dsv.ptr) { ID3D12Resource_Release(t->res); memset(t, 0, sizeof *t); return 0; }
        ID3D12Device_CreateDepthStencilView(g_d3d.dev, t->res, &dv, t->dsv);
    }
    UINT idx = 0;
    t->srv = srv_cpu_nuevo(&idx);
    if (t->srv.ptr) {
        D3D12_SHADER_RESOURCE_VIEW_DESC sv;
        memset(&sv, 0, sizeof sv);
        sv.Format = ds ? DXGI_FORMAT_R24_UNORM_X8_TYPELESS : fmt;
        sv.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
        sv.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
        sv.Texture2D.MipLevels = (UINT)niveles;
        ID3D12Device_CreateShaderResourceView(g_d3d.dev, t->res, &sv, t->srv);
    }
    return 1;
}

int d3d_tex_crear(D3dTextura *t, DXGI_FORMAT fmt, int w, int h, int rt, int ds) { return tex_crear_n(t, fmt, w, h, rt, ds, 1); }
int d3d_tex_crear_mips(D3dTextura *t, DXGI_FORMAT fmt, int w, int h, int niveles) { return tex_crear_n(t, fmt, w, h, 0, 0, niveles); }

void d3d_tex_liberar(D3dTextura *t)
{
    if (t->srv.ptr && g_srv_cpu) {
        D3D12_CPU_DESCRIPTOR_HANDLE b = ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(g_srv_cpu);
        g_srv_cpu_huecos[g_srv_cpu_nhuecos++] = (UINT)((t->srv.ptr - b.ptr) / g_srv_cpu_paso);
    }
    /* RTV/DSV: de vuelta a sus huecos (ver rtv_tomar). Solo los que puso tex_crear_n (t->rt / t->ds). */
    if (t->rt && t->rtv.ptr && g_rtv_nhuecos < sizeof g_rtv_huecos / sizeof g_rtv_huecos[0]) g_rtv_huecos[g_rtv_nhuecos++] = t->rtv;
    if (t->ds && t->dsv.ptr && g_dsv_nhuecos < sizeof g_dsv_huecos / sizeof g_dsv_huecos[0]) g_dsv_huecos[g_dsv_nhuecos++] = t->dsv;
    soltar(t->res);
    memset(t, 0, sizeof *t);
}

void d3d_tex_estado(ID3D12GraphicsCommandList *l, D3dTextura *t, D3D12_RESOURCE_STATES e)
{
    if (t->estado == e) return;
    d3d_barrera(l, t->res, t->estado, e);
    t->estado = e;
}

/* sube una TIRA (filas y..y+h) del nivel: una reserva del anillo + CopyTextureRegion */
static int subir_tira(ID3D12GraphicsCommandList *l, D3dTextura *t, UINT sub, int x, int y, int w, int h,
                      const uint8_t *datos, int pitch, UINT bpp, UINT fila, int intercambiar_rb)
{
    uint64_t gpu;
    uint8_t *dst = d3d_subir((uint64_t)fila * h, D3D12_TEXTURE_DATA_PLACEMENT_ALIGNMENT, &gpu);
    if (!dst) return 0;
    /* d3d_subir puede haber vaciado la lista (anillo lleno -> d3d_esperar_gpu): grabar en una lista cerrada es un
       error de D3D12, asi que se reabre (es el mismo objeto g_d3d.lista) */
    if (l == g_d3d.lista && !g_d3d.lista_abierta) l = d3d_lista();
    for (int j = 0; j < h; j++) {
        uint8_t *o = dst + (size_t)j * fila;
        const uint8_t *s = datos + (size_t)j * pitch;
        if (intercambiar_rb && bpp == 4) {
            for (int i = 0; i < w; i++) { o[4 * i] = s[4 * i + 2]; o[4 * i + 1] = s[4 * i + 1]; o[4 * i + 2] = s[4 * i]; o[4 * i + 3] = s[4 * i + 3]; }
        } else {
            memcpy(o, s, (size_t)w * bpp);
        }
    }
    D3D12_TEXTURE_COPY_LOCATION de, a;
    memset(&de, 0, sizeof de);
    memset(&a, 0, sizeof a);
    de.pResource = g_d3d.subida;
    de.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    de.PlacedFootprint.Offset = gpu - g_d3d.subida_gpu;
    de.PlacedFootprint.Footprint.Format = t->fmt;
    de.PlacedFootprint.Footprint.Width = (UINT)w;
    de.PlacedFootprint.Footprint.Height = (UINT)h;
    de.PlacedFootprint.Footprint.Depth = 1;
    de.PlacedFootprint.Footprint.RowPitch = fila;
    a.pResource = t->res;
    a.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    a.SubresourceIndex = sub;
    d3d_tex_estado(l, t, D3D12_RESOURCE_STATE_COPY_DEST);
    ID3D12GraphicsCommandList_CopyTextureRegion(l, &a, (UINT)x, (UINT)y, 0, &de, NULL);
    return 1;
}

int d3d_tex_subir_nivel(ID3D12GraphicsCommandList *l, D3dTextura *t, int nivel, int x, int y, int w, int h,
                        const void *datos, int pitch, int intercambiar_rb)
{
    int niveles = t->niveles > 0 ? t->niveles : 1;
    if (!t->res || nivel < 0 || nivel >= niveles) return 0;
    int nw = t->w >> nivel, nh = t->h >> nivel;
    if (nw < 1) nw = 1;
    if (nh < 1) nh = 1;
    if (w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > nw || y + h > nh) return 0;
    UINT bpp = bytes_por_pixel(t->fmt);
    UINT fila = ((UINT)w * bpp + D3D12_TEXTURE_DATA_PITCH_ALIGNMENT - 1) & ~(D3D12_TEXTURE_DATA_PITCH_ALIGNMENT - 1);
    /* tiras de <= 8 MB (el anillo de 64 MB admite 16 MB por reserva): una capa 4K BGRA (33 MB) entra en 5 */
    int filas_tira = (int)((8u << 20) / fila);
    if (filas_tira < 1) filas_tira = 1;
    D3D12_RESOURCE_STATES antes = t->estado;
    int ok = 1;
    for (int j = 0; j < h && ok; j += filas_tira) {
        int n = h - j < filas_tira ? h - j : filas_tira;
        ok = subir_tira(l, t, (UINT)nivel, x, y + j, w, n, (const uint8_t *)datos + (size_t)j * pitch, pitch, bpp, fila,
                        intercambiar_rb);
        if (l == g_d3d.lista && !g_d3d.lista_abierta) l = d3d_lista();
    }
    if (antes != D3D12_RESOURCE_STATE_COPY_DEST)
        d3d_tex_estado(l, t, (antes == D3D12_RESOURCE_STATE_RENDER_TARGET || antes == D3D12_RESOURCE_STATE_DEPTH_WRITE) ? antes
                                                                                                               : D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    return ok;
}

int d3d_tex_subir(ID3D12GraphicsCommandList *l, D3dTextura *t, int x, int y, int w, int h, const void *datos, int pitch)
{
    return d3d_tex_subir_nivel(l, t, 0, x, y, w, h, datos, pitch, 0);
}

/* ---- lecturas de vuelta ---- */
int d3d_leer_encolar(ID3D12GraphicsCommandList *l, D3dTextura *t, int x, int y, int w, int h, D3dLectura *lec)
{
    if (!t->res || w <= 0 || h <= 0 || x < 0 || y < 0 || x + w > t->w || y + h > t->h) return 0;
    UINT bpp = bytes_por_pixel(t->fmt);
    UINT pitch = ((UINT)w * bpp + 255u) & ~255u;
    uint64_t tam = (uint64_t)pitch * h;
    /* D24S8 en D3D12 = DOS planos (subrecurso 0 profundidad, 1 stencil R8): el stencil va detras, alineado a 512 */
    UINT pitch_s = ((UINT)w + 255u) & ~255u;
    uint64_t off_s = (tam + 511u) & ~511ull;
    if (t->ds) tam = off_s + (uint64_t)pitch_s * h;
    if (lec->buf && lec->cap < tam) { soltar(lec->buf); lec->buf = NULL; }
    if (!lec->buf) {
        D3D12_HEAP_PROPERTIES hp = { D3D12_HEAP_TYPE_READBACK, D3D12_CPU_PAGE_PROPERTY_UNKNOWN, D3D12_MEMORY_POOL_UNKNOWN, 1, 1 };
        D3D12_RESOURCE_DESC d;
        memset(&d, 0, sizeof d);
        d.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
        d.Width = tam; d.Height = 1; d.DepthOrArraySize = 1; d.MipLevels = 1;
        d.Format = DXGI_FORMAT_UNKNOWN; d.SampleDesc.Count = 1; d.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        if (FAILED(ID3D12Device_CreateCommittedResource(g_d3d.dev, &hp, D3D12_HEAP_FLAG_NONE, &d, D3D12_RESOURCE_STATE_COPY_DEST,
                                                        NULL, &IID_ID3D12Resource, (void **)&lec->buf))) return 0;
        lec->cap = tam;
    }
    lec->w = w; lec->h = h; lec->pitch = pitch; lec->bpp = (int)bpp; lec->fence = 0;
    lec->ds = t->ds; lec->off_stencil = off_s; lec->pitch_stencil = pitch_s;
    D3D12_TEXTURE_COPY_LOCATION de, a;
    memset(&de, 0, sizeof de);
    memset(&a, 0, sizeof a);
    de.pResource = t->res;
    de.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    a.pResource = lec->buf;
    a.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    a.PlacedFootprint.Footprint.Format = t->ds ? DXGI_FORMAT_R32_TYPELESS : t->fmt;
    a.PlacedFootprint.Footprint.Width = (UINT)w;
    a.PlacedFootprint.Footprint.Height = (UINT)h;
    a.PlacedFootprint.Footprint.Depth = 1;
    a.PlacedFootprint.Footprint.RowPitch = pitch;
    D3D12_BOX caja = { (UINT)x, (UINT)y, 0, (UINT)(x + w), (UINT)(y + h), 1 };
    D3D12_RESOURCE_STATES antes = t->estado;
    d3d_tex_estado(l, t, D3D12_RESOURCE_STATE_COPY_SOURCE);
    ID3D12GraphicsCommandList_CopyTextureRegion(l, &a, 0, 0, 0, &de, &caja);
    if (t->ds) {   /* plano 1: stencil */
        de.SubresourceIndex = 1;
        a.PlacedFootprint.Offset = off_s;
        a.PlacedFootprint.Footprint.Format = DXGI_FORMAT_R8_TYPELESS;
        a.PlacedFootprint.Footprint.RowPitch = pitch_s;
        ID3D12GraphicsCommandList_CopyTextureRegion(l, &a, 0, 0, 0, &de, &caja);
    }
    d3d_tex_estado(l, t, antes);
    return 1;
}

void d3d_leer_marcar(D3dLectura *lec, uint64_t valor_fence) { lec->fence = valor_fence; }
int d3d_leer_listo(const D3dLectura *lec) { return lec->fence && ID3D12Fence_GetCompletedValue(g_d3d.fence) >= lec->fence; }

int d3d_leer_esperar(D3dLectura *lec, void *dst, int dst_pitch)
{
    if (!lec->buf || !lec->fence) return 0;
    d3d_esperar_valor(lec->fence);
    D3D12_RANGE r = { 0, (SIZE_T)lec->cap };
    uint8_t *p;
    if (FAILED(ID3D12Resource_Map(lec->buf, 0, &r, (void **)&p))) return 0;
    for (int j = 0; j < lec->h; j++) {
        uint8_t *fila = (uint8_t *)dst + (size_t)j * dst_pitch;
        memcpy(fila, p + (size_t)j * lec->pitch, (size_t)lec->w * lec->bpp);
        if (lec->ds) {   /* D24S8 empaquetado como la PICA: z en los 24 bajos, stencil en el byte alto */
            const uint8_t *s = p + lec->off_stencil + (size_t)j * lec->pitch_stencil;
            for (int i = 0; i < lec->w; i++) {
                uint32_t v;
                memcpy(&v, fila + 4 * i, 4);
                v = (v & 0xFFFFFFu) | ((uint32_t)s[i] << 24);
                memcpy(fila + 4 * i, &v, 4);
            }
        }
    }
    D3D12_RANGE nada = { 0, 0 };
    ID3D12Resource_Unmap(lec->buf, 0, &nada);
    return 1;
}

void d3d_leer_liberar(D3dLectura *lec) { soltar(lec->buf); memset(lec, 0, sizeof *lec); }

/* vacia (sin esperar) y deja la lista abierta otra vez (el mismo objeto: 'l' sigue sirviendo). El llamador espera la
   fence devuelta solo si la necesita (d3d_leer_esperar lo hace). */
uint64_t d3d_ejecutar(ID3D12GraphicsCommandList *l)
{
    (void)l;
    uint64_t v = d3d_vaciar();
    d3d_lista();
    diferidos_recoger();
    return v;
}

/* ---- cache de PSO ---- */
static ID3D12PipelineLibrary *g_lib;
static char g_lib_ruta[300];
static int g_lib_sucia;
static unsigned g_pso_disco, g_pso_creados;
static double g_pso_ms;
typedef struct { uint64_t clave; ID3D12PipelineState *pso; } EntPso;
static EntPso *g_tabla;
static unsigned g_tabla_tam, g_tabla_n;

int d3d_pso_cache_abrir(const char *ruta)
{
    ID3D12Device1 *d1 = NULL;
    if (FAILED(ID3D12Device_QueryInterface(g_d3d.dev, &IID_ID3D12Device1, (void **)&d1))) return 0;
    snprintf(g_lib_ruta, sizeof g_lib_ruta, "%s", ruta);
    void *blob = NULL;
    long tam = 0;
    FILE *f = fopen(ruta, "rb");
    if (f) {
        fseek(f, 0, SEEK_END); tam = ftell(f); fseek(f, 0, SEEK_SET);
        blob = tam > 0 ? malloc((size_t)tam) : NULL;
        if (blob && fread(blob, 1, (size_t)tam, f) != (size_t)tam) { free(blob); blob = NULL; tam = 0; }
        fclose(f);
    }
    /* el blob debe seguir vivo mientras viva la libreria: no se libera */
    HRESULT hr = ID3D12Device1_CreatePipelineLibrary(d1, blob, blob ? (SIZE_T)tam : 0, &IID_ID3D12PipelineLibrary, (void **)&g_lib);
    if (FAILED(hr) && blob) {   /* driver o GPU distintos: cache vieja -> empezar vacia */
        fprintf(stderr, "[d3d12] cache de PSO descartada (0x%08lX): se rearma\n", (unsigned long)hr);
        hr = ID3D12Device1_CreatePipelineLibrary(d1, NULL, 0, &IID_ID3D12PipelineLibrary, (void **)&g_lib);
    }
    ID3D12Device1_Release(d1);
    if (FAILED(hr)) { g_lib = NULL; return 0; }
    fprintf(stderr, "[d3d12] cache de PSO: %s (%ld bytes)\n", ruta, blob ? tam : 0L);
    return 1;
}

/* (F1, 9 oct) antes fallaba EN SILENCIO por cualquier camino (malloc, Serialize, fopen, fwrite, rename) y en la 1a
   partida con D3D12 no quedo archivo: ahora cada guardado deja una linea en el log (bytes, PSO en la libreria) y cada
   fallo su causa. El cambio de archivo es MoveFileEx(REPLACE_EXISTING): nunca queda ni a medias ni borrado. */
static unsigned g_lib_n, g_lib_fallos;   /* StorePipeline bien / mal en esta corrida */
void d3d_pso_cache_guardar(void)
{
    if (!g_lib || !g_lib_sucia) return;
    SIZE_T tam = ID3D12PipelineLibrary_GetSerializedSize(g_lib);
    void *b = tam ? malloc(tam) : NULL;
    if (!b) { fprintf(stderr, "[d3d12] cache de PSO: sin memoria para serializar %llu bytes\n", (unsigned long long)tam); return; }
    HRESULT hr = ID3D12PipelineLibrary_Serialize(g_lib, b, tam);
    if (FAILED(hr)) { fprintf(stderr, "[d3d12] cache de PSO: Serialize fallo (0x%08lX)\n", (unsigned long)hr); free(b); return; }
    char tmp[320];
    snprintf(tmp, sizeof tmp, "%s.tmp", g_lib_ruta);
    FILE *f = fopen(tmp, "wb");
    if (!f) { fprintf(stderr, "[d3d12] cache de PSO: no abre %s para escribir\n", tmp); free(b); return; }
    int ok = fwrite(b, 1, tam, f) == tam;
    ok = (fclose(f) == 0) && ok;
    free(b);
    if (!ok) { fprintf(stderr, "[d3d12] cache de PSO: escritura corta en %s\n", tmp); remove(tmp); return; }
    if (!MoveFileExA(tmp, g_lib_ruta, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        fprintf(stderr, "[d3d12] cache de PSO: no reemplaza %s (error %lu)\n", g_lib_ruta, (unsigned long)GetLastError());
        remove(tmp);
        return;
    }
    g_lib_sucia = 0;
    fprintf(stderr, "[d3d12] cache de PSO guardada: %s (%llu bytes; %u PSO nuevos esta corrida, %u del disco, %u sin guardar)\n",
            g_lib_ruta, (unsigned long long)tam, g_lib_n, g_pso_disco, g_lib_fallos);
}

static EntPso *tabla_buscar(uint64_t clave, int crear)
{
    if (g_tabla_n * 2 >= g_tabla_tam) {
        unsigned nt = g_tabla_tam ? g_tabla_tam * 2 : 1024;
        EntPso *n = calloc(nt, sizeof *n);
        if (!n) return NULL;
        for (unsigned i = 0; i < g_tabla_tam; i++)
            if (g_tabla[i].pso) {
                unsigned j = (unsigned)(g_tabla[i].clave * 0x9E3779B97F4A7C15ull >> 40) & (nt - 1);
                while (n[j].pso) j = (j + 1) & (nt - 1);
                n[j] = g_tabla[i];
            }
        free(g_tabla);
        g_tabla = n;
        g_tabla_tam = nt;
    }
    unsigned j = (unsigned)(clave * 0x9E3779B97F4A7C15ull >> 40) & (g_tabla_tam - 1);
    while (g_tabla[j].pso) { if (g_tabla[j].clave == clave) return &g_tabla[j]; j = (j + 1) & (g_tabla_tam - 1); }
    return crear ? &g_tabla[j] : NULL;
}

ID3D12PipelineState *d3d_pso_obtener(uint64_t clave, const D3D12_GRAPHICS_PIPELINE_STATE_DESC *desc)
{
    EntPso *e = tabla_buscar(clave, 1);
    if (!e) return NULL;
    if (e->pso) return e->pso;
    WCHAR nombre[24];
    swprintf(nombre, 24, L"%016llx", (unsigned long long)clave);
    ID3D12PipelineState *p = NULL;
    LARGE_INTEGER f, t0, t1;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t0);
    if (g_lib && SUCCEEDED(ID3D12PipelineLibrary_LoadGraphicsPipeline(g_lib, nombre, desc, &IID_ID3D12PipelineState, (void **)&p))) {
        g_pso_disco++;
    } else {
        HRESULT hr = ID3D12Device_CreateGraphicsPipelineState(g_d3d.dev, desc, &IID_ID3D12PipelineState, (void **)&p);
        if (FAILED(hr)) { fprintf(stderr, "[d3d12] PSO %016llx fallo (0x%08lX)\n", (unsigned long long)clave, (unsigned long)hr); return NULL; }
        g_pso_creados++;
        if (g_lib) {
            HRESULT hs = ID3D12PipelineLibrary_StorePipeline(g_lib, nombre, p);
            if (SUCCEEDED(hs)) { g_lib_sucia = 1; g_lib_n++; }
            else if (g_lib_fallos++ < 4) fprintf(stderr, "[d3d12] PSO %016llx: StorePipeline fallo (0x%08lX)\n", (unsigned long long)clave, (unsigned long)hs);
        }
    }
    QueryPerformanceCounter(&t1);
    g_pso_ms += (double)(t1.QuadPart - t0.QuadPart) * 1000.0 / (double)f.QuadPart;
    e->clave = clave;
    e->pso = p;
    g_tabla_n++;
    return p;
}

void d3d_pso_estadisticas(unsigned *de_disco, unsigned *creados, double *ms)
{
    if (de_disco) *de_disco = g_pso_disco;
    if (creados) *creados = g_pso_creados;
    if (ms) *ms = g_pso_ms;
}
