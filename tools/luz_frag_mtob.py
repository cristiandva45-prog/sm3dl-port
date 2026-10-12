"""Fragment lighting del material CGFX (MTOB): decodificador + censo.  (agente I, 8 oct 2026)

Lo que el material NO trae como comando PICA (LIGHTING_CONFIG0 del MTOB es una plantilla con
solo el byte 1 = 0x04) vive en campos sueltos. Layout verificado empiricamente (todos los
asserts de abajo pasan en los 4.579 materiales):

MTOB (offsets desde el inicio del objeto, el mismo `m` de pica_cmd.materiales):
  +0x018 flags del material: bit0 fragment lighting, bit1 luz por vertice, bit2 hemisferica,
         bit3 oclusion hemisferica, bit4 niebla, bit5 polygon offset
  +0x024 colores float RGBA x11: emision, ambiente, difuso, especular0, especular1, const0..5
  +0x288 -> fragment shader:
     +0x00 color de buffer (float4)
     +0x10 flags: bit0 clamp highlight, bit1 D0, bit2 D1, bit3 factor geometrico 0,
                  bit4 factor geometrico 1, bit5 reflexion (RR/RG/RB)
     +0x14 capa (layer config 0..7; la 7 es la config 8 del PICA)
     +0x18 selector fresnel: 0 no, 1 alfa primaria, 2 alfa secundaria, 3 ambas
     +0x1C textura de bump (0..2)   +0x20 modo bump: 0 no, 1 normal map, 2 tangent map
     +0x24 renormalizar bump (bool)
     +0x28 -> tabla de LUTs: 6 punteros RR, RG, RB, D0, D1, FR (0 = sin LUT)
        cada LUT: +0 entrada (0 NH,1 VH,2 NV,3 LN,4 SP,5 CP) +4 absoluto +8 escala (codigo PICA)
                  +C -> sampler: +0 tipo 0x40000000, +4 -> nombre tabla, +8 -> nombre sampler

Uso:
  py -I tools\\luz_frag_mtob.py material <szs>          # fragment lighting de cada material
  py -I tools\\luz_frag_mtob.py censo [carpeta_romfs]    # -> extraido\\shaders\\luz\\censo_luz.tsv + resumen
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cgfx  # noqa: E402
import pica_cmd  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "extraido", "shaders", "luz")

LUTS = ("RR", "RG", "RB", "D0", "D1", "FR")
ENTRADAS = ("NH", "VH", "NV", "LN", "SP", "CP")
ESCALAS = {0: 1.0, 1: 2.0, 2: 4.0, 3: 8.0, 6: 0.25, 7: 0.5}
CAPA_A_PICA = (0, 1, 2, 3, 4, 5, 6, 8)
u32 = cgfx.u32


def f32(d, o, n):
    return list(struct.unpack_from(f"<{n}f", d, o))


def leer(b, m):
    """dict con el fragment lighting del material en el MTOB `m`."""
    assert b[m + 4:m + 8] == b"MTOB"
    fl = u32(b, m + 0x18)
    col = [f32(b, m + 0x24 + 16 * i, 4) for i in range(5)]
    fs = cgfx.rel(b, m + 0x288)
    assert fs, "sin fragment shader"
    ff = u32(b, fs + 0x10)
    assert ff < 0x40, f"flags frag {ff:#x}"
    capa, fres, btex, bmodo, bren = (u32(b, fs + k) for k in (0x14, 0x18, 0x1C, 0x20, 0x24))
    assert capa < 8 and fres < 4 and btex < 4 and bmodo < 3 and bren < 2, (capa, fres, btex, bmodo, bren)
    t = cgfx.rel(b, fs + 0x28)
    assert t
    luts = {}
    for i, n in enumerate(LUTS):
        p = cgfx.rel(b, t + 4 * i)
        if not p:
            continue
        ent, esc = u32(b, p), u32(b, p + 4)
        assert ent < 6 and esc in ESCALAS, (n, ent, esc)
        s = cgfx.rel(b, p + 8)
        assert s and u32(b, s) == 0x40000000, f"sampler {n}"
        luts[n] = {"entrada": ENTRADAS[ent], "abs": None, "escala": ESCALAS[esc], "escala_cod": esc,
                   "tabla": cgfx.cadena(b, cgfx.rel(b, s + 4)), "sampler": cgfx.cadena(b, cgfx.rel(b, s + 8))}
    return {
        "luz_frag": bool(fl & 1), "luz_vtx": bool(fl & 2), "hemisferica": bool(fl & 4), "niebla": bool(fl & 16),
        "emision": col[0], "ambiente": col[1], "difuso": col[2], "especular0": col[3], "especular1": col[4],
        "clamp": bool(ff & 1), "usa_d0": bool(ff & 2), "usa_d1": bool(ff & 4),
        "geo0": bool(ff & 8), "geo1": bool(ff & 16), "usa_refl": bool(ff & 32),
        "capa": capa, "config_pica": CAPA_A_PICA[capa], "fresnel": fres,
        "bump_tex": btex, "bump_modo": bmodo, "bump_renorm": bool(bren), "luts": luts,
    }


def leer_luts(b):
    """{(tabla, sampler): (absoluto, [256 entradas crudas])} de la seccion LUTS de un CGFX.
    LUTS: +0x18 n samplers, +0x1C -> DICT. Sampler: +0 tipo 0x80000000, +4 -> nombre, +8 absoluto,
    +0xC bytes de comandos, +0x10 -> comandos PICA (LIGHTING_LUT_DATA 0x1C8.., 2 rafagas de 128).
    Entrada (regs de Azahar pica_core.h): bits 0-11 valor/4095, 12-22 |dif|/2047, bit 23 signo de dif."""
    out = {}
    for tabla, o in cgfx.leer(b).get("luts", []):
        assert b[o + 4:o + 8] == b"LUTS"
        for samp, so in cgfx.diccionario(b, cgfx.rel(b, o + 0x1C)):
            ab, nb, c = u32(b, so + 8), u32(b, so + 0xC), cgfx.rel(b, so + 0x10)
            assert ab < 2 and nb % 4 == 0 and c
            pal = [u32(b, c + 4 * i) for i in range(nb // 4)]
            datos = []
            for reg, _, v in pica_cmd.parsear(pal):
                assert 0x1C8 <= reg <= 0x1CF, hex(reg)
                datos.append(v)
            assert len(datos) == 256, (tabla, samp, len(datos))
            out[(tabla, samp)] = (bool(ab), tuple(datos))
    return out


def lut_float(datos):
    """[(valor, diferencia)] x256 como floats (semantica de LutEntry de Azahar, reimplementada)."""
    r = []
    for w in datos:
        d = ((w >> 12) & 0x7FF) / 2047.0
        r.append(((w & 0xFFF) / 4095.0, -d if w & 0x800000 else d))
    return r


def activas(L):
    """LUTs que el PICA de verdad consulta: habilitadas por los flags del material Y soportadas por la config.
    (tabla de soporte = IsLightingSamplerSupported de regs_lighting.h, reimplementada)"""
    c = L["config_pica"]
    soporte = {"D0": c != 1, "D1": c not in (0, 1, 5), "FR": c not in (0, 2, 4), "RR": c != 3,
               "RG": c in (4, 5, 8), "RB": c in (4, 5, 8)}
    pide = {"D0": L["usa_d0"], "D1": L["usa_d1"], "RR": L["usa_refl"], "RG": L["usa_refl"],
            "RB": L["usa_refl"], "FR": L["fresnel"] != 0}
    return [n for n in LUTS if soporte[n] and pide[n] and n in L["luts"]]


def firma(L):
    """Configuracion de luz que cambia el CODIGO del shader (no los valores de LUT/colores)."""
    act = activas(L)
    return (L["config_pica"], L["clamp"], L["geo0"], L["geo1"], L["fresnel"], L["bump_modo"],
            L["bump_tex"] if L["bump_modo"] else 0, L["bump_renorm"] if L["bump_modo"] == 1 else False,
            tuple((n, L["luts"][n]["entrada"], L["luts"][n]["abs"]) for n in act))


def firma_txt(f):
    c, cl, g0, g1, fr, bm, bt, br, luts = f
    s = f"cfg{c}" + (" clamp" if cl else "") + (" geo0" if g0 else "") + (" geo1" if g1 else "")
    s += f" fres{fr}" if fr else ""
    s += f" bump{bm}t{bt}{'r' if br else ''}" if bm else ""
    return s + " | " + " ".join(f"{n}:{e}{'' if a else '(s)'}" for n, e, a in luts)


def _archivo(ruta):
    """(materiales [(archivo, modelo, material, L, luts_locales)], luts del archivo)."""
    out, todas = [], {}
    try:
        for nom, b in cgfx.archivos_cgfx(ruta):
            loc = leer_luts(b)
            todas.update(loc)
            for mod, mat, m in pica_cmd.materiales(b):
                out.append((os.path.basename(ruta), mod, mat, leer(b, m), loc))
    except Exception as e:  # noqa: BLE001
        out.append((os.path.basename(ruta), "ERROR", repr(e), None, None))
    return out, todas


def resolver(L, loc, glob):
    """Pone 'abs' y 'datos' en cada LUT del material: primero la tabla del mismo CGFX, si no la global."""
    falt = 0
    for v in L["luts"].values():
        k = (v["tabla"], v["sampler"])
        hit = loc.get(k) if loc else None
        if hit is None:
            hit = glob.get(k)
        if hit is None:
            falt += 1
            v["abs"], v["datos"] = False, None
        else:
            v["abs"], v["datos"] = hit
    return falt


def censo(raiz):
    from concurrent.futures import ProcessPoolExecutor
    rutas = [os.path.join(c, a) for sub in ("ObjectData", "StageData") for c, _, arch in
             os.walk(os.path.join(raiz, sub)) for a in arch if a.endswith(".szs")]
    filas, defs = [], collections.defaultdict(set)
    with ProcessPoolExecutor() as ex:
        for r, lu in ex.map(_archivo, rutas, chunksize=8):
            filas += r
            for k, v in lu.items():
                defs[k].add(v)
    err = [f for f in filas if f[1] == "ERROR"]
    # LUT global: si una (tabla, sampler) tiene varias definiciones, se usa la mas frecuente? -> se cuenta y se toma la 1a ordenada
    glob = {k: sorted(v)[0] for k, v in defs.items()}
    ambiguas = {k: len(v) for k, v in defs.items() if len(v) > 1}
    mats, faltan = [], 0
    for a, mo, ma, L, loc in (f for f in filas if f[1] != "ERROR"):
        faltan += resolver(L, loc, glob)
        mats.append((a, mo, ma, L, firma(L)))
    import json
    os.makedirs(SALIDA, exist_ok=True)
    unicas = sorted({v for vs in defs.values() for v in vs}, key=lambda x: x[1])
    with open(os.path.join(SALIDA, "luts.json"), "w", encoding="utf-8") as fh:
        json.dump({"nota": "tabla/sampler -> [absoluto, 256 entradas crudas PICA]; si hay varias definiciones, la 1a ordenada",
                   "luts": {f"{k[0]}/{k[1]}": [v[0], list(v[1])] for k, v in sorted(glob.items())}}, fh)
    C = collections.Counter
    con = [f for f in mats if f[3]["luz_frag"]]
    firmas = C(f[4] for f in con)
    os.makedirs(SALIDA, exist_ok=True)
    with open(os.path.join(SALIDA, "censo_luz.tsv"), "w", encoding="utf-8") as fh:
        fh.write("archivo\tmodelo\tmaterial\tluz_frag\tconfig\tid_config\tluts_declaradas\n")
        ids = {f: i for i, (f, _) in enumerate(firmas.most_common())}
        for a, mo, ma, L, f in mats:
            decl = " ".join(f"{n}:{v['entrada']}{'' if v['abs'] else '(s)'}x{v['escala']:g}"
                            for n, v in L["luts"].items())
            fh.write(f"{a}\t{mo}\t{ma}\t{int(L['luz_frag'])}\t{firma_txt(f)}\t"
                     f"{ids.get(f, '') if L['luz_frag'] else ''}\t{decl}\n")
    r = [f"materiales: {len(mats)} · errores: {len(err)} · con fragment lighting: {len(con)} "
         f"· sin: {len(mats) - len(con)} · configuraciones distintas: {len(firmas)}",
         f"LUTs (tabla/sampler) definidas: {len(defs)} · contenidos distintos: {len(unicas)} · "
         f"nombres con definiciones distintas entre archivos: {len(ambiguas)} · referencias sin resolver: {faltan}"]
    for e in err[:5]:
        r.append(f"  ERROR {e[0]}: {e[2]}")

    def tabla(titulo, cont):
        r.append(f"\n{titulo}")
        for k, v in cont.most_common():
            r.append(f"  {v:5d}  {k}")
    tabla("config PICA (capa)", C(f[3]["config_pica"] for f in con))
    tabla("fresnel (0 no,1 pri,2 sec,3 ambas)", C(f[3]["fresnel"] for f in con))
    tabla("clamp highlight", C(f[3]["clamp"] for f in con))
    tabla("geo factor (g0,g1)", C((f[3]["geo0"], f[3]["geo1"]) for f in con))
    tabla("bump (modo,tex,renorm)", C((f[3]["bump_modo"], f[3]["bump_tex"], f[3]["bump_renorm"]) for f in con))
    tabla("flags D0/D1/refl", C((f[3]["usa_d0"], f[3]["usa_d1"], f[3]["usa_refl"]) for f in con))
    tabla("LUT activas (con entrada; (s)=con signo)", C(" ".join(f"{n}:{e}{'' if a else '(s)'}" for n, e, a in f[4][8])
                                                     for f in con))
    tabla("LUT declaradas (nombre:entrada x escala)", C(f"{n}:{v['entrada']}{'' if v['abs'] else '(s)'}x{v['escala']:g}"
                                                        for f in con for n, v in f[3]["luts"].items()))
    tabla("tablas LUT referenciadas (tabla/sampler), top 30", C(f"{v['tabla']}/{v['sampler']}"
                                                                for f in con for v in f[3]["luts"].values()))
    del r[r.index("\ntablas LUT referenciadas (tabla/sampler), top 30") + 31:]
    tabla("luz por vertice / hemisferica (en materiales con luz frag)", C((f[3]["luz_vtx"], f[3]["hemisferica"]) for f in con))
    r.append("\nnombres (tabla/sampler) con varias definiciones entre archivos:")
    for k, v in sorted(ambiguas.items()):
        r.append(f"  {k[0]}/{k[1]}: {v} versiones")
    # chequeo independiente del decodificado: valor[i] + dif[i] debe dar valor[i+1] (orden PICA:
    # absoluta 0..255 = [0,1); con signo 0..127 = [0,1) y 128..255 = [-1,0), la 255 sigue en la 0)
    malos = tot = 0
    for ab, datos in unicas:
        fl = lut_float(datos)
        sig = list(range(128, 256)) + list(range(0, 128)) if not ab else list(range(256))
        for a_, b_ in zip(sig, sig[1:]):
            tot += 1
            malos += abs(fl[a_][0] + fl[a_][1] - fl[b_][0]) > 3 / 4095
    r.append(f"\ncontinuidad de LUT decodificadas (v[i]+d[i] ~ v[i+1], tol 3/4095): {tot - malos}/{tot} pares")
    ejemplo = {}
    for a, mo, ma, L, f in con:
        ejemplo.setdefault(f, (a, mo, ma, {n: [v["tabla"], v["sampler"], v["escala"]] for n, v in L["luts"].items()}))
    with open(os.path.join(SALIDA, "configs.json"), "w", encoding="utf-8") as fh:
        json.dump([{"id": i, "usos": v, "txt": firma_txt(f), "cfg": f[0], "clamp": f[1], "geo0": f[2], "geo1": f[3],
                    "fresnel": f[4], "bump_modo": f[5], "bump_tex": f[6], "bump_renorm": f[7],
                    "luts": [list(x) for x in f[8]], "ejemplo": ejemplo[f]}
                   for i, (f, v) in enumerate(firmas.most_common())], fh, indent=0)
    r.append("\nCONFIGURACIONES (firma de codigo) por uso:")
    for i, (f, v) in enumerate(firmas.most_common()):
        r.append(f"  C{i:<3d} {v:5d}  {firma_txt(f)}")
    txt = "\n".join(r)
    with open(os.path.join(SALIDA, "censo_luz.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)
    return firmas


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "material":
        filas, _ = _archivo(sys.argv[2])
        for a, mo, ma, L, loc in filas:
            if L is None:
                print("ERROR", ma)
                continue
            resolver(L, loc, {})
            f = firma(L)
            print(f"{mo}/{ma}: luz_frag={L['luz_frag']}  {firma_txt(f)}")
            for n, v in L["luts"].items():
                print(f"    {n}: {dict((k, x) for k, x in v.items() if k != 'datos')}"
                      f"{'' if v.get('datos') else '  (tabla no esta en este archivo)'}")
    elif len(sys.argv) >= 2 and sys.argv[1] == "censo":
        censo(sys.argv[2] if len(sys.argv) > 2 else os.path.join(RAIZ, "extraido", "romfs"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
