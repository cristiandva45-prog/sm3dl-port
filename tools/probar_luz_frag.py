"""Verificador diferencial en GPU del fragment lighting: L<id>.glsl (luz_frag_glsl.py) contra luz_frag_ref.py.

Uso: tools\\.venv_gl\\Scripts\\python.exe tools\\probar_luz_frag.py [--sabotaje N] [-k JUEGOS] [-n PIXELES]
  Para cada una de las configuraciones de configs.json: K juegos de luces al azar (0..4 luces, direccionales y
  posicionales, una o dos caras, atenuacion por distancia y spot con LUTs al azar) x N fragmentos al azar
  (cuaternion sin normalizar, vista, 3 texeles para el bump). LUTs del material: las REALES (luts.json) del
  material de ejemplo, con sus escalas. Entradas en una textura RGBA32F, salidas en 2 adjuntos RGBA32F.
  Criterio: diferencia <= 1 LSB (u8) por canal (la GPU y Python pueden caer a lados distintos de un floor)
  Y >= 99,5 % de canales exactos (si no, un redondeo en vez de truncado pasaria).
  Ademas: prueba del geometry shader flip_quat (triangulo con cuaterniones de signo opuesto).
  --sabotaje N rompe UNA cosa (ver SABOTAJES) y la prueba DEBE fallar.
"""
import ctypes
import json
import math
import os
import random
import struct
import sys

import glfw
from OpenGL import GL

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
import luz_frag_glsl as G  # noqa: E402
import luz_frag_ref as R  # noqa: E402

LUTS = G.LUTS
SABOTAJES = {
    1: ("LUT con signo sin interpolar", "snip", "return luz_lut(fila, i, x * 128.0 - f);", "return luz_lut(fila, i, 0.0);"),
    2: ("Fresnel en la PRIMERA luz", "snip", "if (i == luz_num - 1)", "if (i == 0)"),
    3: ("rotacion por cuaternion con w negado", "snip", "cross(q.xyz, v) + q.w * v", "cross(q.xyz, v) - q.w * v"),
    4: ("factor geometrico sin min(.,1)", "snip", "min(nl / g, 1.0)", "nl / g"),
    5: ("indice con signo sin envolver (i<0 -> 0)", "snip", "if (i < 0) i += 256;", "if (i < 0) i = 0;"),
    6: ("vector medio sin normalizar", "snip", "vec3 hn = normalize(h);", "vec3 hn = h;"),
    7: ("bump sin renormalizar z", "snip", "pert.z = sqrt(max(1.0 - dot(pert.xy, pert.xy), 0.0));", ""),
    8: ("salida redondeada en vez de truncada", "snip", "* 255.0 + 1e-3) / 255.0; }", "* 255.0 + 0.5) / 255.0; }"),
    9: ("spot ignorado", "snip", "sp = luz_sp_escala * (", "sp = 1.0 + 0.0 * ("),
    10: ("decodificar LUT ignorando el signo de la diferencia", "lut", None, None),
    11: ("sin geometry shader de flip de cuaterniones", "geom", None, None),
    12: ("atenuacion por distancia con la distancia a la mitad", "snip", "L.da_escala * dist", "L.da_escala * dist * 0.5"),
}

VERT = """#version 330 core
void main() { vec2 p = vec2((gl_VertexID & 1) * 4.0 - 1.0, (gl_VertexID >> 1) * 4.0 - 1.0); gl_Position = vec4(p, 0.0, 1.0); }
"""
FRAG = """#version 330 core
{snip}
uniform sampler2D entradas;
layout(location = 0) out vec4 o_pri;
layout(location = 1) out vec4 o_sec;
void main() {{
    int x = int(gl_FragCoord.x);
    vec4 nq = texelFetch(entradas, ivec2(x, 0), 0);
    vec3 vi = texelFetch(entradas, ivec2(x, 1), 0).xyz;
    luz_frag(nq, vi, texelFetch(entradas, ivec2(x, 2), 0), texelFetch(entradas, ivec2(x, 3), 0),
             texelFetch(entradas, ivec2(x, 4), 0), o_pri, o_sec);
}}
"""


def compilar(vs, fs, gs=None):
    p = GL.glCreateProgram()
    for tipo, src in ((GL.GL_VERTEX_SHADER, vs), (GL.GL_FRAGMENT_SHADER, fs), (GL.GL_GEOMETRY_SHADER, gs)):
        if src is None:
            continue
        s = GL.glCreateShader(tipo)
        GL.glShaderSource(s, src)
        GL.glCompileShader(s)
        if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
            raise RuntimeError(GL.glGetShaderInfoLog(s).decode(errors="replace")[:1500])
        GL.glAttachShader(p, s)
    GL.glLinkProgram(p)
    if not GL.glGetProgramiv(p, GL.GL_LINK_STATUS):
        raise RuntimeError(GL.glGetProgramInfoLog(p).decode(errors="replace")[:1500])
    return p


def tex_float(ancho, alto, filas_rgba, unidad, comps=4):
    t = GL.glGenTextures(1)
    GL.glActiveTexture(GL.GL_TEXTURE0 + unidad)
    GL.glBindTexture(GL.GL_TEXTURE_2D, t)
    for par in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
        GL.glTexParameteri(GL.GL_TEXTURE_2D, par, GL.GL_NEAREST)
    plano = [v for fila in filas_rgba for px in fila for v in px]
    datos = struct.pack(f"<{len(plano)}f", *plano)
    fmt_i, fmt = (GL.GL_RGBA32F, GL.GL_RGBA) if comps == 4 else (GL.GL_RG32F, GL.GL_RG)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, fmt_i, ancho, alto, 0, fmt, GL.GL_FLOAT, datos)
    return t


def decodificar(cruda, sabotaje):
    """Lado GPU: palabra PICA -> (valor, dif) para la textura. Es el mismo layout que luz_frag_mtob.lut_float."""
    import luz_frag_mtob  # noqa: E402 (solo para este lado; la referencia decodifica por su cuenta)
    v, d = luz_frag_mtob.lut_float([cruda])[0]
    return (v, abs(d)) if sabotaje == 10 else (v, d)


def u(p, nombre, *v, i=False):
    loc = GL.glGetUniformLocation(p, nombre)
    if loc < 0:
        return
    if i:
        GL.glUniform1i(loc, int(v[0]))
    elif len(v) == 1:
        GL.glUniform1f(loc, float(v[0]))
    else:
        GL.glUniform3f(loc, *map(float, v))


def unit(rng):
    while True:
        v = [rng.uniform(-1, 1) for _ in range(3)]
        n = math.sqrt(sum(k * k for k in v))
        if 0.1 < n <= 1:
            return [k / n for k in v]


def juego_luces(rng, n):
    luces = []
    for _ in range(n):
        dirl = rng.random() < 0.5
        luces.append({
            "especular0": [rng.random() for _ in range(3)], "especular1": [rng.random() for _ in range(3)],
            "difusa": [rng.random() for _ in range(3)], "ambiente": [rng.random() * 0.3 for _ in range(3)],
            "posicion": unit(rng) if dirl else [rng.uniform(-30, 30) for _ in range(3)],
            "spot_dir": unit(rng), "direccional": dirl, "dos_caras": rng.random() < 0.3,
            "usa_da": rng.random() < 0.5, "usa_sp": rng.random() < 0.5,
            "da_escala": rng.uniform(0.005, 0.05), "da_sesgo": rng.uniform(-0.1, 0.2),
            "da": [rng.getrandbits(24) for _ in range(256)], "sp": [rng.getrandbits(24) for _ in range(256)]})
    return luces


def fragmentos(rng, n):
    out = []
    for _ in range(n):
        q = unit(rng) + [rng.uniform(-1, 1)]
        e = rng.uniform(0.3, 3.0)
        q = [k * e for k in q]
        vista = [k * rng.uniform(0.5, 60) for k in unit(rng)]
        tex = [[rng.randint(0, 255) / 255.0 for _ in range(4)] for _ in range(3)]
        out.append((q, vista, tex))
    return out


def correr_config(c, lutdb, rng, k_juegos, npx, sab, fbo, vao):
    snip = G.snippet(c)
    if sab and SABOTAJES[sab][1] == "snip":
        _, _, a, b = SABOTAJES[sab]
        snip = snip.replace(a, b)
    p = compilar(VERT, FRAG.format(snip=snip))
    GL.glUseProgram(p)
    ej = c["ejemplo"][3]
    malos = exactos = total = maxd = 0
    for j in range(k_juegos):
        nl = 0 if j == 0 and k_juegos > 2 else rng.randint(1, 4)
        luces = juego_luces(rng, nl)
        est = {"luces": luces, "ambiente_global": [rng.random() * 0.2 for _ in range(3)],
               "luts": {}, "escalas": {}, "sp": (rng.choice(R.ENTRADAS), rng.random() < 0.5,
                                                 rng.choice([0.25, 0.5, 1.0, 2.0, 4.0, 8.0]))}
        filas = []  # filas de la textura de LUT
        fila_mat = {}
        for n, _, _ in c["luts"]:
            tabla, samp, esc = ej[n]
            filas.append(lutdb[f"{tabla}/{samp}"][1])
            fila_mat[n] = len(filas) - 1
            est["luts"][n] = filas[-1]
            est["escalas"][n] = esc
        for i, L in enumerate(luces):
            filas.append(L["da"])
            L["_da"] = len(filas) - 1
            filas.append(L["sp"])
            L["_sp"] = len(filas) - 1
        if not filas:
            filas = [[0] * 256]
        tl = tex_float(256, len(filas), [[(*decodificar(w, sab), 0.0, 0.0) for w in f] for f in filas], 0)
        u(p, "luz_luts", 0, i=True)
        for k, n in enumerate(LUTS):
            u(p, f"luz_lut_fila[{k}]", fila_mat.get(n, 0), i=True)
            u(p, f"luz_lut_escala[{k}]", est["escalas"].get(n, 1.0))
        u(p, "luz_num", nl, i=True)
        u(p, "luz_ambiente_global", *est["ambiente_global"])
        u(p, "luz_sp_entrada", R.ENTRADAS.index(est["sp"][0]), i=True)
        u(p, "luz_sp_abs", est["sp"][1], i=True)
        u(p, "luz_sp_escala", est["sp"][2])
        for i, L in enumerate(luces):
            b = f"luz_fuente[{i}]."
            for campo in ("especular0", "especular1", "difusa", "ambiente", "posicion", "spot_dir"):
                u(p, b + campo, *L[campo])
            u(p, b + "da_escala", L["da_escala"])
            u(p, b + "da_sesgo", L["da_sesgo"])
            u(p, b + "da_fila", L["_da"], i=True)
            u(p, b + "sp_fila", L["_sp"], i=True)
            for campo in ("direccional", "dos_caras", "usa_da", "usa_sp"):
                u(p, b + campo, L[campo], i=True)
        frs = fragmentos(rng, npx)
        te = tex_float(npx, 5, [[f[0] for f in frs], [f[1] + [0.0] for f in frs], [f[2][0] for f in frs],
                                [f[2][1] for f in frs], [f[2][2] for f in frs]], 1)
        u(p, "entradas", 1, i=True)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        GL.glViewport(0, 0, npx, 1)
        GL.glBindVertexArray(vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        sal = []
        for att in (0, 1):
            GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0 + att)
            crudo = GL.glReadPixels(0, 0, npx, 1, GL.GL_RGBA, GL.GL_FLOAT)
            crudo = bytes(crudo) if not isinstance(crudo, bytes) else crudo
            sal.append(struct.unpack(f"<{4 * npx}f", crudo))
        GL.glDeleteTextures([tl, te])
        for x, (q, vista, tex) in enumerate(frs):
            ref = R.iluminar(c, est, q, vista, tex)
            for att in (0, 1):
                for ch in range(4):
                    d = abs(round(sal[att][4 * x + ch] * 255) - round(ref[att][ch] * 255))
                    maxd = max(maxd, d)
                    total += 1
                    exactos += d == 0
                    malos += d > 1
    GL.glDeleteProgram(p)
    return malos, exactos, total, maxd


GVERT = """#version 330 core
layout(location = 0) in vec2 pos;
layout(location = 1) in vec4 quat;
layout(location = 2) in vec4 vis;
out vec4 {p1};
out vec4 {p2};
void main() {{ gl_Position = vec4(pos, 0.0, 1.0); {p1} = quat; {p2} = vis; }}
"""
GFRAG = """#version 330 core
{snip}
in vec4 pica_o1;
in vec4 pica_o2;
layout(location = 0) out vec4 o_pri;
layout(location = 1) out vec4 o_sec;
void main() {{ luz_frag(pica_o1, pica_o2.xyz, vec4(0.5), vec4(0.5), vec4(0.5), o_pri, o_sec); }}
"""


def prueba_flip(c, rng, sab, fbo, vao_dummy):
    """Triangulo con q1 = -q0' y q2 = -q0'': sin alinear signos, la interpolacion colapsa la normal."""
    con_gs = sab != 11
    p1, p2 = ("g_pica_o1", "g_pica_o2") if con_gs else ("pica_o1", "pica_o2")
    gs = G.geom_flip(salidas=("pica_o1", "pica_o2"), quat="pica_o1") if con_gs else None
    p = compilar(GVERT.format(p1=p1, p2=p2), GFRAG.format(snip=G.snippet(c)), gs)
    GL.glUseProgram(p)
    W = 16
    pos = [(-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0)]
    q0 = unit(rng) + [0.6]
    qs = [q0, [-(k + rng.uniform(-0.2, 0.2)) for k in q0], [-(k + rng.uniform(-0.2, 0.2)) for k in q0]]
    vs = [[0.0, 0.0, 5.0, 0.0], [1.0, 0.0, 6.0, 0.0], [0.0, 1.0, 4.0, 0.0]]
    datos = []
    for k in range(3):
        datos += list(pos[k]) + qs[k] + vs[k]
    vao = GL.glGenVertexArrays(1)
    GL.glBindVertexArray(vao)
    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, struct.pack(f"<{len(datos)}f", *datos), GL.GL_STATIC_DRAW)
    for loc, n, off in ((0, 2, 0), (1, 4, 8), (2, 4, 24)):
        GL.glEnableVertexAttribArray(loc)
        GL.glVertexAttribPointer(loc, n, GL.GL_FLOAT, GL.GL_FALSE, 40, ctypes.c_void_p(off))
    luz = juego_luces(rng, 1)[0]
    luz.update({"usa_da": False, "usa_sp": False, "direccional": True, "posicion": [0.0, 0.0, 1.0]})
    filas = []
    est = {"luces": [luz], "ambiente_global": [0.0, 0.0, 0.0], "luts": {}, "escalas": {}, "sp": ("NH", True, 1.0)}
    for k, (n, _, _) in enumerate(c["luts"]):
        rampa = [(min(i, 4095) & 0xFFF) for i in range(0, 4096, 16)]  # LUT suave (rampa) para ver la normal
        filas.append(rampa)
        est["luts"][n], est["escalas"][n] = rampa, 1.0
        u(p, f"luz_lut_fila[{LUTS.index(n)}]", k, i=True)
        u(p, f"luz_lut_escala[{LUTS.index(n)}]", 1.0)
    tl = tex_float(256, max(len(filas), 1), [[(*decodificar(w, 0), 0.0, 0.0) for w in f] for f in (filas or [[0] * 256])], 0)
    u(p, "luz_luts", 0, i=True)
    u(p, "luz_num", 1, i=True)
    u(p, "luz_ambiente_global", 0, 0, 0)
    for campo in ("especular0", "especular1", "difusa", "ambiente", "posicion", "spot_dir"):
        u(p, "luz_fuente[0]." + campo, *luz[campo])
    for campo in ("direccional", "dos_caras", "usa_da", "usa_sp"):
        u(p, "luz_fuente[0]." + campo, luz[campo], i=True)
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
    GL.glViewport(0, 0, W, W)
    GL.glClearColor(0, 0, 0, 0)
    GL.glClear(GL.GL_COLOR_BUFFER_BIT)
    GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
    GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
    crudo = GL.glReadPixels(0, 0, W, W, GL.GL_RGBA, GL.GL_FLOAT)
    crudo = bytes(crudo) if not isinstance(crudo, bytes) else crudo
    sal = struct.unpack(f"<{4 * W * W}f", crudo)
    # referencia: alinear signos como FlipQuaternionIfOpposite y luego interpolar (afin: w = 1)
    qa = [qs[0]] + [([-k for k in q] if sum(a * b for a, b in zip(q, qs[0])) < 0 else q) for q in qs[1:]]
    malos = tot = maxd = 0
    for y in range(W):
        for x in range(W):
            bx, by = (x + 0.5) / W * 2 - 1, (y + 0.5) / W * 2 - 1
            l1, l2 = (bx + 1) / 2, (by + 1) / 2
            l0 = 1 - l1 - l2
            if l0 < 0.02:  # fuera o en el borde del triangulo
                continue
            q = [l0 * qa[0][k] + l1 * qa[1][k] + l2 * qa[2][k] for k in range(4)]
            vis = [l0 * vs[0][k] + l1 * vs[1][k] + l2 * vs[2][k] for k in range(3)]
            ref = R.iluminar(c, est, q, vis, [[0.5] * 4] * 3)[0]
            for ch in range(4):
                d = abs(round(sal[4 * (y * W + x) + ch] * 255) - round(ref[ch] * 255))
                maxd = max(maxd, d)
                tot += 1
                malos += d > 1
    GL.glDeleteTextures([tl])
    GL.glDeleteBuffers(1, [vbo])
    GL.glDeleteVertexArrays(1, [vao])
    GL.glDeleteProgram(p)
    return malos, tot, maxd


def main():
    a = sys.argv[1:]
    sab = int(a[a.index("--sabotaje") + 1]) if "--sabotaje" in a else 0
    K = int(a[a.index("-k") + 1]) if "-k" in a else 3
    N = int(a[a.index("-n") + 1]) if "-n" in a else 128
    if not glfw.init():
        sys.exit("glfw no inicia")
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    w = glfw.create_window(64, 64, "luz", None, None)
    glfw.make_context_current(w)
    print("driver:", GL.glGetString(GL.GL_RENDERER).decode(), "|", "sabotaje:", SABOTAJES[sab][0] if sab else "ninguno")
    fbo = GL.glGenFramebuffers(1)
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
    for att in (0, 1):
        rb = GL.glGenRenderbuffers(1)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, rb)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_RGBA32F, max(N, 16), 16)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0 + att, GL.GL_RENDERBUFFER, rb)
    GL.glDrawBuffers(2, [GL.GL_COLOR_ATTACHMENT0, GL.GL_COLOR_ATTACHMENT1])
    assert GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) == GL.GL_FRAMEBUFFER_COMPLETE
    vao = GL.glGenVertexArrays(1)
    lutdb = json.load(open(os.path.join(G.DIR, "luts.json"), encoding="utf-8"))["luts"]
    cs = G.cargar_configs()
    rng = random.Random(8102026)
    bien_cfg = bien_mats = 0
    tot_malos = tot_ex = tot = maxd = 0
    fallas = []
    for c in cs:
        try:
            m, e, t, md = correr_config(c, lutdb, rng, K, N, sab, fbo, vao)
        except RuntimeError as ex:
            m, e, t, md = 1, 0, 1, 999
            fallas.append(f"L{c['id']}: NO COMPILA {str(ex)[:200]}")
        tot_malos += m
        tot_ex += e
        tot += t
        maxd = max(maxd, md)
        if m == 0:
            bien_cfg += 1
            bien_mats += c["usos"]
        elif len(fallas) < 6:
            fallas.append(f"L{c['id']} ({c['txt']}): {m} canales con >1 LSB, max {md}")
    fm, ft, fmax = prueba_flip(next(c for c in cs if c["luts"]), rng, sab, fbo, vao)
    for f in fallas:
        print("  FALLA", f)
    print(f"configuraciones OK: {bien_cfg}/{len(cs)} (materiales {bien_mats}/{sum(c['usos'] for c in cs)}) · "
          f"canales {tot} · exactos {100.0 * tot_ex / max(tot, 1):.2f}% · >1 LSB {tot_malos} · max {maxd} LSB")
    print(f"flip de cuaterniones (geometry shader): {'OK' if fm == 0 else 'FALLA'} · {ft} canales · >1 LSB {fm} · max {fmax} LSB")
    glfw.terminate()
    # la tolerancia de 1 LSB taparia un error de convencion (redondear en vez de truncar a u8, como espera el
    # TEV): por eso ademas se exige que >= 99,5 % de los canales coincidan EXACTO
    exacto_ok = tot_ex >= 0.995 * tot
    print(f"canales exactos >= 99,5 %: {'OK' if exacto_ok else 'FALLA'}")
    ok = bien_cfg == len(cs) and fm == 0 and exacto_ok
    print("RESULTADO:", "VERDE" if ok else "ROJO")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
