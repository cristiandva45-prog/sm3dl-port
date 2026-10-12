# S1: censo de los PS reales (frag_partida + desconocidos + archivo) vs recetas/configs de luz
import os, re, json, csv, glob, collections
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SH = os.path.join(R, "extraido", "shaders")
def leer(p):
    t = open(p, "rb").read().decode("latin-1")
    m = re.search(r"const uvec4 tev\[6\] = uvec4\[6\]\((.*?)\);", t)
    if not m: return None
    tev = tuple(tuple(int(x) for x in re.findall(r"(\d+)u", s)) for s in re.findall(r"uvec4\(([^)]*)\)", m.group(1)))
    luz = None
    if "const int luz_n" in t:
        g = lambda n: int(re.search(r"const (?:int|uint) " + n + r" = (\d+)u?;", t).group(1))
        luz = (g("luz_n"), g("luz_c0"), g("luz_c1"), g("luz_abs"), g("luz_ent"), g("luz_esc"))
    return tev, luz
rutas = glob.glob(os.path.join(SH, "frag_partida", "*.frag")) + glob.glob(os.path.join(SH, "desconocidos_d3d12", "*.glsl")) \
      + glob.glob(os.path.join(SH, "desconocidos_d3d12_archivo", "*", "*.glsl"))
vistos = {}
for p in rutas:
    h = os.path.basename(p)[2:10]
    x = leer(p)
    if x: vistos[h] = x
rec = json.load(open(os.path.join(SH, "frag", "recetas.json")))
firmas = {tuple(tuple(s) for s in r["firma"]): r["nombre"] for r in rec}
(lambda *a, **k: None)("textos reales distintos:", len(vistos))
luzes = collections.Counter(v[1] for v in vistos.values() if v[1])
(lambda *a, **k: None)("tuplas de luz:", len(luzes))
for l, n in []: print("  n=%d c0=%08X c1=%08X abs=%08X ent=%08X esc=%08X  x%d" % (l + (n,)))
nuevas = {v[0] for v in vistos.values() if v[0] not in firmas}
(lambda *a, **k: None)("TEV fuera de recetas:", len(nuevas), "de", len({v[0] for v in vistos.values()}))
# c0 del material del ROM
mat = list(csv.DictReader(open(os.path.join(R, "extraido", "pica_materiales.tsv"), encoding="utf-8"), delimiter="\t"))
(lambda *a, **k: None)("lighting_config0 distintos en ROM:", collections.Counter(m["lighting_config0"] for m in mat).most_common(8))
