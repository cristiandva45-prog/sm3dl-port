"""Funciones que NO retornan (punto fijo) -> extraido\noreturn.txt (direccion, motivo).

Criterio verificable: el recorrido de la funcion (deteniendose tras un bl a una noreturn ya conocida y tras
svc ExitProcess 0x03 / Break 0x3C) no tiene NINGUNA salida: ni return (bx, pop/ldm pc, mov/ldr/add pc, aunque
sea condicional), ni salto fuera de su rango (cola a otra funcion, salvo a una noreturn), ni caida por el final,
ni instruccion que no decodifica.
Ojo: 0x3A0B68 NO es noreturn: es el despachador de comparaciones float de la RTL de ARM, que lee una palabra de
datos detras del bl y vuelve a una direccion calculada (add ip, lr, r4, lsl #2; bx ip).
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "recomp"))
import recomp  # noqa: E402
from capstone import arm  # noqa: E402

SVC_FIN = {0x03: "svc ExitProcess", 0x3C: "svc Break"}


def analizar(a, fin, nr):
    t = recomp.Traductor(a, fin, set())
    t.noreturn = nr
    ins = t.recorrer()
    motivo = "sin return"
    for i in ins.values():
        if i is None:
            return None
        if recomp.Traductor.termina(i):
            return None
        if i.id == arm.ARM_INS_B and i.operands[0].type == arm.ARM_OP_IMM:
            d = i.operands[0].imm
            if not (a <= d < fin):
                if d in nr:
                    motivo = f"cola a noreturn 0x{d:08X}"
                else:
                    return None
            if i.operands[0].imm == i.address:
                motivo = "bucle infinito b ."
        if i.id == arm.ARM_INS_BL and i.operands[0].type == arm.ARM_OP_IMM and i.operands[0].imm in nr \
                and i.cc in (arm.ARM_CC_AL, arm.ARM_CC_INVALID):
            motivo = f"llama a noreturn 0x{i.operands[0].imm:08X}"
        if i.id == arm.ARM_INS_SVC and i.operands[0].imm in SVC_FIN:
            motivo = SVC_FIN[i.operands[0].imm]
    # caida por el final: la ultima instruccion recorrida no cierra
    ult = ins[max(ins)]
    cierra = (ult.id == arm.ARM_INS_B and ult.cc in (arm.ARM_CC_AL, arm.ARM_CC_INVALID)) \
        or (ult.id == arm.ARM_INS_BL and ult.operands[0].imm in nr) \
        or (ult.id == arm.ARM_INS_SVC and ult.operands[0].imm in SVC_FIN)
    if not cierra:
        return None
    return motivo


def main():
    tam = recomp.tamanos()
    inicios = sorted(tam)
    nr = {}
    while True:
        nuevas = {}
        for a in inicios:
            if a in nr:
                continue
            m = analizar(a, recomp.limite(tam, inicios, a), nr)
            if m:
                nuevas[a] = m
        if not nuevas:
            break
        nr.update(nuevas)
    with open(os.path.join(RAIZ, "extraido", "noreturn.txt"), "w", encoding="utf-8") as fh:
        for a in sorted(nr):
            fh.write(f"{a:08X}\t{nr[a]}\n")
    print(f"noreturn: {len(nr)}")


if __name__ == "__main__":
    main()
