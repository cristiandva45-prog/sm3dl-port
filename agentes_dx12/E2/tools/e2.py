r"""ARNES DE COMPARACION POR PIXEL GL vs D3D12 (agente E2, 9 oct 2026; paso 8 del plan D3D12). NO corre el juego: corre
agentes_dx12\E2\prueba_e2.exe (raster_gl.c REAL + pica + gsp sobre VRAM falsa; ver prueba_e2.c) DOS veces con el MISMO
guion, una por backend (SM3DL_BACKEND), y compara la salida segmento a segmento con el mapa que escribe el exe:
  R (codigo de retorno): EXACTO.   P (pixeles RGBA8/BGRA8): |a-b| <= tol por byte.
  M (memoria del 3DS): por canal en las unidades del formato GSP (RGBA8/RGB8 por byte; 565/5551/4444 por canal).
tol = 1 por defecto (caminos float: float->UNORM8 en el medio punto no es exacto entre APIs; ver principal.md). Cada
escenario dura segundos en un nucleo. Los escenarios son los de A (agentes_dx12\A\tools\equiv.py, importado tal cual) +
los propios de E2 (limpiar, limpiar_memoria: sin dibujar, para probar C1/C4/C6 antes de que exista el dibujo).

Uso (desde cualquier lado; py -I):
  py -I agentes_dx12\E2\tools\e2.py [escenario ...] [--a gl] [--b d3d12] [--tol N] [--sab-gl N] [--sab-cmp N] [--sab-d3d N]
        sin --a/--b: gl contra d3d12. --sab-gl N: el lado B corre con SM3DL_BACKEND_SABOTAJE=N (sabotaje del backend);
        --sab-cmp N: el lado B corre con E2_SABOTAJE=N (sabotaje del comparador); con cualquiera de los dos, exit 0 solo
        si la diferencia se DETECTO en todos los escenarios con salida. --sab-env VAR=VAL: sabotaje propio de una parte en el lado B
        (p. ej. SM3DL_C3_SABOTAJE=1). --sab-d3d N: igual que --sab-gl (mismo env)
        pero para documentar que se sabotea el D3D12 (si su parte lo implementa).
  py -I agentes_dx12\E2\tools\e2.py autoprueba     control GL vs GL exacto + los 4 sabotajes (prueba del arnes)
  py -I agentes_dx12\E2\tools\e2.py volcar         corre todo en GL volcando los textos GLSL a E2\glsl_arnes\
  py -I agentes_dx12\E2\tools\e2.py convertir      glsl_arnes -> DXIL (cadena de B) -> E2\cache_arnes\ y arma la cache
                                                   de E2\trabajo\extraido\shaders\cache_d3d12\ (= la de B + la del arnes)
  py -I agentes_dx12\E2\tools\e2.py lista          escenarios y que partes del D3D12 necesita cada uno
Salida: exit 0 si todo igual dentro de la tolerancia (o, con sabotaje, si se detecto)."""
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys

E2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(E2))
TRAB = os.path.join(E2, "trabajo")
EXE = os.path.join(E2, "prueba_e2.exe")
GLSL_ARNES = os.path.join(E2, "glsl_arnes")
CACHE_ARNES = os.path.join(E2, "cache_arnes")
CACHE_TRAB = os.path.join(TRAB, "extraido", "shaders", "cache_d3d12")
CACHE_JUEGO = [os.path.join(RAIZ, "extraido", "shaders", "cache_d3d12"), os.path.join(RAIZ, "agentes_dx12", "B", "cache_d3d12")]

_cwd = os.getcwd()
os.chdir(RAIZ)                         # equiv.py de A toma RAIZ = cwd al importarse
spec = importlib.util.spec_from_file_location("equiv_a", os.path.join(RAIZ, "agentes_dx12", "A", "tools", "equiv.py"))
eq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eq)
os.chdir(_cwd)
pr = eq.pr


# ------------------------------------------------------------------------------------------------ escenarios propios
def esc_limpiar():
    """sin dibujar: limpiar con colores al azar y leer (rt_crear, rt_limpiar, rt_leer): C1 + C4 + C6"""
    import random
    rng = random.Random(12)
    g = eq.nuevo_guion(256, 4)
    for k in range(12):
        g.limpiar(rng.randrange(1 << 32))
        g.leer(0, 0, 256, 4)
        g.leer(rng.randrange(200), rng.randrange(3), 40, 1)
    return g


def esc_limpiar_memoria():
    """sin dibujar: limpiar y bajar el RT a memoria en los 5 formatos (antes_de_leer -> lecturas): C1 + C4 + C6 (+C5 en alta)"""
    import random
    rng = random.Random(13)
    W, H = 240, 400
    g = eq.nuevo_guion(W, H)
    for fmt, bpp in ((0, 4), (1, 3), (2, 2), (3, 2), (4, 2)):
        g.reg(0x117, fmt << 16)
        g.limpiar(rng.randrange(1 << 32))
        g.w.extend((9, pr.DIR_COLOR, W * H * bpp))
    return g


def esc_estado_var(modo):
    """= esc_estado de A con el blend forzado, para AISLAR: modo 'blend' (todo dibujo con blend), 'copy' (logic op COPY =
    sin blend, lo unico que D3D12 emula sobre RT UNORM), 'logic' (logic op al azar: informativo, D3D12 NO lo emula)."""
    import random
    rng = random.Random(5)
    g = eq.nuevo_guion(256, 4)
    for d in range(150):
        if rng.random() < 0.3:
            g.limpiar(rng.randrange(1 << 32))
        g.reg(0x100, (1 << 8) if modo == "blend" else 0)
        g.reg(0x101, rng.randrange(5) | (rng.randrange(5) << 8) | (rng.randrange(15) << 16) | (rng.randrange(15) << 20) |
              (rng.randrange(15) << 24) | (rng.randrange(15) << 28))
        lo = rng.randrange(16)
        g.reg(0x102, 3 if modo == "copy" else lo)
        g.reg(0x103, rng.randrange(1 << 32))
        g.reg(0x104, rng.randrange(2) | (rng.randrange(8) << 4) | (rng.randrange(256) << 8))
        g.reg(0x105, rng.randrange(2) | (rng.randrange(8) << 4) | (rng.randrange(256) << 8) | (rng.randrange(256) << 16) |
              (rng.randrange(256) << 24))
        g.reg(0x106, rng.randrange(8) | (rng.randrange(8) << 4) | (rng.randrange(8) << 8))
        g.reg(0x107, rng.randrange(2) | (rng.randrange(8) << 4) | (rng.randrange(16) << 8) | (rng.randrange(2) << 12))
        g.reg(0x113, rng.choice([0xF, 0xF, 0]))
        g.reg(0x115, rng.choice([3, 3, 0]))
        g.reg(0x116, rng.choice([3, 3, 2, 0]))
        g.reg(0x040, rng.choice([0, 1, 2, 3]))
        g.reg(0x065, rng.choice([0, 1, 3]))
        x0, x1 = sorted((rng.randrange(256), rng.randrange(256)))
        g.reg(0x066, x0 | (0 << 16)); g.reg(0x067, x1 | (3 << 16))
        eq.tris_azar(g, rng, rng.randrange(1, 8), 256, 4)
        g.leer(0, 0, 256, 4)
    return g


def esc_pres_pasos(escala):
    """los pasos de esc_pres de A, AISLADOS: cada uno empieza en negro (pres_empezar) y se lee la ventana justo despues
    (op 18), asi un DISTINTO dice que paso fue: base punto escalada (C5 copiar a la ventana), base lineal, capa lineal
    1:1, capa punto 1:1, capa punto ESCALADA 40x30 -> 30x30 tras subida parcial (C1 pres_capa)."""
    import random
    rng = random.Random(55)
    W, H = 240, 400
    g = eq.nuevo_guion(W, H)
    g.w.extend((11, escala))
    g.limpiar(rng.randrange(1 << 32))
    eq.tris_azar(g, rng, 16, W, H)
    g.w.extend((12, pr.DIR_COLOR, eq.DIR_SAL, W * H * 4, W * H * 4, W, H, W, H, 0))
    g.w.extend((13, eq.DIR_SAL, 0, W * 4, 400, 240))
    g.w.extend((19, eq.DIR_SAL, 0, W * 4, 400, 240))
    g.w.extend((16, 0, 40, 30, 7, 0, 0, 40, 30))
    g.w.extend((16, 1, 64, 64, 9, 0, 0, 64, 64))
    pasos = [(15, -1 & 0xFFFFFFFF, 2, 3, 62, 60, 0), (15, -1 & 0xFFFFFFFF, 0, 0, 64, 64, 0), (15, 0, 0, 0, 32, 32, 1),
             (17, 0, 10, 10, 50, 40, 1), (17, 1, 0, 0, 64, 64, 0), (17, 0, 0, 0, 30, 30, 0), (17, 0, 3, 7, 61, 50, 1)]
    for p in pasos:
        g.w.extend((14, 64, 64))
        g.w.extend(p)
        g.w.extend((18, 64, 64))
    g.w.extend((16, 0, 40, 30, 8, 5, 5, 20, 20))     # subida parcial de la capa 0 y otra vez escalada
    g.w.extend((14, 64, 64)); g.w.extend((17, 0, 0, 0, 30, 30, 0)); g.w.extend((18, 64, 64))
    return g


def esc_mips():
    """= esc_mips de A CORREGIDO. En el de A solo se fijaba la etapa 0 del TEV (textura 0); las etapas 1-5 quedaban en
    cero = REPLACE del color PRIMARIO, asi que la salida era el color del vertice y la textura NO SE MUESTREABA: medido
    9 oct, cambiar el contenido de las 40 texturas deja la salida identica byte a byte (y SM3DL_C3_SABOTAJE=1/2 no se
    veia). Aqui las etapas 1-5 pasan la anterior (fuente 0xF, REPLACE). Mismo rng y mismo resto que el de A."""
    import random
    from array import array
    rng = random.Random(66)
    g = eq.nuevo_guion(256, 4)
    for j in range(1, 6):
        b = pr.TEV_BASE[j]
        g.reg(b, 0xF | (0xF << 16)); g.reg(b + 1, 0); g.reg(b + 2, 0); g.reg(b + 4, 0)
    for d in range(40):
        w = rng.choice([16, 32, 64])
        px = array("I", [eq.paquete(eq.rgba(rng)) for _ in range(w * w)])
        g.tex(pr.DIR_TEX[0], w, w, px)
        g.reg(0x81, rng.randrange(1 << 32))
        g.reg(0x82, (w << 16) | w)
        g.reg(0x83, (rng.randrange(2) << 1) | (rng.randrange(2) << 2) | (rng.randrange(8) << 8) | (rng.randrange(8) << 12) |
              (rng.randrange(2) << 24))
        g.reg(0x84, rng.randrange(1 << 13) | (rng.randrange(4) << 16) | (rng.randrange(3) << 24))
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


def esc_viewport():
    """viewport PARCIAL y corrido (los de A usan siempre el RT entero, donde un viewport volteado o corrido no se ve):
    RT 240x400 (como el juego), 12 viewports al azar (offset x/y, tamano), triangulos y lectura del RT entero. D2."""
    import random
    rng = random.Random(14)
    W, H = 240, 400
    g = eq.nuevo_guion(W, H)
    g.limpiar(0x10203040)
    for k in range(12):
        vw, vh = rng.randrange(16, W), rng.randrange(16, H)
        vx, vy = rng.randrange(0, W - vw + 1), rng.randrange(0, H - vh + 1)
        g.reg(0x041, pr.f24(vw / 2)); g.reg(0x043, pr.f24(vh / 2))
        g.reg(0x068, (vx & 0x3FF) | ((vy & 0x3FF) << 16))
        eq.tris_azar(g, rng, 6, W, H)
        g.leer(0, 0, W, H)
    return g


def esc_memoria():
    """= esc_memoria de A, salvo el RT que cambia de forma: 128x96 (multiplo de 8) en vez de 128x100. Con 100 filas la
    lectura de memoria cubre la media fila de tiles 12,5 -> 13 (filas 100-103 FUERA del RT): contenido indefinido y el
    GL mismo da distinto contra si mismo ~1 de cada 6 corridas (190 B, medido 9 oct). Asi el control GL vs GL es exacto."""
    import random
    from array import array
    rng = random.Random(33)
    W, H = 240, 400
    g = eq.nuevo_guion(W, H)
    for fmt, bpp in ((0, 4), (1, 3), (2, 2), (3, 2), (4, 2)):
        g.reg(0x117, fmt << 16)
        g.limpiar(rng.randrange(1 << 32))
        eq.tris_azar(g, rng, 12, W, H)
        g.w.extend((9, pr.DIR_COLOR, W * H * bpp))
        g.reg(0x117, fmt << 16)
    g.reg(0x117, 0)
    g.limpiar(0x11223344)
    eq.tris_azar(g, rng, 6, W, H)
    g.w.extend((10, pr.DIR_COLOR, pr.DIR_COLOR + W * H * 4, 0xFFCC8844, 0x200))
    g.leer(0, 0, W, 4)
    eq.tris_azar(g, rng, 6, W, H)
    g.w.extend((10, pr.DIR_COLOR + 4096, pr.DIR_COLOR + 8192, 0x0055AAFF, 0x200))
    g.w.extend((9, pr.DIR_COLOR, W * H * 4))
    g.w.extend((10, pr.DIR_DEPTH, pr.DIR_DEPTH + W * H * 4, 0x80123456, 0x200))
    eq.tris_azar(g, rng, 6, W, H)
    g.w.extend((9, pr.DIR_COLOR, W * H * 4))
    g.reg(0x11E, 128 | (95 << 12))
    eq.tris_azar(g, rng, 3, 128, 96)
    g.w.extend((9, pr.DIR_COLOR, 128 * 96 * 4))
    return g


PARTES = {   # que partes del D3D12 hacen falta (orientativo, para leer el resultado mientras avanzan)
    "limpiar": "C1 C4 C6", "limpiar_memoria": "C1 C4 C6",
    "tev": "C1-C4 C6 D1-D5", "tev_uber": "C1-C4 C6 D1-D5 (F_UBER)", "estado": "C1 C4 C6 D1-D5 (blend/stencil/cull)",
    "mips": "C2 C3 + dibujo", "luz": "C2 C3 (LUT RG32F) + dibujo + GS", "luz_uber": "idem + F_UBER",
    "vertices_arrays": "D4 D5", "vertices_u8": "D4 D5 (indices)", "vertices_u16": "D4 D5", "vertices_cpu": "D4 D5 floats",
    "vertices_sin_elem": "D4 D5", "memoria": "C4 C6 + dibujo", "alta_x2": "C5 (reducir/girar) C6 (asinc)",
    "alta_x3": "C5 C6", "alta_x2_sinc": "C5 C6", "alta_x2_sin_cero_copia": "C5 C6 (no persistente)", "alta_x2_cpu": "C5 C6",
    "alta_x2_verificar": "C5 C6", "pres_x2": "C1 (ventana/capas/presentar) C5 (copiar a ventana) C6 (leer ventana)",
    "pres_x4": "C1 C5 C6", "diferido_apagado": "C6",
}
ESCENARIOS = {"limpiar": lambda: (esc_limpiar(), {}), "limpiar_memoria": lambda: (esc_limpiar_memoria(), {})}
ESCENARIOS.update(eq.ESCENARIOS)
ESCENARIOS["memoria"] = lambda: (esc_memoria(), {})   # version E2 (ver esc_memoria)
ESCENARIOS["mips_a"] = eq.ESCENARIOS["mips"]               # el de A tal cual (NO muestrea: ver esc_mips)
ESCENARIOS["mips"] = lambda: (esc_mips(), {})
ESCENARIOS["viewport"] = lambda: (esc_viewport(), {})
ESCENARIOS["estado_blend"] = lambda: (esc_estado_var("blend"), {})
ESCENARIOS["estado_copy"] = lambda: (esc_estado_var("copy"), {})
ESCENARIOS["estado_logic"] = lambda: (esc_estado_var("logic"), {})
ESCENARIOS["pres_pasos_x2"] = lambda: (esc_pres_pasos(2), {})
PARTES.update({"estado_blend": "D3 D5 (blend)", "estado_copy": "D3 D5 (logic op COPY = sin blend)",
               "estado_logic": "D3 (logic op: D3D12 NO lo emula en UNORM; informativo)",
               "viewport": "D2 (viewport parcial)", "pres_pasos_x2": "C5 (base = copiar a ventana) / C1 (capas), un paso por lectura"})


# ------------------------------------------------------------------------------------------------ correr / comparar
def correr(backend, g_words, nombre, env_extra=None, etiqueta=None):
    os.makedirs(os.path.join(TRAB, "extraido", "shaders"), exist_ok=True)
    gp = os.path.join(TRAB, nombre + ".guion")
    et = etiqueta or backend
    sp = os.path.join(TRAB, "%s.%s.salida" % (nombre, et))
    with open(gp, "wb") as f:
        g_words.tofile(f)
    for r in (sp, sp + ".mapa"):
        if os.path.exists(r):
            os.remove(r)
    e = dict(os.environ)
    for k in ("SM3DL_BACKEND_SABOTAJE", "E2_SABOTAJE", "E2_VOLCAR_GLSL"):
        e.pop(k, None)
    e["SM3DL_BACKEND"] = backend
    e.update(env_extra or {})
    err_previo = ""
    for intento in range(2):   # 1 reintento SOLO si se cae (0xC0000005): el GL se cae ~1-3 % al iniciar, tambien el exe de A
        try:
            p = subprocess.run([EXE, gp, sp], capture_output=True, text=True, cwd=TRAB, env=e, timeout=120)
            rc, err = p.returncode, p.stderr
        except subprocess.TimeoutExpired:
            rc, err = -999, "[arnes] TIMEOUT 120 s"
        if rc not in CAIDAS:
            break
        REINTENTOS.append("%s/%s: %s" % (nombre, et, ([l for l in err.splitlines() if "CAIDA" in l] or ["rc %d" % rc])[0][:160]))
        err_previo = err
    if err_previo:
        err = "[arnes] REINTENTO tras caida\n" + err
    with open(sp + ".log", "w", encoding="utf-8") as f:
        f.write(err)
    datos = open(sp, "rb").read() if os.path.exists(sp) else b""
    mapa = []
    if os.path.exists(sp + ".mapa"):
        for l in open(sp + ".mapa"):
            c = l.split()
            if len(c) == 6:
                mapa.append((int(c[0]), int(c[1]), int(c[2]), int(c[3]), c[4], int(c[5])))
    return rc, datos, mapa, err


CAIDAS = (3221225477, -1073741819, 139)
REINTENTOS = []


def canales(fmt, b, k):
    """canales del pixel k (bytes) segun el formato GSP de la memoria; None = comparar por byte"""
    v = b[2 * k] | (b[2 * k + 1] << 8)
    if fmt == 2: return (v >> 11, (v >> 5) & 63, v & 31)
    if fmt == 3: return (v >> 11, (v >> 6) & 31, (v >> 1) & 31, v & 1)
    if fmt == 4: return (v >> 12, (v >> 8) & 15, (v >> 4) & 15, v & 15)
    return None


def diferencias(da, db, mapa, tol):
    """-> (unidades comparadas, distintas, fuera de tolerancia, max diff, primer segmento fuera {op,cod,tipo}, por_cod)"""
    tot = dist = fuera = maxd = 0
    primero = None
    por_cod = {}
    for (opn, cod, off, n, tipo, fmt) in mapa:
        a, b = da[off:off + n], db[off:off + n]
        if len(a) != n or len(b) != n:
            fuera += n; dist += n; tot += n
            primero = primero or (opn, cod, tipo, "truncado")
            continue
        if a == b:
            tot += n if tipo != "M" or fmt < 2 else n // 2
            continue
        f_seg = 0
        if tipo == "R":
            tot += 1; dist += 1; fuera += 1; f_seg = 1
            maxd = max(maxd, 999)
        elif tipo == "M" and fmt >= 2:
            for k in range(n // 2):
                ca, cb = canales(fmt, a, k), canales(fmt, b, k)
                tot += 1
                if ca != cb:
                    dist += 1
                    d = max(abs(x - y) for x, y in zip(ca, cb))
                    maxd = max(maxd, d)
                    if d > tol: fuera += 1; f_seg += 1
        else:
            for x, y in zip(a, b):
                tot += 1
                if x != y:
                    dist += 1
                    d = abs(x - y)
                    if d > maxd: maxd = d
                    if d > tol: fuera += 1; f_seg += 1
        if f_seg:
            por_cod[cod] = por_cod.get(cod, 0) + f_seg
            if not primero:
                primero = (opn, cod, tipo, "")
    return tot, dist, fuera, maxd, primero, por_cod


RE_ARNES = re.compile(r"etapas (\d+) \((\d+) fallidas\)")


def resumen_log(err):
    l = [x for x in err.splitlines() if "[arnes]" in x]
    m = RE_ARNES.search(err)
    etapas_mal = int(m.group(2)) if m else -1
    avisos = [x for x in err.splitlines() if "[raster]" in x and ("pendiente" in x or "FALL" in x.upper() or "no " in x)]
    return l, etapas_mal, avisos


def comparar(nombre, g, env_extra, a, b, tol, env_b=None, sabotaje=False):
    g.w.append(0)
    rc_a, da, ma, ea = correr(a, g.w, nombre, env_extra, a + "_A")
    eb_env = dict(env_extra or {})
    eb_env.update(env_b or {})
    rc_b, db, mb, eb = correr(b, g.w, nombre, eb_env, b + "_B")
    la, mal_a, _ = resumen_log(ea)
    lb, mal_b, avb = resumen_log(eb)
    mapa = ma if len(ma) >= len(mb) else mb
    tot, dist, fuera, maxd, primero, por_cod = diferencias(da, db, mapa, tol)
    if len(da) != len(db):
        fuera += abs(len(da) - len(db))
    sin_valor = (not da) or rc_a != 0 or mal_a > 0
    sin_valor_b = (not db) or rc_b not in (0, 1) or mal_b > 0 or rc_b == -999
    n_uber = eb.count("sin DXIL para el fragmento")      # D1: cada caida al uber se loguea siempre
    n_sin_vs = eb.count("sin DXIL para el VS")
    if n_sin_vs or (n_uber and nombre in ("tev",)):         # tev usa PRUEBA_TEV: el uber NO tiene ese modo (D1)
        sin_valor_b = True
    if sin_valor:
        ver = "SIN VALOR (lado A: rc %d, %d B, %d etapas fallidas)" % (rc_a, len(da), mal_a)
    elif sin_valor_b and not sabotaje:
        ver = "B NO LISTO (rc %d, %d B, %d etapas fallidas)" % (rc_b, len(db), mal_b)
    elif fuera == 0 and rc_a == rc_b:
        ver = "IGUAL" if dist == 0 else "IGUAL +-%d (%d distintos, max %d)" % (tol, dist, maxd)
    else:
        ver = "DISTINTO (%d fuera de +-%d de %d, max %d, 1er op #%s cod %s %s)" % (
            fuera, tol, tot, maxd, primero[0] if primero else "?", primero[1] if primero else "?",
            primero[2] if primero else "")
    if n_uber or n_sin_vs:
        ver += "  [B: %d FS al uber, %d VS sin DXIL: correr volcar+convertir]" % (n_uber, n_sin_vs)
    print("%-22s %s: rc %d %8d B | %s: rc %d %8d B | %s" % (nombre, a, rc_a, len(da), b, rc_b, len(db), ver))
    if por_cod and not sabotaje:
        print("%22s fuera por op: %s" % ("", ", ".join("op%d=%d" % kv for kv in sorted(por_cod.items()))))
    if not sabotaje and (ver.startswith("B NO") or ver.startswith("DIST")):
        for l in (lb + avb)[:4]:
            print("%22s B: %s" % ("", l[:180]))
    if sabotaje:
        if sin_valor or sin_valor_b:
            return None
        return fuera > 0 or rc_a != rc_b
    if sin_valor or sin_valor_b:
        return None
    return fuera == 0 and rc_a == rc_b


def correr_lote(nombres, a, b, tol, env_b=None, sabotaje=False, titulo=""):
    if titulo:
        print("--- " + titulo)
    bien = mal = nulo = 0
    for n in nombres:
        g, env = ESCENARIOS[n]()
        r = comparar(n, g, env, a, b, tol, env_b, sabotaje)
        if r is None: nulo += 1
        elif r: bien += 1
        else: mal += 1
    que = "con la diferencia DETECTADA" if sabotaje else "IGUALES (tol +-%d)" % tol
    print("RESULTADO: %d/%d %s; %d distintos%s; %d sin valor / B no listo\n" % (
        bien, len(nombres), que, mal, " (NO detectados)" if sabotaje else "", nulo))
    return bien, mal, nulo


# ------------------------------------------------------------------------------------------------ shaders del arnes
def volcar():
    os.makedirs(GLSL_ARNES, exist_ok=True)
    for n, (fn) in ESCENARIOS.items():
        g, env = fn()
        g.w.append(0)
        e = dict(env)
        e["E2_VOLCAR_GLSL"] = GLSL_ARNES
        rc, d, m, err = correr("gl", g.w, n, e, "gl_volcar")
        print("%-22s rc %d %s" % (n, rc, (resumen_log(err)[0] or ["?"])[-1][:150]))
    print("%d textos en %s" % (len(os.listdir(GLSL_ARNES)), GLSL_ARNES))


def convertir():
    """convierte cada texto volcado con la cadena de B (importada; no se tocan sus archivos) y arma la cache de trabajo"""
    spec = importlib.util.spec_from_file_location("cadena_b", os.path.join(RAIZ, "agentes_dx12", "B", "cadena_shaders.py"))
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    tmp = os.path.join(E2, "tmp_cadena")
    os.makedirs(tmp, exist_ok=True)
    os.makedirs(CACHE_ARNES, exist_ok=True)
    cb.GLSL = GLSL_ARNES                      # convertir_uno lee GLSL\<rel>
    ext = {"vert": "vert", "frag": "frag", "geom": "geom"}
    bien = mal = 0
    for f in sorted(os.listdir(GLSL_ARNES)):
        pre, resto = f.split("_", 1)
        h, e = resto.split(".")
        texto = open(os.path.join(GLSL_ARNES, f), "rb").read()
        if "%08X" % cb.fnv_texto(texto) != h:
            print("hash NO coincide:", f); mal += 1; continue
        nom = "G_FLIP.dxil" if pre == "G" else "%s_%s.dxil" % (pre, h)
        dest = os.path.join(CACHE_ARNES, nom)
        if os.path.exists(dest):
            bien += 1; continue
        r = cb.convertir_uno(f, True, tmp)
        if r["dxil"] != 1:
            print("FALLA %s en %s: %s" % (f, r["fallo_en"], r["causa"])); mal += 1; continue
        shutil.copyfile(os.path.join(tmp, f + ".dxil"), dest)
        bien += 1
    print("cache del arnes: %d DXIL bien, %d mal -> %s" % (bien, mal, CACHE_ARNES))
    armar_cache_trabajo()
    return mal == 0


def armar_cache_trabajo():
    os.makedirs(CACHE_TRAB, exist_ok=True)
    origen = next((c for c in CACHE_JUEGO if os.path.isdir(c)), None)
    n = 0
    for d in ([origen] if origen else []) + [CACHE_ARNES]:
        for f in os.listdir(d):
            src = os.path.join(d, f)
            if os.path.isfile(src) and not os.path.exists(os.path.join(CACHE_TRAB, f)):
                shutil.copyfile(src, os.path.join(CACHE_TRAB, f)); n += 1
    print("cache de trabajo %s: +%d archivos (juego: %s)" % (CACHE_TRAB, n, origen))


# ------------------------------------------------------------------------------------------------ main
def opt(nombre, defecto):
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else defecto


def main():
    if not os.path.exists(EXE):
        raise SystemExit("falta %s: py -I agentes_dx12\\E2\\tools\\construir_e2.py" % EXE)
    vals = {opt(k, None) for k in ("--a", "--b", "--tol", "--sab-gl", "--sab-cmp", "--sab-d3d", "--sab-env")}
    args = [x for x in sys.argv[1:] if not x.startswith("--") and x not in vals]
    if args[:1] == ["volcar"]: return volcar()
    if args[:1] == ["convertir"]: sys.exit(0 if convertir() else 1)
    if args[:1] == ["lista"]:
        for n in ESCENARIOS: print("%-22s %s" % (n, PARTES.get(n, "")))
        return
    tol = int(opt("--tol", "1"))
    if args[:1] == ["autoprueba"]:
        nombres = args[1:] or ["limpiar", "tev", "estado", "mips", "viewport", "memoria", "alta_x2", "pres_x2"]
        ok = True
        b, m, z = correr_lote(nombres, "gl", "gl", 0, titulo="CONTROL GL vs GL, EXACTO (debe dar todo IGUAL, 0 distintos)")
        ok &= b == len(nombres)
        b, m, z = correr_lote(nombres, "gl", "gl", 1, {"E2_SABOTAJE": "1"}, False,
                              "SABOTAJE CMP 1 (xor 1 = +-1 en todo pixel) con tol 1: debe PASAR")
        ok &= b == len(nombres)
        b, m, z = correr_lote(nombres, "gl", "gl", 0, {"E2_SABOTAJE": "1"}, True, "SABOTAJE CMP 1 EXACTO: debe DETECTAR")
        ok &= m == 0 and b > 0
        b, m, z = correr_lote(nombres, "gl", "gl", 1, {"E2_SABOTAJE": "2"}, True, "SABOTAJE CMP 2 (un byte +-2) con tol 1: debe DETECTAR")
        ok &= m == 0 and b > 0
        con_r = [x for x in nombres if x.startswith(("alta", "pres"))] or ["alta_x2"]
        b, m, z = correr_lote(con_r, "gl", "gl", 1, {"E2_SABOTAJE": "3"}, True,
                              "SABOTAJE CMP 3 (retorno +1; solo escenarios con codigos de retorno): debe DETECTAR")
        ok &= m == 0 and b > 0
        b, m, z = correr_lote([x for x in nombres if x != "limpiar"], "gl", "gl", 1, {"SM3DL_BACKEND_SABOTAJE": "1"}, True,
                              "SABOTAJE BACKEND GL 1 (sin canal azul) con tol 1: debe DETECTAR (limpiar no dibuja: excluido)")
        ok &= m == 0 and b > 0
        print("AUTOPRUEBA:", "BIEN" if ok else "MAL", "| reintentos por caida: %d" % len(REINTENTOS))
        for r in REINTENTOS: print("   ", r)
        sys.exit(0 if ok else 1)
    a, b = opt("--a", "gl"), opt("--b", "d3d12")
    env_b, sab = None, False
    for k, var in (("--sab-gl", "SM3DL_BACKEND_SABOTAJE"), ("--sab-d3d", "SM3DL_BACKEND_SABOTAJE"), ("--sab-cmp", "E2_SABOTAJE")):
        if k in sys.argv:
            env_b, sab = {var: opt(k, "1")}, True
    if "--sab-env" in sys.argv:          # sabotaje propio de una parte: --sab-env SM3DL_C3_SABOTAJE=1 (lado B)
        k, v = opt("--sab-env", "X=1").split("=", 1)
        env_b, sab = {k: v}, True
    if b == "d3d12" and not os.path.isdir(CACHE_TRAB):
        print("AVISO: no existe la cache de trabajo %s (correr 'volcar' y 'convertir')" % CACHE_TRAB)
    bien, mal, nulo = correr_lote(args or list(ESCENARIOS), a, b, tol, env_b, sab)
    if REINTENTOS:
        print("reintentos por caida: %d" % len(REINTENTOS))
        for r in REINTENTOS: print("   ", r)
    sys.exit(0 if mal == 0 and bien > 0 else 1)


if __name__ == "__main__":
    main()
