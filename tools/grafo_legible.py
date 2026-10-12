"""Grafo de acciones de Mario legible: estados con nombre y condiciones traducidas.

Entrada: extraido\\grafo_llamadas.json (tools\\emular_grafo.py).
Salida:  reportes\\grafo_mario.md (tabla por estado) y extraido\\grafo_mario.dot (Graphviz).
Uso: py -I tools\\grafo_legible.py

Los nombres marcados con '?' son hipotesis (ver reportes\\grafo_mario.md, seccion "Evidencia").
"""
import json
import os
import re
from collections import OrderedDict

AQUI = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(AQUI, "..", "extraido")
REP = os.path.join(AQUI, "..", "reportes")
CODE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extraido", "code.bin"), "rb").read()
MARCA, MARCA_FIN, PARAM, FALSO_7C = 0x30000000, 0x30F00000, 0x3F000000, 0x30F00000
NEW, NODO, ARISTA, AND_ADD, OR_ADD = 0x002932A8, 0x00252134, 0x00251E20, 0x00252000, 0x00251F6C
AND_CTOR, OR_CTOR, NOT_CTOR = 0x0025204C, 0x00251FB8, 0x00252078

# estado (ctor) -> nombre. Evidencia: animaciones que arrancan sus metodos (reportes\estados_crudo.txt)
ESTADOS = {
    0x00171A70: "InicioDeEscena?", 0x001A46C0: "Correr", 0x00174C10: "Esperar", 0x001818F4: "Giro(TurnPoint)",
    0x00173B54: "Salto", 0x00171D5C: "Caer", 0x0017533C: "AgarrePared", 0x00197EE8: "SaltoPared",
    0x00197C5C: "CaerDesdePared", 0x0025211C: "Deslizar agachado", 0x0019E5CC: "Agachado",
    0x0019DC40: "SaltoAtras", 0x00196EAC: "FinAgachado", 0x001962F8: "CaerInicio?", 0x001963D4: "CaerInicio2?",
    0x001B8B30: "LuigiMove(flotar)", 0x0018EB9C: "Sentón(HipDrop)", 0x00181418: "Frenar",
    0x0018A388: "Daño", 0x0019D948: "Morir", 0x001B71F8: "Morir2", 0x00196830: "SaltoLargo",
    0x00197B88: "SaltoGiro", 0x00181284: "DeslizarPared", 0x002520CC: "AtaqueColaSuelo",
    0x0025208C: "AtaqueColaAire", 0x0018F0EC: "ChoquePared", 0x001A7FCC: "RebotePisotón",
    0x00173F04: "Aterrizar", 0x0019DD68: "AterrizarChoque", 0x001749C0: "GiroTrasFrenar",
    0x0019EFAC: "Nadar(parado)", 0x00174838: "NadarBrazada", 0x002D2324: "NadarInicio?",
    0x001BA528: "NadarSuperficie", 0x001972E4: "SentónAcuático", 0x00171CD4: "Bucear", 0x001A7254: "NadarPisotón",
    0x0019F59C: "NadarAgachado", 0x001974B8: "SaltoFueraDelAgua", 0x001A4940: "EmpujarPared?", 0x001B9040: "CaídaLenta(tanuki)",
    0x001BAE80: "AtaqueAéreo", 0x001B79A4: "PlanearHélice", 0x001A79B4: "Estatua", 0x001A73AC: "AterrizajeRígido",
}
# componentes del contexto (PlayerCore). Evidencia: PlayerActor_initPlayer / PlayerCore__ctor
CTX = {0x0: "Fís", 0x3: "Ctrl", 0x5: "Col", 0x7: "Anim", 0x1b: "Entrada", 0x2b: "Hélice", 0xc: "Zona", 0x14: "Vida",
       0x25: "SupAgua", 0x10: "Forma"}
# PlayerInput: offset de vtable -> significado (PlayerInput_update; trigger/hold deducidos de los contadores)
CTRL = {0x08: "stick movido", 0x0C: "dir stick", 0x24: "pulsó A/B (≤5f)", 0x28: "mantiene A/B",
        0x2C: "pulsó X/Y", 0x30: "mantiene X/Y", 0x34: "pulsó L/R", 0x38: "mantiene L/R",
        0x3C: "pulsó L/R'", 0x40: "mantiene L/R'", 0x44: "pulsó X/Y'", 0x54: "pulsó L/R''",
        0x58: "mantiene L/R''", 0x5C: "pulsó X/Y (≤5f)"}
# colisionador: offset de vtable -> sub-chequeador (6 iguales, el significado es hipotesis)
COL = {0x24: "en suelo", 0x28: "pared al frente", 0x2C: "tocando pared", 0x30: "col[28]", 0x34: "col[38]", 0x38: "col[34]",
       0x3C: "flag9c"}
# condiciones construidas en linea: vptr -> significado (evaluar = vptr+8, ver reportes\grafo_mario.md)
INLINE = {0x003D1348: "en suelo", 0x003D1300: "cayendo (vel·grav>0)", 0x003D1A2C: "pisó a un enemigo (ctx8.bit1)",
          0x003D1984: "mantiene A/B", 0x003D1C0C: "Ctrl.vf4c", 0x003D1754: "col[28] (¿techo?)"}
# plantillas por clase: {0},{1},{2} = argumentos ya traducidos. Evidencia: su evaluar() (vptr+8)
CLASES = {
    0x00225458: "subiendo", 0x002D2CC0: "(pulsó A/B (≤5f) Y en suelo Y NO subiendo)",
    0x002D2D2C: "(en suelo Y NO subiendo Y NO stick movido)", 0x002D50C4: "(en suelo Y NO subiendo)",
    0x002D5218: "(en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)", 0x002D34C0: "(mantiene L/R Y NO subiendo Y en suelo)",
    0x002D3B8C: "velocidad ≈ 0", 0x001BAC14: "velocidad² < umbral", 0x001B9F94: "stick movido",
    0x002D3F6C: "stick contrario a la velocidad (frenar)", 0x002D2BD4: "stick hacia atrás",
    0x002D1F18: "stick hacia adelante (N frames)", 0x002D3B1C: "(pulsó L/R' Y hay espacio abajo)",
    0x002D3014: "pared enfrente (agarrable)", 0x002D26E0: "{0} ≥ parámetro", 0x00251FE4: "forma == X",
    0x001B9F30: "forma == 5", 0x001B9FD8: "petición externa bit{1}", 0x00251F4C: "durante {0} frames",
    0x002D30DC: "anim HipDropLand terminó Y ...", 0x002D3790: "{0} anim al 100%",
    0x00251F0C: "toca Floor_code {1}?", 0x001B9EC0: "{0}.vf0", 0x001BAC40: "{0}.vf0", 0x001B9DB0: "{0}.vf0",
    0x001B9FC0: "{1}.vf0({0})", 0x001B9F5C: "{1}.vf4({0})", 0x002D2AB8: "{0}.vf0(0)",
    0x001B99BC: "recuerda({0})", 0x00251E98: "anim {1} terminó",
    0x00251EB4: "({0}.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))", 0x00251EDC: "({0}.vf0 Y en suelo Y ctx1a.vf0)",
    0x00251EF4: "({0}.vf0 Y NO en suelo)", 0x002D35B8: "NO {0}.vf0", 0x002D3BC8: "{0}.vf0 ≠ 0",
    0x002D3C98: "*{0} ≠ 0", 0x002D3584: "({0}.vf0 Y {0}.vf4 > umbral según forma)",
    # 7 oct, ronda 2 (evidencia: evaluar + origen/destino de la arista)
    0x002D36AC: "(pulsó A/B (≤5f) Y tocando pared)", 0x002D2A18: "soltó la pared (4f sin contacto o stick hacia afuera)",
    0x002D2B0C: "sin vida (ctx14.vf8)", 0x002D40DC: "(en suelo Y pasaron N frames Y stick fuerte)",
    0x002D372C: "(pulsó A/B (≤5f) Y stick fuerte no hacia atrás)", 0x002D2A7C: "stick fuerte no hacia atrás (si {2}.vf0)",
    0x002D27A4: "stick hacia adelante", 0x002D3C38: "({2}.vf0 Y stick movido Y en suelo)",
    0x001BACFC: "cerca de la superficie ({0}.vf4 < 200)", 0x002D204C: "profundidad vs umbral según forma",
    0x002D5644: "pared al frente encarada (normal·frente ≥ K)", 0x002D3D44: "pared al frente con código 1", 0x002D2880: "volvió a tocar agua (flanco)", 0x001BAB9C: "{0}.vf0c ≠ 0", 0x001A9558: "valor previo de {0}",
}
# condiciones-reenvio: clase -> offset de vtable que llama sobre su argumento
REENVIO = {0x002D2814: 0x24, 0x002D3CBC: 0x24, 0x002D27CC: 0, 0x002D36D8: 0, 0x002D2C00: 0, 0x002D2C24: 0,
           0x00251F24: 0, 0x002D1E0C: 4, 0x002D27F0: 4, 0x002D2C48: 4, 0x002D1F7C: 0x28, 0x002D3148: 0x38,
           0x002D3FA4: 0x38, 0x002D3654: 0x5C, 0x002D3754: 0x3C, 0x002D37B4: 0x54, 0x002D3C60: 0x14,
           0x002D50EC: 8, 0x002D5A04: 0x58, 0x00251F38: 0}


def main():
    d = json.load(open(os.path.join(EXT, "grafo_llamadas.json"), encoding="utf-8"))
    objs = sorted(d["objetos"], key=lambda o: o["dir"])
    ll = [l for l in d["llamadas"] if l["a"] != NEW]
    por_dir = {o["dir"]: o for o in objs}
    args = {}      # objeto -> argumentos de su ctor
    hijos = {}     # lista AND/OR -> elementos
    nodo_estado = {}
    for l in ll:
        r = l["r"]
        if r[0] in por_dir and por_dir[r[0]]["ctor"] == l["a"] and r[0] not in args:
            args[r[0]] = r[1:] + l["pila"][:3]
        if l["a"] == NODO:
            nodo_estado[r[0]] = r[1]
        if l["a"] in (AND_ADD, OR_ADD):
            hijos.setdefault(r[0], []).append(r[1])

    def obj_de(v):
        for o in objs:
            if o["dir"] <= v < o["dir"] + max(o["tam"], 4):
                return o, v - o["dir"]
        return None, 0

    def nombre_estado(v):
        o, off = obj_de(v)
        if o is None:
            return f"0x{v:08X}"
        if o["dir"] in nodo_estado:   # es un nodo
            o, off = obj_de(nodo_estado[o["dir"]])
        n = ESTADOS.get(o["ctor"], f"FUN_{o['ctor']:08x}" if o["ctor"] else "?")
        return n + (f"+{off:x}" if off else "")

    def ctxn(v):
        k, off = divmod(v - MARCA, 0x1000)
        return CTX.get(k, f"ctx{k:x}") + (f"+{off:x}" if off else "")

    def cond(v, prof=0):
        if prof > 6:
            return "…"
        o, off = obj_de(v)
        if o is None:
            return f"0x{v:08X}"
        c = o["ctor"]
        if o["dir"] in nodo_estado or c in ESTADOS:
            return f"[{nombre_estado(v)} quiere entrar]"
        a = args.get(o["dir"], [])
        if c == NOT_CTOR:
            return "NO " + cond(a[0], prof + 1)
        if c in (AND_CTOR, OR_CTOR):
            sep = " Y " if c == AND_CTOR else " O "
            return "(" + sep.join(cond(x, prof + 1) for x in hijos.get(o["dir"], [])) + ")"
        if c in REENVIO and a:
            arg, k = a[0], REENVIO[c]
            if MARCA <= arg < MARCA_FIN:
                kk = (arg - MARCA) // 0x1000
                if kk == 3:
                    return CTRL.get(k, f"Ctrl.vf{k:x}")
                if kk == 5:
                    return COL.get(k, f"Col.vf{k:x}")
                return f"{ctxn(arg)}.vf{k:x}"
            return f"{nombre_estado(arg)}.vf{k:x}"
        def fa(x):
            if 0x00100000 <= x < 0x00100000 + len(CODE) and x not in por_dir:
                fin = CODE.find(bytes(1), x - 0x00100000)
                t = CODE[x - 0x00100000:fin]
                if 3 <= len(t) < 40 and all(32 <= c < 127 for c in t):
                    return '"' + t.decode() + '"'
            if x == 0:
                return "(actual)"
            if MARCA <= x < MARCA_FIN:
                return ctxn(x)
            if x == PARAM:
                return "PARAM"
            oo, _ = obj_de(x)
            if oo:
                return nombre_estado(x) if (oo["dir"] in nodo_estado or oo["ctor"] in ESTADOS) else "…"
            return str(x if x < 0x80000000 else x - (1 << 32)) if (x < 0x10000 or x > 0xFFFF0000) else f"0x{x:X}"
        if c is None:  # construida en linea: se identifica por su vtable y sus campos
            w = o.get("palabras", [])
            if o.get("vptr") in INLINE:
                return INLINE[o["vptr"]]
            return f"inline[vt {o.get('vptr', 0):08X}]({', '.join(fa(x) for x in w[1:4])})"
        if c == 0x00251F4C and len(a) > 1 and obj_de(a[1])[0] is not None:
            return f"durante {fa(a[0])} frames: {cond(a[1], prof + 1)}"
        if c == 0x001B9FD8 and len(a) > 1:
            return "pisó a un enemigo (ctx8.bit1)" if a[1] == 1 else f"petición externa bit{a[1]}"
        if c in CLASES:
            try:
                return CLASES[c].format(*[fa(x) for x in a[:3]])
            except (IndexError, KeyError):
                return CLASES[c]
        n = 2 if c in (0x002D2B0C, 0x00251F0C) else 3
        return f"F{c:06x}({', '.join(fa(x) for x in a[:n])})"

    # aristas por nodo, sin repetir, en orden de prioridad (orden de alta)
    salida = OrderedDict()
    for l in ll:
        if l["a"] == ARISTA:
            n, c, t = l["r"][:3]
            salida.setdefault(n, [])
            e = (cond(c), nombre_estado(t))
            if e not in salida[n]:
                salida[n].append(e)
    md = ["# Grafo de acciones de Mario (PlayerActionGraph_build)", "",
          "Generado por `tools\\grafo_legible.py` desde la emulacion (`tools\\emular_grafo.py`). "
          "Las aristas van en el orden en que el juego las registra (se evalúan en ese orden y gana la primera que se cumple — CONFIRMADO en PlayerActionExecutor_selectNext 0x0018144C).", ""]
    dot = ["digraph mario {", "  rankdir=LR; node [shape=box, fontname=Arial];"]
    for n, es in salida.items():
        md.append(f"## {nombre_estado(n)}  (nodo 0x{n:08X})")
        for c, t in es:
            md.append(f"- → **{t}** si {c}")
            dot.append(f'  "{nombre_estado(n)}" -> "{t}" [label="{c[:40].replace(chr(34), "")}"];')
        md.append("")
    dot.append("}")
    open(os.path.join(REP, "grafo_mario.md"), "w", encoding="utf-8").write("\n".join(md))
    open(os.path.join(EXT, "grafo_mario.dot"), "w", encoding="utf-8").write("\n".join(dot))
    print("estados con salidas:", len(salida), "aristas unicas:", sum(len(v) for v in salida.values()))


if __name__ == "__main__":
    main()
