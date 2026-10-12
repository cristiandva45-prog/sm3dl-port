r"""Analiza el volcado de SM3DL_ESTUDIO_INTERP (pica_dibujar.c): factibilidad de interpolar cuadros (>60 FPS).
Uso: py -I tools\estudio_interp.py <dibujos.bin>
Responde: (1) los dibujos de un cuadro se emparejan con los del siguiente? (2) que uniforms cambian entre cuadros
(matrices?) (3) los vertices cambian en CPU (hash distinto) o solo los uniforms?"""
import struct, sys, collections

CAMPOS = "vblank swaps prog entrada color_dir base idx_off nv voff es_el topo tex0 tex1 tex2 vhash vbytes usa_gs b".split()
FMT = "<%dI384f" % len(CAMPOS)
TAM = struct.calcsize(FMT)

def leer(ruta):
    datos = open(ruta, "rb").read()
    out = []
    for k in range(len(datos) // TAM):
        v = struct.unpack_from(FMT, datos, k * TAM)
        d = dict(zip(CAMPOS, v[:len(CAMPOS)]))
        d["f"] = v[len(CAMPOS):]
        out.append(d)
    return out

def huella(d):
    return (d["prog"], d["entrada"], d["color_dir"], d["base"], d["idx_off"], d["nv"], d["voff"], d["tex0"], d["tex1"], d["tex2"], d["topo"])

def main():
    regs = leer(sys.argv[1])
    print("dibujos", len(regs), "tamano registro", TAM)
    # cuadro del juego = dibujos entre dos cambios de 'swaps' (cada cuadro hace 2 swaps: arriba y abajo)
    cuadros = collections.OrderedDict()
    for d in regs:
        cuadros.setdefault(d["swaps"], []).append(d)
    ids = list(cuadros)
    print("grupos por swaps:", [(s, len(cuadros[s])) for s in ids][:30])
    # emparejar cuadros consecutivos con el mismo numero de dibujos 'grandes'
    tot = emp = mismos_v = 0
    cambia_reg = collections.Counter()
    pares_unif = 0
    sin_cambio = 0
    rts = collections.Counter()
    for a, b in zip(ids, ids[1:]):
        A, B = cuadros[a], cuadros[b]
        if a % 2 != b % 2 and False:
            continue
        idxB = collections.defaultdict(list)
        for k, d in enumerate(B):
            idxB[huella(d)].append(d)
        usados = collections.Counter()
        for d in A:
            h = huella(d)
            tot += 1
            lst = idxB.get(h, [])
            j = usados[h]
            if j < len(lst):
                usados[h] += 1
                emp += 1
                e = lst[j]
                if e["vhash"] == d["vhash"]:
                    mismos_v += 1
                dif = [r for r in range(96) if any(abs(d["f"][4 * r + c] - e["f"][4 * r + c]) > 1e-6 for c in range(4))]
                if dif:
                    pares_unif += 1
                    for r in dif:
                        cambia_reg[r] += 1
                else:
                    sin_cambio += 1
            else:
                rts[(d["color_dir"], d["prog"])] += 1
    print("\n== emparejamiento entre grupos consecutivos ==")
    print("dibujos de A: %d, emparejados en B: %d (%.1f %%)" % (tot, emp, 100 * emp / max(tot, 1)))
    print("emparejados con los MISMOS vertices: %d (%.1f %%)" % (mismos_v, 100 * mismos_v / max(emp, 1)))
    print("emparejados sin ningun uniform distinto: %d; con uniforms distintos: %d" % (sin_cambio, pares_unif))
    print("registros que cambian (reg: veces):", sorted(cambia_reg.items(), key=lambda x: -x[1])[:40])
    print("no emparejados por (RT, prog):", rts.most_common(10))

    # comparar el mismo grupo par/impar a 2 de distancia (arriba con arriba)
    print("\n== emparejamiento a 2 grupos de distancia (misma pantalla) ==")
    tot = emp = mv = 0
    for a, b in zip(ids, ids[2:]):
        A, B = cuadros[a], cuadros[b]
        cB = collections.Counter(huella(d) for d in B)
        cA = collections.Counter(huella(d) for d in A)
        comun = sum((cA & cB).values())
        tot += len(A)
        emp += comun
    print("dibujos %d, emparejables %d (%.1f %%)" % (tot, emp, 100 * emp / max(tot, 1)))

    # ejemplo de un dibujo 3D con uniforms que cambian: mostrar los registros
    for a, b in zip(ids, ids[1:]):
        A, B = cuadros[a], cuadros[b]
        hB = {huella(d): d for d in B}
        for d in A:
            e = hB.get(huella(d))
            if not e:
                continue
            dif = [r for r in range(96) if any(abs(d["f"][4 * r + c] - e["f"][4 * r + c]) > 1e-6 for c in range(4))]
            if 3 <= len(dif) <= 20 and d["nv"] > 100:
                print("\nejemplo prog %08X rt %08X nv %d, regs que cambian %s" % (d["prog"], d["color_dir"], d["nv"], dif))
                for r in dif[:8]:
                    print("  c%-2d A %s" % (r, ["%.4f" % x for x in d["f"][4 * r:4 * r + 4]]))
                    print("      B %s" % ["%.4f" % x for x in e["f"][4 * r:4 * r + 4]])
                return

main()
