import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from oraculo import *
import importlib.util
spec = importlib.util.spec_from_file_location("cs", os.path.join(R, "agentes_dx12", "B", "cadena_shaders.py")); cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)
viejo = cs.configs_luz()
por = {r["nombre"]: tuple(tuple(s) for s in r["firma"]) for r in rec}
pares = cs.pares_tev_luz()
real_set = set(Lr)
def corr(t, b23=0, esc=None):
    n, c0, c1, ab, ent, e = t
    c0 = (c0 & ~(1 << 30)) | 0x80000400
    c1 = c1 | 0xFF00FFFF | (1 << 18) | (b23 << 23)
    return (1, c0, c1, ab, ent, e if esc is None else esc)
cor = {k: corr(v) for k, v in viejo.items()}
print("configs corregidas que son una tupla real:", sum(v in real_set for v in cor.values()), "/", len(cor))
print("tuplas reales alcanzadas por alguna config corregida (cualquier esc):",
      len({l for l in Lr if any(corr(v, b, l[5]) == l for v in viejo.values() for b in (0, 1))}), "/", len(Lr))
fam("pares ROM x luz vieja", [(por[r], (viejo[c][0] + 1,) + viejo[c][1:]) for r, c in pares])
fam("pares ROM x luz corregida", [(por[r], cor[c]) for r, c in pares])
escs = sorted({l[5] for l in Lr})
h = fam("pares ROM x corregida x esc reales x b23", [(por[r], corr(viejo[c], b, e)) for r, c in pares for e in escs for b in (0, 1)])
h2 = fam("T x corregidas(todas) x esc", [(t, corr(v, 0, e)) for t in T for v in viejo.values() for e in escs[:4]])
