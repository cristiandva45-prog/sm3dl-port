/* PRESENTADOR D3D12 — ver d3d12_presentador.h */
#include "d3d12_presentador.h"
#include <d3dcompiler.h>
#include <stdio.h>
#include <string.h>

/* un rectangulo de 4 vertices (tira) con coordenadas en NDC y UV dadas por constantes raiz:
   R = x0 y0 x1 y1 (NDC), U = u0 v0 u1 v1, F.x = lineal (0/1) */
static const char *HLSL_PRES =
    "cbuffer K : register(b0) { float4 R; float4 U; float4 F; };\n"
    "Texture2D tex : register(t0);\n"
    "SamplerState punto : register(s0);\n"
    "SamplerState lineal : register(s1);\n"
    "struct V { float4 p : SV_Position; float2 uv : TEXCOORD0; };\n"
    "V vs(uint i : SV_VertexID) {\n"
    "    float2 k = float2(i & 1, i >> 1);\n"
    "    V o; o.p = float4(lerp(R.x, R.z, k.x), lerp(R.y, R.w, k.y), 0, 1);\n"
    "    o.uv = float2(lerp(U.x, U.z, k.x), lerp(U.y, U.w, k.y)); return o; }\n"
    "float4 ps(V v) : SV_Target { return F.x > 0.5 ? tex.Sample(lineal, v.uv) : tex.Sample(punto, v.uv); }\n";

static ID3D12RootSignature *g_rs;
static ID3D12PipelineState *g_pso_base, *g_pso_capa;
static D3dTextura g_ran[D3DP_RANURAS], g_capa_tex[2];
static int g_listo;

static ID3DBlob *compilar(const char *e, const char *perfil)
{
    ID3DBlob *b = NULL, *err = NULL;
    if (FAILED(D3DCompile(HLSL_PRES, strlen(HLSL_PRES), "pres", NULL, NULL, e, perfil, D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &b, &err))) {
        fprintf(stderr, "[d3d12-pres] HLSL %s: %s\n", e, err ? (const char *)ID3D10Blob_GetBufferPointer(err) : "?");
        return NULL;
    }
    return b;
}

int d3dp_iniciar(void)
{
    if (g_listo) return 1;
    /* raiz: 12 constantes (b0) + tabla de 1 SRV (t0) + 2 samplers estaticos (punto, lineal; con borde = clamp) */
    D3D12_DESCRIPTOR_RANGE rango = { D3D12_DESCRIPTOR_RANGE_TYPE_SRV, 1, 0, 0, 0 };
    D3D12_ROOT_PARAMETER p[2];
    memset(p, 0, sizeof p);
    p[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    p[0].Constants.Num32BitValues = 12;
    p[0].ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL;
    p[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    p[1].DescriptorTable.NumDescriptorRanges = 1;
    p[1].DescriptorTable.pDescriptorRanges = &rango;
    p[1].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    D3D12_STATIC_SAMPLER_DESC s[2];
    memset(s, 0, sizeof s);
    for (int k = 0; k < 2; k++) {
        s[k].Filter = k ? D3D12_FILTER_MIN_MAG_MIP_LINEAR : D3D12_FILTER_MIN_MAG_MIP_POINT;
        s[k].AddressU = s[k].AddressV = s[k].AddressW = D3D12_TEXTURE_ADDRESS_MODE_CLAMP;
        s[k].MaxLOD = D3D12_FLOAT32_MAX;
        s[k].ShaderRegister = (UINT)k;
        s[k].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    }
    D3D12_ROOT_SIGNATURE_DESC rsd = { 2, p, 2, s, D3D12_ROOT_SIGNATURE_FLAG_NONE };
    ID3DBlob *rsb = NULL, *rse = NULL;
    if (FAILED(D3D12SerializeRootSignature(&rsd, D3D_ROOT_SIGNATURE_VERSION_1, &rsb, &rse))) { fprintf(stderr, "[d3d12-pres] firma raiz\n"); return 0; }
    if (FAILED(ID3D12Device_CreateRootSignature(g_d3d.dev, 0, ID3D10Blob_GetBufferPointer(rsb), ID3D10Blob_GetBufferSize(rsb),
                                                &IID_ID3D12RootSignature, (void **)&g_rs))) return 0;
    ID3D10Blob_Release(rsb);
    ID3DBlob *vs = compilar("vs", "vs_5_0"), *ps = compilar("ps", "ps_5_0");
    if (!vs || !ps) return 0;
    D3D12_GRAPHICS_PIPELINE_STATE_DESC d;
    memset(&d, 0, sizeof d);
    d.pRootSignature = g_rs;
    d.VS.pShaderBytecode = ID3D10Blob_GetBufferPointer(vs); d.VS.BytecodeLength = ID3D10Blob_GetBufferSize(vs);
    d.PS.pShaderBytecode = ID3D10Blob_GetBufferPointer(ps); d.PS.BytecodeLength = ID3D10Blob_GetBufferSize(ps);
    d.BlendState.RenderTarget[0].RenderTargetWriteMask = D3D12_COLOR_WRITE_ENABLE_ALL;
    d.SampleMask = 0xFFFFFFFF;
    d.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    d.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
    d.RasterizerState.DepthClipEnable = TRUE;
    d.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    d.NumRenderTargets = 1;
    d.RTVFormats[0] = DXGI_FORMAT_B8G8R8A8_UNORM;
    d.SampleDesc.Count = 1;
    g_pso_base = d3d_pso_obtener(0x9E5E000000000001ull, &d);
    D3D12_RENDER_TARGET_BLEND_DESC *b = &d.BlendState.RenderTarget[0];
    b->BlendEnable = TRUE;
    b->SrcBlend = b->SrcBlendAlpha = D3D12_BLEND_ONE;
    b->DestBlend = b->DestBlendAlpha = D3D12_BLEND_INV_SRC_ALPHA;
    b->BlendOp = b->BlendOpAlpha = D3D12_BLEND_OP_ADD;
    g_pso_capa = d3d_pso_obtener(0x9E5E000000000002ull, &d);
    ID3D10Blob_Release(vs);
    ID3D10Blob_Release(ps);
    g_listo = g_pso_base && g_pso_capa;
    return g_listo;
}

int d3dp_guardar(ID3D12GraphicsCommandList *l, D3dTextura *f, int r)
{
    if (r < 0 || r >= D3DP_RANURAS || !f || !f->res) return 0;
    D3dTextura *t = &g_ran[r];
    if (!t->res || t->w != f->w || t->h != f->h || t->fmt != f->fmt) {
        if (t->res) d3d_tex_liberar(t);
        if (!d3d_tex_crear(t, f->fmt, f->w, f->h, 0, 0)) return 0;
    }
    D3D12_RESOURCE_STATES ef = f->estado;
    d3d_tex_estado(l, f, D3D12_RESOURCE_STATE_COPY_SOURCE);
    d3d_tex_estado(l, t, D3D12_RESOURCE_STATE_COPY_DEST);
    ID3D12GraphicsCommandList_CopyResource(l, t->res, f->res);
    d3d_tex_estado(l, f, ef);
    d3d_tex_estado(l, t, D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    return 1;
}

D3dTextura *d3dp_ranura(int r) { return r >= 0 && r < D3DP_RANURAS && g_ran[r].res ? &g_ran[r] : NULL; }

int d3dp_empezar(ID3D12GraphicsCommandList *l)
{
    if (!g_listo && !d3dp_iniciar()) return 0;
    float negro[4] = { 0, 0, 0, 1 };
    D3D12_CPU_DESCRIPTOR_HANDLE rtv = d3d_rtv_atras();
    ID3D12GraphicsCommandList_ClearRenderTargetView(l, rtv, negro, 0, NULL);
    return 1;
}

static void rect(ID3D12GraphicsCommandList *l, ID3D12PipelineState *pso, D3dTextura *t, int x0, int y0, int x1, int y1, int lineal, int invertir)
{
    d3d_tex_estado(l, t, D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    D3D12_CPU_DESCRIPTOR_HANDLE c;
    D3D12_GPU_DESCRIPTOR_HANDLE g;
    if (!d3d_srv_reservar(1, &c, &g)) return;
    ID3D12Device_CopyDescriptorsSimple(g_d3d.dev, 1, c, t->srv, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    float W = (float)g_d3d.w, H = (float)g_d3d.h;
    /* k.y = 0 es el vertice de ABAJO en NDC: R.y = borde inferior (y1 de ventana), U.y = v de abajo (1) */
    float k[12] = { 2.0f * x0 / W - 1.0f, 1.0f - 2.0f * y1 / H, 2.0f * x1 / W - 1.0f, 1.0f - 2.0f * y0 / H,
                    0.0f, invertir ? 0.0f : 1.0f, 1.0f, invertir ? 1.0f : 0.0f,
                    lineal ? 1.0f : 0.0f, 0, 0, 0 };
    D3D12_CPU_DESCRIPTOR_HANDLE rtv = d3d_rtv_atras();
    ID3D12GraphicsCommandList_OMSetRenderTargets(l, 1, &rtv, FALSE, NULL);
    D3D12_VIEWPORT vp = { 0, 0, W, H, 0, 1 };
    D3D12_RECT sc = { 0, 0, g_d3d.w, g_d3d.h };
    ID3D12GraphicsCommandList_RSSetViewports(l, 1, &vp);
    ID3D12GraphicsCommandList_RSSetScissorRects(l, 1, &sc);
    ID3D12GraphicsCommandList_SetGraphicsRootSignature(l, g_rs);
    ID3D12GraphicsCommandList_SetPipelineState(l, pso);
    ID3D12GraphicsCommandList_SetGraphicsRoot32BitConstants(l, 0, 12, k, 0);
    ID3D12GraphicsCommandList_SetGraphicsRootDescriptorTable(l, 1, g);
    ID3D12GraphicsCommandList_IASetPrimitiveTopology(l, D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
    ID3D12GraphicsCommandList_DrawInstanced(l, 4, 1, 0, 0);
}

int d3dp_base(ID3D12GraphicsCommandList *l, D3dTextura *t, int x0, int y0, int x1, int y1, int lineal, int invertir)
{
    if (!g_listo || !t || !t->res) return 0;
    rect(l, g_pso_base, t, x0, y0, x1, y1, lineal, invertir);
    return 1;
}

int d3dp_subir(ID3D12GraphicsCommandList *l, int c, const uint8_t *bgra, int w, int h, int x0, int y0, int x1, int y1)
{
    if (c < 0 || c > 1 || w <= 0 || h <= 0) return 0;
    D3dTextura *t = &g_capa_tex[c];
    if (!t->res || t->w != w || t->h != h) {
        if (t->res) d3d_tex_liberar(t);
        if (!d3d_tex_crear(t, DXGI_FORMAT_B8G8R8A8_UNORM, w, h, 0, 0)) return 0;
        x0 = 0; y0 = 0; x1 = w; y1 = h;
    }
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > w) x1 = w;
    if (y1 > h) y1 = h;
    if (x1 <= x0 || y1 <= y0) return 1;
    return d3d_tex_subir(l, t, x0, y0, x1 - x0, y1 - y0, bgra + ((size_t)y0 * w + x0) * 4, w * 4);
}

int d3dp_capa(ID3D12GraphicsCommandList *l, int c, int x0, int y0, int x1, int y1, int lineal)
{
    if (!g_listo || c < 0 || c > 1 || !g_capa_tex[c].res) return 0;
    rect(l, g_pso_capa, &g_capa_tex[c], x0, y0, x1, y1, lineal, 0);
    return 1;
}

int d3dp_leer(ID3D12GraphicsCommandList *l, uint8_t *bgra)
{
    if (!g_d3d.sc) return 0;
    D3dTextura atras;
    memset(&atras, 0, sizeof atras);
    atras.res = g_d3d.atras[g_d3d.cuadro];
    atras.fmt = DXGI_FORMAT_B8G8R8A8_UNORM;
    atras.w = g_d3d.w; atras.h = g_d3d.h;
    atras.estado = D3D12_RESOURCE_STATE_RENDER_TARGET;
    D3dLectura lec;
    memset(&lec, 0, sizeof lec);
    if (!d3d_leer_encolar(l, &atras, 0, 0, atras.w, atras.h, &lec)) return 0;
    d3d_leer_marcar(&lec, d3d_ejecutar(l));
    int ok = d3d_leer_esperar(&lec, bgra, atras.w * 4);
    d3d_leer_liberar(&lec);
    return ok;
}
