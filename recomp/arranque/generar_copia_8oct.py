r"""Genera la COPIA del juego recompilado para el arranque (recomp\arranque\todo.c) con los arreglos que el traductor
todavia no tiene. Usa una copia congelada del traductor (recomp_base.py), para no depender de cambios a medio hacer.

Uso: py -I recomp\arranque\generar.py   (despues: reconstruir.sh, o partir + compilar_todo + compilar)

Arreglos (los mismos que hay que llevar a recomp.py):
1. limite(): cuando Ghidra tiene funciones SOLAPADAS (0x293474 y 0x293478 = la misma con otra entrada), la
   "siguiente funcion" cae DENTRO del tamano de Ghidra y el limite termina ahi; ademas el tamano de Ghidra deja
   fuera la llamada de cola final ('b 0x1051F0' en 0x29348C). Se toma la primera funcion que empiece en o despues
   del final de Ghidra, no la primera despues de la entrada.
2. 'mov{cc} pc, lr' = retorno (lo aplica parchear.py sobre el C generado).
"""
import bisect
import os
import re
import subprocess
import sys

A = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, A)
import recomp_base as recomp  # noqa: E402


def limite(tam, inicios, a):
    fin_g = a + tam.get(a, 0)
    k = bisect.bisect_left(inicios, max(a + 1, fin_g))
    sig = inicios[k] if k < len(inicios) else min(a + 0x1000, recomp.TEXT_FIN)
    return max(sig, fin_g)


def llamadas_manuales():
    """Arreglo 3: 'add lr, pc, #k' (o 'mov lr, pc') + 'mov pc, rX' / 'bx rX' con lr = instruccion siguiente es una
    LLAMADA, no un salto de cola. Es como __cpp_initialize__aeabi_ (0x3A0D9C) llama a cada constructor de
    .init_array; tratado como final de funcion, solo corria el primer constructor y el lock 0x3FA700 quedaba en 0."""
    from capstone import arm
    md = recomp.md
    res = {}
    base, fin = recomp.BASE, recomp.TEXT_FIN
    ins = {}
    for a in range(base, fin, 4):
        try:
            ins[a] = next(md.disasm(recomp.CODE[a - base:a - base + 4], a))
        except StopIteration:
            pass
    for a, i in ins.items():
        if i.cc not in (arm.ARM_CC_AL, arm.ARM_CC_INVALID) or len(i.operands) < 1:
            continue
        es_mov = i.id == arm.ARM_INS_MOV and len(i.operands) == 2 and i.reg_name(i.operands[0].reg) == "pc" \
            and i.operands[1].type == arm.ARM_OP_REG and not i.operands[1].shift.value
        es_bx = i.id == arm.ARM_INS_BX and i.operands[0].type == arm.ARM_OP_REG
        if not (es_mov or es_bx):
            continue
        r = i.reg_name((i.operands[1] if es_mov else i.operands[0]).reg)
        if r in ("lr", "pc"):
            continue
        for k in range(1, 4):
            p = ins.get(a - 4 * k)
            if p is None:
                break
            ops = p.operands
            if not ops or ops[0].type != arm.ARM_OP_REG or p.reg_name(ops[0].reg) != "lr":
                continue
            L = None
            if p.id == arm.ARM_INS_ADD and len(ops) == 3 and p.reg_name(ops[1].reg) == "pc" and ops[2].type == arm.ARM_OP_IMM:
                L = p.address + 8 + ops[2].imm
            elif p.id == arm.ARM_INS_MOV and len(ops) == 2 and ops[1].type == arm.ARM_OP_REG and p.reg_name(ops[1].reg) == "pc":
                L = p.address + 8
            if L == a + 4 and p.cc in (arm.ARM_CC_AL, arm.ARM_CC_INVALID):
                res[a] = recomp.REG[r]
            break  # la escritura de lr mas cercana decide
    return res


INIT_ARRAY = (0x003A0DDC, 0x003A177C)  # la recorre __cpp_initialize__aeabi_ (0x3A0D9C); entradas RELATIVAS a si mismas


def constructores():
    """Arreglo 4: los constructores estaticos de .init_array (armcc: desplazamiento relativo a la entrada).
    Ni Ghidra ni descubrir_funciones.py los ven (no hay puntero absoluto ni bl hacia ellos)."""
    import struct
    res = []
    for a in range(*INIT_ARRAY, 4):
        t = (a + struct.unpack_from("<I", recomp.CODE, a - recomp.BASE)[0]) & 0xFFFFFFFF
        if recomp.BASE <= t < recomp.TEXT_FIN:
            res.append(t)
    return res


def punteros_relativos():
    """Arreglo 6: punteros a funcion PC-RELATIVOS de la biblioteca C de armcc (codigo PIC):
    'ldr rX, [pc, #k]' + 'add rY, pc, rX'  ->  destino = literal + direccion_del_add + 8.
    El literal es un DESPLAZAMIENTO, no una direccion, asi que ni Ghidra ni descubrir_funciones.py los ven. Asi
    pasa __vfscanf/_printf_core (0x10AED4) sus callbacks de lectura (0x289EA0, 0x10A470) y los llama con
    'add lr, pc, #4 ; mov pc, r1' -> rt_externo. Son 8 en todo .text."""
    from capstone import arm
    md, BASE, FIN, CODE = recomp.md, recomp.BASE, recomp.TEXT_FIN, recomp.CODE
    ins = {}
    for a in range(BASE, FIN, 4):
        try:
            ins[a] = next(md.disasm(CODE[a - BASE:a - BASE + 4], a))
        except StopIteration:
            pass
    res = set()
    for a, i in ins.items():
        o = i.operands
        if i.id != arm.ARM_INS_ADD or len(o) != 3 or o[1].type != arm.ARM_OP_REG or o[2].type != arm.ARM_OP_REG:
            continue
        r1, r2 = i.reg_name(o[1].reg), i.reg_name(o[2].reg)
        if "pc" not in (r1, r2) or r1 == r2:
            continue
        rx = r2 if r1 == "pc" else r1
        for k in range(1, 8):
            p = ins.get(a - 4 * k)
            if p is None:
                break
            po = p.operands
            if po and po[0].type == arm.ARM_OP_REG and p.reg_name(po[0].reg) == rx:
                if p.id == arm.ARM_INS_LDR and len(po) == 2 and po[1].type == arm.ARM_OP_MEM                         and p.reg_name(po[1].mem.base) == "pc" and not po[1].mem.index:
                    t = (recomp.u32(p.address + 8 + po[1].mem.disp) + a + 8) & 0xFFFFFFFF
                    if BASE <= t < FIN and t % 4 == 0:
                        res.add(t)
                break  # la escritura de rX mas cercana decide
    return sorted(res)


def punteros_internos(tam):
    """Arreglo 8: punteros de .rodata/.data (vtables) que caen DENTRO del rango de una funcion de Ghidra, justo despues
    de un final incondicional (b / bx lr / pop {pc}): Ghidra fundio dos metodos en una funcion (0x1BD0E4, 60 bytes,
    tiene dentro el metodo 0x1BD118) y descubrir_funciones.py descarta todo lo que cae dentro de un rango de Ghidra.
    El hilo 7 lo llama por 'blx r2' (0x318910) -> rt_externo. ~21 en todo el binario; pasan por la validacion de
    derivadas() (decodifica, nada sospechoso, termina)."""
    import struct
    from capstone import arm
    BASE, FIN, CODE = recomp.BASE, recomp.TEXT_FIN, recomp.CODE
    ini = sorted(tam)
    res = set()

    def dec(a):
        try:
            return next(recomp.md.disasm(CODE[a - BASE:a - BASE + 4], a))
        except StopIteration:
            return None
    for s, n in ((0x003A2000, 257616), (0x003E1000, 76244)):
        for o in range(0, n - 3, 4):
            v = struct.unpack_from("<I", CODE, s - BASE + o)[0]
            if not (BASE <= v < FIN and v % 4 == 0) or v in tam:
                continue
            k = bisect.bisect_right(ini, v) - 1
            if k < 0 or not v < ini[k] + tam[ini[k]]:
                continue
            p = dec(v - 4)
            if p is None or dec(v) is None or p.cc not in (arm.ARM_CC_AL, arm.ARM_CC_INVALID):
                continue
            if recomp.Traductor.termina(p) or p.id == arm.ARM_INS_B:
                res.add(v)
    return sorted(res)


SOSPECHOSAS = None


def derivadas(tam, semillas, forzadas=()):
    """Arreglo 5: cierre sobre las funciones que agrega el arranque (constructores de .init_array).
    descubrir_funciones.py siembra con los LITERALES y saltos de las funciones conocidas, pero los constructores
    nuevos (arreglo 4) no estaban cuando corrio: sus punteros a funcion nunca se sembraron (0x38A188 carga
    0x001ED5B4 y se lo pasa a __aeabi_vec_ctor 0x28EAB4 -> rt_externo). Se recorre cada funcion nueva, se toman sus
    literales que caen en .text (alineados, fuera de toda funcion y fuera del flujo de la funcion anterior) y los
    destinos de b/bl fuera de su rango; se validan como descubrir_funciones (decodifica, nada sospechoso, termina)
    y se repite con las aceptadas."""
    from capstone import arm
    global SOSPECHOSAS
    SOSPECHOSAS = {arm.ARM_INS_CDP, arm.ARM_INS_CDP2, arm.ARM_INS_LDC, arm.ARM_INS_LDC2, arm.ARM_INS_STC,
                   arm.ARM_INS_STC2, arm.ARM_INS_MCRR, arm.ARM_INS_MRRC, arm.ARM_INS_MCRR2, arm.ARM_INS_MRRC2,
                   arm.ARM_INS_MCR2, arm.ARM_INS_MRC2, arm.ARM_INS_BKPT, arm.ARM_INS_UDF, arm.ARM_INS_SWP,
                   arm.ARM_INS_SWPB, arm.ARM_INS_SMC, arm.ARM_INS_HVC, arm.ARM_INS_SRSDA, arm.ARM_INS_RFEDA,
                   arm.ARM_INS_SETEND}
    BASE, FIN = recomp.BASE, recomp.TEXT_FIN
    d = dict(tam)
    inicios = sorted(d)
    flujo = {}

    def recorrido(a):
        if a not in flujo:
            flujo[a] = recomp.Traductor(a, limite(d, inicios, a), set()).recorrer()
        return flujo[a]

    def en_hueco(v):
        if not (BASE <= v < FIN and v % 4 == 0) or v in d:
            return False
        k = bisect.bisect_right(inicios, v) - 1
        if k >= 0:
            a = inicios[k]
            if v < a + d[a] or v in recorrido(a):
                return False
        return True

    def literales(ins):
        for i in ins.values():
            if i is None or i.id != arm.ARM_INS_LDR or len(i.operands) != 2:
                continue
            m = i.operands[1]
            if m.type == arm.ARM_OP_MEM and i.reg_name(m.mem.base) == "pc" and not m.mem.index:
                p = i.address + 8 + m.mem.disp
                if BASE <= p < FIN - 3:
                    yield recomp.u32(p)

    def valida(ins, fin):
        if not ins or any(i is None or i.id in SOSPECHOSAS for i in ins.values()):
            return False
        u = ins[max(ins)]
        cierra = recomp.Traductor.termina(u) or (u.id == arm.ARM_INS_B and u.cc in (arm.ARM_CC_AL, arm.ARM_CC_INVALID))
        return cierra or max(ins) + 4 < fin or (max(ins) + 4 == fin and fin in d)

    nuevas = []
    for v in forzadas:  # punteros de verdad (los usa un salto por registro): solo se exige que decodifiquen
        if v in d:
            continue
        k = bisect.bisect_right(inicios, v)
        sig = inicios[k] if k < len(inicios) else min(v + 0x1000, FIN)
        if valida(recomp.Traductor(v, sig, set()).recorrer(), sig):
            d[v] = 0
            bisect.insort(inicios, v)
            nuevas.append(v)
    flujo.clear()
    pend = list(semillas) + list(nuevas)
    while pend:
        a = pend.pop()
        ins = recorrido(a)
        fin = limite(d, inicios, a)
        cand = [v for v in literales(ins)] + [v for v in recomp.llamadas_de(ins) if not (a <= v < fin)]
        for v in cand:
            if not en_hueco(v):
                continue
            k = bisect.bisect_right(inicios, v)
            sig = inicios[k] if k < len(inicios) else min(v + 0x1000, FIN)
            iv = recomp.Traductor(v, sig, set()).recorrer()
            if not valida(iv, sig):
                continue
            d[v] = 0
            bisect.insort(inicios, v)
            flujo.clear()  # los limites cambiaron
            nuevas.append(v)
            pend.append(v)
    return nuevas


def main():
    recomp.limite = limite
    derivadas_cache, hecho, sueltos = [], [], []
    ctors = constructores()
    relativos = punteros_relativos()
    print(f"punteros PC-relativos (arreglo 6): {len(relativos)}: " + ", ".join(f"0x{x:08X}" for x in relativos))
    viejo_tamanos = recomp.tamanos

    def tamanos(*a, **k):
        d = viejo_tamanos(*a, **k)
        nuevos = [t for t in ctors if t not in d]
        for t in nuevos:
            d[t] = 0  # limite() llega hasta la siguiente funcion
        if not hecho:
            hecho.append(1)
            internos = punteros_internos(d)
            print(f"punteros de vtable dentro de un rango de Ghidra (arreglo 8): {len(internos)}")
            derivadas_cache.extend(derivadas(d, nuevos, relativos + internos))
            print(f"punteros derivados de los constructores (arreglos 5+6): {len(derivadas_cache)}: "
                  + ", ".join(f"0x{x:08X}" for x in sorted(derivadas_cache)[:12]))
        for t in derivadas_cache + sueltos:
            d.setdefault(t, 0)
        return d
    recomp.tamanos = tamanos
    print(f"constructores de .init_array: {len(ctors)}")
    manuales = llamadas_manuales()
    print(f"llamadas manuales (lr fijado a mano + salto por registro): {len(manuales)}: "
          + ", ".join(f"0x{a:08X}" for a in sorted(manuales)[:12]))
    viejo_termina = recomp.Traductor.termina
    recomp.Traductor.termina = staticmethod(lambda i: False if i.address in manuales else viejo_termina(i))
    viejo_traducir = recomp.Traductor.traducir

    def traducir(self, i):
        if i.address in manuales:
            return [f"{{ u32 t = c->r[{manuales[i.address]}]; c->r[14] = 0x{i.address + 4:08X}u; rt_llamar(c, t); }}"]
        return viejo_traducir(self, i)
    recomp.Traductor.traducir = traducir
    salida = os.path.join(A, "todo.c")
    for vuelta in range(4):
        sys.argv = ["recomp", "--todo", "-o", salida]
        recomp.main()
        # Arreglo 7: un SALTO DIRECTO (b/bl/bcc) a codigo que no es funcion sale como rt_externo(c, 0x...) constante y
        # el exe muere ahi (0x28966C __aeabi_uidiv: 'b 0x288738' al nucleo de division compartido; descubrir la
        # rechazo por 'no termina' porque cae por flujo en 0x288760). Es destino de un salto del codigo: es codigo.
        # Se agrega como funcion (el traductor resuelve la caida en la siguiente con rt_llamar) y se regenera.
        with open(salida, encoding="utf-8") as fh:
            nuevos = sorted({int(x, 16) for x in re.findall(r"rt_externo\(c, 0x([0-9A-F]{8})u\)", fh.read())} - set(sueltos))
        if not nuevos:
            break
        print(f"saltos directos a codigo sin funcion (arreglo 7, vuelta {vuelta + 1}): "
              + ", ".join(f"0x{x:08X}" for x in nuevos))
        sueltos.extend(nuevos)
    subprocess.run([sys.executable, "-I", os.path.join(A, "parchear.py")], check=True)


if __name__ == "__main__":
    main()
