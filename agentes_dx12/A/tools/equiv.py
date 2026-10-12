r"""Prueba de EQUIVALENCIA antes/despues del paso 1 de D3D12 (agente A, 8 oct 2026). NO corre el juego: corre dos arneses
chicos (agentes_dx12\A\equiv_antes.exe = codigo de ANTES, equiv_nuevo.exe = codigo NUEVO; ver construir_equiv.py) con el MISMO
guion de registros PICA, sobre una VRAM falsa y la GPU real, y compara la salida byte a byte (pixeles del RT, memoria
codificada, pantalla en alta girada, presentacion). Cada escenario dura unos segundos en un nucleo.
Uso (desde la raiz): py -I agentes_dx12\A\tools\equiv.py [escenario ...] [--sabotaje N]
  escenarios: tev tev_uber estado luz vertices memoria alta pres    (sin argumentos: todos)
  --sabotaje N: el exe NUEVO corre con SM3DL_BACKEND_SABOTAJE=N; la comparacion DEBE salir distinta (exit 1 si NO la detecta)
Salida: exit 0 si todo igual (o, con --sabotaje, si se detecto la diferencia)."""
import importlib.util, os, random, subprocess, sys, hashlib
from array import array

RAIZ = os.getcwd()
A = os.path.join(RAIZ, "agentes_dx12", "A")
TRAB = os.path.join(A, "trabajo")
spec = importlib.util.spec_from_file_location("pr", os.path.join(RAIZ, "agentes_noche", "R", "herr", "probar_raster.py"))
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

DIR_SAL = 0x18400000


def nuevo_guion(ancho, alto, uber=0, fmt=0):
    pr.ANCHO, pr.ALTO = ancho, alto
    g = pr.Guion()
    pr.preparar(g, uber)
    if fmt:
        g.reg(0x117, fmt << 16)
    return g


def rgba(rng):
    return pr.rgba(rng)


def paquete(c):
    return c[0] | (c[1] << 8) | (c[2] << 16) | (c[3] << 24)


def tris_azar(g, rng, n, ancho, alto, z0=-1.0, z1=0.0, indices=None):
    """n triangulos al azar en el RT; atributos v1..v5 al azar (color, prim, sec, tc, tc). Dibuja con DRAWARRAYS o
    DRAWELEMENTS (indices = None | 'u8' | 'u16')."""
    v = array("f")
    nv = 3 * n
    for k in range(nv):
        v.extend((rng.uniform(-1.1, 1.1), rng.uniform(-1.1, 1.1), rng.uniform(z0, z1), 1.0))
        for _ in range(5):
            v.extend((rng.random(), rng.random(), rng.random(), rng.random()))
    g.mem(pr.DIR_VTX, v.tobytes())
    if indices is None:
        g.reg(0x228, nv)
        g.reg(0x22A, 0)
        g.reg(0x22E, 1)
    else:
        idx = list(range(nv))
        rng.shuffle(idx)
        idx = idx + idx[: nv // 3]           # repeticiones: rango unico
        base = 0x10000
        if indices == "u8" and nv > 250:
            raise SystemExit("u8 solo para pocos vertices")
        datos = bytes(idx) if indices == "u8" else array("H", idx).tobytes()
        g.mem(pr.DIR_VTX + base, datos)
        g.reg(0x227, base | (0 if indices == "u8" else (1 << 31)))
        g.reg(0x228, len(idx))
        g.reg(0x22F, 1)


def correr(exe, g, nombre, env=None):
    g.w.append(0)
    gp = os.path.join(TRAB, nombre + ".guion")
    sp = os.path.join(TRAB, nombre + "." + os.path.basename(exe) + ".salida")
    g.w.tofile(open(gp, "wb"))
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([exe, gp, sp], capture_output=True, text=True, cwd=TRAB, env=e, timeout=300)
    log = [l for l in p.stderr.splitlines() if "[arnes]" in l or "no compila" in l or "no enlaza" in l or "SABOTAJE" in l]
    datos = open(sp, "rb").read() if os.path.exists(sp) else b""
    return p.returncode, datos, log


def comparar(nombre, g, env_extra=None, sabotaje=0):
    """corre antes y despues; devuelve True si IGUALES (o, con sabotaje, si se detecto la diferencia)"""
    exe_a = os.path.join(A, "equiv_antes.exe")
    exe_n = os.path.join(A, "equiv_nuevo.exe")
    env = dict(env_extra or {})
    rc_a, da, la = correr(exe_a, g, nombre, env)
    env_n = dict(env)
    if sabotaje:
        env_n["SM3DL_BACKEND_SABOTAJE"] = str(sabotaje)
    rc_n, dn, ln = correr(exe_n, g, nombre, env_n)
    igual = da == dn and rc_a == rc_n
    ha = hashlib.sha1(da).hexdigest()[:10]
    hn = hashlib.sha1(dn).hexdigest()[:10]
    ndif = sum(1 for x, y in zip(da, dn) if x != y) + abs(len(da) - len(dn))
    print("%-22s antes: rc %d %7d B sha1 %s | nuevo: rc %d %7d B sha1 %s | %s%s" % (
        nombre, rc_a, len(da), ha, rc_n, len(dn), hn, "IGUAL" if igual else "DISTINTO (%d B)" % ndif,
        "" if da else "  <<< SALIDA VACIA (prueba sin valor)"))
    for l in la[:2]:
        print("     antes :", l[:200])
    for l in ln[:2]:
        print("     nuevo :", l[:200])
    if sabotaje:
        return not igual
    return igual and rc_a == 0 and len(da) > 0


# ------------------------------------------------------------------------------------------------ escenarios
def esc_tev(uber):
    rng = random.Random(77)
    g = nuevo_guion(256, 4, uber)
    g.w.extend((7, 1))
    for k in range(24):
        firma = pr.tev_azar(rng)
        consts = [rgba(rng) for _ in range(6)]
        buf = rgba(rng)
        for j, (s, o, c, e) in enumerate(firma):
            b = pr.TEV_BASE[j]
            cc = consts[j]
            g.reg(b, s); g.reg(b + 1, o); g.reg(b + 2, c); g.reg(b + 3, paquete(cc)); g.reg(b + 4, e)
        g.reg(0x0E0, rng.choice([0, 0xFF00, rng.randrange(256) << 8]))
        g.reg(0x0FD, paquete(buf))
        ent = [dict(vtx=rgba(rng), prim=rgba(rng), sec=rgba(rng), t0=rgba(rng), t1=rgba(rng), t2=rgba(rng)) for _ in range(256)]
        pr.texturas(g, [[e["t%d" % q] for e in ent] for q in range(3)])
        frags = [[[x / 255 for x in e["vtx"]], [x / 255 for x in e["prim"]], [x / 255 for x in e["sec"]],
                  [(i + 0.5) / 256, 0.5, (i + 0.5) / 256, 0.5], [(i + 0.5) / 256, 0.5, 1.0, 1.0]] for i, e in enumerate(ent)]
        pr.dibujar(g, frags)
        g.leer(0, 0, 256, 1)
    return g


def esc_estado():
    rng = random.Random(5)
    g = nuevo_guion(256, 4)
    for d in range(150):
        if rng.random() < 0.3:
            g.limpiar(rng.randrange(1 << 32))
        blend = rng.random() < 0.6
        g.reg(0x100, (1 << 8) if blend else 0)
        g.reg(0x101, rng.randrange(5) | (rng.randrange(5) << 8) | (rng.randrange(15) << 16) | (rng.randrange(15) << 20) |
              (rng.randrange(15) << 24) | (rng.randrange(15) << 28))
        g.reg(0x102, rng.randrange(16))
        g.reg(0x103, rng.randrange(1 << 32))
        g.reg(0x104, rng.randrange(2) | (rng.randrange(8) << 4) | (rng.randrange(256) << 8))
        g.reg(0x105, rng.randrange(2) | (rng.randrange(8) << 4) | (rng.randrange(256) << 8) | (rng.randrange(256) << 16) |
              (rng.randrange(256) << 24))
        g.reg(0x106, rng.randrange(8) | (rng.randrange(8) << 4) | (rng.randrange(8) << 8))
        g.reg(0x107, rng.randrange(2) | (rng.randrange(8) << 4) | (rng.randrange(16) << 8) | (rng.randrange(2) << 12))
        g.reg(0x113, rng.choice([0xF, 0xF, 0]))      # escritura de color
        g.reg(0x115, rng.choice([3, 3, 0]))          # escritura de profundidad
        g.reg(0x116, rng.choice([3, 3, 2, 0]))       # D24S8 / D24 / D16
        g.reg(0x040, rng.choice([0, 1, 2, 3]))       # culling
        g.reg(0x065, rng.choice([0, 1, 3]))          # tijera
        x0, x1 = sorted((rng.randrange(256), rng.randrange(256)))
        g.reg(0x066, x0 | (0 << 16)); g.reg(0x067, x1 | (3 << 16))
        tris_azar(g, rng, rng.randrange(1, 8), 256, 4)
        g.leer(0, 0, 256, 4)
    return g


def esc_mips():
    """texturas con mipmaps, filtros, envolturas, borde y sesgo de LOD al azar (tex_cargar_mips + RbMuestreador)"""
    rng = random.Random(66)
    g = nuevo_guion(256, 4)
    for d in range(40):
        w = rng.choice([16, 32, 64])
        px = array("I", [paquete(rgba(rng)) for _ in range(w * w)])
        g.tex(pr.DIR_TEX[0], w, w, px)
        g.reg(0x81, rng.randrange(1 << 32))                                       # color de borde
        g.reg(0x82, (w << 16) | w)                                                  # dimensiones
        g.reg(0x83, (rng.randrange(2) << 1) | (rng.randrange(2) << 2) | (rng.randrange(8) << 8) | (rng.randrange(8) << 12) |
              (rng.randrange(2) << 24))                                             # mag, min, wrap_t, wrap_s, mip
        g.reg(0x84, rng.randrange(1 << 13) | (rng.randrange(4) << 16) | (rng.randrange(3) << 24))   # bias, lod_max, lod_min
        g.reg(0x85, pr.DIR_TEX[0] // 8)
        g.reg(0x8E, 0)
        g.reg(0x80, 1)
        g.reg(pr.TEV_BASE[0], 3 | (3 << 16)); g.reg(pr.TEV_BASE[0] + 1, 0); g.reg(pr.TEV_BASE[0] + 2, 0)
        v = array("f")
        for k in range(12):
            v.extend((rng.uniform(-1, 1), rng.uniform(-1, 1), -0.5, 1.0))
            for _ in range(5):
                v.extend((rng.uniform(-1, 2), rng.uniform(-1, 2), rng.random(), rng.random()))
        g.mem(pr.DIR_VTX, v.tobytes())
        g.reg(0x228, 12); g.reg(0x22A, 0); g.reg(0x22E, 1)
        g.leer(0, 0, 256, 4)
    return g


def esc_luz(uber):
    rng = random.Random(9)
    g = nuevo_guion(256, 4, uber)
    for d in range(30):
        g.reg(0x1C6, 0)                                            # luz encendida
        g.reg(0x1C2, rng.randrange(8))                             # num luces - 1
        g.reg(0x1C0, rng.randrange(1 << 30))
        g.reg(0x1C3, rng.randrange(1 << 32) & 0xF0FF0FFF | (rng.randrange(9) << 4))
        g.reg(0x1C4, rng.randrange(1 << 32))
        g.reg(0x1D0, rng.randrange(1 << 32)); g.reg(0x1D1, rng.randrange(1 << 32)); g.reg(0x1D2, rng.randrange(1 << 32))
        g.reg(0x1D9, rng.randrange(1 << 32))
        for num in range(8):
            for q in range(12):
                g.reg(0x140 + 0x10 * num + q, rng.randrange(1 << 32))
        for t in range(24):
            g.reg(0x1C5, t << 8)
            for q in range(256):
                g.reg(0x1C8 + (q & 7), rng.randrange(1 << 24))
        g.reg(0x0E0, 5 | (rng.randrange(256) << 8) | (rng.randrange(2) << 16))
        g.reg(0x0E1, rng.randrange(1 << 32))
        g.reg(0x0E6, 0)
        for q in range(128):
            g.reg(0x0E8 + (q & 7), rng.randrange(1 << 24))
        for j in range(6):
            b = pr.TEV_BASE[j]
            g.reg(b, rng.randrange(1 << 32) & 0x00FF0FFF); g.reg(b + 1, rng.randrange(1 << 32) & 0x00FF0FFF)
            g.reg(b + 2, rng.randrange(10) | (rng.randrange(10) << 16)); g.reg(b + 3, rng.randrange(1 << 32))
            g.reg(b + 4, rng.randrange(4) | (rng.randrange(4) << 16))
        pr.texturas(g, [[rgba(rng) for _ in range(256)] for _ in range(3)])
        tris_azar(g, rng, 4, 256, 4)
        g.leer(0, 0, 256, 4)
    return g


def esc_vertices(modo):
    rng = random.Random(21)
    g = nuevo_guion(256, 4)
    for d in range(20):
        tris_azar(g, rng, rng.randrange(2, 30), 256, 4, indices=modo)
        g.reg(0x25E, rng.choice([0, 0, 0x100, 0x200, 0x300]))      # topologia lista / tira / abanico / shader
        g.reg(0x22F, 1) if modo else g.reg(0x22E, 1)
        g.leer(0, 0, 256, 4)
        g.reg(0x25E, 0)
    return g


def esc_memoria():
    rng = random.Random(33)
    W, H = 240, 400
    g = nuevo_guion(W, H)
    for fmt, bpp in ((0, 4), (1, 3), (2, 2), (3, 2), (4, 2)):
        g.reg(0x117, fmt << 16)
        g.limpiar(rng.randrange(1 << 32))
        tris_azar(g, rng, 12, W, H)
        g.w.extend((9, pr.DIR_COLOR, W * H * bpp))                  # antes_de_leer: baja el RT a memoria y la vuelca
        g.reg(0x117, fmt << 16)
    g.reg(0x117, 0)
    # MemoryFill: completo y parcial, color y profundidad
    g.limpiar(0x11223344)
    tris_azar(g, rng, 6, W, H)
    g.w.extend((10, pr.DIR_COLOR, pr.DIR_COLOR + W * H * 4, 0xFFCC8844, 0x200))
    g.leer(0, 0, W, 4)
    tris_azar(g, rng, 6, W, H)
    g.w.extend((10, pr.DIR_COLOR + 4096, pr.DIR_COLOR + 8192, 0x0055AAFF, 0x200))
    g.w.extend((9, pr.DIR_COLOR, W * H * 4))
    g.w.extend((10, pr.DIR_DEPTH, pr.DIR_DEPTH + W * H * 4, 0x80123456, 0x200))
    tris_azar(g, rng, 6, W, H)
    g.w.extend((9, pr.DIR_COLOR, W * H * 4))
    # cambio de forma del RT en la misma direccion
    g.reg(0x11E, 128 | (99 << 12))
    tris_azar(g, rng, 3, 128, 100)
    g.w.extend((9, pr.DIR_COLOR, 128 * 100 * 4))
    return g


def esc_alta(escala):
    """RT 240x400 a escala interna, DisplayTransfer diferido y pantalla en alta (giro en GPU, lectura asincrona)"""
    rng = random.Random(44)
    W, H = 240, 400
    g = nuevo_guion(W, H)
    g.w.extend((11, escala))
    g.limpiar(rng.randrange(1 << 32))
    for cuadro in range(3):
        tris_azar(g, rng, 10, W, H)
        g.w.extend((12, pr.DIR_COLOR, DIR_SAL, W * H * 4, W * H * 4, W, H, W, H, 0))
        g.w.extend((13, DIR_SAL, 0, W * 4, 400, 240))
        g.w.extend((9, DIR_SAL, 4096))
    g.w.extend((21,))
    g.w.extend((9, DIR_SAL, W * H * 4))
    return g


def esc_pres(escala):
    rng = random.Random(55)
    W, H = 240, 400
    g = nuevo_guion(W, H)
    g.w.extend((11, escala))
    g.limpiar(rng.randrange(1 << 32))
    tris_azar(g, rng, 16, W, H)
    g.w.extend((12, pr.DIR_COLOR, DIR_SAL, W * H * 4, W * H * 4, W, H, W, H, 0))
    g.w.extend((13, DIR_SAL, 0, W * 4, 400, 240))
    g.w.extend((19, DIR_SAL, 0, W * 4, 400, 240))
    g.w.extend((14, 64, 64))
    g.w.extend((15, -1 & 0xFFFFFFFF, 2, 3, 62, 60, 0))
    g.w.extend((15, 0, 0, 0, 32, 32, 1))
    g.w.extend((16, 0, 40, 30, 7, 0, 0, 40, 30))
    g.w.extend((17, 0, 10, 10, 50, 40, 1))
    g.w.extend((16, 1, 64, 64, 9, 0, 0, 64, 64))
    g.w.extend((17, 1, 0, 0, 64, 64, 0))
    g.w.extend((16, 0, 40, 30, 8, 5, 5, 20, 20))
    g.w.extend((17, 0, 0, 0, 30, 30, 0))
    g.w.extend((18, 64, 64))
    g.w.extend((20, 0, 0, 64, 64, 1))
    g.w.extend((18, 64, 64))
    g.w.extend((23,))
    # instantaneas (interpolacion): guarda, repinta, restaura
    g.w.extend((22, DIR_SAL, 0))
    g.w.extend((13, DIR_SAL, 0, W * 4, 400, 240))
    tris_azar(g, rng, 16, W, H)
    g.w.extend((12, pr.DIR_COLOR, DIR_SAL, W * H * 4, W * H * 4, W, H, W, H, 0))
    g.w.extend((13, DIR_SAL, 0, W * 4, 400, 240))
    g.w.extend((22, DIR_SAL, 1))
    g.w.extend((13, DIR_SAL, 0, W * 4, 400, 240))
    return g


ESCENARIOS = {
    "tev": lambda: (esc_tev(0), {}),
    "tev_uber": lambda: (esc_tev(1), {}),
    "estado": lambda: (esc_estado(), {}),
    "mips": lambda: (esc_mips(), {}),
    "luz": lambda: (esc_luz(0), {}),
    "luz_uber": lambda: (esc_luz(1), {}),
    "vertices_arrays": lambda: (esc_vertices(None), {}),
    "vertices_u8": lambda: (esc_vertices("u8"), {}),
    "vertices_u16": lambda: (esc_vertices("u16"), {}),
    "vertices_cpu": lambda: (esc_vertices("u16"), {"SM3DL_VTX_CPU": "1"}),
    "vertices_sin_elem": lambda: (esc_vertices("u16"), {"SM3DL_VTX_CPU": "1", "SM3DL_SIN_ELEMENTOS": "1"}),
    "memoria": lambda: (esc_memoria(), {}),
    "alta_x2": lambda: (esc_alta(2), {}),
    "alta_x3": lambda: (esc_alta(3), {}),
    "alta_x2_sinc": lambda: (esc_alta(2), {"SM3DL_ALTA_ASINC": "0"}),
    "alta_x2_sin_cero_copia": lambda: (esc_alta(2), {"SM3DL_ALTA_CERO_COPIA": "0"}),
    "alta_x2_cpu": lambda: (esc_alta(2), {"SM3DL_ALTA_CPU": "1"}),
    "alta_x2_verificar": lambda: (esc_alta(2), {"SM3DL_ALTA_VERIFICAR": "1"}),
    "pres_x2": lambda: (esc_pres(2), {}),
    "pres_x4": lambda: (esc_pres(4), {}),
    "diferido_apagado": lambda: (esc_alta(2), {"SM3DL_SIN_DIFERIDO": "1"}),
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sab = 0
    if "--sabotaje" in sys.argv:
        sab = int(sys.argv[sys.argv.index("--sabotaje") + 1])
        args = [a for a in args if a != str(sab)]
    os.makedirs(os.path.join(TRAB, "extraido", "shaders"), exist_ok=True)   # la cache de programas escribe aqui
    nombres = args or list(ESCENARIOS)
    bien = 0
    for n in nombres:
        g, env = ESCENARIOS[n]()
        if comparar(n, g, env, sab):
            bien += 1
    print("\nRESULTADO: %d/%d escenarios %s" % (bien, len(nombres), "con la diferencia DETECTADA (sabotaje)" if sab else "IGUALES"))
    sys.exit(0 if bien == len(nombres) else 1)


if __name__ == "__main__":
    main()
