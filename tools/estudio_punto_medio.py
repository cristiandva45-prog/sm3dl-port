r"""Prueba del PUNTO MEDIO sobre el volcado de SM3DL_ESTUDIO_INTERP: con 3 cuadros seguidos A, B, C (30 FPS),
lerp(A, C, 0.5) deberia parecerse al B real si los uniforms se pueden interpolar (eso es lo que hara la interpolacion
de cuadros entre B y C a 60+ FPS). Mide por registro el error relativo |B - mid| / |C - A| y cuenta los SALTOS
(registros donde B no esta entre A y C: contadores, banderas, cambios de estado) que habria que copiar, no mezclar.
Uso: py -I tools\estudio_punto_medio.py <dibujos.bin>"""
import struct, sys, collections, statistics
sys.path.insert(0, __import__("os").path.dirname(__file__))
from estudio_interp import leer, huella

def main():
    regs = leer(sys.argv[1])
    cuadros = collections.OrderedDict()
    for d in regs:
        cuadros.setdefault(d["swaps"], []).append(d)
    ids = list(cuadros)
    err = collections.defaultdict(list)     # reg -> errores relativos (donde cambio algo)
    saltos = collections.Counter()           # reg -> veces que B salio fuera de [A, C] por mucho
    total_reg = collections.Counter()
    tri = 0
    progs_salto = collections.Counter()
    for a, b, c in zip(ids, ids[1:], ids[2:]):
        def indexar(L):
            dct = collections.defaultdict(list)
            for d in L:
                dct[huella(d)].append(d)
            return dct
        IB, IC = indexar(cuadros[b]), indexar(cuadros[c])
        usados = collections.Counter()
        for d in cuadros[a]:
            h = huella(d)
            j = usados[h]
            usados[h] += 1
            if j >= len(IB.get(h, [])) or j >= len(IC.get(h, [])):
                continue
            e, f = IB[h][j], IC[h][j]
            tri += 1
            for r in range(96):
                for k in range(4):
                    A, B, C = d["f"][4 * r + k], e["f"][4 * r + k], f["f"][4 * r + k]
                    if A == B == C:
                        continue
                    total_reg[r] += 1
                    mid = (A + C) / 2
                    span = abs(C - A)
                    escala = max(abs(A), abs(B), abs(C), 1e-6)
                    if abs(B - mid) <= 1e-4 * escala:
                        err[r].append(0.0)
                        continue
                    if span < 1e-9 or abs(B - mid) > 2 * span + 1e-3 * escala:
                        saltos[r] += 1
                        progs_salto[(d["prog"], r)] += 1
                        continue
                    err[r].append(abs(B - mid) / span)
    print("triadas de dibujos emparejados:", tri)
    print("\nreg  componentes_que_cambian  saltos  err_rel_mediana  err_rel_p90   (err 0 = lerp exacto; 0.5 = B igual a A o C)")
    for r in sorted(total_reg, key=lambda r: -total_reg[r]):
        e = sorted(err[r])
        med = statistics.median(e) if e else float("nan")
        p90 = e[int(0.9 * (len(e) - 1))] if e else float("nan")
        print("c%-3d %8d %8d   %8.4f   %8.4f" % (r, total_reg[r], saltos[r], med, p90))
    print("\nsaltos por (prog, reg), los 15 mas comunes:")
    for (p, r), n in progs_salto.most_common(15):
        print("  prog %08X c%d: %d" % (p, r, n))

main()
