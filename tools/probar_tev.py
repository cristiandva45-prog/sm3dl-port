"""Verificador diferencial de los fragment shaders TEV: GLSL de tools/tev_glsl.py ejecutado en la GPU real contra el
modelo entero de tools/tev_ref.py (semantica del rasterizador por software de Azahar).

Uso: tools\\.venv_gl\\Scripts\\python.exe tools\\probar_tev.py [-d DIBUJOS] [--sabotaje N] [--solo R12,R40] [-v]
  Cada receta (extraido\\shaders\\frag\\recetas.json, lo escribe tev_glsl.py) se genera en memoria con
  tev_glsl.generar y se dibuja DIBUJOS veces (uniforms nuevos por dibujo) sobre 256 puntos de 1 px (entradas por
  fragmento: vtx_color, tex0-2 por texel NEAREST de una textura RGBA8 256x1). Salida en un FBO RGBA32F (sin
  redondear). Pasa si |gpu*255 - ref| <= 1 en los 4 canales (tolerancia 1/255).
  --sabotaje 1: LERP con los pesos cruzados   2: la escala x4 se vuelve x2   3: el operando 1-a (alfa) lee a
  (cada uno debe hacer FALLAR la prueba; se aplican sobre la copia en memoria del generador, no al archivo)
  --generador RUTA: prueba otra copia de tev_glsl.py (las recetas se leen igual de extraido\shaders\frag)
"""
import collections
import ctypes
import itertools
import json
import os
import random
import sys

import glfw
from OpenGL import GL

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(RAIZ, "tools"))  # al final: tools\dis.py tapa el modulo estandar 'dis'
import tev_glsl  # noqa: E402
import tev_ref  # noqa: E402

W = 256
BORDES = [0, 1, 2, 126, 127, 128, 129, 253, 254, 255]
VERT = f"""#version 330 core
layout(location=0) in float idx;
layout(location=1) in vec4 col;
out vec4 vtx_color; out vec2 texcoord0; out vec2 texcoord1; out vec2 texcoord2;
void main() {{
    float x = (idx + 0.5) / {W}.0;
    vtx_color = col; texcoord0 = vec2(x, 0.5); texcoord1 = texcoord0; texcoord2 = texcoord0;
    gl_Position = vec4(x * 2.0 - 1.0, 0.0, 0.0, 1.0);
}}
"""


def sabotear(n):
    if n == 1:
        viejo = tev_glsl.combinar

        def combinar(c, a, b, cc, rgb):
            if c == 4:
                uno = "vec3(1.0)" if rgb else "1.0"
                return f"{a} * ({uno} - {cc}) + {b} * {cc}"
            return viejo(c, a, b, cc, rgb)
        tev_glsl.combinar = combinar
    elif n == 2:
        tev_glsl.ESCALA[2] = "2.0"
    elif n == 3:
        tev_glsl.OP_A[1] = "{s}.a"


def u8(rng):
    return rng.choice(BORDES) if rng.random() < 0.3 else rng.randrange(256)


def color(rng):
    return [u8(rng) for _ in range(4)]


def compilar(tipo, src):
    s = GL.glCreateShader(tipo)
    GL.glShaderSource(s, src)
    GL.glCompileShader(s)
    if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
        raise RuntimeError(GL.glGetShaderInfoLog(s))
    return s


class Banco:
    def __init__(self):
        if not glfw.init():
            sys.exit("glfw no inicia")
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        self.w = glfw.create_window(64, 64, "tev", None, None)
        glfw.make_context_current(self.w)
        self.driver = GL.glGetString(GL.GL_RENDERER).decode()
        self.vs = compilar(GL.GL_VERTEX_SHADER, VERT)
        self.fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        rb = GL.glGenRenderbuffers(1)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, rb)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_RGBA32F, W, 1)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_RENDERBUFFER, rb)
        assert GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) == GL.GL_FRAMEBUFFER_COMPLETE
        GL.glViewport(0, 0, W, 1)
        GL.glDisable(GL.GL_DITHER)
        self.tex = list(GL.glGenTextures(3))
        for t in self.tex:
            GL.glBindTexture(GL.GL_TEXTURE_2D, t)
            for p in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
                GL.glTexParameteri(GL.GL_TEXTURE_2D, p, GL.GL_NEAREST)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, W, 1, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 1, GL.GL_FLOAT, False, 20, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 4, GL.GL_FLOAT, False, 20, ctypes.c_void_p(4))

    def programa(self, src):
        fs = compilar(GL.GL_FRAGMENT_SHADER, src)
        p = GL.glCreateProgram()
        GL.glAttachShader(p, self.vs)
        GL.glAttachShader(p, fs)
        GL.glLinkProgram(p)
        if not GL.glGetProgramiv(p, GL.GL_LINK_STATUS):
            raise RuntimeError(GL.glGetProgramInfoLog(p))
        GL.glDeleteShader(fs)
        return p

    def dibujar(self, prog, uni, frags):
        """uni: prim, sec, const[6], buf, update; frags: W dicts con vtx, t0, t1, t2 (u8). -> W listas de 4 floats."""
        GL.glUseProgram(prog)

        def loc(n):
            return GL.glGetUniformLocation(prog, n)
        for nombre, v in (("frag_primario", uni["prim"]), ("frag_secundario", uni["sec"]),
                          ("tev_buffer_color", uni["buf"])):
            if loc(nombre) >= 0:
                GL.glUniform4f(loc(nombre), *[x / 255 for x in v])
        if loc("tev_const") >= 0:
            arr = (ctypes.c_float * 24)(*[x / 255 for c in uni["const"] for x in c])
            GL.glUniform4fv(loc("tev_const"), 6, arr)
        if loc("tev_update") >= 0:
            GL.glUniform1ui(loc("tev_update"), uni["update"])
        for j, t in enumerate(self.tex):
            GL.glActiveTexture(GL.GL_TEXTURE0 + j)
            GL.glBindTexture(GL.GL_TEXTURE_2D, t)
            datos = bytes(x for f in frags for x in f[f"t{j}"])
            GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, W, 1, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, datos)
            if loc(f"tex{j}") >= 0:
                GL.glUniform1i(loc(f"tex{j}"), j)
        vb = (ctypes.c_float * (W * 5))(*[x for i, f in enumerate(frags) for x in [float(i)] + [c / 255 for c in f["vtx"]]])
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, ctypes.sizeof(vb), vb, GL.GL_STREAM_DRAW)
        GL.glClearColor(-1, -1, -1, -1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glDrawArrays(GL.GL_POINTS, 0, W)
        out = (ctypes.c_float * (W * 4))()
        GL.glReadPixels(0, 0, W, 1, GL.GL_RGBA, GL.GL_FLOAT, out)
        return [list(out[i * 4:i * 4 + 4]) for i in range(W)]


VARIANTES = [v for n in (1, 2, 3) for v in itertools.combinations(("buf0_color", "sin_peculiaridad0", "paso_salta"), n)]


def causa(firma, ent, g, dr):
    """Diagnostico de un caso que falla: que hipotesis alternativa del modelo explica lo que dio la GPU.
    Primero las variantes semanticas en enteros (tolerancia 1 LSB), luego las mismas sin truncar (un generador
    en float puro), y si nada lo explica, 'otra' con el tamano del error."""
    for modo, tol in (("int", 1.0), ("real", 1.5)):
        for v in [()] + VARIANTES:
            if v == () and modo == "int":
                continue
            rv = tev_ref.correr(firma, ent, modo, variante=v)
            if max(abs(x * 255 - y) for x, y in zip(g, rv)) <= tol:
                return ("+".join(v) or "semantica ok") + (" (sin truncar u8)" if modo == "real" else "")
    return f"otra ({min(int(dr), 9)}..{min(int(dr), 9) + 1} LSB vs real)"


def ops_de(firma):
    s = set()
    for s_, o, c, e in firma:
        s.add(f"c{c & 15}")
        s.add(f"a{(c >> 16) & 15}")
    return s


def main():
    args = sys.argv[1:]
    dib = int(args[args.index("-d") + 1]) if "-d" in args else 8
    if "--generador" in args:  # otra copia del generador (p. ej. la version vieja) en lugar de tools/tev_glsl.py
        import importlib.util
        global tev_glsl
        spec = importlib.util.spec_from_file_location("tev_glsl_alt", args[args.index("--generador") + 1])
        tev_glsl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tev_glsl)
    if "--sabotaje" in args:
        sabotear(int(args[args.index("--sabotaje") + 1]))
    solo = set(args[args.index("--solo") + 1].split(",")) if "--solo" in args else None
    verbose = "-v" in args
    recetas = json.load(open(os.path.join(RAIZ, "extraido", "shaders", "frag", "recetas.json"), encoding="utf-8"))
    banco = Banco()
    print("driver:", banco.driver)
    iguales = total_rec = 0
    tipos = collections.Counter()
    causas, causas_rec = collections.Counter(), collections.Counter()
    hist_int, hist_real = collections.Counter(), collections.Counter()
    for r in recetas:
        if solo and r["nombre"] not in solo:
            continue
        firma = [tuple(e) for e in r["firma"]]
        try:
            src = tev_glsl.generar(firma, r["nombre"], r["uso"], r["ejemplo"])
        except tev_glsl.SinSoporte as ex:
            print(r["nombre"], "sin soporte:", ex)
            continue
        total_rec += 1
        prog = banco.programa(src)
        rng = random.Random(r["nombre"])
        fallos = casos = 0
        peor, ejemplo = 0.0, None
        cr = set()
        for d in range(dib):
            upd = rng.choice([0, 0xFF00, rng.randrange(256) << 8, rng.randrange(256) << 8])
            uni = dict(prim=color(rng), sec=color(rng), buf=color(rng), const=[color(rng) for _ in range(6)],
                       update=upd)
            frags = [dict(vtx=color(rng), t0=color(rng), t1=color(rng), t2=color(rng)) for _ in range(W)]
            gpu = banco.dibujar(prog, uni, frags)
            for f, g in zip(frags, gpu):
                ent = dict(uni, t3=[0, 0, 0, 0], **f)
                ri = tev_ref.correr(firma, ent, "int")
                rr = tev_ref.correr(firma, ent, "real")
                di = max(abs(x * 255 - y) for x, y in zip(g, ri))
                dr = max(abs(x * 255 - y) for x, y in zip(g, rr))
                hist_int[min(int(di + 0.999), 9)] += 1
                hist_real[min(int(dr + 0.999), 9)] += 1
                casos += 1
                if di > 1.0 + 1e-3:
                    fallos += 1
                    cs = causa(firma, ent, g, dr)
                    causas[cs] += 1
                    cr.add(cs)
                    if di > peor:
                        peor = di
                        ejemplo = (ent, [round(x * 255, 2) for x in g], ri, [round(x, 2) for x in rr])
        GL.glDeleteProgram(prog)
        for cs in cr:
            causas_rec[cs] += 1
        if fallos:
            tipos[" ".join(sorted(ops_de(firma)))] += 1
            print(f"{r['nombre']}: {casos - fallos}/{casos} iguales, peor {peor:.2f}/255")
            if verbose and ejemplo:
                print("   ent", ejemplo[0], "\n   gpu", ejemplo[1], "int", ejemplo[2], "real", ejemplo[3])
        else:
            iguales += 1
    print(f"RECETAS IGUALES: {iguales}/{total_rec}")
    print("diferencia max por caso vs int (LSB):", dict(sorted(hist_int.items())))
    print("diferencia max por caso vs real (LSB):", dict(sorted(hist_real.items())))
    if causas:
        print("causa de los casos que fallan (casos / recetas):")
        for cs, n in causas.most_common():
            print(f"   {cs}: {n} / {causas_rec[cs]}")
    if tipos:
        print("operaciones de las recetas que fallan:", tipos.most_common(10))
    glfw.terminate()
    sys.exit(0 if iguales == total_rec else 1)


if __name__ == "__main__":
    main()
