p=r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\recomp\render\raster_d3d12_copiar.inc"
t=open(p,encoding="utf-8",newline="").read()
old_sh='''    /* blit: A = (sx0, sy0, kx, ky), B = (dx0, dy0, 1/Ws, 1/Hs), C = (lineal, Ws, Hs, 0) */
    "float4 blit(float4 p : SV_Position) : SV_Target {\\n"
    "    float2 s = A.xy + (p.xy - B.xy) * A.zw;\\n"
    "    if (C.x > 0.5) return tex.SampleLevel(lineal, s * B.zw, 0);\\n"
    "    int2 i = clamp(int2(floor(s)), int2(0, 0), int2(C.yz) - 1);\\n"
    "    return tex.Load(int3(i, 0));\\n"
    "}\\n"'''
new_sh='''    /* blit LINEAL: A = (sx0, sy0, kx, ky), B = (dx0, dy0, 1/Ws, 1/Hs), C = (1, Ws, Hs, 0).
     * blit PUNTO (C5b): A = (sx0, sy0, dw, dh), B = (dx0, dy0, sw, sh), C = (0, Ws, Hs, 0) con sw = sx1-sx0, dw = dx1-dx0
     * (con signo = volteo). Texel EN ENTEROS como el valor exacto del GL: s = s0 + floor((2(X-d0)+1)*sw / (2*dw)); en
     * float los EMPATES (centro justo en el borde de un texel, p.ej. 60/58) caian del otro lado (20 px en E2
     * pres_pasos_x2 "base punto (2,3)-(62,60)"). Todos los valores caben exactos en float (< 2^24). */
    "int2 dx_divp(int2 n, int2 d) { n = d < 0 ? -n : n; d = abs(d);\\n"
    "    return n >= 0 ? n / d : -((d - 1 - n) / d); }\\n"
    "float4 blit(float4 p : SV_Position) : SV_Target {\\n"
    "    if (C.x > 0.5) { float2 s = A.xy + (p.xy - B.xy) * A.zw; return tex.SampleLevel(lineal, s * B.zw, 0); }\\n"
    "    int2 X = int2(floor(p.xy)), d0 = int2(B.xy), sw = int2(B.zw), dw = int2(A.zw);\\n"
    "    int2 i = int2(A.xy) + dx_divp((2 * (X - d0) + 1) * sw, 2 * dw);\\n"
    "    i = clamp(i, int2(0, 0), int2(C.yz) - 1);\\n"
    "    return tex.Load(int3(i, 0));\\n"
    "}\\n"'''
assert t.count(old_sh)==1, "sh"
t=t.replace(old_sh,new_sh)
old_k='''    float k[12] = { (float)sx0, (float)sy0, (float)(sx1 - sx0) / (float)(dx1 - dx0), (float)(sy1 - sy0) / (float)(dy1 - dy0),
                    (float)dx0, (float)dy0, 1.0f / (float)src->w, 1.0f / (float)src->h,
                    lineal ? 1.0f : 0.0f, (float)src->w, (float)src->h, 0.0f };'''
new_k=old_k+'''
    if (!lineal) {   /* punto: enteros (ver el HLSL; C5b) */
        k[2] = (float)(dx1 - dx0); k[3] = (float)(dy1 - dy0);
        k[6] = (float)(sx1 - sx0); k[7] = (float)(sy1 - sy0);
    }'''
assert t.count(old_k)==1, "k"
t=t.replace(old_k,new_k)
a="NEAREST = texel floor(s) (Load exacto, sin la imprecision del muestreador de punto)"
assert t.count(a)==1, "a"
t=t.replace(a,"NEAREST = texel floor(s) en ENTEROS (Load exacto, empates como el GL; C5b)")
open(p+".tmp","w",encoding="utf-8",newline="").write(t)
import os; os.replace(p+".tmp",p)
print("ok")
