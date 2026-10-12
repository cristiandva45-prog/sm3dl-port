r"""Agente A (8 oct): que formas de la bateria aparecen/desaparecen entre configuraciones del traductor.

Uso: py -I recomp\prueba_retcalc_formas.py
  v461 = simulacion de antes del agente I (sin noreturn, limite = siguiente inicio, tamanos sin filtro de .text,
         funciones_extra viejo)
  v460 = recomp.py antes del agente A (agentes_8oct\recomp.py.antes_A) + funciones_extra viejo
  ahora = recomp.py actual + funciones_extra actual
"""
import bisect
import importlib.util
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import recomp as NUEVO  # noqa: E402
import bateria  # noqa: E402

VIEJO_TSV = os.path.join(RAIZ, "agentes_8oct", "funciones_extra.antes_A.tsv")


def cargar(ruta, nombre):
    import importlib.machinery
    spec = importlib.util.spec_from_loader(nombre, importlib.machinery.SourceFileLoader(nombre, ruta))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tam_con(m, tsv, filtro=True):
    d = {}
    for linea in open(os.path.join(RAIZ, "extraido", "funciones.tsv")):
        a, t = linea.split()
        d[int(a, 16)] = int(t)
    for linea in open(tsv):
        a, t = linea.split()[:2]
        d.setdefault(int(a, 16), int(t))
    return {a: t for a, t in d.items() if not filtro or m.BASE <= a < m.TEXT_FIN}


def censo(m, tam, limite):
    bateria.RC = m
    inicios = sorted(tam)
    formas = {}
    for a in inicios:
        for ad, i in m.Traductor(a, limite(tam, inicios, a), set()).recorrer().items():
            if i is None or bateria.es_control(i):
                continue
            formas.setdefault(bateria.forma(i), []).append(ad)
    return formas


def limite_viejo(tam, inicios, a):
    k = bisect.bisect_right(inicios, a)
    return inicios[k] if k < len(inicios) else a + 0x1000


def main():
    viejo = cargar(os.path.join(RAIZ, "agentes_8oct", "recomp.py.antes_A"), "recomp_antes_A")
    sim = cargar(os.path.join(RAIZ, "agentes_8oct", "recomp.py.antes_A"), "recomp_sim461")
    sim.Traductor.noreturn = set()
    sim.Traductor.termina = staticmethod(lambda i, t=sim.Traductor.termina: t(i))
    f461 = censo(sim, tam_con(sim, VIEJO_TSV, filtro=False), limite_viejo)
    f460 = censo(viejo, tam_con(viejo, VIEJO_TSV), viejo.limite)
    fnow = censo(NUEVO, NUEVO.tamanos(), NUEVO.limite)
    for (na, a), (nb, b) in (((461, f461), (460, f460)), ((460, f460), ("ahora", fnow))):
        print(f"{na} ({len(a)}) -> {nb} ({len(b)})")
        for k in sorted(set(a) - set(b)):
            print(f"  sale: {k}  ({len(a[k])} usos, p. ej. {', '.join(hex(x) for x in a[k][:3])})")
        for k in sorted(set(b) - set(a)):
            print(f"  entra: {k}  ({len(b[k])} usos, p. ej. {', '.join(hex(x) for x in b[k][:3])})")


if __name__ == "__main__":
    main()
