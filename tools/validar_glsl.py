"""Compila y enlaza los GLSL generados (extraido\\shaders\\glsl\\*.vert) en el driver OpenGL real (3.3 core).

Uso: tools\\.venv_gl\\Scripts\\python.exe tools\\validar_glsl.py
(el venv tiene glfw + PyOpenGL; ventana oculta). Cada .vert va con un fragment shader minimo que consume sus salidas.
"""
import os
import re
import sys

import glfw
from OpenGL import GL

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(RAIZ, "extraido", "shaders", "glsl")


def compilar(tipo, src):
    s = GL.glCreateShader(tipo)
    GL.glShaderSource(s, src)
    GL.glCompileShader(s)
    ok = GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS)
    log = GL.glGetShaderInfoLog(s)
    return s, bool(ok), (log.decode(errors="replace") if isinstance(log, bytes) else log or "")


def frag_para(vert):
    outs = re.findall(r"^out vec4 (pica_o\d+);", vert, re.M)
    lineas = ["#version 330 core"] + [f"in vec4 {o};" for o in outs] + ["out vec4 color;", "void main() {",
             "    color = vec4(0.0)" + "".join(f" + {o}" for o in outs) + ";", "}"]
    return "\n".join(lineas)


def main():
    if not glfw.init():
        sys.exit("glfw no inicia")
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    w = glfw.create_window(64, 64, "validar", None, None)
    if not w:
        sys.exit("no hay contexto 3.3 core")
    glfw.make_context_current(w)
    print("driver:", GL.glGetString(GL.GL_RENDERER).decode(), "|", GL.glGetString(GL.GL_VERSION).decode())
    bien = total = 0
    for f in sorted(os.listdir(DIR)):
        if not f.endswith(".vert"):
            continue
        total += 1
        src = open(os.path.join(DIR, f), encoding="utf-8").read()
        vs, okv, logv = compilar(GL.GL_VERTEX_SHADER, src)
        fs, okf, logf = compilar(GL.GL_FRAGMENT_SHADER, frag_para(src))
        okl, logl = False, ""
        if okv and okf:
            p = GL.glCreateProgram()
            GL.glAttachShader(p, vs)
            GL.glAttachShader(p, fs)
            GL.glLinkProgram(p)
            okl = bool(GL.glGetProgramiv(p, GL.GL_LINK_STATUS))
            logl = GL.glGetProgramInfoLog(p)
            logl = logl.decode(errors="replace") if isinstance(logl, bytes) else logl or ""
        if okl:
            bien += 1
            print(f"OK    {f}" + (f"  (avisos: {logv.strip()[:200]})" if logv.strip() else ""))
        else:
            print(f"FALLA {f}\n  vert: {logv.strip()[:1500]}\n  frag: {logf.strip()[:300]}\n  link: {logl.strip()[:300]}")
    print(f"TOTAL: {bien}/{total} compilan y enlazan")
    glfw.terminate()
    sys.exit(0 if bien == total else 1)


if __name__ == "__main__":
    main()
