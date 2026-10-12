r"""Diferencial de la ruta de printf del juego (8 oct): el arranque caia en el callback de vsnprintf (0x289E90)
con el puntero de salida en 4 y el tamano en 0x34 (debia ser 0x80) al formatear "LightAreaId %04d" desde 0x1C61EC.

Corre ENTERA 0x28CB30 (constructor de cadena con formato: init 0x28AEA0 + formatV 0x28AE5C -> vsnprintf 0x109208
-> _printf_core 0x289EB4 -> callback 0x10A470 + division de armcc) en la original (Unicorn, hasta la trampa) y en la
recompilada nativa (anfitrion de la bateria), y compara registros + la ventana de memoria (objeto y pila).

Uso: py -I recomp\prueba_printf.py [-n 200]
"""
import os
import random
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import recomp as RC  # noqa: E402
import bateria as B  # noqa: E402
from unicorn import UcError  # noqa: E402
from unicorn import arm_const as A  # noqa: E402

F = 0x0028CB30
INDIRECTAS = [0x0010A470, 0x00289E90, 0x00289EA0]   # callbacks por registro (no los ve --cierre): escribir un
#   caracter (0x10A470), NUL final (0x289E90) y LEER el siguiente del formato (0x289EA0; sin el, el arnes colgaba)
TRAMPA = 0x00600010
OBJ = B.HEAP + 0x200
FORMATOS = [0x001C63F4, 0x001C63E4]     # "LightAreaId %04d", "LightArea"


def generar(salida):
    sys.argv = ["recomp", f"{F:X}"] + [f"{a:X}" for a in INDIRECTAS] + ["--cierre", "-o", salida]
    RC.main()


def estado(fmt, val, rnd):
    r = [0] * 15
    r[0], r[1], r[2], r[3] = OBJ, fmt, val, rnd.getrandbits(32)
    for k in range(4, 13):
        r[k] = rnd.getrandbits(32)
    r[13] = B.CENTRO
    r[14] = TRAMPA
    return {"r": r, "nzcv": rnd.getrandbits(4), "fnzcv": 0, "s": [0] * 32, "tls": 0x08001F00, "tls_rw": 0,
            "mem": bytes(B.VENTANA)}


def correr_orig(o, e):
    uc = o.uc
    uc.mem_write(B.HEAP, e["mem"])
    for k in range(13):
        uc.reg_write(A.UC_ARM_REG_R0 + k, e["r"][k])
    uc.reg_write(A.UC_ARM_REG_SP, e["r"][13])
    uc.reg_write(A.UC_ARM_REG_LR, e["r"][14])
    cpsr = uc.reg_read(A.UC_ARM_REG_CPSR)
    uc.reg_write(A.UC_ARM_REG_CPSR, (cpsr & 0x0FFFFFFF) | (e["nzcv"] << 28))
    uc.reg_write(A.UC_ARM_REG_FPSCR, B.FPSCR)
    uc.reg_write(A.UC_ARM_REG_C13_C0_3, e["tls"])
    err = None
    try:
        uc.emu_start(F, TRAMPA, count=200000)
        if uc.reg_read(A.UC_ARM_REG_PC) != TRAMPA:
            err = f"no termino (pc=0x{uc.reg_read(A.UC_ARM_REG_PC):08X})"
    except UcError as ex:
        err = f"{ex} (pc=0x{uc.reg_read(A.UC_ARM_REG_PC):08X})"
    r = [uc.reg_read(A.UC_ARM_REG_R0 + k) for k in range(13)] + [uc.reg_read(A.UC_ARM_REG_SP),
                                                                  uc.reg_read(A.UC_ARM_REG_LR)]
    return {"err": err, "r": r, "nzcv": uc.reg_read(A.UC_ARM_REG_CPSR) >> 28, "fnzcv": 0,
            "s": [uc.reg_read(A.UC_ARM_REG_S0 + k) for k in range(32)], "tls_rw": 0,
            "mem": bytes(uc.mem_read(B.HEAP, B.VENTANA))}


def texto(mem):
    o = OBJ - B.HEAP
    buf, tam = struct.unpack_from("<II", mem, o + 4)
    if not B.HEAP <= buf < B.HEAP + B.VENTANA:
        return f"(buf=0x{buf:08X} tam=0x{tam:X})"
    k = buf - B.HEAP
    return repr(mem[k:k + 40].split(b"\0")[0].decode(errors="replace")) + f" tam=0x{tam:X}"


def main():
    args = sys.argv[1:]
    n = int(args[args.index("-n") + 1]) if "-n" in args else 200
    c_file = os.path.join(AQUI, "gen", "prueba_printf.c")
    exe = os.path.join(AQUI, "build", "prueba_printf.exe")
    generar(c_file)
    B.compilar(c_file, exe)
    o, nat = B.Orig(), B.Nativa(exe)
    rnd = random.Random(1008)
    mal = 0
    vals = [0, 1, 7, 42, 999, 1000, 9999, 10000, 123456, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF]
    while len(vals) < n:
        vals.append(rnd.choice([rnd.getrandbits(32), rnd.randrange(100000)]))
    for j, v in enumerate(vals[:n]):
        fmt = FORMATOS[j % len(FORMATOS)]
        e = estado(fmt, v, rnd)
        ro = correr_orig(o, e)
        try:
            rn = nat.correr(F, e)
        except RuntimeError as ex:
            nat = B.Nativa(exe)
            rn = {"err": f"caida: {ex}"}
        d = B.comparar(ro, rn) if not ro["err"] else f"original: {ro['err']}"
        if d:
            mal += 1
            if mal <= 4:
                print(f"  fmt=0x{fmt:08X} val={v}: {d}")
                print(f"     original: {texto(ro['mem'])}" + ("" if "mem" not in rn else f"   nativa: {texto(rn['mem'])}"))
        elif j < 3:
            print(f"  ok val={v}: {texto(ro['mem'])}")
    nat.p.stdin.close()
    nat.p.wait()
    print(f"{n - mal}/{n} OK")
    sys.exit(1 if mal else 0)


if __name__ == "__main__":
    main()
