"""Lee extraido\\grafo_llamadas.json (de emular_grafo.py) y arma el grafo de acciones de Mario legible.

Uso: py -I tools\\analizar_grafo.py  -> extraido\\grafo_mario.txt (+ resumen por pantalla)
"""
import json
import os
import re
from collections import Counter, defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(AQUI, "..", "extraido")
MARCA, MARCA_FIN, PARAM, FALSO_7C = 0x30000000, 0x30F00000, 0x3F000000, 0x30F00000
NODO_CTOR, ADD_EDGE, ADD_COND, ADD_COND2, NEW = 0x00252134, 0x00251E20, 0x00252000, 0x00251F6C, 0x002932A8


def nombres():
    d = {}
    for linea in open(os.path.join(EXT, "simbolos.txt"), encoding="utf-8"):
        m = re.match(r"\s*(0x[0-9A-Fa-f]+)\s+(\S+)", linea)
        if m:
            d[int(m.group(1), 16)] = m.group(2)
    return d


def main():
    d = json.load(open(os.path.join(EXT, "grafo_llamadas.json"), encoding="utf-8"))
    nom = nombres()
    objs = sorted(d["objetos"], key=lambda o: o["dir"])
    ll = d["llamadas"]

    def fname(a):
        return nom.get(a, f"FUN_{a:08x}")

    # etiqueta de cada objeto = clase (ctor) + numero de orden dentro de la clase
    cuenta = Counter()
    etiqueta = {}
    for o in objs:
        c = fname(o["ctor"]) if o["ctor"] else "sinctor"
        c = c.replace("__ctor", "")
        cuenta[c] += 1
        etiqueta[o["dir"]] = f"{c}#{cuenta[c]}"

    def res(v):
        if MARCA <= v < MARCA_FIN:
            k, off = divmod(v - MARCA, 0x1000)
            return f"ctx[0x{k:x}]" + (f"+0x{off:x}" if off else "")
        if v == FALSO_7C:
            return "ctx7c+4"
        if v == PARAM:
            return "PARAM"
        for o in objs:
            if o["dir"] <= v < o["dir"] + max(o["tam"], 4):
                off = v - o["dir"]
                return etiqueta[o["dir"]] + (f"+0x{off:x}" if off else "")
        if v < 0x10000 or v >= 0xFFFF0000:
            return str(v if v < 0x80000000 else v - (1 << 32))
        return f"0x{v:08X}"

    nodo_de_estado = {}
    out = ["# Grafo de acciones de Mario — sacado emulando PlayerActionGraph_build (tools\\emular_grafo.py)", ""]
    out.append("## Llamadas en orden (sin operator_new)")
    for l in ll:
        if l["a"] == NEW:
            continue
        r, p = l["r"], l["pila"]
        args = [res(x) for x in r[1:]] + [res(x) for x in p[:3]]
        out.append(f"{l['desde']:08X} {fname(l['a'])}({res(r[0])}; {', '.join(args)})")
        if l["a"] == NODO_CTOR:
            nodo_de_estado[r[0]] = res(r[1])

    # aristas
    out += ["", "## Aristas: nodo --cond--> destino  (FUN_00251E20(nodo, a, b))"]
    aristas = []
    for l in ll:
        if l["a"] == ADD_EDGE:
            n, a, b = l["r"][:3]
            aristas.append((res(n), res(a), res(b)))
            out.append(f"{res(n)} ({nodo_de_estado.get(n, '?')}) : {res(a)} -> {res(b)} ({nodo_de_estado.get(b, '')})")
    # listas
    out += ["", "## Listas de condiciones (addTransition / 0x00251F6C)"]
    listas = defaultdict(list)
    for l in ll:
        if l["a"] in (ADD_COND, ADD_COND2):
            listas[res(l["r"][0])].append(res(l["r"][1]))
    for k, v in listas.items():
        out.append(f"{k} = [{', '.join(v)}]")
    open(os.path.join(EXT, "grafo_mario.txt"), "w", encoding="utf-8").write("\n".join(out))
    print("nodos:", len(nodo_de_estado), "aristas:", len(aristas), "listas:", len(listas))
    print(Counter(type(a[1]) for a in aristas))


if __name__ == "__main__":
    main()
