"""Emula PlayerActionGraph_build (0x001A956C) con Unicorn para sacar el grafo de acciones de Mario EXACTO.

No ejecuta nada del juego mas alla de esa funcion: cada llamada que hace se intercepta y se
"stubea" (operator_new reparte memoria de un monticulo falso; el resto devuelve r0 = this).
El PlayerCore que recibe es falso: el campo k vale MARCA + k*0x1000, asi cada argumento se
resuelve a "ctx[k]" o a "objeto creado por X + desplazamiento".

Uso: py -I tools\\emular_grafo.py  -> escribe extraido\\grafo_llamadas.json
"""
import json
import os
import re
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_FPEXC,
                               UC_ARM_REG_C1_C0_2, UC_ARM_REG_CPSR)

AQUI = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(AQUI, "..", "extraido")
BASE = 0x00100000
BUILD = 0x001A956C
OPERATOR_NEW = 0x002932A8
GETTERS_FIJOS = {0x0026E1D4: 0x3F000000}  # tabla global de parametros del jugador
CORE = 0x20000000
SALIDA = 0x21000000
MARCA = 0x30000000      # ctx[k] = MARCA + k*0x1000
MARCA_FIN = 0x30100000
FALSO_7C = 0x30F00000   # lo que devuelve FUN_00308fc0 (core+0x7c)+4
HEAP = 0x10000000
PILA = 0x08000000
FIN = 0x0FFFF000        # direccion de retorno trampa


def nombres():
    d = {}
    for linea in open(os.path.join(EXT, "simbolos.txt"), encoding="utf-8"):
        m = re.match(r"\s*(0x[0-9A-Fa-f]+)\s+(\S+)", linea)
        if m:
            d[int(m.group(1), 16)] = m.group(2)
    return d


def main():
    code = open(os.path.join(EXT, "code.bin"), "rb").read()
    nom = nombres()
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0, 0x1000)
    uc.mem_write(0, b"\x1e\xff\x2f\xe1" * 0x400)  # llamadas a NULL: bx lr
    uc.mem_map(BASE, 0x00500000 - BASE)
    uc.mem_write(BASE, code)
    for base, tam in ((CORE, 0x10000), (SALIDA, 0x10000), (MARCA, 0x01000000), (HEAP, 0x01000000),
                      (PILA, 0x00100000), (FIN, 0x1000), (0x3F000000, 0x10000),
                      (0xE12FF000, 0x1000)):  # vtable leida de NULL -> puntero 'bx lr'; el hook la stubea
        uc.mem_map(base, tam)
    uc.mem_write(CORE, b"".join(struct.pack("<I", MARCA + k * 0x1000) for k in range(0x40)))
    uc.mem_write(CORE + 0x7C, struct.pack("<I", FALSO_7C - 4))
    # VFP encendido
    uc.reg_write(UC_ARM_REG_C1_C0_2, uc.reg_read(UC_ARM_REG_C1_C0_2) | (0xF << 20))
    uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    heap = [HEAP]
    objetos = []   # {dir, tam, ctor}
    llamadas = []

    def alloc(n):
        p = heap[0]
        heap[0] += (n + 0xF) & ~0xF
        objetos.append({"dir": p, "tam": n, "ctor": None})
        return p

    pendiente = [False]  # la instruccion anterior fue bl/blx: esta es la entrada de un llamado

    def es_llamada(w):
        return ((w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF) or (w & 0x0FFFFFF0) == 0x012FFF30             or (w & 0xFE000000) == 0xFA000000

    def hook(uc, addr, size, _):
        if addr == FIN:
            return
        if pendiente[0] and addr == pendiente[0] + 4:
            pendiente[0] = False  # bl condicional no tomado
        if not pendiente[0]:
            if es_llamada(struct.unpack("<I", uc.mem_read(addr, 4))[0]):
                pendiente[0] = addr
            return
        pendiente[0] = False
        r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        sp = uc.reg_read(UC_ARM_REG_SP)
        pila = list(struct.unpack("<6I", uc.mem_read(sp, 24)))
        lr = uc.reg_read(UC_ARM_REG_LR)
        ret = r[0]
        if addr == OPERATOR_NEW:
            ret = alloc(r[0])
        elif addr in GETTERS_FIJOS:
            ret = GETTERS_FIJOS[addr]
        elif addr == 0x00308FC0:
            ret = FALSO_7C
        else:
            for o in objetos:
                if o["dir"] == r[0] and o["ctor"] is None:
                    o["ctor"] = addr
                    break
        llamadas.append({"desde": lr - 4, "a": addr, "r": r, "pila": pila, "ret": ret})
        uc.reg_write(UC_ARM_REG_R0, ret)
        uc.reg_write(UC_ARM_REG_PC, lr)

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM_REG_SP, PILA + 0x000F0000)
    uc.reg_write(UC_ARM_REG_LR, FIN)
    uc.reg_write(UC_ARM_REG_R0, SALIDA)
    uc.reg_write(UC_ARM_REG_R1, CORE)
    try:
        uc.emu_start(BUILD, FIN, count=5_000_000)
        estado = "ok"
    except UcError as e:
        estado = f"error {e} en pc=0x{uc.reg_read(UC_ARM_REG_PC):08X}"
    salida = list(struct.unpack("<16I", uc.mem_read(SALIDA, 64)))
    for o in objetos:  # vtable escrita en linea (objetos sin ctor llamable)
        o["vptr"] = struct.unpack("<I", uc.mem_read(o["dir"], 4))[0]
        o["palabras"] = list(struct.unpack(f"<{max(o['tam'], 4) // 4}I", uc.mem_read(o["dir"], max(o["tam"], 4) // 4 * 4)))
    json.dump({"estado": estado, "objetos": objetos, "llamadas": llamadas, "salida": salida,
               "ret": uc.reg_read(UC_ARM_REG_R0)},
              open(os.path.join(EXT, "grafo_llamadas.json"), "w", encoding="utf-8"))
    print(estado, "| llamadas:", len(llamadas), "| objetos:", len(objetos))
    from collections import Counter
    c = Counter(nom.get(l["a"], f"FUN_{l['a']:08x}") for l in llamadas)
    for k, v in c.most_common(15):
        print(f"  {v:4} {k}")


if __name__ == "__main__":
    main()
