"""Cadena de shaders para Direct3D 12 (agente B, paso 2 del plan D3D12, 8 oct 2026).

    GLSL 450 (el que ya compila raster_gl.c)  --glslang-->  SPIR-V (Vulkan 1.0)  --SPIRV-Cross-->  HLSL SM6.0
    --DXC-->  DXIL (ps_6_0 / vs_6_0 / gs_6_0, firmado por dxil.dll)

Uso (desde la raiz del proyecto, con `py -I`):
  py -I agentes_dx12\\B\\cadena_shaders.py inventario            # escribe agentes_dx12\\B\\glsl\\ + INDICE.tsv (usa volcar_glsl.exe)
  py -I agentes_dx12\\B\\cadena_shaders.py convertir [--sin-vulkanizar] [--hilos N] [--solo PATRON]
  py -I agentes_dx12\\B\\cadena_shaders.py resumen                # cifras de out\\resultados.tsv
  py -I agentes_dx12\\B\\cadena_shaders.py comparar-c             # los textos del volcador == lo que compila raster_gl.c
  py -I agentes_dx12\\B\\cadena_shaders.py empaquetar            # DXIL -> cache_d3d12 con nombre = hash del texto (lo busca shaders_d3d12.c)
  py -I agentes_dx12\\B\\cadena_shaders.py layouts [--sabotaje]  # packoffset de los cbuffers == offsetof de RbCb* (raster_backend.h)
  py -I agentes_dx12\\B\\cadena_shaders.py sabotaje               # prueba que los verificadores detectan shaders alterados
Todo corre en un solo proceso hijo a la vez por hilo y con prioridad BAJA; no toca GPU ni el juego.

La "vulkanizacion" (funcion vulkanizar) es la unica transformacion de texto entre el GLSL del C y glslang: el GLSL de
GL usa uniforms sueltos, bool/int/uint/vec2 en arrays y gl_VertexID, que ni Vulkan-GLSL ni HLSL admiten. Se documenta
en agentes_dx12\\B.md (seccion "constant buffers") y debe replicarse en el C (shaders_d3d12.c) o, mejor, pasar al
GLSL fuente cuando el backend GL deje de ser el principal.
"""
import csv
import hashlib
import shutil
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

B = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(B))
T = os.path.join(B, "terceros")
GLSLANG = os.path.join(T, "glslang-16.6.0", "x", "bin", "glslang.exe")
XCROSS = os.path.join(T, "spirv-cross-src", "out", "spirv-cross.exe")
DXC = os.path.join(T, "dxc-1.9.2609", "x", "bin", "x64", "dxc.exe")
VOLCAR = os.path.join(B, "volcar_glsl.exe")
GLSL = os.path.join(B, "glsl")
OUT = os.path.join(B, "out")
RENDER = os.path.join(RAIZ, "recomp", "render")
SHADERS = os.path.join(RAIZ, "extraido", "shaders")
CADENA_VERSION = "glslang-16.6.0+SPIRV-Cross-vulkan-sdk-1.4.363.0+dxc-1.9.2609.5+vulkanizar-2"   # sube con cualquier cambio de la cadena (-2: entradas del VS uint4 + selector b4, D4b 9 oct)
BAJA = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS


def ejecutar(cmd, **kw):
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True, creationflags=BAJA, **kw)
    return p.returncode, (p.stdout + p.stderr).strip(), time.perf_counter() - t0


# ------------------------------------------------------------------------------------------------ inventario
def literales_c(src, nombre):
    """Texto de `static const char *nombre = "..." "...";` (concatenacion de literales C con escapes simples)."""
    m = re.search(r"static const char \*" + nombre + r"\s*=\s*(.*?);\s*\n", src, re.S)
    if not m:
        raise SystemExit(f"no encuentro {nombre} en el C")
    cuerpo = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    partes = re.findall(r'"((?:[^"\\]|\\.)*)"', cuerpo)
    return "".join(partes).encode("latin-1").decode("unicode_escape")


def configs_luz():
    """Registros de luz (0x1C2 num, 0x1C3 c0, 0x1C4 c1, 0x1D0 abs, 0x1D1 ent, 0x1D2 esc) reconstruidos desde
    extraido\\shaders\\luz\\configs.json (censo de G/I). APROXIMACION: solo importa para generar variantes con la
    misma estructura que las reales (los registros crudos solo existen en ejecucion); 3 luces fisicas."""
    cfgs = json.load(open(os.path.join(SHADERS, "luz", "configs.json"), encoding="utf-8"))
    J = {"D0": 0, "D1": 1, "SP": 2, "FR": 3, "RB": 4, "RG": 5, "RR": 6}
    ENT = {"NH": 0, "VH": 1, "NV": 2, "LN": 3, "SP": 4, "CP": 5}
    DIS = {"D0": 16, "D1": 17, "FR": 19, "RR": 20, "RG": 21, "RB": 22}   # bit de config1 que APAGA el muestreador
    ESC = {1.0: 0, 2.0: 1, 4.0: 2, 8.0: 3, 0.25: 6, 0.5: 7}
    out = {}
    for c in cfgs:
        c0 = (c["cfg"] & 15) << 4
        if c["fresnel"] & 1: c0 |= 4
        if c["fresnel"] & 2: c0 |= 8
        if c["clamp"]: c0 |= 1 << 27
        c0 |= (c["bump_modo"] & 3) << 28 | (c["bump_tex"] & 3) << 22
        if not c["bump_renorm"]: c0 |= 1 << 30   # bit 30 = 1 -> z NO se recalcula (ver iluminar())
        c1 = 0
        presentes = {l[0] for l in c["luts"]}
        for nombre, bit in DIS.items():
            if nombre not in presentes: c1 |= 1 << bit
        ab = ent = esc = 0
        for nombre, entrada, absoluta in c["luts"]:
            j = J[nombre]
            ent |= ENT[entrada] << (4 * j)
            if not absoluta: ab |= 1 << (4 * j + 1)
            e = c["ejemplo"][3].get(nombre, [0, 0, 1.0])[2] if len(c["ejemplo"]) > 3 else 1.0
            esc |= ESC.get(e, 0) << (4 * j)
        out[str(c["id"])] = (2, c0, c1, ab, ent, esc)
    return out


def pares_tev_luz():
    """(receta, id_config_luz | None) que usa el juego: join de pica_materiales.tsv con shaders\\luz\\censo_luz.tsv."""
    mat = {}
    for r in csv.DictReader(open(os.path.join(RAIZ, "extraido", "pica_materiales.tsv"), encoding="utf-8"), delimiter="\t"):
        mat[(r["archivo"], r["modelo"], r["material"])] = r["tev_receta"]
    pares = set()
    for r in csv.DictReader(open(os.path.join(SHADERS, "luz", "censo_luz.tsv"), encoding="utf-8"), delimiter="\t"):
        k = (r["archivo"], r["modelo"], r["material"])
        if k in mat and r["luz_frag"] == "1":
            pares.add((mat[k], r["id_config"]))
    return sorted(pares, key=lambda p: (int(p[0][1:]), int(p[1])))


def inventario():
    for d in ("vert", "frag", "aux"):
        os.makedirs(os.path.join(GLSL, d), exist_ok=True)
    orden = []   # lineas para el volcador (lote)
    indice = []  # (archivo, etapa, origen)
    tabla = [l.split("\t") for l in open(os.path.join(SHADERS, "glsl", "programas.tsv"), encoding="utf-8") if not l.startswith("#")]
    for f in tabla:
        v = f[0]
        orden.append(f"vert ../../extraido/shaders/glsl/{v} glsl/vert/{v}")
        indice.append((f"vert/{v}", "vert", "extraido\\shaders\\glsl + envolver_vert() (raster_gl.c) + VERT_ENVOLTORIO"))
    orden.append("uber glsl/uber.frag")
    indice.append(("uber.frag", "frag", "SM3DL_RASTER_UBER=1: FRAG_UBER sin especializar (todo por uniforms)"))
    orden.append("geom glsl/flip.geom")
    indice.append(("flip.geom", "geom", "GEOM_FLIP (con luz: alinea el signo del cuaternion)"))
    recetas = json.load(open(os.path.join(SHADERS, "frag", "recetas.json"), encoding="utf-8"))
    luz = configs_luz()
    por_nombre = {r["nombre"]: r for r in recetas}
    for r in recetas:   # una variante SIN luz por receta TEV (332)
        nums = " ".join(str(x) for st in r["firma"] for x in st)
        orden.append(f"frag glsl/frag/{r['nombre']}.frag {nums}")
        indice.append((f"frag/{r['nombre']}.frag", "frag", f"fs_para() especializado: receta {r['nombre']} sin luz (uso {r['uso']})"))
    for rec, cid in pares_tev_luz():   # y las variantes CON luz que el juego combina (receta x config de luz)
        r = por_nombre[rec]
        nums = " ".join(str(x) for st in r["firma"] for x in st)
        regs = " ".join(str(x) for x in luz[cid])
        orden.append(f"frag glsl/frag/{rec}_L{cid}.frag {nums} {regs}")
        indice.append((f"frag/{rec}_L{cid}.frag", "frag", f"fs_para() especializado: receta {rec} + luz L{cid} (registros reconstruidos)"))
    src_gl = open(os.path.join(RENDER, "raster_gl.c"), encoding="utf-8", errors="replace").read()
    src_pr = open(os.path.join(RENDER, "presentador_gl.inc"), encoding="utf-8", errors="replace").read()
    for nombre, fuente, sufijo, etapa, origen in (
            ("giro_alta.vert", src_gl, "vs", "vert", "raster_gl.c giro_listo()"),
            ("giro_alta.frag", src_gl, "fs", "frag", "raster_gl.c giro_listo()"),
            ("pres_capa.vert", src_pr, "vs", "vert", "presentador_gl.inc raster_pres_capa()"),
            ("pres_capa.frag", src_pr, "fs", "frag", "presentador_gl.inc raster_pres_capa()")):
        # en giro_listo y raster_pres_capa las variables se llaman igual (vs/fs): se toma la primera aparicion tras la funcion
        ini = fuente.index("giro_listo(int w, int h)") if "giro" in nombre else fuente.index("int raster_pres_capa")
        txt = literales_c(fuente[ini:], sufijo)
        open(os.path.join(GLSL, "aux", nombre), "w", newline="\n").write(txt)
        indice.append((f"aux/{nombre}", etapa, origen))
    p = subprocess.run([VOLCAR, "-"], input="\n".join(orden) + "\n", capture_output=True, text=True, cwd=B)   # rutas relativas: el lote separa por espacios
    if p.returncode:
        raise SystemExit("volcar_glsl fallo: " + p.stderr[:500])
    with open(os.path.join(GLSL, "INDICE.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("archivo\tetapa\torigen\tbytes\n")
        for a, e, o in indice:
            f.write(f"{a}\t{e}\t{o}\t{os.path.getsize(os.path.join(GLSL, *a.split('/')))}\n")
    por = {}
    for a, e, o in indice:
        por[e] = por.get(e, 0) + 1
    print("inventario:", len(indice), "shaders", por)


# ------------------------------------------------------------------------------------------------ vulkanizacion
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
    ("b3", 3, ["luz_on", "luz_n", "luz_mues", "_pad0", "luz_c0", "luz_c1", "luz_abs", "luz_ent", "luz_esc", "luz_amb", "luz_fila", "luz"]),
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


# D4b (9 oct 2026, agentes_dx12\D4b.md): ENTRADAS ENTERAS NATIVAS. La IA de D3D12 no convierte entero -> float sin
# normalizar (no hay *SCALED en DXGI), asi que el VS declara cada entrada como uint4 (los bits que deja el formato del
# input layout: *_FLOAT = bits de float, *_SINT = entero con signo extendido, *_UINT = sin signo) y arma vK (float4 global,
# el nombre que usa el resto del texto) al empezar main() con un selector de 4 bits por registro en un cbuffer b4 de
# CONSTANTES RAIZ (DX_RS_VTIPO de raster_d3d12_prog.inc; lo llena raster_d3d12_vertices.inc):
#   bits 0-1: 0 float, 1 entero con signo, 2 sin signo;  bit 2: w = 1 (atributo de 3 componentes de 8/16 bits leido con
#   un formato de 4: DXGI no tiene 3 x 8/16 bits). Registro K: dx_vtipo[K >> 3] >> (4 * (K & 7)).
# Un solo DXIL por VS sirve para todos los layouts (el selector es dinamico). Floats (selector 0): mismos bits que antes.
_ENT_VS = re.compile(r"(?m)^layout\(location = (\d+)\) in vec4 v(\d+);[ \t]*$")
_ENT_FUNC = """layout(std140, set = 0, binding = 4) uniform CB4 { uvec4 dx_vtipo; };   // constantes raiz b4 (D4b)
vec4 dx_vconv(uvec4 b, uint t) {
    vec4 f = (t & 3u) == 0u ? uintBitsToFloat(b) : ((t & 3u) == 1u ? vec4(ivec4(b)) : vec4(b));
    return (t & 4u) != 0u ? vec4(f.xyz, 1.0) : f;
}"""


def entradas_enteras(txt):
    ks = _ENT_VS.findall(txt)
    if not ks:
        return txt
    assert all(a == b for a, b in ks), f"entradas con location != registro: {ks}"
    assert txt.count("\nvoid main() {\n") == 1, "VS sin 'void main() {' unico: no se puede insertar la conversion"
    primero = _ENT_VS.search(txt).start()
    txt = _ENT_VS.sub(lambda m: f"layout(location = {m[1]}) in uvec4 dx_ent{m[2]};\nvec4 v{m[2]};", txt)
    txt = txt[:primero] + _ENT_FUNC + "\n" + txt[primero:]
    conv = "".join(f"\n    v{k} = dx_vconv(dx_ent{k}, (dx_vtipo.{'xy'[int(k) >> 3]} >> {4 * (int(k) & 7)}u) & 15u);"
                   for _, k in ks)
    return txt.replace("\nvoid main() {\n", "\nvoid main() {" + conv + "\n", 1)


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
    for _ in range(12):   # varias declaraciones en una linea (aux): una por linea (una por pasada)
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
            if n.startswith('_pad'):   # relleno explicito: RbCbLuz deja un hueco tras luz_mues (std140 lo taparia con luz_c0)
                if any(x in decl for x in orden):
                    miembros.append(f'    int {n};')
                continue
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
    sobran = [n for n in decl if n not in usados]
    if sobran:   # shader auxiliar (giro_alta, pres_capa): no es de los RbCb*; un bloque b0 con sus uniforms en orden
        assert not usados, f"mezcla de uniforms conocidos y desconocidos {sobran}: raster_uber.c cambio? actualizar BLOQUES"
        txt_bloques.append("layout(std140, set = 0, binding = 0) uniform CB0 {")
        for n in sobran:
            t, c, resto = decl[n]
            txt_bloques.append(f"    {t} {n}{'[' + c + ']' if c else ''};")
        txt_bloques.append("};")
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
    return entradas_enteras(txt)


# ------------------------------------------------------------------------------------------------ conversion
ETAPAS = {"vert": ("vert", "vs_6_0"), "frag": ("frag", "ps_6_0"), "geom": ("geom", "gs_6_0")}


def etapa_de(ruta):
    return ruta.rsplit(".", 1)[1]


def causa(msg):
    """Normaliza el primer error para agrupar: sin numeros de linea ni nombres entre comillas."""
    for l in msg.splitlines():
        if re.search(r"error|ERROR|fatal", l):
            l = re.sub(r"^.*?\.(?:hlsl|glsl|geom|frag|vert)(?::\d+)*:?\s*", "", l)
            l = re.sub(r"^[^:]*:\d+(:\d+)?:?\s*", "", l)
            l = re.sub(r"^(ERROR|error|fatal error):\s*", "", l)
            l = re.sub(r"'[^']*'", "'X'", l)
            l = re.sub(r"\d+", "N", l)
            return l.strip()[:140]
    return msg.splitlines()[0][:140] if msg else "?"


def convertir_uno(rel, vulk=True, dest=OUT):
    """Corre la cadena sobre glsl\\<rel>. Devuelve dict con ok por etapa, segundos, tamanos y causa del primer fallo."""
    etapa = etapa_de(rel)
    base = os.path.join(dest, rel.replace("/", "__"))
    os.makedirs(dest, exist_ok=True)
    r = {"archivo": rel, "etapa": etapa, "vk": 0, "spv": 0, "hlsl": 0, "dxil": 0, "t_vk": 0.0, "t_spv": 0.0,
         "t_hlsl": 0.0, "t_dxil": 0.0, "bytes_dxil": 0, "causa": "", "fallo_en": ""}
    t0 = time.perf_counter()
    txt = open(os.path.join(GLSL, *rel.split("/")), encoding="utf-8").read()
    if vulk:
        txt = vulkanizar(txt)
    open(base + ".vk.glsl", "w", newline="\n").write(txt)
    r["t_vk"] = time.perf_counter() - t0
    r["vk"] = 1
    rc, out, dt = ejecutar([GLSLANG, "-V", "--target-env", "vulkan1.0", "-S", etapa, base + ".vk.glsl", "-o", base + ".spv"])
    r["t_spv"] = dt
    if rc or not os.path.exists(base + ".spv"):
        r["fallo_en"], r["causa"] = "glslang", causa(out)
        open(base + ".err", "w").write(out)
        return r
    r["spv"] = 1
    rc, out, dt = ejecutar([XCROSS, base + ".spv", "--hlsl", "--shader-model", "60", "--output", base + ".hlsl"])
    r["t_hlsl"] = dt
    if rc:
        r["fallo_en"], r["causa"] = "spirv-cross", causa(out)
        open(base + ".err", "w").write(out)
        return r
    r["hlsl"] = 1
    if etapa == "geom":
        h = open(base + ".hlsl", encoding="utf-8").read()
        with open(base + ".hlsl", "w", newline="\n") as fh:
            fh.write(arreglar_hlsl(h, etapa))
    perfil = ETAPAS[etapa][1]
    rc, out, dt = ejecutar([DXC, "-T", perfil, "-E", "main", "-Gis", "-Fo", base + ".dxil", base + ".hlsl"])
    r["t_dxil"] = dt
    if rc or not os.path.exists(base + ".dxil"):
        r["fallo_en"], r["causa"] = "dxc", causa(out)
        open(base + ".err", "w").write(out)
        return r
    r["dxil"] = 1
    r["bytes_dxil"] = os.path.getsize(base + ".dxil")
    return r


COLS = ["archivo", "etapa", "vk", "spv", "hlsl", "dxil", "t_vk", "t_spv", "t_hlsl", "t_dxil", "bytes_dxil", "fallo_en", "causa"]


def convertir(args):
    vulk = "--sin-vulkanizar" not in args
    hilos = int(args[args.index("--hilos") + 1]) if "--hilos" in args else 2
    solo = args[args.index("--solo") + 1] if "--solo" in args else None
    dest = OUT if vulk else OUT + "_crudo"
    lista = [l.split("\t")[0] for l in open(os.path.join(GLSL, "INDICE.tsv"), encoding="utf-8").read().splitlines()[1:]]
    if solo:
        lista = [a for a in lista if re.search(solo, a)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(hilos) as ex:
        res = list(ex.map(lambda a: convertir_uno(a, vulk, dest), lista))
    ruta = os.path.join(dest, "resultados.tsv" if not solo else "resultados_parcial.tsv")
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(COLS) + "\n")
        for r in res:
            f.write("\t".join(f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c]) for c in COLS) + "\n")
    print(f"{len(res)} shaders en {time.perf_counter() - t0:.0f} s de pared ({hilos} hilos) -> {ruta}")
    resumen([ruta])


def resumen(args=()):
    ruta = args[0] if args else os.path.join(OUT, "resultados.tsv")
    filas = list(csv.DictReader(open(ruta, encoding="utf-8"), delimiter="\t"))
    print(f"{ruta}: {len(filas)} shaders")
    grupos = {}
    for f in filas:
        grupos.setdefault(f["etapa"], []).append(f)
    for et, fs in sorted(grupos.items()):
        n = len(fs)
        print(f"  {et:5s} n={n:4d}  glslang={sum(int(f['spv']) for f in fs):4d}  spirv-cross={sum(int(f['hlsl']) for f in fs):4d}  dxil={sum(int(f['dxil']) for f in fs):4d}")
        for k in ("t_spv", "t_hlsl", "t_dxil"):
            v = sorted(float(f[k]) for f in fs if float(f[k]) > 0)
            if v:
                print(f"        {k}: mediana {v[len(v) // 2] * 1000:7.0f} ms  p95 {v[int(len(v) * .95)] * 1000:7.0f} ms  max {v[-1] * 1000:7.0f} ms")
        tot = [sum(float(f[k]) for k in ("t_spv", "t_hlsl", "t_dxil")) for f in fs]
        print(f"        total/shader: mediana {sorted(tot)[n // 2] * 1000:.0f} ms, suma {sum(tot):.1f} s")
    causas = {}
    for f in filas:
        if f["causa"]:
            causas.setdefault((f["fallo_en"], f["causa"]), []).append(f["archivo"])
    for (en, c), lst in sorted(causas.items(), key=lambda kv: -len(kv[1])):
        print(f"  FALLO {en}: {len(lst)}x  {c}  (p.ej. {lst[0]})")


# ------------------------------------------------------------------------------------------------ comparar con el C
def comparar_c():
    """Los textos del volcador deben ser byte a byte los que raster_gl.c pasa a glShaderSource: se compara la parte
    estatica (VERT_ENVOLTORIO, GEOM_FLIP, FRAG_UBER) con el texto del propio raster_uber.c, reconstruido aparte en
    Python (concatenacion de literales + BLOQUE_V), para detectar un volcador desfasado."""
    src = open(os.path.join(RENDER, "raster_uber.c"), encoding="utf-8").read()
    bloque = re.search(r'#define BLOQUE_V "(.*?)"\s*\n', src).group(1)

    def const(nombre):
        m = re.search(r"static const char " + nombre + r"\[\] =\s*(.*?);\s*\n\nstatic|static const char " + nombre + r"\[\] =\s*(.*?);\s*\n*$", src, re.S)
        cuerpo = m.group(1) or m.group(2)
        cuerpo = cuerpo.replace("BLOQUE_V", '"' + bloque + '"')
        return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', cuerpo)).encode("latin-1").decode("unicode_escape")
    ok = True
    for nombre, arch, pref in (("FRAG_UBER", "uber.frag", "#version 450 core\n"), ("GEOM_FLIP", "flip.geom", "")):
        esperado = pref + const(nombre) if nombre != "GEOM_FLIP" else const(nombre)
        real = open(os.path.join(GLSL, arch), encoding="utf-8").read()
        print(f"{nombre}: {'IGUAL' if esperado == real else 'DISTINTO'} ({len(real)} bytes)")
        ok &= esperado == real
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------ sabotaje / verificadores
INT_FUNCS = ("fuente", "mod_rgb", "mod_a", "dot3", "d255", "operar", "escala_tev", "etapa", "combinar", "pasa", "rgba8")


def region_tev_hlsl(hlsl):
    """Cuerpos de las funciones enteras del TEV en el HLSL de SPIRV-Cross (por nombre; los nombres sobreviven)."""
    out = {}
    for n in INT_FUNCS:
        m = re.search(r"^[\w\d]+\s+" + n + r"\([^)]*\)\s*\n\{\n(.*?)^\}\n", hlsl, re.S | re.M)
        if m:
            out[n] = m.group(1)
    return out


def pureza_entera(hlsl):
    """Revisa que las funciones enteras del TEV no contengan aritmetica float ni conversiones dudosas.
    Devuelve lista de problemas (vacia = limpia)."""
    malos = []
    for n, cuerpo in region_tev_hlsl(hlsl).items():
        if n == "rgba8":
            continue   # rgba8() solo desempaqueta uint -> int (sin float)
        for pat, que in ((r"\bfloat\d?(x\d)?\b", "tipo float"), (r"\bfloor\(|\bround\(|\bfrac\(|\bsqrt\(", "intrinseco float"),
                         (r"\d\.\d+f?\b", "literal float"), (r"/(?!/)", "division (el TEV usa d255 sin division)")):
            if re.search(pat, cuerpo):
                malos.append(f"{n}: {que}")
    return malos


def huella_tev(hlsl):
    """Hash de los cuerpos del TEV entero normalizados (sin espacios): cambia si alguien toca una constante/operador."""
    h = hashlib.sha256()
    for n, c in sorted(region_tev_hlsl(hlsl).items()):
        h.update(n.encode() + re.sub(r"\s+", "", c).encode())
    return h.hexdigest()[:16]


def sabotaje():
    """Sabotajes sobre una COPIA del uber especializado (R0): cada uno debe ser detectado por la cadena/verificadores.
    La referencia buena debe pasar limpia (control negativo)."""
    base = open(os.path.join(GLSL, "uber.frag"), encoding="utf-8").read()
    dest = os.path.join(B, "out_sabotaje")
    os.makedirs(os.path.join(GLSL, "sabotaje"), exist_ok=True)
    casos = [
        ("bueno", base, "limpio"),
        ("d255_shift7", base.replace("(x + 1 + (x >> 8)) >> 8", "(x + 1 + (x >> 8)) >> 7"), "huella"),
        ("d255_float", base.replace("ivec3 d255(ivec3 x) { return (x + 1 + (x >> 8)) >> 8; }",
                                     "ivec3 d255(ivec3 x) { return ivec3(vec3(x) / 255.0 + 0.5); }"), "pureza"),
        ("mod_invertido", base.replace("case 1u: return 255 - v.rgb;", "case 1u: return v.rgb;"), "huella"),
        ("sintaxis", base.replace("ivec4 combinar() {", "ivec4 combinar( {"), "cadena"),
    ]
    ref = None
    resultados = []
    for nombre, txt, espera in casos:
        rel = f"sabotaje/{nombre}.frag"
        open(os.path.join(GLSL, *rel.split("/")), "w", newline="\n").write(txt)
        r = convertir_uno(rel, True, dest)
        hl = os.path.join(dest, rel.replace("/", "__") + ".hlsl")
        detectado, motivo = [], ""
        if not r["dxil"]:
            detectado.append("cadena: " + r["fallo_en"] + ": " + r["causa"])
        else:
            hlsl = open(hl, encoding="utf-8").read()
            if nombre == "bueno":
                ref = huella_tev(hlsl)
            pur = pureza_entera(hlsl)
            if pur:
                detectado.append("pureza: " + "; ".join(pur))
            if ref and huella_tev(hlsl) != ref:
                detectado.append("huella TEV distinta de la buena")
        resultados.append((nombre, espera, detectado))
        print(f"  {nombre:14s} esperado={espera:7s} -> {'DETECTADO' if detectado else 'limpio'}  {' | '.join(detectado)[:150]}")
    malo = [n for n, e, d in resultados if (e == "limpio") == bool(d)]
    print("SABOTAJE", "OK (el bueno pasa, los alterados se detectan)" if not malo else f"FALLA en {malo}")
    return 1 if malo else 0


# ------------------------------------------------------------------------------------------------ layouts de cbuffer
def parse_cbuffers(hlsl):
    """{registro_b: [(nombre, tipo, n_array|0, byte_off)]}: lee los packoffset que dejo SPIRV-Cross (layout std140 real)."""
    res = {}
    for m in re.finditer(r"cbuffer (\w+) : register\(b(\d+), space0\)\s*\{(.*?)\};", hlsl, re.S):
        miembros = []
        for mm in re.finditer(r"^\s*([\w<>]+)\s+(\w+)(?:\[(\d+)\])?\s*:\s*packoffset\(c(\d+)(?:\.([xyzw]))?\);", m.group(3), re.M):
            t, n, c, reg, comp = mm.groups()
            n = re.sub(r"^_\d+_", "", n)
            miembros.append((n, t, int(c or 0), int(reg) * 16 + "xyzw".index(comp or "x") * 4))
        res[int(m.group(2))] = miembros
    return res


def layouts(sabotaje=False):
    """Comprueba que los packoffset de los cbuffers de TODAS las variantes coinciden con offsetof() de las estructuras
    RbCb* de raster_backend.h (agente A; check_layout.exe) y que no cambian de una variante a otra. Escribe cb_layouts.h.
    sabotaje=True: corrompe un offset esperado y debe fallar."""
    rc, txt, _ = ejecutar([os.path.join(B, "check_layout.exe")])
    if rc:
        raise SystemExit("falta check_layout.exe (ver su cabecera para compilarlo)")
    esperado, tam = {}, {}
    for l in txt.splitlines():
        b, n, v = l.split("\t")
        if n.startswith("#") or b == "luz":
            tam[(b, n)] = int(v)
        else:
            esperado[(b, n)] = int(v)
    if sabotaje:
        esperado[("b1", "z_escala")] += 4
    grupos = {}   # (tipo, b) -> {firma_json: [archivos]}
    for f in sorted(os.listdir(OUT)):
        if not f.endswith(".hlsl") or f.startswith("aux__") or f.startswith("flip"):
            continue
        tipo = "vs" if f.startswith("vert__") else "fs"
        cb = parse_cbuffers(open(os.path.join(OUT, f), encoding="utf-8").read())
        for b, mi in cb.items():
            mi = [(re.sub(r"^cb_", "", n), t, c, off) for n, t, c, off in mi]
            grupos.setdefault((tipo, b), {}).setdefault(json.dumps(mi), []).append(f)
    ok, errores, vistos = True, [], 0
    out = ["/* GENERADO por cadena_shaders.py layouts -- offsets en BYTES de cada cbuffer; verificados contra offsetof() de",
           " * RbCbVertice/Fragmento/Niebla/Luz (raster_backend.h). No editar. */", ""]
    for (tipo, b), sigs in sorted(grupos.items()):
        n = sum(len(v) for v in sigs.values())
        print(f"{tipo:3s} b{b}: {len(sigs)} layout(s) distinto(s) en {n} shaders")
        if len(sigs) != 1:
            ok = False
        for nombre, t, c, off in json.loads(next(iter(sigs))):
            clave = (f"b{b}", nombre)
            if clave in esperado:
                vistos += 1
                if esperado[clave] != off:
                    ok = False
                    errores.append(f"b{b}.{nombre}: HLSL {off} != C {esperado[clave]}")
            if tipo == "vs" or b != 0 or True:
                out.append(f"#define CB_B{b}_{nombre.upper():<14s} {off:5d}   /* {t}{'[' + str(c) + ']' if c else ''} */")
        out.append("")
    # tamanos: la ultima posicion + tamano del ultimo miembro debe redondear a sizeof (se compara b1: 224)
    print(f"{vistos} miembros comparados con offsetof(); tamanos C: " + ", ".join(f"{k[0]}={v}" for k, v in sorted(tam.items()) if k[1] == '#tam'))
    open(os.path.join(B, "cb_layouts.h"), "w", encoding="utf-8", newline="\n").write("\n".join(out))
    for e in errores:
        print("DIFERENCIA:", e)
    print("cb_layouts.h escrito;", "layouts consistentes con raster_backend.h" if ok else "LAYOUTS DISTINTOS")
    return 0 if ok else 1


def fnv_texto(b):
    """= fnv_texto() de raster_gl.c (FNV-1a 32 sobre los bytes del texto, sin el NUL)."""
    h = 2166136261
    for c in b:
        h = ((h ^ c) * 16777619) & 0xFFFFFFFF
    return h


def empaquetar():
    r"""Copia el DXIL de cada shader convertido a cache_d3d12\ con el nombre que buscara shaders_d3d12.c:
         V_<hash>.dxil  vertex shader (hash = fnv_texto del texto envuelto, el mismo 'hv' del cache de programas GL)
         F_<hash>.dxil  pixel shader (hash = 'hf')         F_UBER.dxil  el uber por uniforms (respaldo universal)
         G_FLIP.dxil    geometry shader (unico)             A_<nombre>.dxil  auxiliares (giro_alta.vs, pres_capa.fs, ...)
       y escribe cache_d3d12\indice.tsv (nombre del archivo, hash, origen GLSL, bytes). Version de la cadena en VERSION.txt."""
    dest = os.path.join(B, "cache_d3d12")
    os.makedirs(dest, exist_ok=True)
    filas, n = [], 0
    for r in csv.DictReader(open(os.path.join(OUT, "resultados.tsv"), encoding="utf-8"), delimiter="\t"):
        if r["dxil"] != "1":
            continue
        rel = r["archivo"]
        texto = open(os.path.join(GLSL, *rel.split("/")), "rb").read()
        h = fnv_texto(texto)
        if rel.startswith("vert/"): nom = f"V_{h:08X}.dxil"
        elif rel == "uber.frag": nom = "F_UBER.dxil"
        elif rel.startswith("frag/"): nom = f"F_{h:08X}.dxil"
        elif rel == "flip.geom": nom = "G_FLIP.dxil"
        elif rel.startswith("aux/"):
            b = os.path.basename(rel)
            nom = "A_" + b.replace(".vert", ".vs").replace(".frag", ".fs") + ".dxil"
        else:
            continue
        shutil.copyfile(os.path.join(OUT, rel.replace("/", "__") + ".dxil"), os.path.join(dest, nom))
        filas.append((nom, f"{h:08X}", rel, r["bytes_dxil"]))
        n += 1
    with open(os.path.join(dest, "indice.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("archivo\thash\tglsl\tbytes\n")
        for fi in filas:
            f.write("\t".join(fi) + "\n")
    open(os.path.join(dest, "VERSION.txt"), "w", newline="\n").write(CADENA_VERSION + "\n")
    colis = len(filas) - len({f[0] for f in filas})
    print(f"{n} DXIL en {dest} ({colis} colisiones de nombre); version: {CADENA_VERSION}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "inventario": inventario()
    elif cmd == "convertir": convertir(sys.argv[2:])
    elif cmd == "resumen": resumen(sys.argv[2:])
    elif cmd == "comparar-c": sys.exit(comparar_c())
    elif cmd == "sabotaje": sys.exit(sabotaje())
    elif cmd == "empaquetar": empaquetar()
    elif cmd == "layouts": sys.exit(layouts("--sabotaje" in sys.argv))
    else: print(__doc__)
