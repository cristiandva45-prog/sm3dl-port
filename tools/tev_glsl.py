"""Generador de fragment shaders GLSL 3.3 a partir de las recetas TEV (combinador de 6 etapas del PICA200).

Uso:
  py -I tools\\tev_glsl.py            # censa los materiales (pica_cmd) y escribe extraido\\shaders\\frag\\R<n>.frag
  tools\\.venv_gl\\Scripts\\python.exe tools\\tev_glsl.py --validar   # compila cada .frag en el driver real

Receta = las 6 etapas sin el color constante (pica_cmd.firma_tev); numeradas igual que el censo (R0 = la mas usada).
Lo que varia por material entra como uniform: tev_const[6] (0x0C3..), tev_buffer_color (0x0FD) y tev_update
(bits 8-15 de 0x0E0: actualizacion del buffer del combinador por etapa).
Semantica (3dbrew "GPU/Internal Registers" TEXENV; Azahar regs_texturing.h como lectura):
  fuentes 0 color_vtx, 1 luz primaria, 2 luz secundaria, 3-5 tex0-2, 0xD buffer previo, 0xE constante, 0xF previo
  operandos rgb: color, 1-color, a, 1-a, r, 1-r, g, 1-g, b, 1-b ; alfa: a, 1-a, r, 1-r, g, 1-g, b, 1-b
  combinadores: REPLACE, MOD, ADD, ADDS (a+b-.5), LERP (a*c+b*(1-c)), SUB, DOT3_RGB, DOT3_RGBA, MULADD (a*b+c),
  ADDMUL (min(a+b,1)*c); escala 1/2/4; resultado acotado a [0,1].
Precision y casos borde como el rasterizador por software de Azahar (verificado por tools/probar_tev.py contra
tools/tev_ref.py): cada operacion se trunca a u8 antes de la escala (q8), ADDS resta 128/255, DOT3 con la formula
entera por canal; la etapa 0 lee el buffer = 0 y sus fuentes de color 1-2 "previo" pasan a ser la fuente 3; una etapa
"paso" con escala != 1 se calcula, y aunque se salte sigue actualizando el buffer del combinador.
Fuera por ahora: fragment lighting real (frag_primario/frag_secundario entran como uniforms), alpha test, niebla,
tex3/procedural, blend (es estado fijo de la API, no del shader).
"""
import collections
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(RAIZ, "tools"))  # al final: tools\dis.py tapa el modulo estandar 'dis'
SALIDA = os.path.join(RAIZ, "extraido", "shaders", "frag")

FUENTE = {0: "vtx_color", 1: "frag_primario", 2: "frag_secundario", 3: "t0", 4: "t1", 5: "t2", 6: "t3",
          0xD: "buf_prev", 0xE: "tev_const[{k}]", 0xF: "prev"}
OP_RGB = {0: "{s}.rgb", 1: "(vec3(1.0) - {s}.rgb)", 2: "{s}.aaa", 3: "(vec3(1.0) - {s}.aaa)", 4: "{s}.rrr",
          5: "(vec3(1.0) - {s}.rrr)", 8: "{s}.ggg", 9: "(vec3(1.0) - {s}.ggg)", 0xC: "{s}.bbb",
          0xD: "(vec3(1.0) - {s}.bbb)"}
OP_A = {0: "{s}.a", 1: "(1.0 - {s}.a)", 2: "{s}.r", 3: "(1.0 - {s}.r)", 4: "{s}.g", 5: "(1.0 - {s}.g)",
        6: "{s}.b", 7: "(1.0 - {s}.b)"}
ESCALA = {0: "1.0", 1: "2.0", 2: "4.0", 3: "1.0"}


class SinSoporte(Exception):
    pass


def fuente(n, k):
    if n not in FUENTE:
        raise SinSoporte(f"fuente {n:X}")
    if n == 6:
        raise SinSoporte("tex3 (procedural)")
    return FUENTE[n].format(k=k)


def combinar(c, a, b, cc, rgb):
    """Expresion del combinador c sobre los argumentos ya modificados."""
    uno = "vec3(1.0)" if rgb else "1.0"
    medio = "vec3(128.0 / 255.0)" if rgb else (128.0 / 255.0).__repr__()
    if c == 0:
        return a
    if c == 1:
        return f"{a} * {b}"
    if c == 2:
        return f"{a} + {b}"
    if c == 3:
        return f"{a} + {b} - {medio}"  # medio = 128/255, como el hardware (no 0.5)
    if c == 4:
        return f"{a} * {cc} + {b} * ({uno} - {cc})"
    if c == 5:
        return f"{a} - {b}"
    if c in (6, 7):
        if not rgb:
            raise SinSoporte("dot3 en alfa")
        return f"dot3_u8({a}, {b})"
    if c == 8:
        return f"{a} * {b} + {cc}"
    if c == 9:
        return f"min({a} + {b}, {uno}) * {cc}"
    raise SinSoporte(f"combinador {c}")


def etapa(k, s, o, c, e, L):
    srgb = [(s >> sh) & 0xF for sh in (0, 4, 8)]
    sa = [(s >> sh) & 0xF for sh in (16, 20, 24)]
    orgb = [(o >> sh) & 0xF for sh in (0, 4, 8)]
    oa = [(o >> sh) & 0x7 for sh in (12, 16, 20)]
    crgb, ca = c & 0xF, (c >> 16) & 0xF
    if k == 0:  # etapa 0: las fuentes de color 1 y 2 "previo" leen la fuente 3 (Azahar sw_rasterizer)
        srgb = [srgb[2] if (j < 2 and srgb[j] == 0xF) else srgb[j] for j in range(3)]
    argr = []
    for j in range(3):
        if orgb[j] not in OP_RGB:
            raise SinSoporte(f"operando rgb {orgb[j]}")
        argr.append(OP_RGB[orgb[j]].format(s=fuente(srgb[j], k)))
    arga = [OP_A[oa[j]].format(s=fuente(sa[j], k)) for j in range(3)]
    L.append(f"    // etapa {k}")
    L.append(f"    vec3 r{k} = clamp(q8({combinar(crgb, *argr, True)}) * {ESCALA[e & 3]}, 0.0, 1.0);")
    if crgb == 7:  # DOT3_RGBA: el alfa sale del mismo producto
        L.append(f"    float a{k} = r{k}.r;")
    else:
        L.append(f"    float a{k} = clamp(q8({combinar(ca, *arga, False)}) * {ESCALA[(e >> 16) & 3]}, 0.0, 1.0);")
    # buffer del combinador: la etapa k lee el valor que dejo la k-1 (las etapas 0-3 pueden actualizarlo)
    L.append(f"    buf_prev = buf_sig;")
    if k < 4:
        L.append(f"    if ((tev_update & {1 << (8 + k)}u) != 0u) buf_sig.rgb = r{k};")
        L.append(f"    if ((tev_update & {1 << (12 + k)}u) != 0u) buf_sig.a = a{k};")
    L.append(f"    prev = vec4(r{k}, a{k});")


def generar(firma, nombre, uso, ejemplo):
    L = ["#version 330 core",
         f"// GENERADO por tools/tev_glsl.py: receta {nombre} ({uso} materiales, p. ej. {ejemplo}). No editar.",
         "in vec4 vtx_color;", "in vec2 texcoord0;", "in vec2 texcoord1;", "in vec2 texcoord2;",
         "uniform sampler2D tex0;", "uniform sampler2D tex1;", "uniform sampler2D tex2;",
         "uniform vec4 frag_primario;    // TODO: fragment lighting por fragmento",
         "uniform vec4 frag_secundario;",
         "uniform vec4 tev_const[6];", "uniform vec4 tev_buffer_color;", "uniform uint tev_update;",
         "out vec4 color;", "",
         "// u8 truncado de una operacion del combinador (el +1e-3 absorbe el error de float; el paso real es 1/255)",
         "float q8(float x) { return floor(clamp(x, 0.0, 1.0) * 255.0 + 1e-3) / 255.0; }",
         "vec3 q8(vec3 x) { return floor(clamp(x, vec3(0.0), vec3(1.0)) * 255.0 + 1e-3) / 255.0; }",
         "// DOT3 entero por canal: ((2a-255)(2b-255)+128)/256 truncado hacia 0, suma acotada a 0..255",
         "vec3 dot3_u8(vec3 a, vec3 b) {",
         "    vec3 p = (round(a * 255.0) * 2.0 - 255.0) * (round(b * 255.0) * 2.0 - 255.0) + 128.0;",
         "    vec3 t = trunc(p / 256.0);",
         "    return vec3(clamp(t.r + t.g + t.b, 0.0, 255.0) / 255.0);",
         "}", "", "void main() {",
         "    vec4 t0 = texture(tex0, texcoord0);", "    vec4 t1 = texture(tex1, texcoord1);",
         "    vec4 t2 = texture(tex2, texcoord2);",
         "    vec4 prev = vec4(0.0);", "    vec4 buf_sig = tev_buffer_color;",
         "    vec4 buf_prev = vec4(0.0);  // la etapa 0 lee 0; tev_buffer_color entra desde la etapa 1"]
    import pica_cmd
    for k, (s, o, c, e) in enumerate(firma):
        # en la etapa 0 "previo" de la fuente de color 1 es la fuente 3: solo es paso si la 3 tambien es previo
        if (pica_cmd.tev_es_paso(s, o, c) and (e & 3) in (0, 3) and ((e >> 16) & 3) in (0, 3)
                and not (k == 0 and (s >> 8) & 0xF != 0xF)):
            L.append(f"    // etapa {k}: pasa (previo sin cambios; el buffer se actualiza igual)")
            L.append(f"    buf_prev = buf_sig;")
            if k < 4:
                L.append(f"    if ((tev_update & {1 << (8 + k)}u) != 0u) buf_sig.rgb = prev.rgb;")
                L.append(f"    if ((tev_update & {1 << (12 + k)}u) != 0u) buf_sig.a = prev.a;")
            continue
        etapa(k, s, o, c, e, L)
    L += ["    color = prev;", "}"]
    return "\n".join(L) + "\n"


def recetas():
    """[(firma, uso, ejemplo)] ordenadas como el censo de pica_cmd (R0 = la mas usada)."""
    from concurrent.futures import ProcessPoolExecutor
    import pica_cmd
    raiz = os.path.join(RAIZ, "extraido", "romfs")
    rutas = [os.path.join(c, a) for sub in ("ObjectData", "StageData") for c, _, arch in
             os.walk(os.path.join(raiz, sub)) for a in arch if a.endswith(".szs")]
    firmas, ej = collections.Counter(), {}
    with ProcessPoolExecutor() as ex:
        for filas in ex.map(pica_cmd._censo_archivo, rutas, chunksize=8):
            for arch, nmod, nmat, st, n in filas:
                if nmod == "ERROR":
                    continue
                f = pica_cmd.firma_tev(st)
                firmas[f] += 1
                ej.setdefault(f, f"{arch}/{nmat}")
    return [(f, n, ej[f]) for f, n in firmas.most_common()]


def validar():
    import glfw
    from OpenGL import GL
    if not glfw.init():
        sys.exit("glfw no inicia")
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    w = glfw.create_window(64, 64, "tev", None, None)
    glfw.make_context_current(w)
    print("driver:", GL.glGetString(GL.GL_RENDERER).decode(), GL.glGetString(GL.GL_VERSION).decode())
    vert = ("#version 330 core\nlayout(location=0) in vec4 p;\nout vec4 vtx_color;\nout vec2 texcoord0;\n"
            "out vec2 texcoord1;\nout vec2 texcoord2;\nvoid main(){vtx_color=p;texcoord0=p.xy;texcoord1=p.yz;"
            "texcoord2=p.zw;gl_Position=p;}\n")
    ok = mal = 0
    for f in sorted(os.listdir(SALIDA)):
        if not f.endswith(".frag"):
            continue
        prog = GL.glCreateProgram()
        logs = []
        for tipo, src in ((GL.GL_VERTEX_SHADER, vert), (GL.GL_FRAGMENT_SHADER, open(os.path.join(SALIDA, f)).read())):
            s = GL.glCreateShader(tipo)
            GL.glShaderSource(s, src)
            GL.glCompileShader(s)
            if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
                logs.append(GL.glGetShaderInfoLog(s))
            GL.glAttachShader(prog, s)
        GL.glLinkProgram(prog)
        if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
            logs.append(GL.glGetProgramInfoLog(prog))
        if logs:
            mal += 1
            print(f, "FALLA", logs[0][:300])
        else:
            ok += 1
    print(f"compilan y enlazan: {ok}/{ok + mal}")
    glfw.terminate()
    sys.exit(0 if not mal else 1)


def main():
    if "--validar" in sys.argv:
        validar()
        return
    os.makedirs(SALIDA, exist_ok=True)
    n = sin = 0
    motivos = collections.Counter()
    todas = recetas()
    import json  # las firmas, para que tools/probar_tev.py no tenga que repetir el censo
    json.dump([{"nombre": f"R{k}", "firma": f, "uso": uso, "ejemplo": ej} for k, (f, uso, ej) in enumerate(todas)],
              open(os.path.join(SALIDA, "recetas.json"), "w", encoding="utf-8"), indent=0)
    for k, (f, uso, ej) in enumerate(todas):
        try:
            txt = generar(f, f"R{k}", uso, ej)
        except SinSoporte as ex:
            sin += 1
            motivos[str(ex)] += uso
            continue
        open(os.path.join(SALIDA, f"R{k}.frag"), "w", encoding="utf-8").write(txt)
        n += 1
    print(f"recetas generadas: {n}, sin soporte: {sin}", dict(motivos))


if __name__ == "__main__":
    main()
