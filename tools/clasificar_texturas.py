"""Clasifica las texturas extraidas del ROM para el escalado con IA (agente T6).

Clases (columna `clase` del TSV):
  escalar          textura normal, se escala con el modelo de IA
  escalar_mosaico  se repite (wrap repeat y bordes que casan): escalar con borde envuelto (sin costuras)
  alfa_aparte      tiene alfa real: escalar RGB y alfa por separado
  nitido           pixel art / pocos colores: escalar con vecino mas cercano (sin IA)
  excluir          no tocar: fuentes, texto, HUD, iconos, LUTs, ruido, gradientes, < 16 px, mapas de normales

Fuentes de datos (todas locales y de solo lectura):
  - romfs\\*.szs -> CGFX: formato PICA real, tamano y, por material, el wrap (repeat/clamp) y el mapeo
    (entorno/esfera) con el lector de tools\\cgfx_gltf.py;
  - extraido\\texturas_png\\<szs>\\<textura>.png: pixeles decodificados (n.o de colores, alfa, costuras);
  - extraido\\pica_materiales.tsv: materiales por archivo (solo se usa para el conteo/receta TEV).

Uso:
  py -I tools\\clasificar_texturas.py                 # genera texturas_hd_reglas.tsv + resumen
  py -I tools\\clasificar_texturas.py --hoja          # ademas, la hoja de ejemplos (agentes_tex\\T6\\hoja_clases.png)
  py -I tools\\clasificar_texturas.py --autotest      # pruebas + sabotaje (no toca el TSV)
"""
import collections
import json
import os
import re
import sys

from PIL import Image, ImageChops, ImageStat

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

ROMFS = os.path.join(RAIZ, "extraido", "romfs")
PNGS = os.path.join(RAIZ, "extraido", "texturas_png")
SALIDA = os.path.join(RAIZ, "texturas_hd_reglas.tsv")
CACHE_META = os.path.join(RAIZ, "agentes_tex", "T6", "meta_cgfx.json")

FORMATOS = ["RGBA8", "RGB8", "RGBA5551", "RGB565", "RGBA4", "LA8", "HILO8", "L8", "A8", "LA4", "L4", "A4",
            "ETC1", "ETC1A4"]

# ---------------------------------------------------------------- reglas por nombre (data-driven, ver bitacora)
# Cada regla: (motivo, regex sobre el nombre de la textura, minusculas). Se evalua en orden.
RE_EXCLUIR_NOMBRE = [
    # OJO: "_nm01_" / "_xx01_" son PREFIJOS de grupo del juego, NO "normal map" (error de la v0: excluia
    # 1.082 difusas buenas). Los mapas de normales terminan en _nrm / Norm / _nr.
    ("lut", re.compile(r"(^|_)(lut|lutc|lutd|lutf|lutrr|lutrg|lutrb|fresnel|dist0|dist1)(_|$|\d)|^lm_|_lm$")),
    ("normal", re.compile(r"nrm(_\d+)?(\.\d+)?$|nrm_|norm(_\d+)?(\.\d+)?$|(^|_)normal|_nr(_\d+)?(\.\d+)?$|bump")),
    ("especular", re.compile(r"_spc(_\d+)?(\.\d+)?$|(^|_)spec(ular)?(_|\d|$)")),
    ("sombra_mascara", re.compile(r"(^|_)(shadow|kage)(\d|_|$)|mask(_\d+)?$|^pattern")),
    ("fuente_texto", re.compile(r"font|moji|glyph|(^|_)(letter|text|msg)(_|\d|$)")),
    ("hud_icono", re.compile(r"(^|_)(icon|hud|btn|button|cursor|gauge|menu|cmn|digit)(_|\d|$)")),
]
RE_NITIDO_NOMBRE = re.compile(r"(^|_)(dot|pixel|8bit|nes|dotmario)(_|\d|$)")


def _u32(d, o):
    return int.from_bytes(d[o:o + 4], "little")


# ---------------------------------------------------------------- metadatos del CGFX
def recoger_meta(usar_cache=True):
    """{(szs, textura): {w,h,fmt,envolver_repeat,env_map,materiales}} leyendo los CGFX del ROM."""
    if usar_cache and os.path.exists(CACHE_META):
        with open(CACHE_META, "r", encoding="utf-8") as f:
            return {tuple(k.split("|", 1)): v for k, v in json.load(f).items()}
    import cgfx
    import cgfx_gltf
    import szs
    import texturas
    meta = {}
    for carpeta, _, archivos in os.walk(ROMFS):
        for a in sorted(archivos):
            if not a.endswith(".szs"):
                continue
            base = a[:-4]
            try:
                cgfxs = list(cgfx.archivos_cgfx(os.path.join(carpeta, a)))
            except Exception as e:  # noqa: BLE001
                print("  [saltado %s: %s]" % (a, e))
                continue
            for _, b in cgfxs:
                try:
                    texs = texturas.texturas_de(b)
                except Exception:  # noqa: BLE001
                    texs = []
                for nombre, ancho, alto, fmt, _datos in texs:
                    meta.setdefault((base, nombre.replace("/", "_")), {
                        "w": ancho, "h": alto, "fmt": fmt, "usos": 0, "repeat": 0, "clamp": 0, "env": 0,
                        "mats": []})
                try:
                    cgfx_gltf._d = b
                    modelos = cgfx.leer(b).get("modelos", [])
                    for mn, o in modelos:
                        if b[o + 4:o + 8] != b"CMDL":
                            continue
                        mod = cgfx_gltf.leer_modelo(b, o)
                        for mat_n, m in mod["materiales"]:
                            t = m.get("textura")
                            if not t:
                                continue
                            e = meta.get((base, t.replace("/", "_")))
                            if e is None:
                                continue
                            e["usos"] += 1
                            ws, wt = m["envolver"]
                            if ws == 10497 or wt == 10497:
                                e["repeat"] += 1
                            else:
                                e["clamp"] += 1
                            if m["mapeo"] != 0:
                                e["env"] += 1
                            if len(e["mats"]) < 4 and mat_n not in e["mats"]:
                                e["mats"].append(mat_n)
                except Exception:  # noqa: BLE001
                    pass
    os.makedirs(os.path.dirname(CACHE_META), exist_ok=True)
    with open(CACHE_META, "w", encoding="utf-8") as f:
        json.dump({"%s|%s" % k: v for k, v in meta.items()}, f)
    return meta


# ---------------------------------------------------------------- estadisticas de pixeles
def estadisticas(img):
    """Mide la imagen RGBA. Devuelve dict de numeros simples (sin numpy)."""
    img = img.convert("RGBA")
    w, h = img.size
    a = img.getchannel("A")
    amin, amax = a.getextrema()
    ha = a.histogram()
    n = w * h
    semi = sum(ha[1:255])
    transp = ha[0]
    # colores distintos (RGB solo donde alfa>0)
    cols = img.getcolors(maxcolors=1 << 20)
    ncol = len(cols) if cols else 1 << 20
    rgb = img.convert("RGB")
    st = ImageStat.Stat(rgb)
    media = tuple(st.mean)
    desv = sum(st.stddev) / 3.0
    # variacion por filas / columnas: gradiente = cada fila (o columna) casi constante
    fila = rgb.resize((1, h), Image.BOX).resize((w, h), Image.NEAREST) if h > 1 else rgb
    col = rgb.resize((w, 1), Image.BOX).resize((w, h), Image.NEAREST) if w > 1 else rgb
    dif_fila = sum(ImageStat.Stat(ImageChops.difference(rgb, fila)).mean) / 3.0
    dif_col = sum(ImageStat.Stat(ImageChops.difference(rgb, col)).mean) / 3.0
    grad = min(dif_fila, dif_col)
    # ruido: diferencia con el vecino (1 px a la derecha) frente a la desviacion total
    if w > 2:
        der = ImageChops.offset(rgb, 1, 0)
        vec = sum(ImageStat.Stat(ImageChops.difference(rgb, der)).mean) / 3.0
    else:
        vec = 0.0
    # costura: diferencia entre bordes opuestos vs diferencia entre filas/cols vecinas dentro de la imagen
    cos = {"costura_h": -1.0, "costura_v": -1.0, "ref_h": 0.0, "ref_v": 0.0}
    if w >= 8:
        e1 = sum(ImageStat.Stat(ImageChops.difference(rgb.crop((0, 0, 1, h)), rgb.crop((w - 1, 0, w, h)))).mean) / 3.0
        r = sum(ImageStat.Stat(ImageChops.difference(rgb.crop((0, 0, w - 1, h)), rgb.crop((1, 0, w, h)))).mean) / 3.0
        cos["costura_h"], cos["ref_h"] = e1, r
    if h >= 8:
        e1 = sum(ImageStat.Stat(ImageChops.difference(rgb.crop((0, 0, w, 1)), rgb.crop((0, h - 1, w, h)))).mean) / 3.0
        r = sum(ImageStat.Stat(ImageChops.difference(rgb.crop((0, 0, w, h - 1)), rgb.crop((0, 1, w, h)))).mean) / 3.0
        cos["costura_v"], cos["ref_v"] = e1, r
    return {"w": w, "h": h, "ncol": ncol, "amin": amin, "amax": amax, "frac_semi": semi / n,
            "frac_transp": transp / n, "desv": desv, "grad": grad, "vecino": vec, "media": media, **cos}


def casa_borde(s):
    """True si los bordes opuestos casan casi tanto como filas vecinas (textura 'seamless')."""
    ok = False
    for c, r in (("costura_h", "ref_h"), ("costura_v", "ref_v")):
        if s[c] >= 0:
            if s[c] > max(6.0, 2.5 * s[r] + 3.0):
                return False
            ok = True
    return ok


# ---------------------------------------------------------------- clasificador (funcion pura)
def clasificar(nombre, s, m, fmt_nombre):
    """-> (clase, motivo). `s` = estadisticas, `m` = meta del CGFX (o None)."""
    n = nombre.lower()
    w, h = s["w"], s["h"]
    # 1) tamano
    if w < 16 or h < 16:
        return "excluir", "menor_16px"
    if w * h <= 16 * 16:
        return "excluir", "menor_16px"
    # 2) mapas de entorno / LUT por uso
    if m and m["usos"] and m["env"] == m["usos"]:
        return "excluir", "mapa_entorno"
    # 3) por nombre
    for motivo, rx in RE_EXCLUIR_NOMBRE:
        if rx.search(n):
            return "excluir", "nombre_" + motivo
    # 4) formatos de datos, no de color
    if fmt_nombre in ("HILO8",):
        return "excluir", "formato_" + fmt_nombre.lower()
    # 4b) mapa de normales sin nombre revelador: color medio ~ (128,128,255)
    mr, mg, mb = s["media"]
    if 95 <= mr <= 165 and 95 <= mg <= 165 and mb >= 190 and s["desv"] > 3:
        return "excluir", "pixel_normal_map"
    # 5) forma: gradientes de 1 px de informacion y color plano
    if s["ncol"] <= 1:
        return "excluir", "color_plano"
    if s["grad"] < 2.0 and s["desv"] > 4.0 and s["ncol"] > 1:
        return "excluir", "gradiente"
    # 6) ruido puro: vecinos tan distintos como cualquier par y sin estructura
    if s["desv"] > 20 and s["vecino"] > 0.8 * s["desv"] and s["ncol"] > 0.5 * w * h:
        return "excluir", "ruido"
    # 7) pixel art / pocos colores
    if RE_NITIDO_NOMBRE.search(n):
        return "nitido", "nombre_pixel"
    tiene_alfa = s["amin"] < 255
    if s["ncol"] <= 6 and not tiene_alfa:
        return "nitido", "pocos_colores_%d" % s["ncol"]
    # 8) alfa real
    if tiene_alfa and s["amax"] > 0:
        # recorte binario o suave: ambos van a alfa_aparte
        if s["frac_transp"] < 0.002 and s["frac_semi"] < 0.002:
            pass  # alfa casi todo opaco, ruido: tratar como normal
        else:
            return "alfa_aparte", "alfa_%.0f%%transp_%.0f%%semi" % (100 * s["frac_transp"], 100 * s["frac_semi"])
    # 9) mosaico
    rep = bool(m and m["repeat"])
    if rep and casa_borde(s):
        return "escalar_mosaico", "wrap_repeat+bordes_casan"
    if (not m) and casa_borde(s) and w >= 32 and h >= 32:
        return "escalar_mosaico", "bordes_casan_sin_material"
    return "escalar", "normal"


# ---------------------------------------------------------------- orquestacion
def listar_pngs():
    for c in sorted(os.listdir(PNGS)):
        cp = os.path.join(PNGS, c)
        if os.path.isdir(cp):
            for f in sorted(os.listdir(cp)):
                if f.lower().endswith(".png"):
                    yield c, f[:-4], os.path.join(cp, f)


def correr(hoja=False):
    meta = recoger_meta()
    filas = []
    for i, (carp, nombre, ruta) in enumerate(listar_pngs()):
        m = meta.get((carp, nombre))
        im = Image.open(ruta)
        s = estadisticas(im)
        fmt = FORMATOS[m["fmt"]] if m and 0 <= m["fmt"] < len(FORMATOS) else "?"
        clase, motivo = clasificar(nombre, s, m, fmt)
        filas.append((carp, nombre, s["w"], s["h"], fmt, clase, motivo, s, m, ruta))
    cab = ["archivo_rom", "textura", "w", "h", "formato", "clase", "motivo", "colores", "alfa_min", "alfa_transp_pct",
           "alfa_semi_pct", "wrap_repeat", "usos_material", "materiales"]
    tmp = SALIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(cab) + "\n")
        for carp, nombre, w, h, fmt, clase, motivo, s, m, _ in filas:
            f.write("\t".join(map(str, [
                carp + ".szs", nombre, w, h, fmt, clase, motivo, s["ncol"], s["amin"],
                round(100 * s["frac_transp"], 1), round(100 * s["frac_semi"], 1),
                m["repeat"] if m else "", m["usos"] if m else "", ",".join(m["mats"]) if m else ""])) + "\n")
    os.replace(tmp, SALIDA)
    resumen(filas)
    if hoja:
        hacer_hoja(filas)
    return filas


def resumen(filas):
    c = collections.Counter(f[5] for f in filas)
    unicos = collections.Counter()
    vistos = set()
    for f in filas:
        k = (f[1], f[2], f[3])
        if k not in vistos:
            vistos.add(k)
            unicos[f[5]] += 1
    print("TOTAL filas %d (nombres unicos nombre+tam %d)" % (len(filas), len(vistos)))
    for k in ("escalar", "escalar_mosaico", "alfa_aparte", "nitido", "excluir"):
        print("  %-16s %5d filas  %5d unicas" % (k, c[k], unicos[k]))
    mot = collections.Counter(f[6].split("_%")[0] if f[5] != "alfa_aparte" else "alfa" for f in filas if f[5] == "excluir")
    print("  excluir por motivo:", dict(mot.most_common()))


def hacer_hoja(filas, por_clase=8, celda=128):
    from PIL import ImageDraw
    clases = ["escalar", "escalar_mosaico", "alfa_aparte", "nitido", "excluir"]
    ancho = celda * por_clase + 160
    hoja = Image.new("RGB", (ancho, (celda + 28) * len(clases)), (40, 40, 40))
    d = ImageDraw.Draw(hoja)
    for r, cl in enumerate(clases):
        sel = [f for f in filas if f[5] == cl]
        # muestras repartidas de forma determinista
        paso = max(1, len(sel) // por_clase)
        sel = sel[::paso][:por_clase]
        d.text((4, r * (celda + 28) + 4), "%s\n(%d)" % (cl, sum(1 for f in filas if f[5] == cl)), fill=(255, 255, 0))
        for j, f in enumerate(sel):
            im = Image.open(f[9]).convert("RGBA")
            esc = min(celda / im.width, celda / im.height)
            im = im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.NEAREST)
            fondo = Image.new("RGBA", im.size, (90, 90, 120, 255))
            fondo.alpha_composite(im)
            x, y = 160 + j * celda, r * (celda + 28)
            hoja.paste(fondo.convert("RGB"), (x, y))
            d.text((x, y + celda + 2), "%s %dx%d" % (f[1][:18], f[2], f[3]), fill=(220, 220, 220))
            d.text((x, y + celda + 13), f[6][:20], fill=(150, 200, 150))
    dest = os.path.join(RAIZ, "agentes_tex", "T6", "hoja_clases.png")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    hoja.save(dest)
    print("hoja:", dest)


def _sint(w, h, f):
    im = Image.new("RGBA", (w, h))
    im.putdata([f(x, y) for y in range(h) for x in range(w)])
    return im


def autotest():
    """Pruebas con datos sinteticos + reales. SABOTAJE: SM3DL_T6_SABOTAJE=fuente anula la regla de fuentes y
    la prueba 'fuente real excluida' DEBE fallar (se ve rojo)."""
    global RE_EXCLUIR_NOMBRE
    if os.environ.get("SM3DL_T6_SABOTAJE") == "fuente":
        RE_EXCLUIR_NOMBRE = [x for x in RE_EXCLUIR_NOMBRE if x[0] != "fuente_texto"]
    fallos = []

    def esperar(desc, got, quiero):
        ok = got[0] == quiero
        print("%s  %-46s -> %s (%s)" % ("OK  " if ok else "FALLA", desc, got[0], got[1]))
        if not ok:
            fallos.append(desc)

    M = {"w": 64, "h": 64, "fmt": 12, "usos": 1, "repeat": 1, "clamp": 0, "env": 0, "mats": []}
    import math as _m
    teja = _sint(64, 64, lambda x, y: (int(128 + 100 * _m.sin(x * _m.pi / 8)), int(128 + 100 * _m.cos(y * _m.pi / 8)), int(128 + 90 * _m.sin((x + y) * _m.pi / 16)), 255))
    esperar("mosaico periodico (wrap repeat)", clasificar("rock_xx01_Rock01_dif", estadisticas(teja), M, "ETC1"), "escalar_mosaico")
    rampa = _sint(64, 64, lambda x, y: (x * 4 % 256, (y * 3 + x) % 256, (x * y) % 256, 255))
    esperar("textura que NO casa en el borde", clasificar("object_xx01_Cuerpo_dif", estadisticas(rampa), dict(M, repeat=0, clamp=1), "ETC1"), "escalar")
    esperar("nombre _nrm -> normal", clasificar("rock_nm01_Rock_nrm", estadisticas(rampa), M, "ETC1"), "excluir")
    esperar("prefijo _nm01_ NO es normal (v0 fallaba)", clasificar("worldmap_nm01_BasicFloor001_dif", estadisticas(rampa), dict(M, repeat=0), "ETC1"), "escalar")
    azul = _sint(64, 64, lambda x, y: (120 + x % 20, 120 + y % 20, 250, 255))
    esperar("normal map sin nombre (color 128,128,255)", clasificar("Cosa01", estadisticas(azul), M, "ETC1"), "excluir")
    esperar("menor de 16 px", clasificar("x_dif", estadisticas(_sint(8, 32, lambda x, y: (x * 30, y * 7, 9, 255))), M, "ETC1"), "excluir")
    deg = _sint(64, 64, lambda x, y: (200 - y, y * 3, 40 + y, 255))
    esperar("gradiente vertical de 1 px de info", clasificar("sky_dif", estadisticas(deg), dict(M, repeat=0), "ETC1"), "excluir")
    plano = _sint(64, 64, lambda x, y: (10, 200, 30, 255))
    esperar("color plano", clasificar("flat_dif", estadisticas(plano), M, "ETC1"), "excluir")
    pix = _sint(64, 64, lambda x, y: [(0, 0, 0, 255), (255, 255, 255, 255), (200, 30, 30, 255)][(x // 8 + y // 8) % 3])
    esperar("pocos colores -> nitido", clasificar("obj_dif", estadisticas(pix), M, "ETC1"), "nitido")
    alfa = _sint(64, 64, lambda x, y: ((x * 7) % 200, 90, (y * 5) % 200, 0 if x < 20 else 255))
    esperar("alfa real -> alfa_aparte", clasificar("plant_dif", estadisticas(alfa), M, "ETC1A4"), "alfa_aparte")
    esperar("HILO8 -> excluir", clasificar("Cosa02", estadisticas(rampa), M, "HILO8"), "excluir")
    esperar("_spc -> excluir", clasificar("lawn_nm01_Lawn001_spc", estadisticas(rampa), M, "ETC1"), "excluir")
    # datos reales: atlas de fuentes del juego (HUD/texto) deben salir excluidos
    ff = os.path.join(RAIZ, "extraido", "fuentes")
    reales = [f for f in sorted(os.listdir(ff)) if f.startswith("muestra_") and f.endswith(".png")] if os.path.isdir(ff) else []
    esperar("hay atlas de fuentes reales para probar", ("ok" if reales else "no", "%d" % len(reales)), "ok")
    for f in reales:
        im = Image.open(os.path.join(ff, f))
        esperar("fuente real excluida: " + f, clasificar(f[8:-4], estadisticas(im), None, "?"), "excluir")
    print("FALLAS: %d %s" % (len(fallos), fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    if "--autotest" in sys.argv:
        sys.exit(autotest())
    else:
        correr(hoja="--hoja" in sys.argv)
