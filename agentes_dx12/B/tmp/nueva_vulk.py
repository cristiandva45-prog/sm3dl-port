_DECL = re.compile(r"^uniform\s+(?P<t>\w+)\s+(?P<n>\w+)(?:\[(?P<c>\d+)\])?\s*;(?P<r>.*)$")
_PACK4 = {"bool": "uvec4", "int": "ivec4", "uint": "uvec4", "float": "vec4"}

# Layout de los cbuffers = EL MISMO que las estructuras RbCb* de recomp\render\raster_backend.h (agente A):
#   b0 RbCbVertice (VS), b1 RbCbFragmento, b2 RbCbNiebla, b3 RbCbLuz. Cada miembro va a su bloque y en el ORDEN de la
#   estructura de A (el padding lo pone std140, que coincide con los _pN de A: se comprueba con `layouts`).
#   Todos los miembros se declaran SIEMPRE (con o sin ESPECIALIZADO/LUZ) para que el layout no dependa de la variante.
BLOQUES = [
    ("b0", 0, ["pica_c", "pica_i", "pica_b", "omap", "clip_on", "clip_coef"]),
    ("b1", 1, ["tev", "tev_const", "tev_buf", "tev_upd", "tex_modo", "tex0_proy", "alfa_func", "alfa_ref", "wbuffer",
               "z_escala", "z_offset", "tijera_modo", "tijera", "niebla", "niebla_flip", "niebla_color"]),
    ("b2", 2, ["niebla_lut"]),
    ("b3", 3, ["luz_on", "luz_n", "luz_mues", "luz_c0", "luz_c1", "luz_abs", "luz_ent", "luz_esc", "luz_amb", "luz_fila", "luz"]),
]
# nombres que en el fs_para() ESPECIALIZADO son `const` globales: el miembro del cbuffer se llama cb_<n> y, sin
# ESPECIALIZADO, un #define lo devuelve a su nombre original
_CHOCAN = ["tev", "luz_n", "luz_mues", "luz_c0", "luz_c1", "luz_abs", "luz_ent", "luz_esc"]
_LUZ_ESTRUCTURA = ("struct Luz { vec4 esp0; vec4 esp1; vec4 dif; vec4 amb; vec4 pos; vec4 spot; float da_escala; "
                   "float da_sesgo; int num; int cfg; };   // = RbLuz (std140 con vec3 la dejaria con da_escala en .w de spot)")


def _indexar(src, nombre, f):
    """Reemplaza cada `nombre[expr]` (corchetes balanceados) por f(expr)."""
    out, i, pat = [], 0, re.compile(r"\b" + re.escape(nombre) + r"\[")
    while True:
        m = pat.search(src, i)
        if not m:
            out.append(src[i:])
            return "".join(out)
        j, prof = m.end(), 1
        while prof:
            prof += {"[": 1, "]": -1}.get(src[j], 0)
            j += 1
        out.append(src[i:m.start()])
        out.append(f(src[m.end():j - 1]))
        i = j


GEOM_D3D = """#version 450 core
// GEOM_FLIP reescrito para D3D12 (mismo calculo; ver cadena_shaders.py): SPIRV-Cross->HLSL no admite bloques de interfaz
// en arrays ni gl_in[].gl_ClipDistance, asi que la interfaz son varyings sueltos por ubicacion (0..4 = V.color,tc01,
// tc2w,quat,view; 5 = V.cd, la clip distance que el VS ahora tambien manda en el bloque V).
layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;
layout(location = 0) in vec4 gi_color[];
layout(location = 1) in vec4 gi_tc01[];
layout(location = 2) in vec4 gi_tc2w[];
layout(location = 3) in vec4 gi_quat[];
layout(location = 4) in vec4 gi_view[];
layout(location = 5) in float gi_cd[];
layout(location = 0) out vec4 go_color;
layout(location = 1) out vec4 go_tc01;
layout(location = 2) out vec4 go_tc2w;
layout(location = 3) out vec4 go_quat;
layout(location = 4) out vec4 go_view;
layout(location = 5) out float go_cd;
in gl_PerVertex { vec4 gl_Position; } gl_in[];
out float gl_ClipDistance[1];
void main() {
    for (int k = 0; k < 3; k++) {
        gl_Position = gl_in[k].gl_Position;
        gl_ClipDistance[0] = gi_cd[k];
        go_color = gi_color[k]; go_tc01 = gi_tc01[k]; go_tc2w = gi_tc2w[k]; go_view = gi_view[k]; go_cd = gi_cd[k];
        go_quat = (k > 0 && dot(gi_quat[k], gi_quat[0]) < 0.0) ? -gi_quat[k] : gi_quat[k];
        EmitVertex();
    }
    EndPrimitive();
}
"""


def _gs_d3d(src):
    # el GS del C debe seguir teniendo ESTA semantica (si cambia, hay que re-portar GEOM_D3D)
    assert "(k > 0 && dot(gi[k].quat, gi[0].quat) < 0.0) ? -gi[k].quat : gi[k].quat" in src, "GEOM_FLIP cambio: re-portar GEOM_D3D"
    return GEOM_D3D


def arreglar_hlsl(hlsl, etapa):
    """Parche de SPIRV-Cross 1.4.363.0 (HLSL, GS): emite `gl_in[k].gl_Position` sin declarar `gl_in`; el valor esta en gl_PositionIn[k]."""
    if etapa == "geom":
        hlsl = re.sub(r"gl_in\[(\w+)\]\.gl_Position", lambda m: "gl_PositionIn[" + m.group(1) + "]", hlsl)
    return hlsl


def vulkanizar(src, d3d_flipy=True):
    """GLSL de GL -> GLSL para glslang -V:
      1. uniforms sueltos -> cbuffers std140 con el layout de RbCb* (tabla BLOQUES); arrays de bool/int/uint/float ->
         vec4 empaquetado (std140 daria 16 bytes por elemento) y vec2[] -> vec4[]; bool -> uint (un bool no tiene
         layout en un UBO); struct Luz con vec4 (= RbLuz);
      2. samplers -> layout(set=0, binding=N): sampler2D N -> t(N)/s(N) en HLSL (tex0..2 = t0..t2, luz_luts = t3);
      3. in/out de bloque y sueltos -> layout(location=...); gl_VertexID -> gl_VertexIndex;
      4. D3D: el VS emite y invertido (gl_Position.y = -y) para que la fila r de la imagen D3D sea la fila r de GL;
         la clip distance viaja tambien en el bloque V (cd) porque el GS no puede leer gl_ClipDistance."""
    if "layout(triangle_strip" in src:
        return _gs_d3d(src)
    for _ in range(3):   # varias declaraciones en una linea (aux): una por linea
        src = re.sub(r"(?m)^((?:uniform|in|out)\b[^\n/]*?;)[ \t]+(?=(?:uniform|in|out)\b)", r"\1\n", src)
    src = src.replace("vec4 view; }", "vec4 view; float cd; }")
    src = src.replace("gl_ClipDistance[0] = clip_on != 0 ? dot(pos, clip_coef) : 1.0;",
                      "vo.cd = clip_on != 0 ? dot(pos, clip_coef) : 1.0;\n    gl_ClipDistance[0] = vo.cd;")
    # struct Luz del uber: se sustituye por la version vec4 y se reescriben los accesos .xyz
    src = re.sub(r"struct Luz \{.*?\};", "", src, flags=re.S)
    src = re.sub(r"\bluz\[(\w+)\]\.(esp0|esp1|dif|amb|pos|spot)\b", r"luz[\1].\2.xyz", src)
    lineas, res, decl, tex, loc = src.split("\n"), [], {}, [0], {"in": 0, "out": 0}
    repack, punto = [], None
    for l in lineas:
        m = _DECL.match(l.strip()) if not l.startswith(" ") else None
        if m:
            if m["t"].startswith("sampler"):
                res.append(f"layout(set = 0, binding = {tex[0]}) uniform {m['t']} {m['n']};{m['r']}")
                tex[0] += 1
            else:
                decl[m["n"]] = (m["t"], m["c"], m["r"])
                if punto is None:
                    punto = len(res)
                    res.append("@@BLOQUES@@")
            continue
        if re.match(r"^(layout\(location = 0\) )?(in|out) V\s*\{", l) or re.match(r"^(in|out)\s+V\s*\{", l):
            if punto is None or "@@BLOQUES@@" not in res:
                pass
            res.append(f"layout(location = 0) {l}" if l.startswith(("in ", "out ")) else l)
            continue
        ms = re.match(r"^(in|out)\s+(?!gl_)(\w+)\s+(\w+)\s*;(.*)$", l)
        if ms:
            res.append(f"layout(location = {loc[ms.group(1)]}) {l}")
            loc[ms.group(1)] += 1
            continue
        res.append(l)
    # bloques: miembros de la tabla BLOQUES que existan en el fuente (todos los del uber; los del VS solo b0)
    usados = set()
    txt_bloques = []
    for _, b, orden in BLOQUES:
        miembros = []
        for n in orden:
            if n not in decl:
                continue
            usados.add(n)
            t, c, resto = decl[n]
            cb = ("cb_" + n) if n in _CHOCAN else n
            if n == "luz":
                miembros.append(f"    Luz {cb}[{c}];")
            elif c and t in _PACK4:
                miembros.append(f"    {_PACK4[t]} {cb}4[{(int(c) + 3) // 4}];")
                repack.append((n, t, "esc"))
            elif c and t == "vec2":
                miembros.append(f"    vec4 {cb}4[{(int(c) + 1) // 2}];")
                repack.append((n, t, "v2"))
            elif c and t in ("uvec4", "ivec4", "vec4"):
                miembros.append(f"    {t} {cb}[{c}];")
            elif t == "bool":
                miembros.append(f"    uint {cb};")
            else:
                miembros.append(f"    {t} {cb};")
        if miembros:
            if any("Luz " in m_ for m_ in miembros):
                txt_bloques.append(_LUZ_ESTRUCTURA)
            txt_bloques.append(f"layout(std140, set = 0, binding = {b}) uniform CB{b} {{")
            txt_bloques.extend(miembros)
            txt_bloques.append("};")
    sobran = set(decl) - usados
    assert not sobran, f"uniforms sin bloque en BLOQUES: {sorted(sobran)} (raster_uber.c cambio? actualizar la tabla)"
    if "@@BLOQUES@@" in res:
        # los uniforms de un shader auxiliar (no estan en BLOQUES) ya no pasan por aqui: ver rama siguiente
        pass
    macros = [f"#define {n} cb_{n}" for n in _CHOCAN if n in usados]
    if macros:
        txt_bloques.append("#ifndef ESPECIALIZADO")
        txt_bloques.extend(macros)
        txt_bloques.append("#endif")
    i = res.index("@@BLOQUES@@") if "@@BLOQUES@@" in res else None
    if i is not None:
        res[i:i + 1] = []
    # punto de insercion: antes de `in V` (fragmento: ya esta definido ESPECIALIZADO) o donde estaba el primer uniform
    ins = next((k for k, l in enumerate(res) if re.match(r"^layout\(location = 0\) in V\s*\{", l)), None)
    if ins is None:
        ins = i if i is not None else len(res)
    res[ins:ins] = txt_bloques
    txt = "\n".join(res)
    for n, t, kind in repack:
        cb = ("cb_" + n) if n in _CHOCAN else n
        if kind == "esc":
            ctor = " != 0u" if t == "bool" else ""
            txt = _indexar(txt, n, lambda e, cb=cb, ctor=ctor: f"({cb}4[({e}) >> 2][({e}) & 3]{ctor})")
        else:
            txt = _indexar(txt, n, lambda e, cb=cb: f"((({e}) & 1) == 0 ? {cb}4[({e}) >> 1].xy : {cb}4[({e}) >> 1].zw)")
    txt = txt.replace("gl_VertexID", "gl_VertexIndex")
    if d3d_flipy:
        txt = txt.replace("gl_Position = vec4(pos.x, pos.y, -pos.z, pos.w);", "gl_Position = vec4(pos.x, -pos.y, -pos.z, pos.w);")
    return txt
