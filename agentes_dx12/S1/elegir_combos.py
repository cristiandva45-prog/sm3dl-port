r"""S1 (10 oct 2026): elige las combinaciones TEV x luz EXTRA que el inventario debe convertir de antemano y las escribe en
extraido\shaders\frag\combos_s1.json (lo lee tools\precompilar_d3d12.py). Fuentes, todas datos REALES del juego:
  - TEV: recetas.json (materiales del ROM) + las firmas de los PS que el juego armo (frag_partida\, desconocidos_d3d12\).
  - luz: las tuplas (luz_n, 0x1C3, 0x1C4, 0x1D0, 0x1D1, 0x1D2) de esos mismos PS.
  - oraculo: cache_gl\ (nombre = hash del texto de cada PS que el juego uso en GL): solo se agrega un candidato del
    producto cruz si su hash es uno de esos (si no, seria convertir miles de PS que nadie usa).
Ademas, sin oraculo: las 52 firmas TEV nuevas sin luz, y por cada par (receta, config) del ROM las escalas de LUT reales
vistas para esa misma config (luz corregida, ver configs_luz_reales() en precompilar_d3d12.py).
Uso: py -I agentes_dx12\S1\elegir_combos.py"""
import os, sys, json, subprocess, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analizar import vistos, rec, firmas, SH, R
EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hash_fs.exe")
spec = importlib.util.spec_from_file_location("pre", os.path.join(R, "tools", "precompilar_d3d12.py"))
pre = importlib.util.module_from_spec(spec); spec.loader.exec_module(pre)
spec = importlib.util.spec_from_file_location("cs", os.path.join(R, "agentes_dx12", "B", "cadena_shaders.py"))
cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)
cs.configs_luz_B = cs.configs_luz


def hashes(combos):
    lin = [" ".join(str(x) for s in t for x in s) + ("" if l is None else " " + " ".join(str(x) for x in ((l[0] - 1,) + tuple(l[1:]))))
           for t, l in combos]
    p = subprocess.run([EXE], input="\n".join(lin) + "\n", capture_output=True, text=True, creationflags=0x4000)
    h = p.stdout.split()
    assert len(h) == len(lin) and "ERR" not in h
    return h


gl = {f[:-4].split("_")[1] for f in os.listdir(os.path.join(SH, "cache_gl")) if f.endswith(".bin") and f.count("_") == 3}
por = {r["nombre"]: tuple(tuple(s) for s in r["firma"]) for r in rec}
nombre_de = {v: k for k, v in por.items()}
extra = []   # recetas nuevas (firmas TEV que no estan en recetas.json), en orden estable
for t in sorted({v[0] for v in vistos.values()} - set(por.values())):
    n = f"P{len(extra)}"; extra.append({"nombre": n, "firma": [list(s) for s in t]}); nombre_de[t] = n; por[n] = t
T = sorted(por.values())
Lr = sorted({v[1] for v in vistos.values() if v[1]})
escs = sorted({l[5] for l in Lr})
cor = pre.configs_luz_reales(cs)   # {id_config: (luz_n, c0, c1, abs, ent, esc)}
pares = cs.pares_tev_luz()
L = lambda c: (cor[c][0] + 1,) + tuple(cor[c][1:])   # registro 0x1C2 -> luz_n
cand = {}   # (receta, luz|None) -> motivo
for e in extra:
    cand[(e["nombre"], None)] = "TEV nueva sin luz"
# 0) sin oraculo: cada par (receta, config) del ROM con la luz CORREGIDA (configs_luz_reales)
for r, c in pares:
    cand.setdefault((r, L(c)), "par del ROM con luz corregida")
# 1) producto cruz T x {sin luz, luces reales}, filtrado por el oraculo GL
fam = [(t, None) for t in T] + [(t, l) for t in T for l in Lr]
for (t, l), h in zip(fam, hashes(fam)):
    if h in gl: cand.setdefault((nombre_de[t], l), "cruz TEV x luz real, usado en GL")
# 2) pares (receta, config) del ROM x escalas de LUT reales x bit 23 de 0x1C4, filtrado por el oraculo GL
fam = []
for r, c in pares:
    n_, c0, c1, ab, ent, _ = L(c)
    for e in escs:
        for b in (0, 1 << 23):
            fam.append((por[r], (n_, c0, c1 | b, ab, ent, e)))
for (t, l), h in zip(fam, hashes(fam)):
    if h in gl: cand.setdefault((nombre_de[t], l), "par del ROM con escala real, usado en GL")
# 3) sin oraculo: por cada par del ROM, las escalas reales vistas con la MISMA config (c0, c1, abs, ent)
esc_de = {}
for l in Lr:
    esc_de.setdefault(l[1:5], set()).add(l[5])
for r, c in pares:
    n_, c0, c1, ab, ent, _ = L(c)
    for e in sorted(esc_de.get((c0, c1, ab, ent), ())):
        cand.setdefault((r, (n_, c0, c1, ab, ent, e)), "par del ROM con escala real de su config")
todos = list(cand)
hs = hashes([(por[r], l) for r, l in todos])
ya = {f[2:10] for f in os.listdir(os.path.join(SH, "cache_d3d12")) if f.startswith("F_")}
combos, vistos_h = [], set()
for (r, l), h in zip(todos, hs):
    if h in vistos_h: continue
    vistos_h.add(h)
    combos.append({"receta": r, "luz": None if l is None else list(l), "hash": h, "motivo": cand[(r, l)]})
base = set(hashes([(por[r["nombre"]], None) for r in rec] + [(por[r], L(c)) for r, c in pares]))
cubre = (vistos_h | base | {k for k in vistos}) & gl
print(f"combos extra: {len(combos)} ({sum(h not in ya for h in vistos_h)} sin DXIL hoy); recetas nuevas: {len(extra)}")
print(f"cobertura GL esperada: {len(cubre)}/{len(gl)} (hoy {len(gl & ya)})")
out = os.path.join(SH, "frag", "combos_s1.json")
tmp = out + ".tmp"
json.dump({"generado_por": r"agentes_dx12\S1\elegir_combos.py", "recetas_extra": extra, "combos": combos},
          open(tmp, "w", encoding="utf-8", newline="\n"), indent=0)
os.replace(tmp, out)
print("escrito", os.path.relpath(out, R))
