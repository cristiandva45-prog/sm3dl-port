"""Equivalencia del TEV entero a traves de la cadena GLSL -> SPIR-V -> HLSL -> DXIL, EJECUTADA en D3D12 sobre WARP
(rasterizador por software de Windows, en CPU; no usa la GPU ni el juego) y comparada a 0 LSB con tools\\tev_ref.py.

El compute shader se arma con el MISMO texto del TEV de raster_uber.c (glsl\\uber.frag, generado por volcar_glsl.exe:
funciones rgba8 ... combinar, tal cual) + una entrada/salida por SSBO. Cada caso = una receta TEV REAL del juego
(332, extraido\\shaders\\frag\\recetas.json) x entradas aleatorias con bordes (0,1,127,128,254,255).

Uso (raiz del proyecto):  py -I agentes_dx12\\B\\verif_tev_warp.py [-n CASOS_POR_RECETA] [--sabotaje N]
  --sabotaje 1: d255 con >>7   2: modificador "1-x" sin invertir   3: el buffer del combinador se actualiza una etapa antes
  4: escala x4 como x2   (cada uno debe producir diferencias > 0)
Requiere haber corrido antes: cadena_shaders.py inventario  (y compilado warp_cs.exe; ver su cabecera).
"""
import json
import os
import random
import struct
import subprocess
import sys
import time

B = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(B))
sys.path.insert(0, B)
import cadena_shaders as cs  # noqa: E402
sys.path.append(os.path.join(RAIZ, "tools"))  # al final: tools\dis.py tapa el modulo estandar 'dis'
import tev_ref  # noqa: E402

S = 64   # palabras u32 por caso en la entrada
BORDES = [0, 1, 2, 126, 127, 128, 129, 253, 254, 255]


def extraer_tev(uber):
    L = uber.split("\n")
    rgba8 = next(l for l in L if l.startswith("ivec4 rgba8("))
    i0 = next(i for i, l in enumerate(L) if "TEV en enteros u8" in l)
    i1 = next(i for i, l in enumerate(L) if l.startswith("bool pasa("))
    return rgba8 + "\n" + "\n".join(L[i0:i1])


def comp_glsl(sabotaje=0):
    tev = extraer_tev(open(os.path.join(cs.GLSL, "uber.frag"), encoding="utf-8").read())
    if sabotaje == 1:
        assert "(x + 1 + (x >> 8)) >> 8" in tev
        tev = tev.replace("(x + 1 + (x >> 8)) >> 8", "(x + 1 + (x >> 8)) >> 7")
    elif sabotaje == 2:
        assert "case 1u: return 255 - v.rgb;" in tev
        tev = tev.replace("case 1u: return 255 - v.rgb;", "case 1u: return v.rgb;")
    elif sabotaje == 3:
        assert "if (k < 4) {" in tev
        tev = tev.replace("if (k < 4) {", "if (k < 3) {")
    elif sabotaje == 4:
        assert "int escala_tev(uint e) { return e == 3u ? 1 : (1 << int(e)); }" in tev
        tev = tev.replace("(1 << int(e)); }", "(1 << int(e & 1u)); }")
    cab = """#version 450 core
layout(local_size_x = 64) in;
layout(std430, set = 0, binding = 0) readonly buffer EN { uint d[]; } en;
layout(std430, set = 0, binding = 1) buffer SA { uint r[]; } sa;
uvec4 tev[6];
uint tev_upd, tev_buf;
uint tev_const[6];
ivec4 c_vtx, c_pri, c_sec;
ivec4 c_tex[4];
"""
    main = """
ivec4 leer4(uint o) { return ivec4(int(en.d[o]), int(en.d[o + 1u]), int(en.d[o + 2u]), int(en.d[o + 3u])); }
void main() {
    uint i = gl_GlobalInvocationID.x, b = i * 64u;
    for (uint k = 0u; k < 6u; k++) tev[k] = uvec4(en.d[b + 4u * k], en.d[b + 4u * k + 1u], en.d[b + 4u * k + 2u], en.d[b + 4u * k + 3u]);
    tev_upd = en.d[b + 24u]; tev_buf = en.d[b + 25u];
    for (uint k = 0u; k < 6u; k++) tev_const[k] = en.d[b + 26u + k];
    c_vtx = leer4(b + 32u); c_pri = leer4(b + 36u); c_sec = leer4(b + 40u);
    c_tex[0] = leer4(b + 44u); c_tex[1] = leer4(b + 48u); c_tex[2] = leer4(b + 52u); c_tex[3] = ivec4(0);
    ivec4 res = combinar();
    for (uint k = 0u; k < 4u; k++) sa.r[i * 4u + k] = uint(res[k]);
}
"""
    return cab + tev + main


def caso(rng, firma):
    def u8():
        return rng.choice(BORDES) if rng.random() < 0.25 else rng.randint(0, 255)

    def c4():
        return [u8() for _ in range(4)]
    ent = {"vtx": c4(), "prim": c4(), "sec": c4(), "t0": c4(), "t1": c4(), "t2": c4(), "t3": [0, 0, 0, 0],
           "buf": c4(), "const": [c4() for _ in range(6)]}
    ent["update"] = rng.randint(0, 255) << 8
    return ent


def empacar(firma, ent):
    w = [0] * S
    for k, st in enumerate(firma):
        w[4 * k:4 * k + 4] = list(st)
    w[24] = ent["update"]
    w[25] = sum(ent["buf"][c] << (8 * c) for c in range(4))
    for k in range(6):
        w[26 + k] = sum(ent["const"][k][c] << (8 * c) for c in range(4))
    for off, nom in ((32, "vtx"), (36, "prim"), (40, "sec"), (44, "t0"), (48, "t1"), (52, "t2")):
        w[off:off + 4] = ent[nom]
    return w


def main():
    args = sys.argv[1:]
    n = int(args[args.index("-n") + 1]) if "-n" in args else 120
    sab = int(args[args.index("--sabotaje") + 1]) if "--sabotaje" in args else 0
    rng = random.Random(1234)
    work = os.path.join(B, "out_tev")
    os.makedirs(work, exist_ok=True)
    # 1. shader: cadena completa
    src = comp_glsl(sab)
    base = os.path.join(work, f"tev_cs{'_sab' + str(sab) if sab else ''}")
    open(base + ".comp", "w", newline="\n").write(src)
    t0 = time.perf_counter()
    for cmd, tag in (([cs.GLSLANG, "-V", "--target-env", "vulkan1.0", "-S", "comp", base + ".comp", "-o", base + ".spv"], "glslang"),
                     ([cs.XCROSS, base + ".spv", "--hlsl", "--shader-model", "60", "--output", base + ".hlsl"], "spirv-cross"),
                     ([cs.DXC, "-T", "cs_6_0", "-E", "main", "-Gis", "-Fo", base + ".dxil", base + ".hlsl"], "dxc")):
        rc, out, _ = cs.ejecutar(cmd)
        if rc:
            sys.exit(f"{tag} fallo:\n{out[:800]}")
    print(f"cadena glslang->SPIRV-Cross->DXC OK en {time.perf_counter() - t0:.2f} s; {base}.dxil {os.path.getsize(base + '.dxil')} bytes")
    pur = cs.pureza_entera(open(base + ".hlsl", encoding="utf-8").read())
    print("pureza entera del HLSL:", "limpia" if not pur else pur)
    # 2. casos + referencia
    recetas = json.load(open(os.path.join(cs.SHADERS, "frag", "recetas.json"), encoding="utf-8"))
    casos, esp, omit = [], [], 0
    for r in recetas:
        firma = [tuple(s) for s in r["firma"]]
        for _ in range(n):
            ent = caso(rng, firma)
            try:
                e = tev_ref.correr(firma, ent)
            except tev_ref.NoModelado:
                omit += 1
                break   # esta receta usa algo que tev_ref no modela (p.ej. dot3 en alfa): se omite entera
            casos.append(empacar(firma, ent))
            esp.append([int(x) for x in e])
    N = len(casos)
    pad = (-N) % 64
    casos += [[0] * S] * pad
    open(base + ".in", "wb").write(b"".join(struct.pack(f"<{S}I", *c) for c in casos))
    print(f"{N} casos de {len(recetas) - omit} recetas (omitidas por tev_ref: {omit})")
    # 3. ejecutar en WARP
    t0 = time.perf_counter()
    rc, out, _ = cs.ejecutar([os.path.join(B, "warp_cs.exe"), base + ".dxil", base + ".in", base + ".out", str((N + pad) // 64), str((N + pad) * 16)])
    if rc:
        sys.exit("warp_cs fallo: " + out[:600])
    print(out.splitlines()[0] if out else "", f"| ejecucion {time.perf_counter() - t0:.2f} s")
    raw = open(base + ".out", "rb").read()
    got = struct.unpack(f"<{(N + pad) * 4}I", raw)
    malos, peor = 0, 0
    ej = None
    for i in range(N):
        g = list(got[4 * i:4 * i + 4])
        if g != esp[i]:
            malos += 1
            peor = max(peor, max(abs(a - b) for a, b in zip(g, esp[i])))
            ej = ej or (i, g, esp[i])
    print(f"RESULTADO: {N - malos}/{N} casos IDENTICOS a tev_ref (0 LSB); diferentes {malos}; error maximo {peor} LSB" + (f"; primer caso {ej}" if ej else ""))
    sys.exit(1 if malos else 0)


if __name__ == "__main__":
    main()
