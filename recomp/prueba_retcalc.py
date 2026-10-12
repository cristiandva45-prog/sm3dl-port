r"""Agente A (8 oct): diferencial del retorno calculado de 0x3A0B68 (despachador de comparaciones float de ARM).

Corre ENTERAS las dos funciones que la llaman -- 0x3A0C08 (bl en 0x3A0D08) y 0x3A0D30 (bl en 0x3A0D7C) -- en la
original (Unicorn, hasta volver a una trampa) y en la recompilada nativa x86-64 (anfitrion por tuberia de la
bateria), con NaN, +-inf, 0, -0, iguales, subnormales y al azar. Compara r0-r14, NZCV, s0-s31 y la ventana de pila.

Uso: py -I recomp\prueba_retcalc.py [-n 3000] [--sabotaje]
  --sabotaje : traduce como antes del arreglo (el bl a 0x3A0B68 sigue en X+4 = la palabra de DATOS). Debe FALLAR.
"""
import itertools
import os
import random
import struct
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import recomp as RC  # noqa: E402
import bateria as B  # noqa: E402
from unicorn import UcError  # noqa: E402
from unicorn import arm_const as A  # noqa: E402

FUNCS = [0x003A0B68, 0x003A0C08, 0x003A0D30]
LLAMADORES = {0x003A0C08: "0x3A0D08 (dato 0x3EFFFFED: siempre retorna POR el llamador)",
              0x003A0D30: "0x3A0D7C (dato 0x806DB6DB: vuelve DENTRO a 0x3A0D84 / 0x3A0D90)"}
TRAMPA = 0x00600010
ESP = [0x00000000, 0x80000000, 0x7F800000, 0xFF800000, 0x7FC00000, 0xFFC00000, 0x7F800001, 0x7FBFFFFF,
       0x3F800000, 0xBF800000, 0x40000000, 0x00000001, 0x807FFFFF, 0x00800000, 0x7F7FFFFF, 0xFF7FFFFF,
       0x5F000000, 0x5F800000, 0xDF000000, 0x4F800000, 0xBF000000, 0x3EFFFFFF, 0x3DCCCCCD, 0x4B000000]


def generar(sabotaje, salida):
    if sabotaje:  # el arreglo apagado: el traductor vuelve a seguir en X+4 (la palabra de datos)
        RC.es_bl_retcalc = lambda i: False
        RC.RETCALC = set()
    sys.argv = ["recomp"] + [f"{a:X}" for a in FUNCS] + ["-o", salida]
    RC.main()


def casos(n, rnd):
    pares = list(itertools.product(ESP, ESP))  # incluye todos los iguales (a, a)
    while len(pares) < n:
        x = rnd.getrandbits(32)
        y = rnd.choice([x, x ^ 0x80000000, rnd.getrandbits(32), rnd.choice(ESP)])
        pares.append((x, y))
    return pares[:n] if n >= len(ESP) ** 2 else rnd.sample(pares, n)


def estado(r0, r1, rnd):
    r = [rnd.getrandbits(32) for _ in range(15)]
    r[0], r[1] = r0, r1
    r[13] = B.CENTRO
    r[14] = TRAMPA
    return {"r": r, "nzcv": rnd.getrandbits(4), "fnzcv": rnd.getrandbits(4),
            "s": [rnd.getrandbits(32) for _ in range(32)], "tls": rnd.getrandbits(32), "tls_rw": 0,
            "mem": bytes(rnd.getrandbits(8) for _ in range(B.VENTANA))}


def correr_orig(o, a, e):
    uc = o.uc
    uc.mem_write(B.HEAP, e["mem"])
    for k in range(13):
        uc.reg_write(A.UC_ARM_REG_R0 + k, e["r"][k])
    uc.reg_write(A.UC_ARM_REG_SP, e["r"][13])
    uc.reg_write(A.UC_ARM_REG_LR, e["r"][14])
    cpsr = uc.reg_read(A.UC_ARM_REG_CPSR)
    uc.reg_write(A.UC_ARM_REG_CPSR, (cpsr & 0x0FFFFFFF) | (e["nzcv"] << 28))
    for k in range(32):
        uc.reg_write(A.UC_ARM_REG_S0 + k, e["s"][k])
    uc.reg_write(A.UC_ARM_REG_FPSCR, B.FPSCR | (e["fnzcv"] << 28))
    err = None
    try:
        uc.emu_start(a, TRAMPA, count=20000)
        if uc.reg_read(A.UC_ARM_REG_PC) != TRAMPA:  # emu_start(count) se detiene SIN error al agotar el tope
            err = f"no termino (pc=0x{uc.reg_read(A.UC_ARM_REG_PC):08X})"
    except UcError as ex:
        err = str(ex)
    r = [uc.reg_read(A.UC_ARM_REG_R0 + k) for k in range(13)] + [uc.reg_read(A.UC_ARM_REG_SP),
                                                                  uc.reg_read(A.UC_ARM_REG_LR)]
    return {"err": err, "r": r, "nzcv": uc.reg_read(A.UC_ARM_REG_CPSR) >> 28,
            "fnzcv": uc.reg_read(A.UC_ARM_REG_FPSCR) >> 28, "s": [uc.reg_read(A.UC_ARM_REG_S0 + k) for k in range(32)],
            "tls_rw": 0, "mem": bytes(uc.mem_read(B.HEAP, B.VENTANA))}


def main():
    args = sys.argv[1:]
    n = int(args[args.index("-n") + 1]) if "-n" in args else 3000
    sab = "--sabotaje" in args
    build = os.path.join(AQUI, "build")
    os.makedirs(build, exist_ok=True)
    c_file = os.path.join(AQUI, "gen", "prueba_retcalc" + ("_sab" if sab else "") + ".c")
    exe = os.path.join(build, "prueba_retcalc" + ("_sab" if sab else "") + ".exe")
    generar(sab, c_file)
    B.compilar(c_file, exe)
    o, nat = B.Orig(), B.Nativa(exe)
    from collections import Counter
    from unicorn import UC_HOOK_CODE
    vistos = Counter()  # cobertura: por donde sale F (dentro del llamador o por pop {r4, pc})
    for x in (0x003A0D84, 0x003A0D90, 0x003A0BF0, 0x003A0C04, 0x003A0BD0):
        o.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: vistos.__setitem__(a, vistos[a] + 1), None, x, x)
    rnd = random.Random(808)
    total_mal = 0
    for f, desc in LLAMADORES.items():
        mal, ej, adentro = 0, [], 0
        for r0, r1 in casos(n, rnd):
            e = estado(r0, r1, rnd)
            ro = correr_orig(o, f, e)
            try:
                rn = nat.correr(f, e)
            except RuntimeError as ex:
                print(f"  el anfitrion se cayo: {ex}")
                nat = B.Nativa(exe)
                rn = {"err": "caida"}
            d = ro["err"] and f"original: {ro['err']}" or B.comparar(ro, rn)
            if d:
                mal += 1
                if len(ej) < 3:
                    ej.append(f"r0=0x{r0:08X} r1=0x{r1:08X}: {d}")
        total_mal += mal
        print(f"0x{f:08X} [{desc}]: {n - mal}/{n} OK")
        for x in ej:
            print("   ", x)
        print("    cobertura:", ", ".join(f"0x{a:08X} x{v}" for a, v in sorted(vistos.items())))
        vistos.clear()
    nat.p.stdin.close()
    nat.p.wait()
    print("SABOTAJE: " + ("DETECTADO (falla, como debe)" if total_mal else "NO DETECTADO (la prueba no mira)")
          if sab else ("TODO OK" if total_mal == 0 else f"FALLAS: {total_mal}"))
    sys.exit(0 if (total_mal > 0) == sab else 1)


if __name__ == "__main__":
    main()
