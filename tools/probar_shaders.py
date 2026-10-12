"""Verificador del traductor de shaders: arbol estructurado (shader_glsl.Programa.evaluar) contra la maquina de
pilas del hardware (shader_ref.correr), en todos los programas de extraido\\shaders.

Uso: py -I tools\\probar_shaders.py [-n PRUEBAS] [--sabotaje N]
  --sabotaje 1: invierte la polaridad de jmpu en el arbol   2: el loop corre una vuelta menos
  --sabotaje 3: la guarda de un salto ignora la bandera     (cada uno debe hacer FALLAR la prueba)
Mide tambien la cobertura: que instrucciones del programa ejecuto la referencia en alguna prueba.
"""
import itertools
import os
import random
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
import pica_ops  # noqa: E402
import shader_glsl  # noqa: E402
import shader_ref  # noqa: E402
import shbin  # noqa: E402

ESPECIALES = [0.0, -0.0, 1.0, -1.0, 0.5, 2.0, float("inf"), float("-inf"), float("nan")]


def valor(rng):
    if rng.random() < 0.15:
        return rng.choice(ESPECIALES)
    return rng.choice([rng.uniform(-2, 2), float(rng.randint(-3, 3))])


def mismo(x, y):
    return (x != x and y != y) or x == y


def estado(sh, ent, rng, bools):
    e = sh.entradas[ent]
    v = [[valor(rng) for _ in range(4)] for _ in range(16)]
    c = [[valor(rng) for _ in range(4)] for _ in range(96)]
    i = [[rng.randint(0, 3), rng.randint(0, 40), rng.randint(0, 4), 0] for _ in range(4)]
    b = list(bools)
    for t, k, val in e["constantes"]:  # las constantes del DVLE tapan los uniforms, como en la carga del shader
        if t == "c":
            c[k] = list(val)
        elif t == "i":
            i[k] = list(val)
        else:
            b[k] = val
    return v, c, i, b


def bools_usados(sh):
    u = set()
    for pc in range(len(sh.codigo)):
        ins = sh.instr(pc)
        if ins["op"] in ("ifu", "callu", "jmpu"):
            u.add(ins["uni"])
    return sorted(u)


def sabotear(n):
    P = shader_glsl.Programa
    if n == 1:
        viejo = P.cond

        def cond(self, ins):
            c = viejo(self, ins)
            return ("u", c[1], not c[2]) if ins["op"] == "jmpu" else c
        P.cond = cond
    elif n == 2:
        viejo = P._lista

        def _lista(self, nodos, st):
            for nd in nodos:
                if nd[0] == "loop":
                    st.i = [[max(0, x[0] - 1)] + list(x[1:]) for x in st.i]
                    break
            return viejo(self, nodos, st)
        P._lista = _lista
    elif n == 3:
        viejo = P._lista

        def _lista(self, nodos, st):
            nodos = [("guard", [], nd[2]) if nd[0] == "guard" and len(nd[1]) == 1 else nd for nd in nodos]
            return viejo(self, nodos, st)
        P._lista = _lista


def main():
    args = sys.argv[1:]
    n = int(args[args.index("-n") + 1]) if "-n" in args else 200
    if "--sabotaje" in args:
        sabotear(int(args[args.index("--sabotaje") + 1]))
    d = os.path.join(RAIZ, "extraido", "shaders")
    total_ok = total = 0
    for f in sorted(os.listdir(d)):
        if not f.endswith(".shbin"):
            continue
        sh = shbin.Shbin(open(os.path.join(d, f), "rb").read())
        usados = bools_usados(sh)
        combos = list(itertools.product([False, True], repeat=len(usados)))
        if len(combos) > 256:
            combos = random.Random(1).sample(combos, 256)
        for ent in range(len(sh.entradas)):
            prog = shader_glsl.Programa(sh, ent)
            rng = random.Random(f"{f}{ent}")
            fallos, cubiertas, pruebas = 0, set(), 0
            ejemplo = None
            for k in range(max(n, len(combos))):
                bools = [False] * 16
                for u, val in zip(usados, combos[k % len(combos)]):
                    bools[u] = val
                v, c, i, b = estado(sh, ent, rng, bools)
                ref = pica_ops.Estado(v, c, i, b)
                pcs = set()
                viejo_instr = sh.instr

                def espia(pc, _v=viejo_instr):
                    pcs.add(pc)
                    return _v(pc)
                sh.instr = espia
                try:
                    shader_ref.correr(sh, sh.entradas[ent]["main"], ref)
                finally:
                    sh.instr = viejo_instr
                cubiertas |= pcs
                arb = prog.evaluar(pica_ops.Estado(v, c, i, b))
                pruebas += 1
                ok = all(mismo(x, y) for ro, ao in zip(ref.o, arb.o) for x, y in zip(ro, ao))
                if not ok:
                    fallos += 1
                    if ejemplo is None:
                        ejemplo = next(f"o{j}: ref {ro} arbol {ao}" for j, (ro, ao) in enumerate(zip(ref.o, arb.o))
                                       if not all(mismo(x, y) for x, y in zip(ro, ao)))
            total += pruebas
            total_ok += pruebas - fallos
            alcanzable = {pc for pc in range(len(sh.codigo)) if sh.instr(pc)["op"] not in ("nop",)}
            print(f"{f[:-6]} e{ent}: {pruebas - fallos}/{pruebas} iguales, cobertura "
                  f"{len(cubiertas & alcanzable)}/{len(alcanzable)} instr" + (f"  FALLA {ejemplo}" if ejemplo else ""))
    print(f"TOTAL: {total_ok}/{total}")
    sys.exit(0 if total_ok == total else 1)


if __name__ == "__main__":
    main()
