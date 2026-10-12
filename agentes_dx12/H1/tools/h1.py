r"""PRUEBA DE LA CINTA DE INTERMEDIOS (agente H1, 10 oct 2026). NO corre el juego: arma un guion de registros PICA con
3 cuadros (A, B, C: los mismos 24 dibujos con distintos uniforms del VS), lo corre en agentes_dx12\H1\prueba_h1.exe
(raster_gl.c + interp.c + gsp.c REALES, GPU real, ventana oculta 64x64) y mira que el intermedio B-C hecho por la CINTA
(D3D12) sea IDENTICO al de la re-ejecucion de siempre. Segundos, un nucleo.
Uso (desde cualquier lado; py -I):
  py -I agentes_dx12\H1\tools\h1.py construir        compila prueba_h1.exe (banderas de compilar.py --d3d12)
  py -I agentes_dx12\H1\tools\h1.py shaders          corre en GL volcando los textos y los pasa a DXIL (cadena de B)
  py -I agentes_dx12\H1\tools\h1.py probar [--sab N] [--backend gl|d3d12] [--t T]
        --sab N: SM3DL_H1_SABOTAJE=N (1 = b0 grabado siempre, 2 = dibujos impares saltados): DEBE fallar.
  py -I agentes_dx12\H1\tools\h1.py todo             probar d3d12 + GL + los 2 sabotajes (exit 0 si todo como se espera)"""
import importlib.util
import os
import random
import shutil
import struct
import subprocess
import sys
from array import array

H1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(H1))
RD = os.path.join(RAIZ, "recomp", "render")
GD = os.path.join(RAIZ, "recomp", "gpu")
EXE = os.path.join(H1, "prueba_h1.exe")
TRAB = os.path.join(H1, "trabajo")
GLSL = os.path.join(H1, "glsl")
CACHE_PROPIA = os.path.join(H1, "cache")
CACHE_TRAB = os.path.join(TRAB, "extraido", "shaders", "cache_d3d12")
CACHES_BASE = [os.path.join(RAIZ, "extraido", "shaders", "cache_d3d12"), os.path.join(RAIZ, "agentes_dx12", "B", "cache_d3d12"),
               os.path.join(RAIZ, "agentes_dx12", "E2", "cache_arnes")]

spec = importlib.util.spec_from_file_location("pr", os.path.join(RAIZ, "agentes_noche", "R", "herr", "probar_raster.py"))
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

# VS de prueba: como el de R, pero LEE pica_c (c0 mueve la posicion, c1 el color, c2 las coordenadas de textura)
VERT = """#version 330 core
layout(location = 0) in vec4 v0;
layout(location = 1) in vec4 v1;
layout(location = 2) in vec4 v2;
layout(location = 3) in vec4 v3;
layout(location = 4) in vec4 v4;
layout(location = 5) in vec4 v5;
uniform vec4 pica_c[96];
uniform ivec4 pica_i[4];
uniform bool pica_b[16];
out vec4 pica_o0;  // posicion.xyzw
vec4 r[16];
vec4 o[16];
void pica_main() { o[0] = v0 + vec4(pica_c[0].xy, 0.0, 0.0); o[1] = clamp(v1 + pica_c[1], 0.0, 1.0); o[2] = v2; o[3] = v3; o[4] = v4 + vec4(pica_c[2].xy, pica_c[2].xy); o[5] = v5; }
void main() {
    for (int k = 0; k < 16; k++) { r[k] = vec4(0.0); o[k] = vec4(0.0); }
    pica_main();
    pica_o0 = o[0];
    gl_Position = vec4(o[0].x, o[0].y, -o[0].z, o[0].w);
}
"""
ANCHO, ALTO = 128, 64
NDIB = 24


def f32(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def uniform(g, idx, v):
    g.reg(0x2C0, idx | (1 << 31))
    for c in (v[3], v[2], v[1], v[0]):   # f32: la palabra 0 es w
        g.reg(0x2C1, f32(c))


def tev(g, preset):
    """etapa 0 segun preset; etapas 1-5 pasan la anterior (si no, REPLACE del color primario las pisa)"""
    s, o, c = [(0, 0, 0), (3 | (3 << 16), 0, 1 | (1 << 16)), (4 | (4 << 16), 0, 2 | (2 << 16))][preset]
    b = pr.TEV_BASE
    g.reg(b[0], s); g.reg(b[0] + 1, o); g.reg(b[0] + 2, c); g.reg(b[0] + 3, 0); g.reg(b[0] + 4, 0)
    for j in range(1, 6):
        g.reg(b[j], 15 | (15 << 16)); g.reg(b[j] + 1, 0); g.reg(b[j] + 2, 0); g.reg(b[j] + 3, 0); g.reg(b[j] + 4, 0)


def guion(t=0.5, ndib=None, tocar=False):
    NDIB = ndib or globals()['NDIB']
    pr.ANCHO, pr.ALTO = ANCHO, ALTO
    g = pr.Guion()
    pr.preparar(g, 0)
    g.w.extend((6,))          # el VS propio (reemplaza el de R)
    b = VERT.encode()
    n = len(b)
    b += b"\0" * ((-n) % 4)
    g.w.append(n)
    g.w.frombytes(b)
    g.w.extend((7, 0))        # TEV real (no PRUEBA_TEV)
    rng = random.Random(1010)
    cols = [[pr.rgba(rng) for _ in range(256)] for _ in range(3)]
    pr.texturas(g, cols)
    # vertices de los 24 dibujos (3 triangulos cada uno) en UN buffer; cada dibujo su tramo (huella propia)
    v = array("f")
    for d in range(NDIB):
        for k in range(9):
            v.extend((rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), rng.uniform(-0.9, -0.1), 1.0))
            v.extend((rng.random(), rng.random(), rng.random(), rng.uniform(0.3, 1.0)))
            v.extend((0, 0, 0, 1)); v.extend((0, 0, 0, 1))
            v.extend((rng.random(), rng.random(), rng.random(), rng.random()))
            v.extend((rng.random(), rng.random(), 0, 0))
    signos = [(rng.choice((-1, 1)), rng.choice((-1, 1))) for _ in range(NDIB)]
    for cuadro in range(3):   # A, B, C
        if cuadro == 2:
            g.w.append(41)
        g.limpiar(0x20304050)
        g.mem(pr.DIR_VTX, v.tobytes())
        for d in range(NDIB):
            tev(g, d % 3)
            dosd = d % 5 == 0                        # 2D: interp no lo mezcla (b0 reusado en la cinta)
            sten = d == 7                            # stencil: real (regla de H2 sin programa conocido)
            g.reg(0x107, (0 if dosd else 1) | ((1 if dosd else 4) << 4) | (0xF << 8) | ((0 if dosd else 1) << 12))
            g.reg(0x115, 0 if dosd else 3)
            g.reg(0x105, (1 | (1 << 4) | (0xFF << 8) | (0xFF << 24)) if sten else 0)
            g.reg(0x106, (3 << 8) if sten else 0)
            if d % 2:
                g.reg(0x100, 0x100)
                g.reg(0x101, (6 << 16) | (7 << 20) | (6 << 24) | (7 << 28))   # ADD, SRC_ALPHA / 1-SRC_ALPHA
            else:
                g.reg(0x100, 0x100)
                g.reg(0x101, (1 << 16) | (0 << 20) | (1 << 24) | (0 << 28))   # ONE / ZERO
            sx, sy = signos[d]
            uniform(g, 0, (sx * 0.05 * cuadro, sy * 0.04 * cuadro, 0, 0))
            uniform(g, 1, (0.08 * cuadro, -0.05 * cuadro, 0.03 * cuadro, 0))
            uniform(g, 2, (0.07 * cuadro, 0.11 * cuadro, 0, 0))
            for q in range(3, 12):                   # registros que el VS no lee: tambien cambian
                uniform(g, q, (0.01 * q * cuadro, d * 0.001, 0, 1))
            g.reg(0x25E, 0)
            g.reg(0x228, 9)
            g.reg(0x22A, 9 * d)
            g.reg(0x22E, 1)
            if tocar and cuadro == 2 and d == NDIB // 2:   # textura 0 con otro contenido a mitad del cuadro C
                otra = [[255 - x for x in c] for c in cols[0]]
                px = array("I", [c[0] | (c[1] << 8) | (c[2] << 16) | (c[3] << 24) for c in otra]) * 8
                g.tex(pr.DIR_TEX[0], 256, 8, px)
        if cuadro < 2:
            g.w.append(40)
        else:
            g.w.append(42)
    g.w.extend((43, f32(t)))
    g.w.append(44)
    g.w.append(0)
    return g


def construir():
    base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
            "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function", "-DSM3DL_CON_D3D12"]
    inc = ["-I", RD, "-I", GD]
    fuentes = [os.path.join(H1, "prueba_h1.c")] + [os.path.join(RD, n) for n in (
        "pica.c", "pica_dibujar.c", "texturas.c", "texturas_hd.c", "interp.c", "d3d12_base.c", "d3d12_recursos.c", "d3d12_presentador.c")] + [
        os.path.join(GD, "gsp.c")]
    libs = ["-lopengl32", "-lgdi32", "-luser32", "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47"]
    r = subprocess.run(base + inc + fuentes + libs + ["-o", EXE], capture_output=True, text=True)
    sal = (r.stdout + r.stderr).strip()
    print("prueba_h1.exe rc", r.returncode)
    if sal:
        print(sal[:6000])
    return r.returncode == 0


def correr(backend, env_extra=None, t=0.5, ndib=None, tocar=False):
    os.makedirs(TRAB, exist_ok=True)
    gp = os.path.join(TRAB, "guion.bin")
    with open(gp, "wb") as f:
        guion(t, ndib, tocar).w.tofile(f)
    e = dict(os.environ)
    for k in ("SM3DL_H1_SABOTAJE", "H1_VOLCAR_GLSL", "SM3DL_D3D12_REPETIR_RAPIDO", "H1_ESPERA_INVALIDA"):
        e.pop(k, None)
    e["SM3DL_BACKEND"] = backend
    e["SM3DL_SIN_AUDIO"] = "1"
    e["SM3DL_D3D12_REPETIR_RAPIDO"] = "1"
    e.update(env_extra or {})
    p = subprocess.run([EXE, gp], capture_output=True, text=True, cwd=TRAB, env=e, timeout=120)
    lineas = [l for l in p.stderr.splitlines() if l.startswith("[h1]") or "CINTA" in l or "fallo" in l.lower()]
    return p.returncode, lineas, p.stderr


def shaders():
    os.makedirs(GLSL, exist_ok=True)
    rc, lin, err = correr("gl", {"H1_VOLCAR_GLSL": GLSL})
    print("volcado GL rc %d: %d textos" % (rc, len(os.listdir(GLSL))))
    spec = importlib.util.spec_from_file_location("cadena_b", os.path.join(RAIZ, "agentes_dx12", "B", "cadena_shaders.py"))
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    tmp = os.path.join(H1, "tmp_cadena")
    os.makedirs(tmp, exist_ok=True)
    os.makedirs(CACHE_PROPIA, exist_ok=True)
    cb.GLSL = GLSL
    bien = mal = 0
    for f in sorted(os.listdir(GLSL)):
        pre, resto = f.split("_", 1)
        h, _ = resto.split(".")
        texto = open(os.path.join(GLSL, f), "rb").read()
        if "%08X" % cb.fnv_texto(texto) != h:
            print("hash NO coincide:", f); mal += 1; continue
        nom = "G_FLIP.dxil" if pre == "G" else "%s_%s.dxil" % (pre, h)
        dest = os.path.join(CACHE_PROPIA, nom)
        if os.path.exists(dest):
            bien += 1; continue
        r = cb.convertir_uno(f, True, tmp)
        if r["dxil"] != 1:
            print("FALLA %s en %s: %s" % (f, r["fallo_en"], r["causa"])); mal += 1; continue
        shutil.copyfile(os.path.join(tmp, f + ".dxil"), dest)
        bien += 1
    print("cache propia: %d DXIL bien, %d mal" % (bien, mal))
    os.makedirs(CACHE_TRAB, exist_ok=True)
    n = 0
    for d in [c for c in CACHES_BASE if os.path.isdir(c)] + [CACHE_PROPIA]:
        for f in os.listdir(d):
            src = os.path.join(d, f)
            if os.path.isfile(src) and (d == CACHE_PROPIA or not os.path.exists(os.path.join(CACHE_TRAB, f))):
                shutil.copyfile(src, os.path.join(CACHE_TRAB, f)); n += 1
    print("cache de trabajo: +%d archivos" % n)
    return mal == 0


def probar(backend="d3d12", sab=0, t=0.5, ndib=None, tocar=False):
    env = {"SM3DL_H1_SABOTAJE": str(sab)} if sab else {}
    if tocar:
        env["H1_ESPERA_INVALIDA"] = "1"
    rc, lin, err = correr(backend, env, t, ndib, tocar)
    print("--- %s%s%s t=%.2f, %d dibujos por cuadro: rc %d" % (backend, " SABOTAJE %d" % sab if sab else "",
          " TEXTURA RE-SUBIDA" if tocar else "", t, ndib or NDIB, rc))
    for l in lin:
        print("   ", l[:400])
    if rc not in (0, 1):
        print(err[-3000:])
    return rc


def main():
    a = sys.argv[1:]
    if not a or a[0] == "todo":
        ok = construir()
        r = [probar("d3d12", 0, 0.5) == 0, probar("d3d12", 0, 0.3) == 0, probar("gl", 0, 0.5) == 0,
             probar("d3d12", 0, 0.5, tocar=True) == 0, probar("d3d12", 0, 0.5, ndib=344) == 0,
             probar("d3d12", 1, 0.5) == 1, probar("d3d12", 2, 0.5) == 1]
        print("RESUMEN: d3d12 t=0,5 %s | d3d12 t=0,3 %s | gl (sin cinta) %s | textura re-subida -> camino de siempre %s | "
              "344 dibujos %s | sabotaje 1 %s | sabotaje 2 %s" % tuple(
            ("bien" if x else "MAL") if i < 5 else ("DETECTADO" if x else "NO DETECTADO") for i, x in enumerate(r)))
        sys.exit(0 if ok and all(r) else 1)
    if a[0] == "construir":
        sys.exit(0 if construir() else 1)
    if a[0] == "shaders":
        sys.exit(0 if shaders() else 1)
    if a[0] == "probar":
        sab = int(a[a.index("--sab") + 1]) if "--sab" in a else 0
        be = a[a.index("--backend") + 1] if "--backend" in a else "d3d12"
        t = float(a[a.index("--t") + 1]) if "--t" in a else 0.5
        nd = int(a[a.index("--ndib") + 1]) if "--ndib" in a else None
        sys.exit(probar(be, sab, t, nd, "--tocar" in a))
    print(__doc__)


if __name__ == "__main__":
    main()
