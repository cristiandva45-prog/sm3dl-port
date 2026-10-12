r"""(P1, 10 oct 2026) prueba del ATAJO de textura_para SIN el juego. Un nucleo, segundos.
  py -I agentes_dx12\P1\tools\p1.py construir   -> P1\prueba_p1.exe (prueba_e2.c de E2 + ops 30-32) y P1\e2_con_p1.exe (= arnes E2)
  py -I agentes_dx12\P1\tools\p1.py prueba      -> textura cambia en la MISMA direccion: GL atajo vs GL sin atajo (SM3DL_P1_ATAJO=0),
                                                   byte a byte; y SM3DL_P1_SABOTAJE=1 debe salir DISTINTO
  py -I agentes_dx12\P1\tools\p1.py e2 [esc..]  -> arnes de E2 (GL vs D3D12) con mi exe, carpeta propia P1\trabajo_e2
Ops nuevas del guion (solo en prueba_p1.c): 30 dir n datos = escritura de CPU SIN aviso (memcpy directo, como el juego
recompilado); 31 dir n = aviso de flush de cache (gsp_cpu_escribio con la direccion VIRTUAL); 32 = cierre de cuadro."""
import importlib.util, os, random, shutil, subprocess, sys
from array import array

P1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(P1))
E2D = os.path.join(RAIZ, "agentes_dx12", "E2")
RD = os.path.join(RAIZ, "recomp", "render")
GD = os.path.join(RAIZ, "recomp", "gpu")
EXE = os.path.join(P1, "prueba_p1.exe")
TRAB = os.path.join(P1, "trabajo")


def construir():
    src = open(os.path.join(E2D, "prueba_e2.c"), encoding="utf-8").read()
    viejo = "        if (op == 0) break;\n"
    assert src.count(viejo) == 1
    nuevo = viejo + (
        "        if (op == 30) {   /* P1: escritura de CPU sin aviso */\n"
        "            uint32_t dir = g[i], b = g[i + 1];\n"
        "            uint8_t *p = (uint8_t *)gsp_fisica_a_host(dir, b);\n"
        "            if (p) memcpy(p, &g[i + 2], b); else fprintf(stderr, \"[arnes] op30 sin memoria\\n\");\n"
        "            i += 2 + (b + 3) / 4;\n"
        "            continue;\n"
        "        }\n"
        "        if (op == 31) { gsp_cpu_escribio(g[i], g[i + 1]); i += 2; continue; }   /* P1: flush */\n"
        "        if (op == 32) { gsp_cuadro_tex++; continue; }                           /* P1: cierre de cuadro */\n")
    src = src.replace(viejo, nuevo).replace("\r\n", "\n")
    src = "void gsp_cpu_escribio(uint32_t v, uint32_t tam);\n" + src.replace('#include "raster_gl.c"\n', '#include "raster_gl.c"\n', 1)
    # la declaracion necesita stdint: va despues de los include
    src = src.replace("void gsp_cpu_escribio(uint32_t v, uint32_t tam);\n", "", 1).replace(
        '#include "raster_gl.c"\n', '#include "raster_gl.c"\nvoid gsp_cpu_escribio(uint32_t v, uint32_t tam);\n', 1)
    open(os.path.join(P1, "prueba_p1.c"), "w", encoding="utf-8").write(src)
    base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
            "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function", "-DSM3DL_CON_D3D12", "-I", RD, "-I", GD]
    comunes = [os.path.join(RD, n) for n in ("pica.c", "pica_dibujar.c", "texturas.c", "d3d12_base.c", "d3d12_recursos.c",
                                             "d3d12_presentador.c", "texturas_hd.c")] + [os.path.join(GD, "gsp.c")]
    libs = ["-lopengl32", "-lgdi32", "-luser32", "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47", "-ldbghelp"]
    rc = 0
    for c, o in ((os.path.join(P1, "prueba_p1.c"), EXE), (os.path.join(E2D, "prueba_e2.c"), os.path.join(P1, "e2_con_p1.exe"))):
        r = subprocess.run(base + [c] + comunes + libs + ["-o", o], capture_output=True, text=True)
        print(os.path.basename(o), "rc", r.returncode, (r.stdout + r.stderr).strip()[:3000])
        rc |= r.returncode
    return rc


def guion_prueba(limite=False):
    os.chdir(RAIZ)
    spec = importlib.util.spec_from_file_location("equiv_a", os.path.join(RAIZ, "agentes_dx12", "A", "tools", "equiv.py"))
    eq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eq)
    pr = eq.pr
    rng = random.Random(1010)
    W = 32
    D = pr.DIR_TEX[0]
    VIRT = D - 0x18000000 + 0x1F000000
    g = eq.nuevo_guion(64, 64)
    for j in range(1, 6):
        b = pr.TEV_BASE[j]
        g.reg(b, 0xF | (0xF << 16)); g.reg(b + 1, 0); g.reg(b + 2, 0); g.reg(b + 4, 0)
    v = array("f")
    for (x, y, s, t) in ((-1, -1, 0, 0), (1, -1, 1, 0), (-1, 1, 0, 1), (1, -1, 1, 0), (1, 1, 1, 1), (-1, 1, 0, 1)):
        v.extend((x, y, -0.5, 1.0))
        for _ in range(3):
            v.extend((1, 1, 1, 1))
        v.extend((s, t, 0, 0)); v.extend((s, t, 0, 0))
    g.mem(pr.DIR_VTX, v.tobytes())

    def dibujar(veces=3):
        for _ in range(veces):
            g.reg(0x81, 0)
            g.reg(0x82, (W << 16) | W)
            g.reg(0x83, 0)
            g.reg(0x84, 0)
            g.reg(0x85, D // 8)
            g.reg(0x8E, 0)
            g.reg(0x80, 1)
            g.reg(pr.TEV_BASE[0], 3 | (3 << 16)); g.reg(pr.TEV_BASE[0] + 1, 0); g.reg(pr.TEV_BASE[0] + 2, 0)
            g.reg(0x228, 6); g.reg(0x22A, 0); g.reg(0x22E, 1)
            g.leer(0, 0, 64, 64)

    def azar():
        return bytes(rng.randrange(256) for _ in range(W * W * 4))
    casos = []
    g.mem(D, azar()); dibujar(); casos.append("inicial")
    for k in range(3):                       # 1) escritura con aviso (gsp_escribir_fisica: DMA/transfer/fill/bajada de RT)
        g.mem(D, azar()); dibujar(); casos.append("escribir_fisica")
    for k in range(3):                       # 2) CPU sin aviso + flush de cache
        d = azar(); g.w.extend((30, D, len(d))); g.w.frombytes(d); g.w.extend((31, VIRT, len(d))); dibujar()
        casos.append("cpu+flush")
    for k in range(3):                       # 3) CPU sin aviso + cierre de cuadro
        d = azar(); g.w.extend((30, D, len(d))); g.w.frombytes(d); g.w.append(32); dibujar(); casos.append("cpu+cuadro")
    for k in range(2):                       # 4) CPU sin aviso, flush PARCIAL (solo la ultima fila de tiles)
        d = azar(); g.w.extend((30, D, len(d))); g.w.frombytes(d); g.w.extend((31, VIRT + len(d) - 64, 64)); dibujar()
        casos.append("cpu+flush_parcial")
    if limite:                               # 5) LIMITE documentado: CPU sin aviso en el mismo cuadro -> el atajo NO lo ve
        d = azar(); g.w.extend((30, D, len(d))); g.w.frombytes(d); dibujar(); casos.append("cpu_sin_aviso")
    return eq, g, casos


def correr(eq, g, nombre, env):
    os.makedirs(TRAB, exist_ok=True)
    eq.TRAB = TRAB
    e = {"SM3DL_BACKEND": "gl"}
    e.update(env)
    return eq.correr(EXE, g, nombre, e)


def prueba():
    eq, g, casos = guion_prueba()
    rc0, d0, _ = correr(eq, g, "ref", {"SM3DL_P1_ATAJO": "0"})
    rc1, d1, l1 = correr(eq, g, "atajo", {})
    rc2, d2, _ = correr(eq, g, "sabotaje", {"SM3DL_P1_SABOTAJE": "1"})
    seg = 64 * 64 * 4
    n = len(d0) // seg
    def dif(a, b):
        return [k for k in range(n) if a[k * seg:(k + 1) * seg] != b[k * seg:(k + 1) * seg]]
    # la prueba MIDE: lecturas consecutivas de contenidos distintos deben diferir en la referencia
    distintos_ref = sum(1 for k in range(3, n, 3) if d0[k * seg:(k + 1) * seg] != d0[(k - 3) * seg:(k - 2) * seg])
    print("lecturas %d (rc %d/%d/%d); en la referencia cambian %d de %d cambios de contenido" % (n, rc0, rc1, rc2, distintos_ref, n // 3 - 1))
    da, ds = dif(d0, d1), dif(d0, d2)
    print("ATAJO vs referencia: %d lecturas distintas %s" % (len(da), da[:12]))
    print("SABOTAJE vs referencia: %d lecturas distintas (casos: %s)" % (len(ds), sorted({casos[k // 3] for k in ds})))
    ok = rc0 == rc1 == 0 and n > 0 and not da and ds and distintos_ref == n // 3 - 1
    eq, g, casos = guion_prueba(limite=True)
    _, l0, _ = correr(eq, g, "lim_ref", {"SM3DL_P1_ATAJO": "0"})
    _, l1, _ = correr(eq, g, "lim_atajo", {})
    nl = len(l0) // seg
    dl = [k for k in range(nl) if l0[k * seg:(k + 1) * seg] != l1[k * seg:(k + 1) * seg]]
    print("LIMITE (CPU sin aviso, mismo cuadro): %d lecturas distintas %s -> el atajo SI se toma en modo normal" % (len(dl), dl))
    ok = ok and dl == [nl - 3, nl - 2, nl - 1]
    print("PRUEBA P1:", "BIEN" if ok else "MAL")
    return 0 if ok else 1


def e2(nombres):
    spec = importlib.util.spec_from_file_location("e2", os.path.join(E2D, "tools", "e2.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.EXE = os.path.join(P1, "e2_con_p1.exe")
    m.TRAB = os.path.join(P1, "trabajo_e2")
    dst = os.path.join(m.TRAB, "extraido", "shaders", "cache_d3d12")
    if not os.path.isdir(dst):
        shutil.copytree(os.path.join(E2D, "trabajo", "extraido", "shaders", "cache_d3d12"), dst)
    bien, mal, nulo = m.correr_lote(nombres or list(m.ESCENARIOS), "gl", "d3d12", 1)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] or ["prueba"]
    if a[0] == "construir":
        sys.exit(construir())
    if a[0] == "prueba":
        sys.exit(prueba())
    if a[0] == "e2":
        sys.exit(e2(a[1:]))
