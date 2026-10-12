"""Descubre las funciones que Ghidra no tiene (metodos llamados solo por vtable, callbacks, destinos de bl
que cayeron en huecos) para que el recompilador las traduzca.

Uso: py -I tools\\descubrir_funciones.py
Sale: extraido\\funciones_extra.tsv  (direccion  tamano  origen)  -- recomp.py la lee junto a funciones.tsv

Semillas (solo direcciones alineadas a 4 que caen en un HUECO, fuera de toda funcion conocida):
  - palabras de .rodata/.data que apuntan a .text (vtables, tablas de callbacks)
  - literales de los literal pools que las funciones cargan con 'ldr rX, [pc, #k]'
  - destinos de bl/b de las funciones ya conocidas
Cada semilla se valida recorriendola con el mismo recorrer() del traductor: todo decodifica, nada de
instrucciones que solo aparecen al leer datos como codigo, y el recorrido termina (return o salto fuera).
Se repite con las funciones nuevas hasta que no aparece ninguna mas.
"""
import bisect
import os
import struct
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "recomp"))
import recomp  # noqa: E402
from capstone import arm  # noqa: E402

BASE, TEXT_FIN, CODE = recomp.BASE, recomp.TEXT_FIN, recomp.CODE
SEGMENTOS = {"rodata": (0x003A2000, 257616), "data": (0x003E1000, 76244)}
# instrucciones que en este juego solo salen al decodificar datos (texto, tablas) como si fueran codigo
SOSPECHOSAS = {arm.ARM_INS_CDP, arm.ARM_INS_CDP2, arm.ARM_INS_LDC, arm.ARM_INS_LDC2, arm.ARM_INS_STC, arm.ARM_INS_STC2,
               arm.ARM_INS_MCRR, arm.ARM_INS_MRRC, arm.ARM_INS_MCRR2, arm.ARM_INS_MRRC2, arm.ARM_INS_MCR2,
               arm.ARM_INS_MRC2, arm.ARM_INS_BKPT, arm.ARM_INS_UDF, arm.ARM_INS_SWP, arm.ARM_INS_SWPB,
               arm.ARM_INS_SMC, arm.ARM_INS_HVC, arm.ARM_INS_SRSDA, arm.ARM_INS_RFEDA, arm.ARM_INS_SETEND}


def literales(insns):
    """Valores que la funcion carga de su literal pool."""
    for i in insns.values():
        if i is None or i.id != arm.ARM_INS_LDR or len(i.operands) != 2:
            continue
        mem = i.operands[1]
        if mem.type == arm.ARM_OP_MEM and i.reg_name(mem.mem.base) == "pc" and not mem.mem.index:
            p = i.address + 8 + mem.mem.disp
            if BASE <= p < TEXT_FIN - 3:
                yield recomp.u32(p)


def valida(insns, entrada, fin):
    """None si parece una funcion de verdad; si no, el motivo."""
    if not insns:
        return "vacia"
    for i in insns.values():
        if i is None:
            return "no decodifica"
        if i.id in SOSPECHOSAS:
            return f"sospechosa {i.mnemonic}"
    ult = max(insns)
    i = insns[ult]
    # el ultimo tramo recorrido debe cerrar: si el recorrido se corto por el limite, es dato o la mitad de otra cosa
    termina = recomp.Traductor.termina(i) or (i.id == arm.ARM_INS_B and i.cc in (arm.ARM_CC_AL, arm.ARM_CC_INVALID))
    if not termina and ult + 4 >= fin:
        return "no termina"
    return None


def cae_en_siguiente(insns, fin, origen):
    """El recorrido llega por flujo justo al inicio de la siguiente funcion (0x149750 'sub r0,#0x60; nop' -> metodo;
    0x1051F0 'push; bl; bl; pop {r4,lr}; nop' -> 0x105204). Para semillas que vienen de un PUNTERO la guarda es mas
    estricta: una tabla de ceros (andeq r0,r0,r0) o un dato que decodifica tambien 'caeria' en la funcion de al lado."""
    ult = max(insns)
    if ult + 4 != fin:
        return False
    if origen == "salto":  # destino de un salto del codigo: es codigo seguro
        return True
    if any(recomp.u32(a) == 0 for a in insns):
        return False
    al = (arm.ARM_CC_AL, arm.ARM_CC_INVALID)
    return insns[min(insns)].cc in al and insns[ult].cc in al


def main():
    tam = recomp.tamanos(extra=False)
    conocidas = sorted(tam)

    def en_funcion(x):
        k = bisect.bisect_right(conocidas, x) - 1
        return k >= 0 and x < conocidas[k] + tam[conocidas[k]]

    # el flujo de cada funcion conocida llega hasta la siguiente (recomp.limite): lo que alcanza ya esta traducido
    recorridos, cubiertas = {}, set()
    for a in conocidas:
        fin = recomp.limite(tam, conocidas, a)
        recorridos[a] = (fin, recomp.Traductor(a, fin, set()).recorrer())
        cubiertas.update(recorridos[a][1])

    def en_hueco(v):  # para punteros: fuera de todo codigo alcanzado y de los rangos de Ghidra
        return BASE <= v < TEXT_FIN and v % 4 == 0 and v not in tam and v not in cubiertas and not en_funcion(v)

    def salta_fuera(a, fin, v):  # para saltos: si salen del rango de su funcion necesitan entrada propia
        return BASE <= v < TEXT_FIN and v % 4 == 0 and v not in tam and not (a <= v < fin)

    semillas = {}  # direccion -> origen
    for seg, (s, n) in SEGMENTOS.items():
        for off in range(0, n - 3, 4):
            v = struct.unpack_from("<I", CODE, s - BASE + off)[0]
            if en_hueco(v):
                semillas.setdefault(v, seg)
    print(f"semillas de .rodata/.data: {len(semillas)}")

    nuevas_de = Counter()
    for a, (fin, ins) in recorridos.items():  # literales y saltos de las funciones conocidas
        for v in literales(ins):
            if en_hueco(v) and v not in semillas:
                semillas[v] = "literal"
                nuevas_de["literal"] += 1
        for v in recomp.llamadas_de(ins):
            if salta_fuera(a, fin, v) and v not in semillas:
                semillas[v] = "salto"
                nuevas_de["salto"] += 1
    print(f"semillas de literales/saltos: {dict(nuevas_de)}")

    aceptadas, rechazos, rechazadas = {}, Counter(), {}
    probadas = set()
    esperando = {}  # caen en una semilla que aun no se decidio: a -> (fin, motivo)
    cae_n = Counter()
    while True:
        pend = sorted(set(semillas) - probadas - set(esperando))
        if not pend:
            # reintentar las que caen en otra semilla: si esa ya se acepto, se aceptan; si nada cambia, se rechazan
            listas = [a for a, (fin, _) in esperando.items() if fin in aceptadas or fin in rechazadas]
            if not listas:
                for a, (fin, motivo) in esperando.items():
                    rechazos[f"{semillas[a]}: {motivo}"] += 1
                    rechazadas[a] = (semillas[a], motivo, fin)
                break
            pend = sorted(listas)
            for a in pend:
                del esperando[a]
                probadas.discard(a)
        inicios = sorted(set(conocidas) | set(semillas))
        for a in pend:
            probadas.add(a)
            fin = recomp.limite(tam, inicios, a)
            ins = recomp.Traductor(a, fin, set()).recorrer()
            motivo = valida(ins, a, fin)
            if motivo == "no termina" and cae_en_siguiente(ins, fin, semillas[a]):
                # cae por flujo en la funcion de al lado (thunk que ajusta this, o una llamada que sigue de largo):
                # el traductor lo resuelve con rt_llamar(fin), asi que vale si fin es una funcion de verdad
                if fin in tam or fin in aceptadas:
                    motivo = None
                    cae_n[semillas[a]] += 1
                elif fin in semillas and fin not in rechazadas:
                    esperando[a] = (fin, motivo)
                    continue
            if motivo:
                rechazos[f"{semillas[a]}: {motivo}"] += 1
                rechazadas[a] = (semillas[a], motivo, fin)
                continue
            aceptadas[a] = (fin, ins)
            cubiertas.update(ins)
            for v in literales(ins):
                if en_hueco(v) and v not in semillas:
                    semillas[v] = "derivada"
            for v in recomp.llamadas_de(ins):
                if salta_fuera(a, fin, v) and v not in semillas:
                    semillas[v] = "derivada"
    # limites finales con todos los inicios conocidos
    inicios = sorted(set(conocidas) | set(aceptadas))
    salida = os.path.join(RAIZ, "extraido", "funciones_extra.tsv")
    cubiertos, n_ins = 0, 0
    with open(salida, "w", encoding="utf-8") as fh:
        for a in sorted(aceptadas):
            fin = recomp.limite(tam, inicios, a)
            ins = recomp.Traductor(a, fin, set()).recorrer()
            n_ins += len(ins)
            fh.write(f"{a:08X}\t{fin - a}\t{semillas[a]}\n")
    print(f"aceptadas: {len(aceptadas)} ({Counter(semillas[a] for a in aceptadas)}), {n_ins} instrucciones")
    print(f"  de ellas caen en la siguiente funcion: {dict(cae_n)}")
    print("rechazadas:", dict(rechazos.most_common()))
    with open(os.path.join(RAIZ, "extraido", "funciones_rechazadas.tsv"), "w", encoding="utf-8") as fh:
        for a in sorted(rechazadas):
            o, m, fin = rechazadas[a]
            fh.write(f"{a:08X}\t{fin - a}\t{o}\t{m}\n")
    print(f"-> {salida}")


if __name__ == "__main__":
    main()
