"""Recompilador estatico ARM11 -> C para Super Mario 3D Land (prototipo).

Uso: py -I recomp\\recomp.py <dir_funcion> [...] [--cierre] [--todo] -o recomp\\gen\\juego.c
  --cierre : agrega tambien las funciones a las que llaman (bl), recursivamente
  --excluir <dir,...> : direcciones que NO se traducen (se llaman por rt_externo; p. ej. las que una prueba stubea)

Cada funcion original X se vuelve  void f_X(CPU *c).  Instrucciones = sentencias C sobre el CPU virtual;
saltos internos = goto; bl a una funcion traducida = llamada directa; a una no traducida = rt_externo;
saltos indirectos = rt_llamar (tabla generada al final). Lo no soportado se emite como rt_desconocida().

Limites de funcion: tabla de tamanos de Ghidra (extraido\\funciones.tsv). Se recorre desde la entrada
siguiendo saltos, para no traducir los literal pools.
"""
import os
import re
import struct
import sys
from collections import Counter

import capstone
from capstone import arm

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # copia en recomp/arranque: apunta a recomp
RAIZ = os.path.dirname(AQUI)
CODE = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
BASE = 0x00100000
TEXT_FIN = BASE + 2758524

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
md.detail = True

REG = {f"r{i}": i for i in range(16)}
REG.update({"sb": 9, "sl": 10, "fp": 11, "ip": 12, "sp": 13, "lr": 14, "pc": 15})
CC = {arm.ARM_CC_EQ: "c->z", arm.ARM_CC_NE: "!c->z", arm.ARM_CC_HS: "c->c", arm.ARM_CC_LO: "!c->c",
      arm.ARM_CC_MI: "c->n", arm.ARM_CC_PL: "!c->n", arm.ARM_CC_VS: "c->v", arm.ARM_CC_VC: "!c->v",
      arm.ARM_CC_HI: "(c->c && !c->z)", arm.ARM_CC_LS: "(!c->c || c->z)", arm.ARM_CC_GE: "(c->n == c->v)",
      arm.ARM_CC_LT: "(c->n != c->v)", arm.ARM_CC_GT: "(!c->z && c->n == c->v)",
      arm.ARM_CC_LE: "(c->z || c->n != c->v)"}

FALTAN = Counter()

# extensiones de signo/cero (ARMv6): V = fuente ya rotada, A = sumando de las variantes 'xta'
EXTENSIONES = {
    "uxtb": "(u32)(u8)(V)", "uxth": "(u32)(u16)(V)", "sxtb": "(u32)(s32)(s8)(V)", "sxth": "(u32)(s32)(s16)(V)",
    "uxtab": "A + (u32)(u8)(V)", "uxtah": "A + (u32)(u16)(V)",
    "sxtab": "A + (u32)(s32)(s8)(V)", "sxtah": "A + (u32)(s32)(s16)(V)",
    "uxtb16": "uxtb16(V)", "sxtb16": "sxtb16(V)", "uxtab16": "uxtab16(A, V)", "sxtab16": "sxtab16(A, V)",
}


def u32(a):
    return struct.unpack_from("<I", CODE, a - BASE)[0]


def tamanos(extra=True):
    d = {}
    p = os.path.join(RAIZ, "extraido", "funciones.tsv")
    for linea in open(p):
        a, t = linea.split()
        d[int(a, 16)] = int(t)
    # las que Ghidra no tiene (vtables, epilogos que corto, callbacks): tools\descubrir_funciones.py
    p = os.path.join(RAIZ, "extraido", "funciones_extra.tsv")
    if extra and os.path.exists(p) and "--sin-extra" not in sys.argv:
        for linea in open(p):
            a, t = linea.split()[:2]
            d.setdefault(int(a, 16), int(t))
    return d


class Error(Exception):
    pass


class ImmRotado:
    """Operando inmediato ya rotado (capstone entrega #valor, #rotacion por separado)."""
    type = arm.ARM_OP_IMM
    subtracted = False

    def __init__(self, imm, rot):
        self.imm, self.rot = imm, rot


class Traductor:
    def __init__(self, entrada, fin, traducidas):
        self.entrada, self.fin, self.trad = entrada, fin, traducidas
        self.lineas = []

    # ---------- operandos ----------
    def rn(self, i, op):
        name = i.reg_name(op.reg)
        if name not in REG:
            raise Error(f"registro {name}")
        return REG[name]

    def rv(self, i, op):
        """valor C de un registro como operando (pc = direccion+8)."""
        r = self.rn(i, op)
        return f"0x{i.address + 8:08X}u" if r == 15 else f"c->r[{r}]"

    def sreg(self, i, op):
        name = i.reg_name(op.reg)
        m = re.fullmatch(r"s(\d+)", name)
        if not m:
            raise Error(f"registro vfp {name}")
        return int(m.group(1))

    def op2(self, i, op, necesita_carry):
        """(expresion C, expresion de acarreo o None) para el operando flexible."""
        if op.type == arm.ARM_OP_IMM:
            v = op.imm & 0xFFFFFFFF
            carry = None
            rot = getattr(op, "rot", None)
            if necesita_carry and (rot if rot is not None else v > 0xFF):
                carry = str(v >> 31)  # constante rotada: el acarreo es su bit 31
            return f"0x{v:08X}u", carry
        if op.type != arm.ARM_OP_REG:
            raise Error("op2 raro")
        v = self.rv(i, op)
        st, sv = op.shift.type, op.shift.value
        if st == arm.ARM_SFT_INVALID or (st == arm.ARM_SFT_LSL and sv == 0):
            return v, None
        cin = "c->c"
        if st in (arm.ARM_SFT_LSL, arm.ARM_SFT_LSR, arm.ARM_SFT_ASR, arm.ARM_SFT_ROR):
            fn = {arm.ARM_SFT_LSL: "lsl_i", arm.ARM_SFT_LSR: "lsr_i", arm.ARM_SFT_ASR: "asr_i", arm.ARM_SFT_ROR: "ror_i"}[st]
            args = f"{v}, {sv}, {cin}, &co" if fn == "lsl_i" else f"{v}, {sv}, &co"
            return f"{fn}({args})", "co"
        if st == arm.ARM_SFT_RRX:
            return f"rrx({v}, {cin}, &co)", "co"
        fn = {arm.ARM_SFT_LSL_REG: "lsl_r", arm.ARM_SFT_LSR_REG: "lsr_r", arm.ARM_SFT_ASR_REG: "asr_r",
              arm.ARM_SFT_ROR_REG: "ror_r"}.get(st)
        if fn:
            sr = REG[i.reg_name(sv)]
            return f"{fn}({v}, c->r[{sr}], {cin}, &co)", "co"
        raise Error(f"desplazamiento {st}")

    def direccion(self, i, mem, extra):
        """(expresion de direccion efectiva, sentencia de writeback o '')."""
        base = REG[i.reg_name(mem.mem.base)]
        bexp = f"0x{i.address + 8:08X}u" if base == 15 else f"c->r[{base}]"
        if mem.mem.index:
            idx = f"c->r[{REG[i.reg_name(mem.mem.index)]}]"
            if mem.shift.type == arm.ARM_SFT_LSL and mem.shift.value:
                idx = f"({idx} << {mem.shift.value})"
            elif mem.shift.type == arm.ARM_SFT_LSR:
                idx = f"({idx} >> {mem.shift.value})"
            elif mem.shift.type == arm.ARM_SFT_ASR:
                idx = f"(u32)((s32){idx} >> {mem.shift.value})"
            elif mem.shift.type == arm.ARM_SFT_ROR:  # 'ldrb r1, [r1, r4, ror #29]' (0x2372xx)
                idx = f"ror32({idx}, {mem.shift.value})"
            elif mem.shift.type not in (arm.ARM_SFT_INVALID, arm.ARM_SFT_LSL):
                raise Error("indice desplazado raro")
            off = f"- {idx}" if mem.subtracted else f"+ {idx}"
        else:
            d = mem.mem.disp  # capstone ya lo da con signo
            off = f"+ 0x{d & 0xFFFFFFFF:08X}u" if d >= 0 else f"- 0x{-d:08X}u"
        if extra is not None:  # post-indice: se accede en base y luego base += extra
            if extra.type == arm.ARM_OP_IMM:
                e = extra.imm
                if extra.subtracted and e > 0:
                    e = -e
                inc = f"+ 0x{e:08X}u" if e >= 0 else f"- 0x{-e:08X}u"
            else:
                r = f"c->r[{REG[i.reg_name(extra.reg)]}]"
                inc = f"- {r}" if extra.subtracted else f"+ {r}"
            return bexp, f"c->r[{base}] = c->r[{base}] {inc};"
        efect = f"({bexp} {off})"
        if i.writeback:
            return f"ea", f"c->r[{base}] = ea;"
        return efect, ""

    # ---------- emision ----------
    def llamar(self, destino, ret):
        if destino in self.trad:
            return f"c->r[14] = 0x{ret:08X}u; f_{destino:08X}(c);"
        return f"c->r[14] = 0x{ret:08X}u; rt_externo(c, 0x{destino:08X}u);"

    def traducir(self, i):
        """Lista de sentencias C para la instruccion i (sin la condicion)."""
        m = i.mnemonic.split(".")[0]
        ops = i.operands
        sig = i.address + 4
        # quitar sufijo de condicion del mnemonico (capstone lo deja pegado: moveq, ldrne...)
        base_m = m
        if i.cc != arm.ARM_CC_AL:
            for suf in ("eq", "ne", "hs", "lo", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le", "cs", "cc"):
                if base_m.endswith(suf) and len(base_m) > len(suf):
                    base_m = base_m[: -len(suf)]
                    break
        # La 'S' se decide por el MNEMONICO: capstone marca update_flags tambien en adc/sbc/rsc,
        # que solo LEEN el acarreo (bug hallado por la bateria por instruccion).
        s = False
        if base_m.endswith("s") and base_m[:-1] in ("mov", "mvn", "add", "adc", "sub", "sbc", "rsb", "rsc", "and",
                                                     "orr", "eor", "bic", "mul", "mla", "lsl", "lsr", "asr", "ror", "rrx"):
            base_m = base_m[:-1]
            s = True
        m = base_m
        # constante con rotacion: capstone la da como DOS inmediatos (#24, #28 = 24 ror 28)
        if len(ops) >= 2 and ops[-1].type == arm.ARM_OP_IMM and ops[-2].type == arm.ARM_OP_IMM and \
                m in ("mov", "mvn", "add", "adc", "sub", "sbc", "rsb", "rsc", "and", "orr", "eor", "bic",
                      "cmp", "cmn", "tst", "teq"):
            v, rot = ops[-2].imm & 0xFFFFFFFF, ops[-1].imm & 31
            ops = list(ops[:-2]) + [ImmRotado(((v >> rot) | (v << (32 - rot))) & 0xFFFFFFFF if rot else v, rot)]

        # ----- saltos -----
        if m == "b":
            t = ops[0].imm
            if self.entrada <= t < self.fin:
                return [f"goto L_{t:08X};"]
            return [self.llamar(t, sig).replace(f"c->r[14] = 0x{sig:08X}u; ", "") + " return;"]
        if m == "bl":
            return [self.llamar(ops[0].imm, sig)]
        if m == "blx":
            if ops[0].type == arm.ARM_OP_IMM:
                raise Error("blx a thumb")
            return [f"{{ u32 t = {self.rv(i, ops[0])}; c->r[14] = 0x{sig:08X}u; rt_llamar(c, t); }}"]
        if m == "bx":
            r = self.rn(i, ops[0])
            if r == 14:
                return ["return;"]
            return [f"rt_llamar(c, c->r[{r}]); return;"]
        # ----- procesamiento de datos -----
        if m in ("mov", "mvn"):
            d = self.rn(i, ops[0])
            e, co = self.op2(i, ops[1], s)
            if m == "mvn":
                e = f"~({e})"
            if d == 15:
                return [f"{{ u32 co = c->c; (void)co; u32 t = {e}; rt_llamar(c, t); return; }}"]
            out = [f"{{ u32 co = c->c; u32 res = {e}; c->r[{d}] = res;"]
            if s:
                out.append(f"nz(c, res);" + (f" c->c = {co};" if co else ""))
            return [" ".join(out) + " }"]
        if m in ("lsl", "lsr", "asr", "ror") and len(ops) == 3:
            d, a = self.rn(i, ops[0]), self.rv(i, ops[1])
            if ops[2].type == arm.ARM_OP_IMM:
                n = ops[2].imm
                fn = {"lsl": "lsl_i", "lsr": "lsr_i", "asr": "asr_i", "ror": "ror_i"}[m]
                e = f"lsl_i({a}, {n}, c->c, &co)" if m == "lsl" else f"{fn}({a}, {n}, &co)"
            else:
                fn = {"lsl": "lsl_r", "lsr": "lsr_r", "asr": "asr_r", "ror": "ror_r"}[m]
                e = f"{fn}({a}, {self.rv(i, ops[2])}, c->c, &co)"
            return [f"{{ u32 co = c->c; u32 res = {e}; c->r[{d}] = res;" + (" nz(c, res); c->c = co;" if s else "") + " }"]
        if m in ("add", "adc", "sub", "sbc", "rsb", "rsc"):
            d = self.rn(i, ops[0])
            if len(ops) == 2:
                a, (b, _) = f"c->r[{d}]", self.op2(i, ops[1], False)
            else:
                a, (b, _) = self.rv(i, ops[1]), self.op2(i, ops[2], False)
            if m in ("rsb", "rsc"):
                a, b = b, a
            cin = {"add": "0", "adc": "c->c", "sub": "1", "sbc": "c->c", "rsb": "1", "rsc": "c->c"}[m]
            fn = "add_f" if m in ("add", "adc") else "sub_f"
            if s:
                e = f"{fn}(c, {a}, {b}, {cin})"
            else:
                e = f"{a} + {b}" if m == "add" else f"{a} + {b} + c->c" if m == "adc" else \
                    f"{a} - {b}" if m in ("sub", "rsb") else f"{a} - {b} - !c->c"
            if d == 15:
                return [f"{{ u32 co = c->c; (void)co; u32 t = {e}; rt_llamar(c, t); return; }}"]
            return [f"{{ u32 co = c->c; (void)co; c->r[{d}] = {e}; }}"]
        if m in ("and", "orr", "eor", "bic"):
            d = self.rn(i, ops[0])
            if len(ops) == 2:
                a, (b, co) = f"c->r[{d}]", self.op2(i, ops[1], s)
            else:
                a, (b, co) = self.rv(i, ops[1]), self.op2(i, ops[2], s)
            opc = {"and": "&", "orr": "|", "eor": "^", "bic": "& ~"}[m]
            r = [f"{{ u32 co = c->c; u32 res = {a} {opc}({b}); c->r[{d}] = res;"]
            if s:
                r.append("nz(c, res);" + (f" c->c = {co};" if co else ""))
            return [" ".join(r) + " }"]
        if m in ("cmp", "cmn", "tst", "teq"):
            a = self.rv(i, ops[0])
            b, co = self.op2(i, ops[1], m in ("tst", "teq"))
            if m == "cmp":
                return [f"{{ u32 co = c->c; (void)co; sub_f(c, {a}, {b}, 1); }}"]
            if m == "cmn":
                return [f"{{ u32 co = c->c; (void)co; add_f(c, {a}, {b}, 0); }}"]
            opc = "&" if m == "tst" else "^"
            return [f"{{ u32 co = c->c; nz(c, {a} {opc} ({b}));" + (f" c->c = {co};" if co else "") + " }"]
        if m in ("mul", "mla"):
            d, a, b = self.rn(i, ops[0]), self.rv(i, ops[1]), self.rv(i, ops[2])
            e = f"{a} * {b}" + (f" + {self.rv(i, ops[3])}" if m == "mla" else "")
            return [f"{{ u32 res = {e}; c->r[{d}] = res;" + (" nz(c, res);" if s else "") + " }"]
        if m in ("umull", "smull", "umlal", "smlal"):
            lo, hi, a, b = self.rn(i, ops[0]), self.rn(i, ops[1]), self.rv(i, ops[2]), self.rv(i, ops[3])
            if m[0] == "u":
                e = f"(u64){a} * (u64){b}"
            else:
                e = f"(u64)((s64)(s32){a} * (s64)(s32){b})"
            if m.endswith("lal"):
                e = f"({e}) + (((u64)c->r[{hi}] << 32) | c->r[{lo}])"
            return [f"{{ u64 res = {e}; c->r[{lo}] = (u32)res; c->r[{hi}] = (u32)(res >> 32);"
                    + (" c->n = (u32)(res >> 63); c->z = res == 0;" if s else "") + " }"]
        if m == "clz":
            return [f"c->r[{self.rn(i, ops[0])}] = clz32({self.rv(i, ops[1])});"]
        if m in EXTENSIONES:
            # 'uxtb16 r5, r5, ror #8': la rotacion (0/8/16/24) viene como shift ROR del operando fuente
            src = ops[-1]
            if len(ops) != (3 if m[3] == "a" else 2) or src.shift.type not in (arm.ARM_SFT_INVALID, arm.ARM_SFT_ROR) \
                    or (src.shift.type == arm.ARM_SFT_ROR and src.shift.value not in (8, 16, 24)):
                raise Error("extension rara")
            v = self.rv(i, src)
            if src.shift.type == arm.ARM_SFT_ROR:
                v = f"ror32({v}, {src.shift.value})"
            e = EXTENSIONES[m].replace("V", v)
            if m[3] == "a":
                e = e.replace("A", self.rv(i, ops[1]))
            return [f"c->r[{self.rn(i, ops[0])}] = {e};"]
        if m in ("uhadd8", "uhsub8"):  # no tocan banderas GE
            return [f"c->r[{self.rn(i, ops[0])}] = {m}({self.rv(i, ops[1])}, {self.rv(i, ops[2])});"]
        if m == "nop":
            return []
        # ----- memoria -----
        if m in ("ldr", "ldrb", "ldrh", "ldrsb", "ldrsh", "str", "strb", "strh", "ldrd", "strd"):
            dos = m in ("ldrd", "strd")
            ri = 2 if dos else 1
            mem = ops[ri]
            extra = ops[ri + 1] if len(ops) > ri + 1 else None
            d = self.rn(i, ops[0])
            # tabla de saltos (switch): goto a cada caso
            if i.address in getattr(self, "tablas", {}):
                idx, destinos = self.tablas[i.address]
                casos = " ".join(f"case {j}: goto L_{t:08X};" if self.entrada <= t < self.fin
                                 else f"case {j}: rt_llamar(c, 0x{t:08X}u); return;" for j, t in enumerate(destinos))
                return [f"switch (c->r[{idx}]) {{ {casos} default: rt_llamar(c, R32(0x{i.address + 8:08X}u + (c->r[{idx}] << 2))); return; }}"]
            # literal del pool: constante
            if m == "ldr" and mem.mem.base == arm.ARM_REG_PC and not mem.mem.index and extra is None:
                v = u32(i.address + 8 + mem.mem.disp)
                if d == 15:
                    return [f"rt_llamar(c, 0x{v:08X}u); return;"]
                return [f"c->r[{d}] = 0x{v:08X}u;"]
            ea, wb = self.direccion(i, mem, extra)
            pre = f"u32 ea = {self.direccion_pre(i, mem)}; " if ea == "ea" else ""
            if m.startswith("ldr"):
                lee = {"ldr": "R32(a)", "ldrb": "R8(a)", "ldrh": "R16(a)", "ldrsb": "(u32)(s32)(s8)R8(a)",
                       "ldrsh": "(u32)(s32)(s16)R16(a)"}
                if dos:
                    d2 = self.rn(i, ops[1])
                    cuerpo = f"u32 v0 = R32(a), v1 = R32(a + 4); {wb} c->r[{d}] = v0; c->r[{d2}] = v1;"
                else:
                    cuerpo = f"u32 v = {lee[m]}; {wb} " + (f"rt_llamar(c, v); return;" if d == 15 else f"c->r[{d}] = v;")
            else:
                if dos:
                    d2 = self.rn(i, ops[1])
                    cuerpo = f"W32(a, c->r[{d}]); W32(a + 4, c->r[{d2}]); {wb}"
                else:
                    val = f"0x{i.address + 12:08X}u" if d == 15 else f"c->r[{d}]"
                    w = {"str": "W32", "strb": "W8", "strh": "W16"}[m]
                    cuerpo = f"{w}(a, {val}); {wb}"
            return [f"{{ {pre}u32 a = {ea}; {cuerpo} }}"]
        if m in ("push", "pop", "ldm", "stm", "ldmia", "stmia", "ldmib", "stmib", "ldmda", "stmda", "ldmdb", "stmdb"):
            return self.multiple(i, m)
        # ----- ARMv6: desplazamientos con 2 operandos (capstone pone el desplazamiento DENTRO del operando) -----
        if m in ("lsl", "lsr", "asr", "ror") and len(ops) == 2:
            d = self.rn(i, ops[0])
            e, co = self.op2(i, ops[1], s)
            return [f"{{ u32 co = c->c; u32 res = {e}; c->r[{d}] = res;" + (f" nz(c, res); c->c = {co or 'c->c'};" if s else "") + " }"]
        if m == "rrx":
            d, a = self.rn(i, ops[0]), self.rv(i, ops[1])
            return [f"{{ u32 co = c->c; u32 res = rrx({a}, c->c, &co); c->r[{d}] = res;" + (" nz(c, res); c->c = co;" if s else "") + " }"]
        # ----- multiplicaciones de media palabra -----
        mm = re.fullmatch(r"smul([bt])([bt])", m) or re.fullmatch(r"smla([bt])([bt])", m)
        if mm:
            d, a, b = self.rn(i, ops[0]), self.rv(i, ops[1]), self.rv(i, ops[2])
            x = f"{'lo16' if mm.group(1) == 'b' else 'hi16'}({a})"
            y = f"{'lo16' if mm.group(2) == 'b' else 'hi16'}({b})"
            e = f"(u32)({x} * {y})" + (f" + {self.rv(i, ops[3])}" if m.startswith("smla") else "")
            return [f"c->r[{d}] = {e};"]  # (la bandera Q no se modela: nadie la lee con mrs)
        if m in ("smuad", "smusd", "smlad", "smlsd"):
            d, a, b = self.rn(i, ops[0]), self.rv(i, ops[1]), self.rv(i, ops[2])
            sg = "+" if m in ("smuad", "smlad") else "-"
            e = f"(u32)(lo16({a}) * lo16({b})) {sg} (u32)(hi16({a}) * hi16({b}))"
            if m.startswith("sml"):
                e += f" + {self.rv(i, ops[3])}"
            return [f"c->r[{d}] = {e};"]
        # ----- saturacion -----
        if m in ("usat", "ssat"):
            d, n = self.rn(i, ops[0]), ops[1].imm
            e, _ = self.op2(i, ops[2], False)
            fn = "usat_n" if m == "usat" else "ssat_n"
            return [f"{{ u32 co = c->c; (void)co; c->r[{d}] = {fn}((s32)({e}), {n}); }}"]
        if m in ("ssat16", "usat16"):
            d, n, a = self.rn(i, ops[0]), ops[1].imm, self.rv(i, ops[2])
            fn = "ssat_n" if m == "ssat16" else "usat_n"
            return [f"c->r[{d}] = par16({fn}(lo16({a}), {n}), {fn}(hi16({a}), {n}));"]
        # ----- coprocesador 15 -----
        if m in ("mrc", "mcr"):
            cop, opc1, rt, crn, crm, opc2 = [o.imm for o in ops[:2]] + [self.rn(i, ops[2])] + [o.imm for o in ops[3:6]]
            if (cop, crn, crm, opc1) == (15, 13, 0, 0) and opc2 in (2, 3):
                campo = "tls" if opc2 == 3 else "tls_rw"
                return [f"c->r[{rt}] = c->{campo};" if m == "mrc" else f"c->{campo} = c->r[{rt}];"]
            if m == "mcr" and cop == 15 and crn == 7:
                return []  # cache y barreras de memoria: sin efecto en el modelo
            raise Error(f"cp{cop} c{crn},c{crm},{opc1},{opc2}")
        # ----- exclusivos (un solo hilo a la vez en el modelo: el monitor basta) -----
        if m in ("ldrex", "ldrexh", "ldrexb"):
            d, base = self.rn(i, ops[0]), REG[i.reg_name(ops[1].mem.base)]
            lee = {"ldrex": "R32", "ldrexh": "R16", "ldrexb": "R8"}[m]
            return [f"{{ u32 a = c->r[{base}]; c->excl = 1; c->excl_addr = a; c->r[{d}] = {lee}(a); }}"]
        if m in ("strex", "strexh", "strexb"):
            d, t, base = self.rn(i, ops[0]), self.rn(i, ops[1]), REG[i.reg_name(ops[2].mem.base)]
            w = {"strex": "W32", "strexh": "W16", "strexb": "W8"}[m]
            return [f"{{ u32 a = c->r[{base}]; if (c->excl && c->excl_addr == a) {{ {w}(a, c->r[{t}]); c->r[{d}] = 0; }}"
                    f" else c->r[{d}] = 1; c->excl = 0; }}"]
        if m == "clrex":
            return ["c->excl = 0;"]
        # ----- empaquetado y bytes -----
        if m in ("pkhbt", "pkhtb"):
            d, a = self.rn(i, ops[0]), self.rv(i, ops[1])
            b, _ = self.op2(i, ops[2], False)
            if m == "pkhbt":
                return [f"{{ u32 co = c->c; (void)co; c->r[{d}] = ({a} & 0xFFFFu) | (({b}) & 0xFFFF0000u); }}"]
            return [f"{{ u32 co = c->c; (void)co; c->r[{d}] = ({a} & 0xFFFF0000u) | (({b}) & 0xFFFFu); }}"]
        if m in ("rev", "rev16", "revsh"):
            d, a = self.rn(i, ops[0]), self.rv(i, ops[1])
            e = {"rev": f"__builtin_bswap32({a})",
                 "rev16": f"((({a}) & 0xFF00FF00u) >> 8) | ((({a}) & 0x00FF00FFu) << 8)",
                 "revsh": f"(u32)(s32)(s16)(u16)__builtin_bswap16((u16){a})"}[m]
            return [f"c->r[{d}] = {e};"]
        # ----- SIMD de 16 bits (las banderas GE no se modelan: el juego no usa SEL) -----
        if m in ("qadd16", "qsub16", "qasx", "qsax", "sadd16", "ssub16", "sasx", "ssax"):
            d, a, b = self.rn(i, ops[0]), self.rv(i, ops[1]), self.rv(i, ops[2])
            sat = m.startswith("q")
            lo, hi = {"add16": ("lo16(A) + lo16(B)", "hi16(A) + hi16(B)"), "sub16": ("lo16(A) - lo16(B)", "hi16(A) - hi16(B)"),
                      "asx": ("lo16(A) - hi16(B)", "hi16(A) + lo16(B)"), "sax": ("lo16(A) + hi16(B)", "hi16(A) - lo16(B)")}[m[1:]]
            lo, hi = lo.replace("A", a).replace("B", b), hi.replace("A", a).replace("B", b)
            f = "sat16" if sat else "(u32)(u16)"
            return [f"c->r[{d}] = par16({f}({lo}), {f}({hi}));"]
        if m == "pld":
            return []
        # ----- VFP -----
        return self.vfp(i, m)

    def direccion_pre(self, i, mem):
        base = REG[i.reg_name(mem.mem.base)]
        if mem.mem.index:
            idx = f"c->r[{REG[i.reg_name(mem.mem.index)]}]"
            if mem.shift.type == arm.ARM_SFT_LSL and mem.shift.value:
                idx = f"({idx} << {mem.shift.value})"
            return f"c->r[{base}] {'-' if mem.subtracted else '+'} {idx}"
        d = mem.mem.disp
        return f"c->r[{base}] + 0x{d & 0xFFFFFFFF:08X}u"

    def lista_regs(self, i, ops):
        regs = []
        for o in ops:
            n = i.reg_name(o.reg)
            if n in REG:
                regs.append(("r", REG[n]))
            elif re.fullmatch(r"s\d+", n):
                regs.append(("s", int(n[1:])))
            elif re.fullmatch(r"d\d+", n):
                k = int(n[1:])
                if k >= 16:
                    raise Error("d16+ no existe en VFPv2")
                regs += [("s", 2 * k), ("s", 2 * k + 1)]
            else:
                raise Error(f"registro en lista {n}")
        return regs

    def multiple(self, i, m):
        ops = i.operands
        if m in ("push", "pop"):
            base, regs, modo = 13, self.lista_regs(i, ops), ("db" if m == "push" else "ia")
            wb = True
            carga = m == "pop"
        else:
            base = REG[i.reg_name(ops[0].reg)]
            regs = self.lista_regs(i, ops[1:])
            modo = m[3:] or "ia"
            wb = i.writeback
            carga = m.startswith("ldm")
        n = len(regs)
        inicio = {"ia": "b", "ib": "b + 4", "da": f"b - {4 * n - 4}", "db": f"b - {4 * n}"}[modo]
        nuevo = f"b + {4 * n}" if modo in ("ia", "ib") else f"b - {4 * n}"
        out = [f"{{ u32 b = c->r[{base}]; u32 a = {inicio};"]
        ret = False
        if carga:
            for k, (t, r) in enumerate(regs):
                if t == "r" and r == 15:
                    out.append(f"u32 npc = R32(a + {4 * k});")
                    ret = True
                elif not (t == "r" and r == base and wb):
                    out.append(f"c->{t}[{r}] = R32(a + {4 * k});")
            if wb:
                out.append(f"c->r[{base}] = {nuevo};")
            if any(t == "r" and r == base for t, r in regs) and wb:
                k = [r for _, r in regs].index(base)
                out.append(f"c->r[{base}] = R32(a + {4 * k});")
        else:
            for k, (t, r) in enumerate(regs):
                val = f"0x{i.address + 12:08X}u" if (t == "r" and r == 15) else f"c->{t}[{r}]"
                out.append(f"W32(a + {4 * k}, {val});")
            if wb:
                out.append(f"c->r[{base}] = {nuevo};")
        if ret:
            # pop {..., pc}: si se vuelve a donde llamaron (lr guardado) es un return normal
            out.append("(void)npc; return;")
        return [" ".join(out) + " }"]

    def vfp(self, i, m):
        ops = i.operands
        full = i.mnemonic
        tipo = full.split(".")[-1] if "." in full else ""
        base_m = m
        dob = self.vfp_doble(i, m, ops, full)
        if dob is not None:
            return dob
        if base_m in ("vldr", "vstr"):
            sr = self.sreg(i, ops[0])
            mem = ops[1]
            if mem.mem.base == arm.ARM_REG_PC:
                v = u32(i.address + 8 + mem.mem.disp)
                if base_m == "vldr":
                    return [f"c->s[{sr}] = 0x{v:08X}u;"]
            ea = f"c->r[{REG[i.reg_name(mem.mem.base)]}] + 0x{mem.mem.disp & 0xFFFFFFFF:08X}u"
            return [f"c->s[{sr}] = R32({ea});" if base_m == "vldr" else f"W32({ea}, c->s[{sr}]);"]
        if base_m in ("vpush", "vpop"):
            regs = self.lista_regs(i, ops)
            n = len(regs)
            if base_m == "vpush":
                return ["{ u32 a = c->r[13] - %d; " % (4 * n) + " ".join(f"W32(a + {4 * k}, c->s[{r}]);" for k, (_, r) in enumerate(regs))
                        + f" c->r[13] = a; }}"]
            return ["{ u32 a = c->r[13]; " + " ".join(f"c->s[{r}] = R32(a + {4 * k});" for k, (_, r) in enumerate(regs))
                    + f" c->r[13] = a + {4 * n}; }}"]
        if base_m in ("vldmia", "vstmia", "vldmdb", "vstmdb"):
            b = REG[i.reg_name(ops[0].reg)]
            regs = self.lista_regs(i, ops[1:])
            n = len(regs)
            db = base_m.endswith("db")
            out = [f"{{ u32 a = c->r[{b}]" + (f" - {4 * n};" if db else ";")]
            for k, (_, r) in enumerate(regs):
                out.append(f"c->s[{r}] = R32(a + {4 * k});" if base_m.startswith("vld") else f"W32(a + {4 * k}, c->s[{r}]);")
            if i.writeback:
                out.append(f"c->r[{b}] = a;" if db else f"c->r[{b}] = a + {4 * n};")
            return [" ".join(out) + " }"]
        if base_m == "vmrs":
            if i.reg_name(ops[0].reg) == "apsr_nzcv":
                return ["c->n = c->fn; c->z = c->fz; c->c = c->fc; c->v = c->fv;"]
            raise Error("vmrs a registro")
        if base_m == "vmov":
            a, b = ops[0], ops[1]
            na = i.reg_name(a.reg) if a.type == arm.ARM_OP_REG else ""
            if a.type == arm.ARM_OP_REG and na in REG and len(ops) == 2:
                return [f"c->r[{REG[na]}] = c->s[{self.sreg(i, b)}];"]
            if na.startswith("s") and b.type == arm.ARM_OP_REG and i.reg_name(b.reg) in REG:
                return [f"c->s[{self.sreg(i, a)}] = {self.rv(i, b)};"]
            if na.startswith("s") and b.type == arm.ARM_OP_REG:
                return [f"c->s[{self.sreg(i, a)}] = c->s[{self.sreg(i, b)}];"]
            if na.startswith("s") and b.type == arm.ARM_OP_FP:
                v = struct.unpack("<I", struct.pack("<f", b.fp))[0]
                return [f"c->s[{self.sreg(i, a)}] = 0x{v:08X}u;"]
            raise Error("vmov raro")
        if tipo and tipo != "f32" and base_m not in ("vcvt",):
            raise Error(f"vfp tipo {tipo}")
        S = lambda o: f"F(c->s[{self.sreg(i, o)}])"
        if base_m in ("vadd", "vsub", "vmul", "vdiv"):
            d = self.sreg(i, ops[0])
            a, b = (S(ops[0]), S(ops[1])) if len(ops) == 2 else (S(ops[1]), S(ops[2]))
            o = {"vadd": "+", "vsub": "-", "vmul": "*", "vdiv": "/"}[base_m]
            return [f"c->s[{d}] = FB({a} {o} {b});"]
        if base_m in ("vmla", "vmls", "vnmla", "vnmls", "vnmul"):
            d = self.sreg(i, ops[0])
            a, b = S(ops[1]), S(ops[2])
            dd = S(ops[0])
            e = {"vmla": f"{dd} + FFN({a} * {b})", "vmls": f"{dd} - FFN({a} * {b})",
                 "vnmul": "VNMUL", "vnmla": f"-{dd} - FFN({a} * {b})", "vnmls": f"-{dd} + FFN({a} * {b})"}[base_m]
            if e == "VNMUL":  # el ARM normaliza el NaN del producto y DESPUES cambia el signo
                return [f"c->s[{d}] = FB({a} * {b}) ^ 0x80000000u;"]
            return [f"c->s[{d}] = FB({e});"]
        if base_m in ("vneg", "vabs"):
            d, a = self.sreg(i, ops[0]), self.sreg(i, ops[1])
            return [f"c->s[{d}] = c->s[{a}] ^ 0x80000000u;" if base_m == "vneg" else f"c->s[{d}] = c->s[{a}] & 0x7FFFFFFFu;"]
        if base_m == "vsqrt":
            return [f"c->s[{self.sreg(i, ops[0])}] = FB(sqrt_f({S(ops[1])}));"]
        if base_m in ("vcmp", "vcmpe"):
            b = "0.0f" if ops[1].type in (arm.ARM_OP_IMM, arm.ARM_OP_FP) else S(ops[1])
            return [f"vcmp(c, {S(ops[0])}, {b});"]
        if base_m == "vcvt":
            if full.endswith(".s32.f32"):
                return [f"c->s[{self.sreg(i, ops[0])}] = f2s({S(ops[1])});"]
            if full.endswith(".u32.f32"):
                return [f"c->s[{self.sreg(i, ops[0])}] = f2u({S(ops[1])});"]
            if full.endswith(".f32.s32"):
                return [f"c->s[{self.sreg(i, ops[0])}] = FB((float)(s32)c->s[{self.sreg(i, ops[1])}]);"]
            if full.endswith(".f32.u32"):
                return [f"c->s[{self.sreg(i, ops[0])}] = FB((float)c->s[{self.sreg(i, ops[1])}]);"]
            raise Error(f"vcvt {full}")
        if m == "svc":
            return [f"rt_svc(c, 0x{ops[0].imm:X}u, 0x{i.address:08X}u);"]
        raise Error(f"mnemonico {full}")

    def dreg(self, i, op):
        name = i.reg_name(op.reg)
        mm = re.fullmatch(r"d(\d+)", name)
        if not mm or int(mm.group(1)) >= 16:
            raise Error(f"registro doble {name}")
        return int(mm.group(1))

    def vfp_doble(self, i, m, ops, full):
        """Instrucciones VFP que tocan registros d (doble precision) o el FPSCR. None si no aplica."""
        nombres = [i.reg_name(o.reg) if o.type == arm.ARM_OP_REG else "" for o in ops]
        hay_d = any(re.fullmatch(r"d\d+", n or "") for n in nombres) or full.endswith(".f64")
        if m == "vmsr":
            if nombres[0] == "fpscr":
                return [f"{{ u32 v = {self.rv(i, ops[1])}; c->fpscr = v; c->fn = v >> 31; c->fz = (v >> 30) & 1;"
                        f" c->fc = (v >> 29) & 1; c->fv = (v >> 28) & 1; }}"]
            raise Error("vmsr raro")
        if not hay_d or m in ("vpush", "vpop", "vldmia", "vstmia", "vldmdb", "vstmdb"):
            return None
        D = lambda o: f"GD({self.dreg(i, o)})"
        if m in ("vldr", "vstr"):
            k, mem = self.dreg(i, ops[0]), ops[1]
            if mem.mem.base == arm.ARM_REG_PC:
                a = i.address + 8 + mem.mem.disp
                if m == "vldr":
                    return [f"c->s[{2 * k}] = 0x{u32(a):08X}u; c->s[{2 * k + 1}] = 0x{u32(a + 4):08X}u;"]
            ea = f"c->r[{REG[i.reg_name(mem.mem.base)]}] + 0x{mem.mem.disp & 0xFFFFFFFF:08X}u"
            if m == "vldr":
                return [f"{{ u32 a = {ea}; c->s[{2 * k}] = R32(a); c->s[{2 * k + 1}] = R32(a + 4); }}"]
            return [f"{{ u32 a = {ea}; W32(a, c->s[{2 * k}]); W32(a + 4, c->s[{2 * k + 1}]); }}"]
        if m == "vmov":
            if len(ops) == 3 and nombres[0] in REG and nombres[1] in REG:  # vmov rA, rB, dN
                k = self.dreg(i, ops[2])
                return [f"c->r[{REG[nombres[0]]}] = c->s[{2 * k}]; c->r[{REG[nombres[1]]}] = c->s[{2 * k + 1}];"]
            if len(ops) == 3 and nombres[1] in REG:  # vmov dN, rA, rB
                k = self.dreg(i, ops[0])
                return [f"{{ u32 x = {self.rv(i, ops[1])}, y = {self.rv(i, ops[2])}; c->s[{2 * k}] = x; c->s[{2 * k + 1}] = y; }}"]
            if len(ops) == 2 and ops[1].type == arm.ARM_OP_REG:  # vmov.f64 dX, dY
                a, b = self.dreg(i, ops[0]), self.dreg(i, ops[1])
                return [f"{{ u32 x = c->s[{2 * b}], y = c->s[{2 * b + 1}]; c->s[{2 * a}] = x; c->s[{2 * a + 1}] = y; }}"]
            if len(ops) == 2 and ops[1].type == arm.ARM_OP_FP:
                bits = struct.unpack("<Q", struct.pack("<d", ops[1].fp))[0]
                return [f"SD({self.dreg(i, ops[0])}, 0x{bits:016X}ull);"]
            raise Error("vmov doble raro")
        if m in ("vadd", "vsub", "vmul", "vdiv"):
            d = self.dreg(i, ops[0])
            a, b = (D(ops[0]), D(ops[1])) if len(ops) == 2 else (D(ops[1]), D(ops[2]))
            o = {"vadd": "+", "vsub": "-", "vmul": "*", "vdiv": "/"}[m]
            return [f"{{ double r = {a} {o} {b}; SD({d}, DB(r)); }}"]
        if m in ("vmla", "vmls"):
            d = self.dreg(i, ops[0])
            p = f"DF((u32)DB({D(ops[1])} * {D(ops[2])}), (u32)(DB({D(ops[1])} * {D(ops[2])}) >> 32))"
            return [f"{{ double r = {D(ops[0])} {'+' if m == 'vmla' else '-'} {p}; SD({d}, DB(r)); }}"]
        if m in ("vneg", "vabs"):
            d, a = self.dreg(i, ops[0]), self.dreg(i, ops[1])
            op = "^ 0x80000000u" if m == "vneg" else "& 0x7FFFFFFFu"
            return [f"{{ u32 x = c->s[{2 * a}], y = c->s[{2 * a + 1}] {op}; c->s[{2 * d}] = x; c->s[{2 * d + 1}] = y; }}"]
        if m == "vsqrt":
            return [f"{{ double r = __builtin_sqrt({D(ops[1])}); SD({self.dreg(i, ops[0])}, DB(r)); }}"]
        if m in ("vcmp", "vcmpe"):
            b = "0.0" if ops[1].type in (arm.ARM_OP_IMM, arm.ARM_OP_FP) else D(ops[1])
            return [f"vcmpd(c, {D(ops[0])}, {b});"]
        if m == "vcvt":
            t = full.split(".")[-2:]  # p. ej. ['f64', 'f32']
            if t == ["f64", "f32"]:
                return [f"{{ double r = (double)F(c->s[{self.sreg(i, ops[1])}]); SD({self.dreg(i, ops[0])}, DB(r)); }}"]
            if t == ["f32", "f64"]:
                return [f"c->s[{self.sreg(i, ops[0])}] = FB((float){D(ops[1])});"]
            if t == ["f64", "s32"]:
                return [f"SD({self.dreg(i, ops[0])}, DB((double)(s32)c->s[{self.sreg(i, ops[1])}]));"]
            if t == ["f64", "u32"]:
                return [f"SD({self.dreg(i, ops[0])}, DB((double)c->s[{self.sreg(i, ops[1])}]));"]
            if t == ["s32", "f64"]:
                return [f"c->s[{self.sreg(i, ops[0])}] = d2s({D(ops[1])});"]
            if t == ["u32", "f64"]:
                return [f"c->s[{self.sreg(i, ops[0])}] = d2u({D(ops[1])});"]
            raise Error(f"vcvt {full}")
        raise Error(f"vfp doble {full}")

    # ---------- funcion completa ----------
    def tabla_saltos(self, i):
        """switch compilado: 'cmp rX, #N ; ldrls pc, [pc, rX, lsl #2]' + N+1 direcciones. Devuelve (rX, destinos) o None."""
        if i.id != arm.ARM_INS_LDR or len(i.operands) != 2:
            return None
        d, mem = i.operands
        if i.reg_name(d.reg) != "pc" or mem.type != arm.ARM_OP_MEM or i.reg_name(mem.mem.base) != "pc" \
                or not mem.mem.index or mem.shift.type != arm.ARM_SFT_LSL or mem.shift.value != 2:
            return None
        idx = i.reg_name(mem.mem.index)
        for k in range(1, 6):
            try:
                p = next(md.disasm(CODE[i.address - 4 * k - BASE:i.address - 4 * k - BASE + 4], i.address - 4 * k))
            except StopIteration:
                break
            if p.id == arm.ARM_INS_CMP and p.operands[0].type == arm.ARM_OP_REG and i.reg_name(p.operands[0].reg) == idx \
                    and p.operands[1].type == arm.ARM_OP_IMM:
                n = p.operands[1].imm
                if i.cc == arm.ARM_CC_LO:  # ldrlo: indices 0..N-1 (ldrls: 0..N); 0x100CAC usa lo
                    n -= 1
                return REG[idx], [u32(i.address + 8 + 4 * j) for j in range(n + 1)]
        return None

    def recorrer(self):
        self.tablas = {}
        vistos, pend, insns = set(), [self.entrada], {}
        while pend:
            a = pend.pop()
            while a not in vistos and self.entrada <= a < self.fin:
                vistos.add(a)
                try:
                    i = next(md.disasm(CODE[a - BASE:a - BASE + 4], a))
                except StopIteration:
                    insns[a] = None
                    break
                insns[a] = i
                tab = self.tabla_saltos(i)
                if tab:
                    self.tablas[a] = tab
                    pend += [t for t in tab[1] if self.entrada <= t < self.fin]
                m = i.mnemonic
                cond = i.cc not in (arm.ARM_CC_AL, arm.ARM_CC_INVALID)
                if i.id == arm.ARM_INS_B and i.operands and i.operands[0].type == arm.ARM_OP_IMM:  # por id: 'bls'/'blo' empiezan con 'bl'
                    t = i.operands[0].imm
                    if self.entrada <= t < self.fin:
                        pend.append(t)
                    if not cond:
                        break
                elif self.termina(i) and not cond:
                    break
                a += 4
        return insns

    @staticmethod
    def termina(i):
        m = i.mnemonic.split(".")[0]
        ops = i.operands
        if m.startswith("bx"):
            return True
        if m.startswith(("pop", "ldm")) and any(i.reg_name(o.reg) == "pc" for o in ops if o.type == arm.ARM_OP_REG):
            return True
        if m.startswith(("mov", "ldr", "add", "sub")) and ops and ops[0].type == arm.ARM_OP_REG and i.reg_name(ops[0].reg) == "pc":
            return True
        return False

    def generar(self):
        insns = self.recorrer()
        out = [f"void f_{self.entrada:08X}(CPU *c)", "{"]
        orden = sorted(insns)
        for k, a in enumerate(orden):
            i = insns[a]
            out.append(f"L_{a:08X}:;")
            if i is None:
                out.append(f"    rt_desconocida(c, 0x{a:08X}u); return;")
                FALTAN["(no decodifica)"] += 1
                continue
            try:
                cuerpo = self.traducir(i)
            except Error as e:
                FALTAN[f"{i.mnemonic} ({e})"] += 1
                cuerpo = [f"rt_desconocida(c, 0x{a:08X}u); return; /* {i.mnemonic} {i.op_str}: {e} */"]
            com = f"    /* {a:08X}: {i.mnemonic} {i.op_str} */"
            out.append(com)
            if i.cc not in (arm.ARM_CC_AL, arm.ARM_CC_INVALID) and cuerpo:
                out.append(f"    if ({CC[i.cc]}) {{ " + " ".join(cuerpo) + " }")
            else:
                out += ["    " + x for x in cuerpo]
            # si la siguiente instruccion no se recorrio y esta cae, es el fin (o un salto ya emitido)
            cae = i.cc not in (arm.ARM_CC_AL, arm.ARM_CC_INVALID) or (not self.termina(i) and i.mnemonic != "b")
            if k + 1 < len(orden) and orden[k + 1] != a + 4 and cae:
                out.append(f"    goto L_{a + 4:08X};")
        if orden:
            ult = insns[orden[-1]]
            if ult is not None and not (self.termina(ult) and ult.cc in (arm.ARM_CC_AL,)) and ult.mnemonic != "b":
                out.append(f"    rt_llamar(c, 0x{orden[-1] + 4:08X}u); return; /* cae fuera de la funcion */")
        out.append("}")
        etiquetas = {f"L_{a:08X}" for a in insns}

        def arreglar(linea):  # red de seguridad: goto a etiqueta no traducida -> salir por rt_llamar
            return re.sub(r"goto (L_([0-9A-F]{8}));",
                          lambda mt: mt.group(0) if mt.group(1) in etiquetas
                          else f"{{ rt_llamar(c, 0x{mt.group(2)}u); return; }}", linea)
        out = [arreglar(x) for x in out]
        return out, insns


def limite(tam, inicios, a):
    """Fin de la funcion que empieza en a = inicio de la siguiente funcion conocida.
    No se usa el tamano de Ghidra como limite: mide solo el primer tramo contiguo y deja afuera los bloques que el
    compilador puso detras del literal pool (casos de switch, epilogos; 0x100C7C: 164 bytes y sus casos en 0x100D24+).
    El recorrido sigue el flujo, asi que el literal pool que queda en medio no se traduce."""
    import bisect
    k = bisect.bisect_right(inicios, a)
    sig = inicios[k] if k < len(inicios) else min(a + 0x1000, TEXT_FIN)
    return max(sig, a + tam.get(a, 0))


def llamadas_de(insns):
    for i in insns.values():
        if i is not None and i.id in (arm.ARM_INS_BL, arm.ARM_INS_B) and i.operands \
                and i.operands[0].type == arm.ARM_OP_IMM:
            yield i.operands[0].imm


def main():
    args = sys.argv[1:]
    salida = os.path.join(AQUI, "gen", "juego.c")
    if "-o" in args:
        k = args.index("-o")
        salida = args[k + 1]
        del args[k:k + 2]
    excluir = set()
    if "--excluir" in args:
        k = args.index("--excluir")
        excluir = {int(x, 16) for x in args[k + 1].split(",") if x}
        del args[k:k + 2]
    cierre = "--cierre" in args
    todo = "--todo" in args
    args = [x for x in args if not x.startswith("--")]
    tam = tamanos()
    inicios = sorted(tam)
    if todo:
        pedidas = sorted(tam)
    else:
        pedidas = [int(x, 16) for x in args]
    traducidas = set(pedidas) - excluir
    if cierre:
        pend = list(traducidas)
        while pend:
            a = pend.pop()
            t = Traductor(a, limite(tam, inicios, a), set())
            for d in llamadas_de(t.recorrer()):
                if d not in traducidas and d not in excluir and BASE <= d < TEXT_FIN:
                    traducidas.add(d)
                    pend.append(d)
    cuerpo = []
    n_ins = 0
    for a in sorted(traducidas):
        if a not in tam:
            print(f"aviso: 0x{a:08X} no esta en funciones.tsv (Ghidra no la descubrio); limite = siguiente funcion")
        t = Traductor(a, limite(tam, inicios, a), traducidas)
        lineas, insns = t.generar()
        n_ins += len(insns)
        cuerpo += lineas + [""]
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as fh:
        fh.write("/* GENERADO por recomp/recomp.py - no editar a mano */\n#include \"recomp.h\"\n\n")
        for a in sorted(traducidas):
            fh.write(f"void f_{a:08X}(CPU *c);\n")
        fh.write("\n#define FFN(x) F(FB(x))  /* producto intermedio redondeado y con NaN canonico, como vmla */\n\n")
        fh.write("\n".join(cuerpo))
        fh.write("\nvoid rt_llamar(CPU *c, u32 addr)\n{\n    switch (addr) {\n")
        for a in sorted(traducidas):
            fh.write(f"    case 0x{a:08X}u: f_{a:08X}(c); return;\n")
        fh.write("    default: rt_externo(c, addr); return;\n    }\n}\n")
    print(f"ok: {len(traducidas)} funciones, {n_ins} instrucciones -> {salida}")
    if FALTAN:
        print("sin soporte:", ", ".join(f"{k} x{v}" for k, v in FALTAN.most_common(25)))


if __name__ == "__main__":
    main()
