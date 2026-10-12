/* PRUEBA DE d3d12_recursos (8 oct noche), sin ventana, segundos:
 *  1. textura RGBA8 400x240: subida completa + una region (13,7 50x20) con otro patron; lectura de vuelta completa
 *     -> EXACTA: 0 bytes distintos contra lo esperado.
 *  2. render target 64x64 limpiado a (0.25, 0.5, 0.75, 1) -> lectura = (64,128,191,255) (redondeo UNORM).
 *  3. profundidad D24S8 limpiada a z = 0.5, stencil 7 -> lectura R32: z24 = 0x7FFFFF/0x800000, stencil 7.
 *  4. PSO por la cache en disco (HLSL compilado con d3dcompiler_47 de Windows) dibuja un triangulo rojo que cubre el
 *     RT: pixel central = (255,0,0,255). 2a corrida: el PSO sale DEL DISCO.
 * SM3DL_D3D_SABOTAJE=1: la region se sube 1 px corrida -> la comparacion 1 TIENE que fallar. */
#include "d3d12_recursos.h"
#include <d3dcompiler.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *HLSL =
    "float4 vs(uint i : SV_VertexID) : SV_Position { float2 p = float2((i << 1) & 2, i & 2); return float4(p * 2 - 1, 0, 1); }\n"
    "float4 ps() : SV_Target { return float4(1, 0, 0, 1); }\n";

static ID3DBlob *compilar(const char *entrada, const char *perfil)
{
    ID3DBlob *b = NULL, *err = NULL;
    if (FAILED(D3DCompile(HLSL, strlen(HLSL), "prueba", NULL, NULL, entrada, perfil, D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &b, &err))) {
        fprintf(stderr, "[prueba] HLSL: %s\n", err ? (const char *)ID3D10Blob_GetBufferPointer(err) : "?");
        return NULL;
    }
    return b;
}

int main(void)
{
    int sab = getenv("SM3DL_D3D_SABOTAJE") != NULL, fallas = 0;
    if (!d3d_iniciar(NULL, 0, 0)) return 1;
    ID3D12GraphicsCommandList *l = d3d_empezar_cuadro(0);

    /* 1 */
    enum { W = 400, H = 240 };
    static uint8_t a[W * H * 4], esperado[W * H * 4], leido[W * H * 4], region[50 * 20 * 4];
    for (int i = 0; i < W * H * 4; i++) a[i] = (uint8_t)(i * 2654435761u >> 13);
    for (int i = 0; i < 50 * 20 * 4; i++) region[i] = (uint8_t)(i * 40503u + 7);
    memcpy(esperado, a, sizeof a);
    for (int y = 0; y < 20; y++) memcpy(esperado + ((size_t)(7 + y) * W + 13) * 4, region + (size_t)y * 50 * 4, 50 * 4);
    D3dTextura t;
    if (!d3d_tex_crear(&t, DXGI_FORMAT_R8G8B8A8_UNORM, W, H, 0, 0)) return 1;
    d3d_tex_subir(l, &t, 0, 0, W, H, a, W * 4);
    d3d_tex_subir(l, &t, 13 + (sab ? 1 : 0), 7, 50, 20, region, 50 * 4);
    D3dLectura lec = { 0 };
    d3d_leer_encolar(l, &t, 0, 0, W, H, &lec);
    d3d_leer_marcar(&lec, d3d_ejecutar(l));
    d3d_leer_esperar(&lec, leido, W * 4);
    unsigned dist = 0;
    for (int i = 0; i < W * H * 4; i++) dist += leido[i] != esperado[i];
    fprintf(stderr, "[prueba] 1 textura 400x240 + region%s: %u bytes distintos -> %s\n", sab ? " (SABOTAJE 1 px)" : "", dist,
            dist == 0 ? "EXACTA" : "DISTINTA");
    fallas += sab ? dist == 0 : dist != 0;

    /* 2 */
    D3dTextura rt;
    d3d_tex_crear(&rt, DXGI_FORMAT_R8G8B8A8_UNORM, 64, 64, 1, 0);
    float c[4] = { 0.25f, 0.5f, 0.75f, 1.0f };
    ID3D12GraphicsCommandList_ClearRenderTargetView(l, rt.rtv, c, 0, NULL);
    D3dLectura lr = { 0 };
    uint8_t px[64 * 64 * 4];
    d3d_leer_encolar(l, &rt, 0, 0, 64, 64, &lr);
    d3d_leer_marcar(&lr, d3d_ejecutar(l));
    d3d_leer_esperar(&lr, px, 64 * 4);
    /* float -> UNORM8 no es exacto en el medio punto (0,5 x 255 = 127,5: la RTX da 127; la norma tolera 0,6 ULP) */
    int ok2 = px[0] == 64 && (px[1] == 127 || px[1] == 128) && px[2] == 191 && px[3] == 255 && !memcmp(px, px + 4 * 4095, 4);
    fprintf(stderr, "[prueba] 2 RT limpiado: (%u,%u,%u,%u) -> %s\n", px[0], px[1], px[2], px[3], ok2 ? "bien" : "MAL");
    fallas += !ok2;

    /* 3 */
    D3dTextura z;
    d3d_tex_crear(&z, 0, 64, 64, 0, 1);
    ID3D12GraphicsCommandList_ClearDepthStencilView(l, z.dsv, D3D12_CLEAR_FLAG_DEPTH | D3D12_CLEAR_FLAG_STENCIL, 0.5f, 7, 0, NULL);
    D3dLectura lz = { 0 };
    uint32_t zz[64 * 64];
    d3d_leer_encolar(l, &z, 0, 0, 64, 64, &lz);
    d3d_leer_marcar(&lz, d3d_ejecutar(l));
    int ok3 = d3d_leer_esperar(&lz, zz, 64 * 4);
    unsigned z24 = zz[0] & 0xFFFFFF, st = zz[0] >> 24;
    ok3 = ok3 && (z24 == 0x7FFFFF || z24 == 0x800000) && st == 7;
    fprintf(stderr, "[prueba] 3 profundidad: z24 0x%06X stencil %u -> %s\n", z24, st, ok3 ? "bien" : "MAL");
    fallas += !ok3;

    /* 4 */
    d3d_pso_cache_abrir("prueba_pso_cache.bin");
    D3D12_ROOT_SIGNATURE_DESC rsd = { 0, NULL, 0, NULL, D3D12_ROOT_SIGNATURE_FLAG_NONE };
    ID3DBlob *rsb = NULL, *rse = NULL;
    ID3D12RootSignature *rs = NULL;
    D3D12SerializeRootSignature(&rsd, D3D_ROOT_SIGNATURE_VERSION_1, &rsb, &rse);
    ID3D12Device_CreateRootSignature(g_d3d.dev, 0, ID3D10Blob_GetBufferPointer(rsb), ID3D10Blob_GetBufferSize(rsb),
                                     &IID_ID3D12RootSignature, (void **)&rs);
    ID3DBlob *vs = compilar("vs", "vs_5_0"), *ps = compilar("ps", "ps_5_0");
    int ok4 = 0;
    if (vs && ps && rs) {
        D3D12_GRAPHICS_PIPELINE_STATE_DESC d;
        memset(&d, 0, sizeof d);
        d.pRootSignature = rs;
        d.VS.pShaderBytecode = ID3D10Blob_GetBufferPointer(vs); d.VS.BytecodeLength = ID3D10Blob_GetBufferSize(vs);
        d.PS.pShaderBytecode = ID3D10Blob_GetBufferPointer(ps); d.PS.BytecodeLength = ID3D10Blob_GetBufferSize(ps);
        d.BlendState.RenderTarget[0].RenderTargetWriteMask = D3D12_COLOR_WRITE_ENABLE_ALL;
        d.SampleMask = 0xFFFFFFFF;
        d.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
        d.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
        d.RasterizerState.DepthClipEnable = TRUE;
        d.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
        d.NumRenderTargets = 1;
        d.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
        d.SampleDesc.Count = 1;
        ID3D12PipelineState *p = d3d_pso_obtener(0x5133D1A000000001ull, &d);
        if (p) {
            ID3D12GraphicsCommandList_SetGraphicsRootSignature(l, rs);
            ID3D12GraphicsCommandList_SetPipelineState(l, p);
            D3D12_VIEWPORT vp = { 0, 0, 64, 64, 0, 1 };
            D3D12_RECT sc = { 0, 0, 64, 64 };
            ID3D12GraphicsCommandList_RSSetViewports(l, 1, &vp);
            ID3D12GraphicsCommandList_RSSetScissorRects(l, 1, &sc);
            ID3D12GraphicsCommandList_OMSetRenderTargets(l, 1, &rt.rtv, FALSE, NULL);
            ID3D12GraphicsCommandList_IASetPrimitiveTopology(l, D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
            ID3D12GraphicsCommandList_DrawInstanced(l, 3, 1, 0, 0);
            d3d_leer_encolar(l, &rt, 0, 0, 64, 64, &lr);
            d3d_leer_marcar(&lr, d3d_ejecutar(l));
            d3d_leer_esperar(&lr, px, 64 * 4);
            const uint8_t *m = px + (32 * 64 + 32) * 4;
            ok4 = m[0] == 255 && m[1] == 0 && m[2] == 0 && m[3] == 255;
            fprintf(stderr, "[prueba] 4 triangulo con PSO: centro (%u,%u,%u,%u) -> %s\n", m[0], m[1], m[2], m[3], ok4 ? "bien" : "MAL");
        }
    }
    fallas += !ok4;
    unsigned dd = 0, cc = 0;
    double ms = 0;
    d3d_pso_estadisticas(&dd, &cc, &ms);
    fprintf(stderr, "[prueba] PSO: %u del disco, %u creados (%.2f ms)\n", dd, cc, ms);
    d3d_pso_cache_guardar();
    d3d_tex_liberar(&t); d3d_tex_liberar(&rt); d3d_tex_liberar(&z);
    d3d_leer_liberar(&lec); d3d_leer_liberar(&lr); d3d_leer_liberar(&lz);
    d3d_cerrar();
    fprintf(stderr, "[prueba] %s\n", fallas ? "HAY FALLAS" : "todo bien");
    return fallas != 0;
}
