"""Generador GLSL del FRAGMENT LIGHTING del PICA200, una funcion por configuracion de material.  (agente I, 8 oct 2026)

Entrada: extraido\\shaders\\luz\\configs.json (lo escribe `luz_frag_mtob.py censo`): 105 configuraciones de
codigo distintas en los 4.146 materiales con luz por fragmento.
Salida:  extraido\\shaders\\luz\\L<id>.glsl  (snippet autocontenido: uniforms + helpers + `luz_frag(...)`)
         extraido\\shaders\\luz\\flip_quat.geom (geometry shader opcional: alinea el signo de los cuaterniones
         del triangulo antes de interpolar, como FlipQuaternionIfOpposite del rasterizador).

Lo que es CODIGO (constante por configuracion, va en el texto): config PICA (que LUTs existen), LUTs activas,
su entrada (NH/VH/NV/LN/SP/CP) y si es absoluta o con signo, clamp highlights, factor geometrico 0/1,
selector de Fresnel, bump (modo, textura, renormalizacion).
Lo que es DATO (uniforms que pone el runtime): luces (cuantas, color ya multiplicado por el material,
posicion/direccion, dos caras, atenuacion por distancia y spot con su LUT), filas de LUT y escalas,
ambiente global. Las LUTs van en UNA textura RG32F de 256 x N (r = valor, g = diferencia), leida con texelFetch.

Semantica: reimplementada a partir de Azahar (renderer_software/sw_lighting.cpp y
shader/generator/glsl_fs_shader_gen.cpp, GPLv2: solo lectura de referencia, nada copiado literal).

Uso: py -I tools\\luz_frag_glsl.py            # genera los 105 + flip_quat.geom
     (compilar/verificar: tools\\.venv_gl\\Scripts\\python.exe tools\\probar_luz_frag.py)
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(RAIZ, "extraido", "shaders", "luz")
LUTS = ("RR", "RG", "RB", "D0", "D1", "FR")
ENTRADAS = ("NH", "VH", "NV", "LN", "SP", "CP")
MAX_LUCES = 8

COMUN = """\
// ---- fragment lighting PICA200: interfaz con el runtime ----
struct LuzFuente {
    vec3 especular0;   // ya multiplicados por el color del material (como LIGHTn_SPECULAR0... del PICA)
    vec3 especular1;
    vec3 difusa;
    vec3 ambiente;
    vec3 posicion;     // espacio de vista; si direccional, es la direccion HACIA la luz
    vec3 spot_dir;
    float da_escala;   // atenuacion por distancia: lut_DA(clamp(escala*dist + sesgo, 0, 1))
    float da_sesgo;
    int da_fila;       // fila de la LUT en luz_luts
    int sp_fila;
    bool direccional;
    bool dos_caras;
    bool usa_da;
    bool usa_sp;
};
uniform LuzFuente luz_fuente[8];
uniform int luz_num;                 // 0..8
uniform vec3 luz_ambiente_global;
uniform sampler2D luz_luts;          // RG32F 256 x N: r = valor, g = diferencia (entrada PICA decodificada)
uniform int luz_lut_fila[6];         // RR RG RB D0 D1 FR
uniform float luz_lut_escala[6];
uniform int luz_sp_entrada;          // 0 NH 1 VH 2 NV 3 LN 4 SP 5 CP (spot: lo fija la luz, no el material)
uniform bool luz_sp_abs;
uniform float luz_sp_escala;

// u8 truncado (mismo +1e-3 que el q8 del TEV para absorber el error de float)
vec4 luz_q8(vec4 x) { return floor(clamp(x, vec4(0.0), vec4(1.0)) * 255.0 + 1e-3) / 255.0; }
vec3 luz_qrot(vec4 q, vec3 v) { return v + 2.0 * cross(q.xyz, cross(q.xyz, v) + q.w * v); }
float luz_lut(int fila, int i, float d) {
    vec2 e = texelFetch(luz_luts, ivec2(i, fila), 0).rg;
    return e.r + e.g * d;
}
float luz_lut_abs(int fila, float x) {      // indice 0..255 sobre [0,1)
    float f = clamp(floor(x * 256.0), 0.0, 255.0);
    return luz_lut(fila, int(f), x * 256.0 - f);
}
float luz_lut_sig(int fila, float x) {      // 0..127 = [0,1), 128..255 = [-1,0)
    float f = clamp(floor(x * 128.0), -128.0, 127.0);
    int i = int(f);
    if (i < 0) i += 256;
    return luz_lut(fila, i, x * 128.0 - f);
}
"""

GEOM = """\
#version 330 core
// Alinea el signo del cuaternion de normal de los 3 vertices con el del primero antes de interpolar
// (sin esto, q y -q -la misma rotacion- se promedian a ~0 y la normal sale basura en el triangulo).
layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;
{decl}
void main() {{
    for (int k = 0; k < 3; ++k) {{
        gl_Position = gl_in[k].gl_Position;
{copia}
        if (k > 0 && dot(g_{quat}[k], g_{quat}[0]) < 0.0) {quat} = -g_{quat}[k];
        EmitVertex();
    }}
    EndPrimitive();
}}
"""


def geom_flip(salidas=("pica_o0", "pica_o1", "pica_o2", "pica_o3", "pica_o4", "pica_o5", "pica_o6"),
              quat="pica_o1"):
    """Geometry shader de paso. El vertex shader debe renombrar sus salidas a g_<nombre> (o se usa un
    #define en la union); `quat` es la salida 'normquat' del outmap del VSH."""
    decl = "\n".join(f"in vec4 g_{s}[];\nout vec4 {s};" for s in salidas)
    copia = "\n".join(f"        {s} = g_{s}[k];" for s in salidas)
    return GEOM.format(decl=decl, copia=copia, quat=quat)


def _entrada(e, cfg):
    return {
        "NH": "dot(normal, hn)",
        "VH": "dot(nv, hn)",
        "NV": "dot(normal, nv)",
        "LN": "dot(lv, normal)",
        "SP": "dot(lv, L.spot_dir)",
        # cos phi solo existe en la config 7 (codigo 8); en las demas el hardware da 0
        "CP": "dot(hn - normal * dot(normal, hn), tangente)" if cfg == 8 else "0.0",
    }[e]


def _consulta(fila, expr, absoluta):
    if absoluta:
        return f"luz_lut_abs({fila}, L.dos_caras ? abs({expr}) : max({expr}, 0.0))"
    return f"luz_lut_sig({fila}, {expr})"


def soporta(cfg, lut):
    """IsLightingSamplerSupported de regs_lighting.h (reimplementada)."""
    return {"D0": cfg != 1, "D1": cfg not in (0, 1, 5), "FR": cfg not in (0, 2, 4), "RR": cfg != 3,
            "RG": cfg in (4, 5, 8), "RB": cfg in (4, 5, 8), "SP": cfg not in (2, 3)}[lut]


def funcion(c, nombre="luz_frag"):
    """GLSL de `void nombre(vec4 normquat, vec3 vista, vec4 t0, vec4 t1, vec4 t2, out vec4 primario,
    out vec4 secundario)` para la configuracion c (dict de configs.json)."""
    cfg = c["cfg"]
    act = {n: (e, a) for n, e, a in c["luts"]}
    for n in act:
        assert soporta(cfg, n), (n, cfg)
    S = []
    w = S.append
    w(f"// config: {c.get('txt', '')}")
    w(f"void {nombre}(vec4 normquat, vec3 vista, vec4 t0, vec4 t1, vec4 t2, out vec4 primario, out vec4 secundario) {{")
    if c["bump_modo"]:
        w(f"    vec3 pert = 2.0 * t{c['bump_tex']}.rgb - 1.0;")
        if c["bump_modo"] == 1:
            if c["bump_renorm"]:
                w("    pert.z = sqrt(max(1.0 - dot(pert.xy, pert.xy), 0.0));")
            w("    vec3 sn = pert, st = vec3(1.0, 0.0, 0.0);")
        else:
            w("    vec3 sn = vec3(0.0, 0.0, 1.0), st = pert;")
    else:
        w("    vec3 sn = vec3(0.0, 0.0, 1.0), st = vec3(1.0, 0.0, 0.0);")
    w("    vec4 q = normalize(normquat);")
    w("    vec3 normal = luz_qrot(q, sn);")
    w("    vec3 tangente = luz_qrot(q, st);")
    w("    vec3 nv = normalize(vista);")
    w("    vec4 dif = vec4(0.0, 0.0, 0.0, 1.0);")
    w("    vec4 esp = vec4(0.0, 0.0, 0.0, 1.0);")
    w(f"    for (int i = 0; i < {MAX_LUCES}; ++i) {{")
    w("        if (i >= luz_num) break;")
    w("        LuzFuente L = luz_fuente[i];")
    w("        vec3 lv = L.direccional ? L.posicion : L.posicion + vista;")
    w("        float dist = length(lv);")
    w("        lv = normalize(lv);")
    w("        vec3 h = nv + lv;")
    w("        vec3 hn = normalize(h);")
    w("        float nl = L.dos_caras ? abs(dot(lv, normal)) : max(dot(lv, normal), 0.0);")
    w("        float da = 1.0;")
    w("        if (L.usa_da) da = luz_lut_abs(L.da_fila, clamp(L.da_escala * dist + L.da_sesgo, 0.0, 1.0));")
    w("        float sp = 1.0;")
    if soporta(cfg, "SP"):
        w("        if (L.usa_sp) {")
        w("            float x;")
        for k, e in enumerate(ENTRADAS):
            w(f"            {'if' if k == 0 else 'else if'} (luz_sp_entrada == {k}) x = {_entrada(e, cfg)};")
        w("            else x = 0.0;")
        w("            sp = luz_sp_escala * (luz_sp_abs ? luz_lut_abs(L.sp_fila, L.dos_caras ? abs(x) : max(x, 0.0))"
          " : luz_lut_sig(L.sp_fila, x));")
        w("        }")

    def val(n):
        e, a = act[n]
        return f"luz_lut_escala[{LUTS.index(n)}] * {_consulta(f'luz_lut_fila[{LUTS.index(n)}]', _entrada(e, cfg), a)}"
    w(f"        float d0 = {val('D0') if 'D0' in act else '1.0'};")
    w(f"        float rr = {val('RR') if 'RR' in act else '1.0'};")
    w(f"        vec3 refl = vec3(rr, {val('RG') if 'RG' in act else 'rr'}, {val('RB') if 'RB' in act else 'rr'});")
    w(f"        float d1 = {val('D1') if 'D1' in act else '1.0'};")
    w("        vec3 s0 = d0 * L.especular0;")
    w("        vec3 s1 = d1 * refl * L.especular1;")
    if c["geo0"] or c["geo1"]:
        w("        float g = dot(h, h);")
        w("        g = g == 0.0 ? 0.0 : min(nl / g, 1.0);")
        if c["geo0"]:
            w("        s0 *= g;")
        if c["geo1"]:
            w("        s1 *= g;")
    if "FR" in act and c["fresnel"]:
        w("        if (i == luz_num - 1) {   // solo la ultima luz aplica Fresnel")
        w(f"            float fr = {val('FR')};")
        if c["fresnel"] & 1:
            w("            dif.a = fr;")
        if c["fresnel"] & 2:
            w("            esp.a = fr;")
        w("        }")
    w(f"        float ch = {'(nl == 0.0 ? 0.0 : 1.0)' if c['clamp'] else '1.0'};")
    w("        dif.rgb += (L.difusa * nl + L.ambiente) * da * sp;")
    w("        esp.rgb += (s0 + s1) * ch * da * sp;")
    w("    }")
    w("    dif.rgb += luz_ambiente_global;")
    # salida en u8 TRUNCADO, como el rasterizador por software (static_cast<u8>(clamp*255)) y como
    # espera el TEV del agente G (fuentes exactas k/255)
    w("    primario = luz_q8(dif);")
    w("    secundario = luz_q8(esp);")
    w("}")
    return "\n".join(S) + "\n"


def snippet(c, nombre="luz_frag"):
    return COMUN + "\n" + funcion(c, nombre)


def cargar_configs():
    return json.load(open(os.path.join(DIR, "configs.json"), encoding="utf-8"))


def main():
    cs = cargar_configs()
    for c in cs:
        open(os.path.join(DIR, f"L{c['id']}.glsl"), "w", encoding="utf-8").write(
            f"// Generado por tools\\luz_frag_glsl.py — config L{c['id']} ({c['usos']} materiales)\n" + snippet(c))
    open(os.path.join(DIR, "flip_quat.geom"), "w", encoding="utf-8").write(geom_flip())
    print(f"{len(cs)} snippets L*.glsl + flip_quat.geom en {DIR} (cubren {sum(c['usos'] for c in cs)} materiales)")


if __name__ == "__main__":
    sys.exit(main())
