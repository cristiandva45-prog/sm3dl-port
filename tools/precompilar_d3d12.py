r"""Cache DXIL del backend Direct3D 12 en extraido\shaders\cache_d3d12\ (agente E1, 9 oct 2026).

El juego NO compila shaders en D3D12: busca cada texto GLSL que arma la capa comun (raster_gl.c: envolver_vert(),
fs_para(), FRAG_UBER, GEOM_FLIP) por su hash FNV-1a (= fnv_texto() de raster_gl.c) en esta carpeta:
    V_<hash>.dxil  VS · F_<hash>.dxil  PS especializado · F_UBER.dxil  uber (respaldo) · G_FLIP.dxil  GS
    A_<aux>.{vs,fs}.dxil  auxiliares (giro_alta, pres_capa) · indice.tsv · VERSION.txt (= SD_CADENA_VERSION)
La cadena GLSL -> glslang -> SPIR-V -> SPIRV-Cross -> HLSL -> DXC -> DXIL es la del agente B
(agentes_dx12\B\cadena_shaders.py + terceros\ con versiones fijas, ver agentes_dx12\B.md); este guion la REUSA como
modulo (no la copia) redirigiendo sus carpetas de trabajo, y agrega lo que faltaba para integrarla:
  - instalacion ATOMICA y validada en extraido\shaders\cache_d3d12\ (carpeta .nuevo + rename; nunca deja media cache),
  - verificacion de que la cache instalada corresponde al C de HOY (deriva): re-inventario de los textos (segundos,
    solo el volcador) + comparacion de las funciones que volcar_glsl.c copio de raster_gl.c,
  - regeneracion de cero desde los materiales del ROM (.shbin -> .vert verificado, recetas TEV, censo de luz).

Uso (desde la raiz del proyecto; `py`, NO el `python` del PATH):
  py -I tools\precompilar_d3d12.py verificar            # segundos: cache instalada == textos del C de hoy (codigo 0 = ok)
  py -I tools\precompilar_d3d12.py instalar [--desde DIR]   # segundos: copia DXIL validado (defecto: agentes_dx12\B\cache_d3d12)
  py -I tools\precompilar_d3d12.py regenerar [--hilos N]    # DE CERO: ~100 s de pared con 2 hilos, prioridad baja
  py -I tools\precompilar_d3d12.py regenerar --solo REGEX   # convierte un subconjunto y lo compara BYTE A BYTE con lo instalado
  py -I tools\precompilar_d3d12.py desconocidos [--hilos N]  # (F1) convierte e instala los PS volcados en desconocidos_d3d12
  py -I tools\precompilar_d3d12.py cobertura          # (F1) PS de cache_gl (los que el juego uso en GL) con / sin DXIL
  py -I tools\precompilar_d3d12.py sabotaje             # prueba que verificar/deriva detectan caches y textos alterados
Opciones comunes: --trabajo DIR (defecto agentes_dx12\E1\trabajo), --dest DIR (defecto extraido\shaders\cache_d3d12).
Nada de esto toca la GPU ni corre el juego.
"""
import argparse
import csv
import importlib.util
import os
import re
import shutil
import struct
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(RAIZ, "extraido", "shaders", "cache_d3d12")
B_DIR = os.path.join(RAIZ, "agentes_dx12", "B")
CADENA_PY = os.path.join(B_DIR, "cadena_shaders.py")
ORIGEN_B = os.path.join(B_DIR, "cache_d3d12")
TRABAJO = os.path.join(RAIZ, "agentes_dx12", "E1", "trabajo")
RENDER = os.path.join(RAIZ, "recomp", "render")
BAJA = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
FIJOS = ("indice.tsv", "VERSION.txt")
# (F1, 9 oct) textos de PS que el juego armo DE VERDAD y el inventario no genera (los vuelca D1 en DESCONOCIDOS al caer al
# uber). `desconocidos` los convierte, los instala y los guarda en PARTIDA, que desde entonces es parte del inventario
# (frag/partida/F_<hash>.frag): verificar/instalar/regenerar los esperan igual que a los de las recetas.
SHADERS = os.path.join(RAIZ, "extraido", "shaders")
PARTIDA = os.path.join(SHADERS, "frag_partida")
DESCONOCIDOS = os.path.join(SHADERS, "desconocidos_d3d12")
ARCHIVO_DESC = os.path.join(SHADERS, "desconocidos_d3d12_archivo")
CACHE_GL = os.path.join(SHADERS, "cache_gl")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

cad = None   # modulo cadena_shaders de B, ya redirigido a la carpeta de trabajo


class _Subproceso:
    r"""Envuelve subprocess para cadena_shaders.inventario(): el lote del volcador separa por ESPACIOS (la ruta del
    proyecto tiene uno), por eso B usa rutas relativas '../../extraido/...' desde agentes_dx12\B. Desde otra carpeta
    de trabajo se reescribe ese prefijo con la ruta relativa correcta."""

    def __init__(self, rel_raiz):
        self.rel = rel_raiz.replace("\\", "/")

    def __getattr__(self, n):
        return getattr(subprocess, n)

    def run(self, cmd, input=None, **kw):
        if isinstance(input, str):
            input = input.replace(" ../../extraido/", " " + self.rel + "/extraido/")
        return subprocess.run(cmd, input=input, **kw)


# (fuente real, marcador que busca cadena_shaders.inventario(), funcion donde viven HOY los literales vs/fs)
_AUX = (("raster_gl.c", "giro_listo(int w, int h)", "static int giro_programa(void)"),
        ("presentador_gl.inc", "int raster_pres_capa", "static int gl_pres_capa("))


def render_sustituto(trabajo):
    r"""inventario() de B (8 oct) saca los textos auxiliares de raster_gl.c giro_listo() y presentador_gl.inc
    raster_pres_capa(); desde la separacion del backend (agente A) esos literales viven en raster_backend_gl.c
    (giro_programa / gl_pres_capa). Sin tocar el guion de B, se le da una carpeta render\ sustituta: raster_uber.c tal
    cual y, por cada auxiliar, el marcador que espera seguido del texto REAL de raster_backend_gl.c desde su funcion."""
    d = os.path.join(trabajo, "render")
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(os.path.join(RENDER, "raster_uber.c"), os.path.join(d, "raster_uber.c"))
    bgl = open(os.path.join(RENDER, "raster_backend_gl.c"), encoding="utf-8", errors="replace").read()
    for arch, marca, func in _AUX:
        if func not in bgl:
            raise SystemExit(f"no encuentro {func} en raster_backend_gl.c: actualizar _AUX en precompilar_d3d12.py")
        open(os.path.join(d, arch), "w", encoding="utf-8", newline="\n").write(
            f"/* sustituto generado por precompilar_d3d12.py */\n{marca}\n" + bgl[bgl.index(func):])
    return d


def cargar_cadena(trabajo):
    global cad
    if not os.path.exists(CADENA_PY):
        raise SystemExit(f"falta la cadena de B: {CADENA_PY}")
    spec = importlib.util.spec_from_file_location("cadena_shaders", CADENA_PY)
    cad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cad)
    os.makedirs(trabajo, exist_ok=True)
    rel = os.path.relpath(RAIZ, trabajo)
    if " " in rel:
        raise SystemExit("la carpeta de trabajo debe estar dentro del proyecto (ruta relativa sin espacios)")
    cad.B = trabajo
    cad.GLSL = os.path.join(trabajo, "glsl")
    cad.OUT = os.path.join(trabajo, "out")
    cad.VOLCAR = os.path.join(trabajo, "volcar_glsl.exe")
    cad.subprocess = _Subproceso(rel)
    cad.RENDER = render_sustituto(trabajo)
    cad.configs_luz_B = cad.configs_luz   # (S1) las variantes con la luz de B se QUEDAN (nunca menos DXIL); las corregidas van por combos_s1.json
    for herr in (cad.GLSLANG, cad.XCROSS, cad.DXC):
        if not os.path.exists(herr):
            print("AVISO: falta herramienta (solo la necesita 'regenerar'):", herr)


# (S1, 10 oct) configs_luz() de B reconstruia 0x1C2/0x1C3/0x1C4 a partir del censo de materiales con 3 luces y bits que el
# juego NO escribe: de los 382 textos receta x luz del inventario, 0 aparecian en cache_gl\ (= 0 los usaba el juego). Las
# 37 tuplas de luz reales de frag_partida\ dicen: siempre luz_n = 1 (0x1C2 = 0), 0x1C3 con bit 31 y bit 10 (0x400)
# encendidos y bit 30 apagado, 0x1C4 con 0xFF00FFFF (apagados por luz: sombra 0-7, spot 8-15, atenuacion 24-31) y el
# bit 18 encendido; abs/ent/esc (0x1D0-0x1D2) salen bien del censo. Con eso 18 de las 105 configs dan EXACTAMENTE una
# tupla real y los pares del ROM pasan de 0 a 97 PS usados en GL. Las escalas de LUT (0x1D2) son por material, no por
# config: las variantes reales van por combos_s1.json (junto con estos 382 pares corregidos).
def configs_luz_reales(cs):
    out = {}
    for k, (n, c0, c1, ab, ent, esc) in cs.configs_luz_B().items():
        out[k] = (0, (c0 & ~(1 << 30)) | 0x80000400, c1 | 0xFF00FFFF | (1 << 18), ab, ent, esc)
    return out


# (S1) combinaciones TEV x luz extra que el juego usa (elegidas por agentes_dx12\S1\elegir_combos.py desde frag_partida\,
# desconocidos y el oraculo cache_gl\): recetas TEV nuevas P* + combos (receta, luz | null). Parte del inventario.
COMBOS = os.path.join(SHADERS, "frag", "combos_s1.json")


def agregar_combos(ruta=None):
    import json
    ruta = COMBOS if ruta is None else ruta
    if not os.path.exists(ruta):
        return 0
    j = json.load(open(ruta, encoding="utf-8"))
    firma = {r["nombre"]: r["firma"] for r in json.load(open(os.path.join(SHADERS, "frag", "recetas.json"), encoding="utf-8"))}
    firma.update({r["nombre"]: r["firma"] for r in j["recetas_extra"]})
    d = os.path.join(cad.GLSL, "frag", "combos")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    orden, filas = [], []
    for i, c in enumerate(j["combos"]):
        nums = " ".join(str(x) for st in firma[c["receta"]] for x in st)
        if c["luz"] is not None:
            l = c["luz"]
            nums += " " + " ".join(str(x) for x in [l[0] - 1] + l[1:])   # luz_n -> registro 0x1C2
        a = f"frag/combos/{c['receta']}_C{i}.frag"
        orden.append(f"frag glsl/{a} {nums}")
        filas.append((a, c["motivo"]))
    p = subprocess.run([cad.VOLCAR, "-"], input="\n".join(orden) + "\n", capture_output=True, text=True, cwd=cad.B)
    if p.returncode:
        raise SystemExit("volcar_glsl fallo con combos_s1.json: " + p.stderr[:500])
    with open(os.path.join(cad.GLSL, "INDICE.tsv"), "a", encoding="utf-8", newline="\n") as f:
        for (a, m), c in zip(filas, j["combos"]):
            b = open(os.path.join(cad.GLSL, *a.split("/")), "rb").read()
            if f"{cad.fnv_texto(b):08X}" != c["hash"]:
                raise SystemExit(f"combos_s1.json: {a} tiene hash {cad.fnv_texto(b):08X} != {c['hash']} (el C cambio: "
                                 "correr agentes_dx12\\S1\\elegir_combos.py)")
            f.write(f"{a}\tfrag\tcombo S1: {m}\t{len(b)}\n")
    return len(filas)


def compilar(fuente, exe, deps):
    """zig cc -O1, solo si el exe falta o es mas viejo que sus fuentes (raster_uber.c cambia -> se recompila)."""
    if os.path.exists(exe) and all(os.path.getmtime(exe) >= os.path.getmtime(d) for d in deps):
        return
    cmd = [sys.executable, "-m", "ziglang", "cc", "-O1", "-o", exe, fuente, "-I" + RENDER]
    p = subprocess.run(cmd, capture_output=True, text=True, creationflags=BAJA)
    if p.returncode:
        raise SystemExit(f"no compila {os.path.basename(fuente)}:\n{p.stderr[:1500]}")
    print("compilado", os.path.relpath(exe, RAIZ))


def utilitarios(trabajo, layout=False):
    v = os.path.join(B_DIR, "volcar_glsl.c")
    compilar(v, os.path.join(trabajo, "volcar_glsl.exe"), [v, os.path.join(RENDER, "raster_uber.c")])
    if layout:
        c = os.path.join(B_DIR, "check_layout.c")
        compilar(c, os.path.join(trabajo, "check_layout.exe"), [c, os.path.join(RENDER, "raster_backend.h")])


# ------------------------------------------------------------------------------------------------ nombres y DXBC
def nombre_de(rel, h):
    """Mismo esquema que cadena_shaders.empaquetar() y que busca shaders_d3d12.c."""
    if rel.startswith("vert/"): return f"V_{h:08X}.dxil"
    if rel == "uber.frag": return "F_UBER.dxil"
    if rel.startswith("frag/"): return f"F_{h:08X}.dxil"
    if rel == "flip.geom": return "G_FLIP.dxil"
    if rel.startswith("aux/"):
        return "A_" + os.path.basename(rel).replace(".vert", ".vs").replace(".frag", ".fs") + ".dxil"
    return None


def esperados_de_inventario():
    """{archivo_cache: (hash, rel)} con los textos que acaba de volcar el inventario (= lo que arma el C de hoy)."""
    out = {}
    filas = open(os.path.join(cad.GLSL, "INDICE.tsv"), encoding="utf-8").read().splitlines()[1:]
    for l in filas:
        rel = l.split("\t")[0]
        if rel.startswith("sabotaje/"):
            continue
        h = cad.fnv_texto(open(os.path.join(cad.GLSL, *rel.split("/")), "rb").read())
        n = nombre_de(rel, h)
        if n:
            out.setdefault(n, (h, rel))   # 9 textos repetidos comparten archivo (mismo hash = mismo texto)
    return out, len(filas)


def validar_dxbc(b):
    """None si es un contenedor DXBC sano y FIRMADO con parte DXIL (mismas reglas que sd_valido de shaders_d3d12.c)."""
    if len(b) < 32 or b[:4] != b"DXBC":
        return "sin cabecera DXBC"
    if b[4:20] == b"\0" * 16:
        return "sin firma (hash 0: falto dxil.dll)"
    tam, npart = struct.unpack_from("<II", b, 24)
    if tam != len(b):
        return f"tamano {tam} != archivo {len(b)} (truncado)"
    if npart == 0 or 32 + 4 * npart > len(b):
        return "tabla de partes rota"
    partes = []
    for k in range(npart):
        off = struct.unpack_from("<I", b, 32 + 4 * k)[0]
        if off + 8 > len(b):
            return "parte fuera del archivo"
        cc, n = b[off:off + 4], struct.unpack_from("<I", b, off + 4)[0]
        if off + 8 + n > len(b):
            return f"parte {cc!r} fuera del archivo"
        partes.append(cc)
    if b"DXIL" not in partes:
        return "sin parte DXIL"
    return None


def verificar_carpeta(dest, esperados, version):
    """Lista de problemas (vacia = ok) de una cache instalada frente a los textos esperados."""
    prob = []
    if not os.path.isdir(dest):
        return [f"no existe {dest}"]
    vt = os.path.join(dest, "VERSION.txt")
    v = open(vt, encoding="utf-8").read().strip() if os.path.exists(vt) else ""
    if v != version:
        prob.append(f"VERSION.txt '{v}' != cadena '{version}' (el C ignoraria toda la cache)")
    for n, (h, rel) in sorted(esperados.items()):
        p = os.path.join(dest, n)
        if not os.path.exists(p):
            prob.append(f"falta {n} ({rel})")
            continue
        e = validar_dxbc(open(p, "rb").read())
        if e:
            prob.append(f"invalido {n}: {e}")
    for f in sorted(os.listdir(dest)):
        if f not in esperados and f not in FIJOS:
            prob.append(f"sobra {f} (ningun texto del C de hoy lo pide: cache vieja)")
    ip = os.path.join(dest, "indice.tsv")
    if os.path.exists(ip):   # tambien F_UBER/G_FLIP/A_*: su nombre no lleva hash, el indice si (texto viejo = DXIL viejo)
        en_indice = {}
        for r in csv.DictReader(open(ip, encoding="utf-8"), delimiter="	"):
            en_indice[r["archivo"]] = r["hash"]
        for n, (h, rel) in sorted(esperados.items()):
            if n not in en_indice:
                prob.append(f"indice.tsv sin {n}")
            elif en_indice[n] != f"{h:08X}":
                prob.append(f"{n}: el texto de HOY ({rel}) tiene hash {h:08X} y el DXIL es del {en_indice[n]}")
    else:
        prob.append("falta indice.tsv")
    return prob


# ------------------------------------------------------------------------------------------------ deriva C <-> volcador
_FUNCS = ("reemplazar", "envolver_vert", "luz_soporta", "luz_mues_de")


def _cuerpo(src, nombre):
    m = re.search(r"^static [^\n;]*\b" + nombre + r"\([^)]*\)\s*\n\{.*?\n\}\n", src, re.S | re.M)
    if not m:
        return None
    t = re.sub(r"/\*.*?\*/", "", m.group(0), flags=re.S)
    t = re.sub(r"//[^\n]*", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _formatos_fs(src, nombre):
    """Literales de formato de los snprintf(cab, ...) de la cabecera del fragment shader especializado."""
    m = re.search(r"^static [^\n;]*\b" + nombre + r"\([^)]*\)\s*\n\{.*?\n\}\n", src, re.S | re.M)
    if not m:
        return None
    cuerpo, lits, i = m.group(0), [], 0
    while (i := cuerpo.find("snprintf(cab", i)) >= 0:
        # hasta el ')' que cierra, saltando literales (los formatos traen ';' y ')' dentro: "luz_n = %u;\n", ");\n")
        j, prof, partes = i + len("snprintf"), 0, []
        while j < len(cuerpo):
            c = cuerpo[j]
            if c == '"':
                k = j + 1
                while cuerpo[k] != '"':
                    k += 2 if cuerpo[k] == "\\" else 1
                partes.append(cuerpo[j + 1:k])
                j = k
            elif c == "(":
                prof += 1
            elif c == ")":
                prof -= 1
                if prof == 0:
                    break
            j += 1
        lits.append("".join(partes).replace("#define PRUEBA_TEV\\n", ""))   # solo el arnes TEV; el juego pasa ""
        i = j
    return lits


def deriva(src_gl=None):
    """Problemas si las funciones que volcar_glsl.c copio de raster_gl.c ya no son iguales (el hash del texto del
    volcador dejaria de ser el que calcula el juego: la cache entera fallaria en silencio y todo caeria al uber)."""
    if src_gl is None:
        src_gl = open(os.path.join(RENDER, "raster_gl.c"), encoding="utf-8", errors="replace").read()
    src_v = open(os.path.join(B_DIR, "volcar_glsl.c"), encoding="utf-8", errors="replace").read()
    prob = []
    for f in _FUNCS:
        a, b = _cuerpo(src_gl, f), _cuerpo(src_v, f)
        if a is None or b is None:
            prob.append(f"deriva: no encuentro {f}() en {'raster_gl.c' if a is None else 'volcar_glsl.c'}")
        elif a != b:
            prob.append(f"deriva: {f}() de volcar_glsl.c != raster_gl.c")
    fa, fb = _formatos_fs(src_gl, "fs_para"), _formatos_fs(src_v, "frag_especializado")
    # raster_gl.c tiene ademas el "%s" de PRUEBA_TEV en la primera linea: el volcador lo pasa vacio (igual texto)
    if not fa or not fb or fa != fb:
        prob.append(f"deriva: cabecera de fs_para() != frag_especializado() del volcador ({fa} vs {fb})")
    if "memcpy(txt + m, FRAG_UBER, sizeof FRAG_UBER);" not in src_gl:
        prob.append("deriva: fs_para() ya no concatena FRAG_UBER como el volcador")
    return prob


def agregar_textos(rutas):
    """Copia textos GLSL ya armados (F_<hash>.frag/.glsl) a glsl/frag/partida/ y los agrega a INDICE.tsv. Devuelve los rel."""
    d = os.path.join(cad.GLSL, "frag", "partida")
    os.makedirs(d, exist_ok=True)
    rels = []
    with open(os.path.join(cad.GLSL, "INDICE.tsv"), "a", encoding="utf-8", newline="\n") as f:
        for r in rutas:
            b = open(r, "rb").read()
            n = f"F_{cad.fnv_texto(b):08X}.frag"
            open(os.path.join(d, n), "wb").write(b)
            rel = "frag/partida/" + n
            f.write(f"{rel}\tfrag\ttexto real de una partida ({os.path.basename(r)})\t{len(b)}\n")
            rels.append(rel)
    return rels


def inventariar(trabajo, partida=None):
    utilitarios(trabajo)
    t0 = time.perf_counter()
    cad.inventario()
    if cad.comparar_c():
        raise SystemExit("comparar-c: FRAG_UBER/GEOM_FLIP del volcador != raster_uber.c")
    partida = PARTIDA if partida is None else partida
    if os.path.isdir(partida):   # los PS que ya aparecieron en partidas reales (ver `desconocidos`)
        agregar_textos(sorted(os.path.join(partida, f) for f in os.listdir(partida) if f.endswith(".frag")))
    agregar_combos()
    esp, n = esperados_de_inventario()
    print(f"inventario: {n} textos -> {len(esp)} archivos distintos en {time.perf_counter() - t0:.1f} s")
    return esp


# ------------------------------------------------------------------------------------------------ subcomandos
def verificar(a):
    esp = inventariar(a.trabajo)
    prob = deriva() + verificar_carpeta(a.dest, esp, cad.CADENA_VERSION)
    for p in prob[:40]:
        print("PROBLEMA:", p)
    if len(prob) > 40:
        print(f"... y {len(prob) - 40} mas")
    tam = sum(os.path.getsize(os.path.join(a.dest, f)) for f in os.listdir(a.dest)) if os.path.isdir(a.dest) else 0
    print(f"verificar {os.path.relpath(a.dest, RAIZ)}: {len(esp)} esperados, {tam / 1e6:.1f} MB ->",
          "OK" if not prob else f"{len(prob)} PROBLEMAS")
    return 1 if prob else 0


def instalar_desde(origen, dest, esp, respaldo=None):
    vo = os.path.join(origen, "VERSION.txt")
    v = open(vo, encoding="utf-8").read().strip() if os.path.exists(vo) else ""
    if v != cad.CADENA_VERSION:
        raise SystemExit(f"origen con VERSION '{v}' != cadena '{cad.CADENA_VERSION}': regenerar")
    malos = []
    fuente = {}
    for n in esp:
        p = os.path.join(origen, n)
        if not os.path.exists(p) and respaldo and os.path.exists(os.path.join(respaldo, n)):
            p = os.path.join(respaldo, n)   # p. ej. los PS de partida: B no los tiene, la cache instalada si
        fuente[n] = p
        e = validar_dxbc(open(p, "rb").read()) if os.path.exists(p) else "falta en el origen"
        if e:
            malos.append(f"{n}: {e}")
    if malos:
        for m in malos[:20]:
            print("ORIGEN MALO:", m)
        raise SystemExit(f"{len(malos)} DXIL faltan o son invalidos en {origen}: no se instala nada (correr regenerar)")
    nuevo, viejo = dest + ".nuevo", dest + ".viejo"
    shutil.rmtree(nuevo, ignore_errors=True)
    os.makedirs(nuevo)
    with open(os.path.join(nuevo, "indice.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("archivo\thash\tglsl\tbytes\n")
        for n, (h, rel) in sorted(esp.items()):
            shutil.copyfile(fuente[n], os.path.join(nuevo, n))
            f.write(f"{n}\t{h:08X}\t{rel}\t{os.path.getsize(os.path.join(nuevo, n))}\n")
    open(os.path.join(nuevo, "VERSION.txt"), "w", newline="\n").write(cad.CADENA_VERSION + "\n")
    shutil.rmtree(viejo, ignore_errors=True)
    if os.path.exists(dest):
        os.replace(dest, viejo)
    os.replace(nuevo, dest)
    shutil.rmtree(viejo, ignore_errors=True)
    print(f"instalados {len(esp)} DXIL en {os.path.relpath(dest, RAIZ)} (desde {os.path.relpath(origen, RAIZ)})")


def instalar(a):
    esp = inventariar(a.trabajo)
    d = deriva()
    if d:
        for p in d:
            print("PROBLEMA:", p)
        raise SystemExit("el volcador ya no reproduce el texto del C: no se instala (re-copiar las funciones en volcar_glsl.c)")
    instalar_desde(a.desde, a.dest, esp, respaldo=a.dest)
    return verificar_carpeta_e_informar(a.dest, esp)


def verificar_carpeta_e_informar(dest, esp):
    prob = verificar_carpeta(dest, esp, cad.CADENA_VERSION)
    for p in prob[:20]:
        print("PROBLEMA:", p)
    print("verificacion tras instalar:", "OK" if not prob else f"{len(prob)} PROBLEMAS")
    return 1 if prob else 0


def regenerar(a):
    t0 = time.perf_counter()
    print("1/6 .vert == tools\\shader_glsl.py desde los .shbin del RomFS")
    p = subprocess.run([sys.executable, "-I", os.path.join(B_DIR, "verif_vert_generador.py")], capture_output=True,
                       text=True, cwd=RAIZ, creationflags=BAJA)
    print("   ", (p.stdout + p.stderr).strip().splitlines()[-1:] or "?")
    if p.returncode:
        raise SystemExit("los .vert de extraido\\shaders\\glsl no coinciden con el generador: regenerarlos primero "
                         "(tools\\shader_glsl.py) y volver a correr")
    print("2/6 inventario de textos (volcador recompilado si raster_uber.c cambio) + deriva")
    esp = inventariar(a.trabajo)
    d = deriva()
    if d:
        for x in d:
            print("PROBLEMA:", x)
        raise SystemExit("deriva C <-> volcador: no se regenera")
    for herr in (cad.GLSLANG, cad.XCROSS, cad.DXC):
        if not os.path.exists(herr):
            raise SystemExit(f"falta {herr} (ver agentes_dx12\\B.md seccion 1: versiones fijas y fuentes)")
    nuevos = a.solo == "nuevos"   # (S1) solo los que FALTAN en la cache instalada, y se instalan (no es comparacion)
    if nuevos:
        rels = sorted(rel for n, (h, rel) in esp.items() if not os.path.exists(os.path.join(a.dest, n)))
        print(f"   --solo nuevos: {len(rels)} textos sin DXIL en {os.path.relpath(a.dest, RAIZ)}")
        if not rels:
            return verificar_carpeta_e_informar(a.dest, esp)
        a.solo = "^(" + "|".join(re.escape(r) for r in rels) + ")$"
    args = ["--hilos", str(a.hilos)] + (["--solo", a.solo] if a.solo else [])
    print("3/6 convertir", " ".join(args))
    if a.solo:
        shutil.rmtree(cad.OUT, ignore_errors=True)   # que no se mezclen .dxil de una corrida anterior
    cad.convertir(args)
    tsv = os.path.join(cad.OUT, "resultados_parcial.tsv" if a.solo else "resultados.tsv")
    filas = list(csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"))
    fallos = [r for r in filas if r["dxil"] != "1"]
    if fallos:
        for r in fallos[:10]:
            print("FALLO:", r["archivo"], r["fallo_en"], r["causa"])
        raise SystemExit(f"{len(fallos)} shaders no llegaron a DXIL")
    if nuevos:   # origen = los nuevos; el resto sale de la cache instalada (instalar_desde: .nuevo + os.replace)
        if len(filas) != len(rels):
            raise SystemExit(f"convertidos {len(filas)} de {len(rels)}: no se instala nada")
        origen = os.path.join(a.trabajo, "cache_nuevos")
        shutil.rmtree(origen, ignore_errors=True)
        os.makedirs(origen)
        for r in filas:
            rel = r["archivo"]
            n = nombre_de(rel, cad.fnv_texto(open(os.path.join(cad.GLSL, *rel.split("/")), "rb").read()))
            shutil.copyfile(os.path.join(cad.OUT, rel.replace("/", "__") + ".dxil"), os.path.join(origen, n))
        open(os.path.join(origen, "VERSION.txt"), "w", newline="\n").write(cad.CADENA_VERSION + "\n")
        instalar_desde(origen, a.dest, esp, respaldo=a.dest)
        rc = verificar_carpeta_e_informar(a.dest, esp)
        print(f"regenerar --solo nuevos: {len(filas)} DXIL nuevos, {time.perf_counter() - t0:.0f} s de pared")
        return rc
    if a.solo:   # modo comprobacion: el DXIL nuevo debe ser identico al instalado (DXC es determinista)
        ref = a.dest if os.path.isdir(a.dest) else ORIGEN_B
        iguales, dif = 0, []
        for r in filas:
            rel = r["archivo"]
            h = cad.fnv_texto(open(os.path.join(cad.GLSL, *rel.split("/")), "rb").read())
            n = nombre_de(rel, h)
            nuevo = open(os.path.join(cad.OUT, rel.replace("/", "__") + ".dxil"), "rb").read()
            pr = os.path.join(ref, n)
            if os.path.exists(pr) and open(pr, "rb").read() == nuevo:
                iguales += 1
            else:
                dif.append(n)
        print(f"--solo: {iguales}/{len(filas)} DXIL regenerados IDENTICOS byte a byte a {os.path.relpath(ref, RAIZ)}",
              "" if not dif else f"; distintos: {dif[:10]}")
        return 1 if dif else 0
    print("4/6 layouts de cbuffers == offsetof(RbCb*) de raster_backend.h")
    utilitarios(a.trabajo, layout=True)
    if cad.layouts():
        raise SystemExit("layouts de cbuffers distintos de raster_backend.h: no se instala")
    print("5/6 empaquetar en", os.path.relpath(os.path.join(a.trabajo, "cache_d3d12"), RAIZ))
    cad.empaquetar()
    print("6/6 instalar")
    instalar_desde(os.path.join(a.trabajo, "cache_d3d12"), a.dest, esp, respaldo=a.dest)
    rc = verificar_carpeta_e_informar(a.dest, esp)
    print(f"regenerar: {time.perf_counter() - t0:.0f} s de pared")
    return rc


def desconocidos(a):
    r"""PS que el juego armo y no estaban en la cache (D1 los vuelca en desconocidos_d3d12\F_<hash>.glsl al caer al uber):
    1) cada texto debe tener el hash de su nombre (= el hsrc que busca D1; si no, se rechaza: no es el texto del juego);
    2) los que ya cubre la cache solo se archivan; 3) el resto: glslang -> SPIRV-Cross -> DXC con la cadena de B;
    4) una sola instalacion atomica (instalar_desde: .nuevo + os.replace) con la cache de hoy + los nuevos, y verificacion;
    5) recien entonces los textos pasan a frag_partida\ (parte del inventario desde ahora) y la carpeta de desconocidos
    se archiva en desconocidos_d3d12_archivo\<fecha>\. Si algo falla en 1-4 no cambia nada."""
    t0 = time.perf_counter()
    esp = inventariar(a.trabajo, a.partida)
    if deriva():
        raise SystemExit("deriva C <-> volcador: correr verificar primero")
    if not os.path.isdir(a.desconocidos):
        print("no hay", a.desconocidos, "(nada que convertir)")
        return 0
    entradas = sorted(f for f in os.listdir(a.desconocidos) if re.fullmatch(r"F_[0-9A-F]{8}\.glsl", f))
    malos, nuevos, cubiertos = [], [], 0
    for f in entradas:
        b = open(os.path.join(a.desconocidos, f), "rb").read()
        h = cad.fnv_texto(b)
        if f"F_{h:08X}.glsl" != f:
            malos.append(f"{f}: el texto tiene hash {h:08X} (alterado o truncado: no es lo que busca el juego)")
        elif f"F_{h:08X}.dxil" in esp:
            cubiertos += 1
        else:
            nuevos.append(os.path.join(a.desconocidos, f))
    print(f"desconocidos: {len(entradas)} textos -> {len(nuevos)} nuevos, {cubiertos} ya cubiertos, {len(malos)} rechazados")
    for m in malos[:10]:
        print("RECHAZADO:", m)
    if malos:
        raise SystemExit("hay textos rechazados: no se instala nada")
    if nuevos:
        for herr in (cad.GLSLANG, cad.XCROSS, cad.DXC):
            if not os.path.exists(herr):
                raise SystemExit(f"falta {herr}")
        rels = agregar_textos(nuevos)
        shutil.rmtree(cad.OUT, ignore_errors=True)
        patron = "^(" + "|".join(re.escape(r) for r in rels) + ")$"
        cad.convertir(["--hilos", str(a.hilos), "--solo", patron])
        filas = list(csv.DictReader(open(os.path.join(cad.OUT, "resultados_parcial.tsv"), encoding="utf-8"), delimiter="\t"))
        fallos = [r for r in filas if r["dxil"] != "1"]
        for r in fallos[:10]:
            print("FALLO:", r["archivo"], r["fallo_en"], r["causa"])
        if fallos or len(filas) != len(rels):
            raise SystemExit(f"{len(fallos)} de {len(rels)} no llegaron a DXIL: no se instala nada")
        origen = os.path.join(a.trabajo, "cache_partida")
        shutil.rmtree(origen, ignore_errors=True)
        os.makedirs(origen)
        for rel in rels:
            shutil.copyfile(os.path.join(cad.OUT, rel.replace("/", "__") + ".dxil"),
                            os.path.join(origen, os.path.basename(rel)[:-5] + ".dxil"))
            h = int(os.path.basename(rel)[2:10], 16)
            esp[f"F_{h:08X}.dxil"] = (h, rel)
        open(os.path.join(origen, "VERSION.txt"), "w", newline="\n").write(cad.CADENA_VERSION + "\n")
        instalar_desde(origen, a.dest, esp, respaldo=a.dest)
        if verificar_carpeta_e_informar(a.dest, esp):
            raise SystemExit("la cache instalada no verifica: los textos se quedan en desconocidos (no se archivan)")
        os.makedirs(a.partida, exist_ok=True)
        for r in nuevos:
            shutil.copyfile(r, os.path.join(a.partida, os.path.basename(r)[:-5] + ".frag"))
    arch = os.path.join(a.archivo, time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(arch, exist_ok=True)
    for f in os.listdir(a.desconocidos):
        os.replace(os.path.join(a.desconocidos, f), os.path.join(arch, f))
    print(f"desconocidos: {len(nuevos)} PS nuevos instalados en {os.path.relpath(a.dest, RAIZ)} y guardados en "
          f"{os.path.relpath(a.partida, RAIZ)}; carpeta archivada en {os.path.relpath(arch, RAIZ)} "
          f"({time.perf_counter() - t0:.0f} s)")
    return 0


def cobertura(a):
    r"""Que parte de los PS que el juego YA uso en GL tiene DXIL. cache_gl\ guarda binarios del DRIVER (sin el texto: no se
    puede reconstruir el GLSL desde ahi; el nombre lleva solo hv_hf_gs_driver), pero el hf dice que textos aparecieron."""
    esp = inventariar(a.trabajo, a.partida)
    hs = {f"{h:08X}" for n, (h, rel) in esp.items() if n.startswith("F_")}
    gl = [f[:-4].split("_") for f in os.listdir(CACHE_GL) if f.endswith(".bin")] if os.path.isdir(CACHE_GL) else []
    hf = {q[1] for q in gl if len(q) == 4}
    hv = {q[0] for q in gl if len(q) == 4}
    hvs = {f"{h:08X}" for n, (h, rel) in esp.items() if n.startswith("V_")}
    print(f"cache_gl: {len(gl)} programas, {len(hf)} PS distintos -> {len(hf & hs)} con DXIL, {len(hf - hs)} sin "
          f"(o de un texto de una version vieja del C); {len(hv)} VS -> {len(hv & hvs)} con DXIL")
    return 0


def sabotaje(a):
    """Cada alteracion debe producir PROBLEMAS; el control limpio no. Trabaja sobre una COPIA de la cache instalada."""
    esp = inventariar(a.trabajo)
    if not os.path.isdir(a.dest):
        raise SystemExit("primero instalar")
    tmp = os.path.join(a.trabajo, "sabotaje_cache")
    nombres = sorted(n for n in esp if n.startswith("F_") and n != "F_UBER.dxil")

    def copia():
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(a.dest, tmp)
        return tmp

    def sin_firma(d):
        p = os.path.join(d, nombres[0]); b = bytearray(open(p, "rb").read()); b[4:20] = b"\0" * 16
        open(p, "wb").write(b)

    def truncado(d):
        p = os.path.join(d, nombres[1]); b = open(p, "rb").read(); open(p, "wb").write(b[:len(b) // 2])

    def borrado(d):
        os.remove(os.path.join(d, "V_" + next(n for n in esp if n.startswith("V_"))[2:]))

    def sobrante(d):
        shutil.copyfile(os.path.join(d, nombres[2]), os.path.join(d, "F_DEADBEEF.dxil"))

    def version(d):
        open(os.path.join(d, "VERSION.txt"), "w", newline="\n").write("otra-cadena\n")

    casos = [("control limpio", None), ("DXIL sin firma", sin_firma), ("DXIL truncado", truncado),
             ("VS borrado", borrado), ("archivo de una cache vieja", sobrante), ("VERSION distinta", version)]
    ok = True
    for nombre, f in casos:
        d = copia()
        if f:
            f(d)
        prob = verificar_carpeta(d, esp, cad.CADENA_VERSION)
        detecta = bool(prob)
        bien = detecta == (f is not None)
        ok &= bien
        print(f"{'OK  ' if bien else 'MAL '} {nombre:28s} -> {len(prob)} problema(s){': ' + prob[0] if prob else ''}")
    shutil.rmtree(tmp, ignore_errors=True)
    # texto del C distinto (p. ej. alguien toca FRAG_UBER sin regenerar): un texto con un byte mas cambia de hash
    k = next(n for n in nombres)
    h, rel = esp[k]
    texto = open(os.path.join(cad.GLSL, *rel.split("/")), "rb").read() + b"\n"
    esp2 = dict(esp); del esp2[k]; esp2[nombre_de(rel, cad.fnv_texto(texto))] = (cad.fnv_texto(texto), rel)
    prob = verificar_carpeta(a.dest, esp2, cad.CADENA_VERSION)
    bien = any(p.startswith("falta ") for p in prob)
    ok &= bien
    print(f"{'OK  ' if bien else 'MAL '} {'texto del C cambiado':28s} -> {len(prob)} problema(s)")
    # deriva: el control debe estar limpio y cada sabotaje del C detectarse
    src = open(os.path.join(RENDER, "raster_gl.c"), encoding="utf-8", errors="replace").read()
    for nombre, mod in (("control deriva", None),
                        ("deriva en envolver_vert", lambda s: s.replace("static char *envolver_vert(char *v)\n{",
                                                                        "static char *envolver_vert(char *v)\n{ v = v;", 1)),
                        ("deriva en cabecera fs_para", lambda s: s.replace('"#define ESPECIALIZADO\\nconst uvec4',
                                                                           '"#define ESPECIALIZADO \\nconst uvec4', 1)),
                        ("deriva en cabecera LUZ", lambda s: s.replace('"const int luz_mues = %d;\\n"',
                                                                       '"const int luz_mues = %d; \\n"', 1)),
                        ("deriva en luz_mues_de", lambda s: re.sub(r"(static int luz_mues_de\(uint32_t c0, uint32_t c1\)\n\{)",
                                                                   r"\1 c0 ^= 1;", s, count=1))):
        s2 = mod(src) if mod else src
        if mod and s2 == src:
            print("MAL ", nombre, "-> el sabotaje no cambio el texto (no sabotea)")
            ok = False
            continue
        prob = deriva(s2)
        bien = bool(prob) == (mod is not None)
        ok &= bien
        print(f"{'OK  ' if bien else 'MAL '} {nombre:28s} -> {len(prob)} problema(s){': ' + prob[0] if prob else ''}")
    print("sabotaje:", "todos los casos se comportan como deben" if ok else "ALGUN VERIFICADOR NO DETECTA")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["verificar", "instalar", "regenerar", "sabotaje", "desconocidos", "cobertura"])
    ap.add_argument("--trabajo", default=TRABAJO)
    ap.add_argument("--dest", default=DEST)
    ap.add_argument("--desde", default=ORIGEN_B)
    ap.add_argument("--hilos", type=int, default=2)
    ap.add_argument("--solo", default=None)
    ap.add_argument("--desconocidos", default=DESCONOCIDOS)
    ap.add_argument("--partida", default=PARTIDA)
    ap.add_argument("--archivo", default=ARCHIVO_DESC)
    a = ap.parse_args()
    a.trabajo, a.dest, a.desde, a.desconocidos, a.partida, a.archivo = (
        os.path.abspath(x) for x in (a.trabajo, a.dest, a.desde, a.desconocidos, a.partida, a.archivo))
    cargar_cadena(a.trabajo)
    sys.exit({"verificar": verificar, "instalar": instalar, "regenerar": regenerar, "sabotaje": sabotaje,
              "desconocidos": desconocidos, "cobertura": cobertura}[a.cmd](a))


if __name__ == "__main__":
    main()
