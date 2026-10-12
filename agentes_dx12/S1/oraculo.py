# S1: cuantos PS de cache_gl (usados de verdad en GL) cubre cada familia de candidatos, por hash (sin convertir nada)
import os, sys, subprocess, json
sys.path.insert(0, os.path.dirname(__file__))
from analizar import vistos, rec, firmas, SH, R
EXE = os.path.join(os.path.dirname(__file__), "hash_fs.exe")
def hashes(lineas):
    p = subprocess.run([EXE], input="\n".join(lineas) + "\n", capture_output=True, text=True, creationflags=0x4000)
    return p.stdout.split()
# control: los textos reales se rehacen con su hash
ks = sorted(vistos)
hs = hashes([" ".join(str(x) for s in vistos[k][0] for x in s) + ("" if not vistos[k][1] else " " + " ".join(
    str(x) for x in ((vistos[k][1][0] - 1,) + vistos[k][1][1:]))) for k in ks])
print("control rehash:", sum(a == b for a, b in zip(ks, hs)), "/", len(ks))
gl = {f[:-4].split("_")[1] for f in os.listdir(os.path.join(SH, "cache_gl")) if f.endswith(".bin") and f.count("_") == 3}
cache = {f[2:10] for f in os.listdir(os.path.join(SH, "cache_d3d12")) if f.startswith("F_")}
print("GL PS:", len(gl), "cubiertos hoy:", len(gl & cache))
T = sorted({tuple(tuple(s) for s in r["firma"]) for r in rec} | {v[0] for v in vistos.values()})
Lr = sorted({v[1] for v in vistos.values() if v[1]})
def fam(nombre, combos):
    lin = [" ".join(str(x) for s in t for x in s) + ("" if l is None else " " + " ".join(str(x) for x in ((l[0] - 1,) + l[1:]))) for t, l in combos]
    h = set(hashes(lin))
    print(f"{nombre:40s} {len(lin):6d} candidatos -> {len(h & gl):4d} en GL ({len((h & gl) - cache)} nuevos)")
    return h
a = fam("T x sin luz", [(t, None) for t in T])
b = fam("T x luz reales", [(t, l) for t in T for l in Lr])
print("union:", len((a | b | cache) & gl))
