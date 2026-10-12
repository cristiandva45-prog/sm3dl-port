"""Verificador de equivalencia: corre la funcion ORIGINAL (code.bin) y la DECOMPILADA (decomp.bin) en Unicorn
con las mismas entradas al azar y compara retorno, memoria escrita y orden de llamadas virtuales.

Uso: py -I decomp\\verificar.py [nombre ...] [-n 2000]
     (sin nombres: todas las que tengan generador en CASOS)

Una funcion queda VERIFICADA si las N pruebas coinciden. Si una falla, se imprime la entrada exacta.
"""
import json
import os
import random
import re
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn import arm_const as A

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
CODE = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
BUILD = json.load(open(os.path.join(AQUI, "build", "simbolos.json")))
DECOMP = open(os.path.join(AQUI, "build", "decomp.bin"), "rb").read()

BASE, FIN_JUEGO = 0x00100000, 0x00500000
DATOS = (0x003E1000, 0x00431000)          # .data + .bss del juego (se compara)
HEAP, HEAP_T = 0x08000000, 0x00100000     # memoria de las pruebas (se compara)
PILA, PILA_T = 0x0F000000, 0x00100000
ESPIA, N_ESPIAS = 0x0E000000, 256         # metodos falsos: el k-esimo vive en ESPIA + 4k
TRAMPA = 0x0FFFF000                       # direccion de retorno
# emu_start(count=N) se detiene SIN error al agotar el tope: si el PC no quedo en la TRAMPA, la corrida
# no termino. No es OK ni falla del codigo: la prueba se descarta (antes podia dar un verde falso).
NO_TERMINO = "no termino (tope de instrucciones)"
FPSCR_3DS = 0x03000000                    # DN+FZ, redondeo al mas cercano: lo que pone el juego (vmsr en 0x105208)


def simbolos_juego():
    d = {}
    for linea in open(os.path.join(RAIZ, "extraido", "simbolos.txt"), encoding="utf-8"):
        m = re.match(r"\s*(0x[0-9A-Fa-f]+)\s+(\S+)", linea)
        if m:
            d[m.group(2)] = int(m.group(1), 16)
    return d


class Maquina:
    def __init__(self):
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        try:
            uc.ctl_set_cpu_model(A.UC_CPU_ARM_1176)
        except Exception:
            pass
        uc.mem_map(BASE, FIN_JUEGO - BASE)
        uc.mem_write(BASE, CODE)
        uc.mem_map(BUILD["base"], (len(DECOMP) + 0xFFFF) & ~0xFFFF)
        uc.mem_write(BUILD["base"], DECOMP)
        for b, t in ((HEAP, HEAP_T), (PILA, PILA_T), (ESPIA, 0x1000), (TRAMPA, 0x1000)):
            uc.mem_map(b, t)
        uc.mem_write(ESPIA, b"\x1e\xff\x2f\xe1" * N_ESPIAS)  # bx lr (el hook decide antes)
        uc.reg_write(A.UC_ARM_REG_C1_C0_2, uc.reg_read(A.UC_ARM_REG_C1_C0_2) | (0xF << 20))
        uc.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.uc = uc
        self.datos0 = bytes(uc.mem_read(DATOS[0], DATOS[1] - DATOS[0]))
        self.stubs = {}
        self.log = []
        uc.hook_add(UC_HOOK_CODE, self._espia, begin=ESPIA, end=ESPIA + 4 * N_ESPIAS)
        self._hooks_stub = []

    def _espia(self, uc, addr, size, _):
        """Metodo virtual falso k: devuelve la palabra de this+0x100+4k (en r0 Y en s0, por si es float),
        suma 1 a this+0x44 y anota la llamada con sus argumentos."""
        k = (addr - ESPIA) // 4
        this = uc.reg_read(A.UC_ARM_REG_R0)
        ret = struct.unpack("<I", uc.mem_read(this + 0x100 + 4 * k, 4))[0]
        uc.reg_write(A.UC_ARM_REG_S0, ret)
        cnt = struct.unpack("<I", uc.mem_read(this + 0x44, 4))[0]
        uc.mem_write(this + 0x44, struct.pack("<I", (cnt + 1) & 0xFFFFFFFF))
        self.log.append(("vf", k, this, uc.reg_read(A.UC_ARM_REG_R1)))
        uc.reg_write(A.UC_ARM_REG_R0, ret)
        uc.reg_write(A.UC_ARM_REG_PC, uc.reg_read(A.UC_ARM_REG_LR))

    def poner_stubs(self, stubs):
        for h in self._hooks_stub:
            self.uc.hook_del(h)
        self._hooks_stub = []
        for addr, fn in stubs.items():
            def cb(uc, a, size, _, fn=fn):
                ret = fn(uc, self)
                if ret is not None:
                    uc.reg_write(A.UC_ARM_REG_R0, ret & 0xFFFFFFFF)
                uc.reg_write(A.UC_ARM_REG_PC, uc.reg_read(A.UC_ARM_REG_LR))
            self._hooks_stub.append(self.uc.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr))

    def correr(self, func, caso):
        uc = self.uc
        uc.mem_write(HEAP, bytes(HEAP_T))
        uc.mem_write(DATOS[0], self.datos0)
        for a, b in caso.get("mem", []):
            uc.mem_write(a, b)
        self.log = []
        self.guion = list(caso.get("guion", []))
        caso.get("antes", lambda m: None)(self)
        regs = caso.get("r", [])
        for i, v in enumerate(regs):
            uc.reg_write(A.UC_ARM_REG_R0 + i, v & 0xFFFFFFFF)
        for i, v in enumerate(caso.get("s", [])):
            uc.reg_write(A.UC_ARM_REG_S0 + i, struct.unpack("<I", struct.pack("<f", v))[0] if isinstance(v, float) else v)
        uc.reg_write(A.UC_ARM_REG_FPSCR, FPSCR_3DS)
        uc.reg_write(A.UC_ARM_REG_SP, PILA + PILA_T - 0x100)
        uc.reg_write(A.UC_ARM_REG_LR, TRAMPA)
        try:
            uc.emu_start(func, TRAMPA, count=2_000_000)
            err = None if uc.reg_read(A.UC_ARM_REG_PC) == TRAMPA else NO_TERMINO
        except UcError as e:
            err = f"{e} pc=0x{uc.reg_read(A.UC_ARM_REG_PC):08X}"
        return {
            "err": err,
            "r0": uc.reg_read(A.UC_ARM_REG_R0),
            "s0": uc.reg_read(A.UC_ARM_REG_S0),
            "heap": bytes(uc.mem_read(HEAP, HEAP_T)),
            "datos": bytes(uc.mem_read(DATOS[0], DATOS[1] - DATOS[0])),
            "log": list(self.log),
        }


# ---------------- generadores de entradas ----------------
R = random.Random(1234)
ESPECIALES = [0.0, -0.0, 1.0, -1.0, 0.1, 0.1000001, 1e-39, -1e-39, 1e30, float("inf"), float("-inf"), float("nan")]


def f32():
    x = R.random()
    if x < 0.3:
        return R.choice(ESPECIALES)
    if x < 0.5:
        return float(R.randint(-3, 3))
    return R.uniform(-2, 2) * (10 ** R.randint(-3, 3))


def pf(x):
    return struct.pack("<f", x)


def u32():
    return R.choice([0, 1, 2, 0xFFFFFFFF, 0x80000000, R.getrandbits(32), R.getrandbits(8), R.randint(0, 40)])


def objeto_espia(addr, ret, por_metodo=None):
    """Objeto falso de 0x900 bytes: [0]=vt (en addr+0x500), +0x44 = contador de llamadas,
    +0x100+4k = lo que devuelve el metodo k (ret para todos, salvo los de por_metodo)."""
    vt = addr + 0x500
    slots = [ret & 0xFFFFFFFF] * N_ESPIAS
    for k, v in (por_metodo or {}).items():
        slots[k] = v & 0xFFFFFFFF
    return [(addr, struct.pack("<I", vt)), (addr + 0x100, b"".join(struct.pack("<I", s) for s in slots)),
            (vt, b"".join(struct.pack("<I", ESPIA + 4 * k) for k in range(N_ESPIAS)))]


def stub_guion(nombre):
    """Stub que anota (nombre, r0, r1, r2) y devuelve el siguiente valor del guion del caso."""
    def fn(uc, m):
        m.log.append((nombre, uc.reg_read(A.UC_ARM_REG_R0), uc.reg_read(A.UC_ARM_REG_R1),
                      uc.reg_read(A.UC_ARM_REG_R2)))
        return m.guion.pop(0) if m.guion else 0
    return fn


def gen_flags():
    p = HEAP + 0x100
    return {"r": [p, R.choice([R.randint(0, 31), R.randint(32, 300), R.getrandbits(32)])],
            "mem": [(p, struct.pack("<I", u32()))]}


def gen_msg():
    return {"r": [R.choice([R.randint(0, 70), u32()])]}


def gen_actor_vec():
    a = HEAP + 0x200
    vals = [f32() for _ in range(0x80 // 4)]
    if R.random() < 0.4:
        # productos que se cancelan: (1e8 + -1e8) + 1 = 1, pero 1e8 + (-1e8 + 1) = 0 en float
        grande = R.choice([1e8, 3e7, 1e10, 16777216.0])
        chico = R.choice([1.0, 0.5, -1.0, 1e-3])
        orden = R.sample([grande, -grande, chico], 3)
        for k, v in enumerate(orden):
            vals[6 + k] = 1.0     # arriba (+0x18)
            vals[9 + k] = v       # velocidad (+0x24)
    return {"r": [a], "mem": [(a, b"".join(pf(x) for x in vals))]}


def gen_cond_simple():
    self_, hijo = HEAP + 0x100, HEAP + 0x400
    ret = R.choice([0, 1, 2, 0xFFFFFFFF, R.getrandbits(32)])
    return {"r": [self_], "mem": [(self_ + 4, struct.pack("<I", hijo))] + objeto_espia(hijo, ret)}


def gen_lista():
    """Lista intrusiva AND/OR con 0..6 elementos y desplazamiento de enlace al azar."""
    self_ = HEAP + 0x100
    off = R.choice([0, 4, 8, 0xC, 0x10, 0x14])
    n = R.randint(0, 6)
    elems = [HEAP + 0x1000 + i * 0x100 for i in range(n)]
    mem = [(self_ + 0x10, struct.pack("<I", off))]
    enlaces = [e + off for e in elems]
    centinela = self_ + 4
    mem.append((self_ + 8, struct.pack("<I", enlaces[0] if n else centinela)))
    for i, e in enumerate(elems):
        cond = HEAP + 0x10000 + i * 0x1000
        mem.append((e, struct.pack("<I", cond)))
        mem.append((enlaces[i] + 4, struct.pack("<I", enlaces[i + 1] if i + 1 < n else centinela)))
        mem += objeto_espia(cond, R.choice([0, 1, 2, 0xFFFFFFFF, R.getrandbits(32)]))
    return {"r": [self_], "mem": mem}


def gen_select():
    self_, nodo = HEAP + 0x100, HEAP + 0x200
    n = R.randint(0, 6)
    its = [HEAP + 0x1000 + i * 0x40 for i in range(n)]
    mem = [(self_, struct.pack("<I", nodo)), (self_ + 4, struct.pack("<I", u32())),
           (nodo + 0xC, struct.pack("<I", its[0] if n else nodo + 8))]
    for i, it in enumerate(its):
        arista, cond = HEAP + 0x3000 + i * 0x40, HEAP + 0x10000 + i * 0x1000
        mem.append((it + 4, struct.pack("<I", its[i + 1] if i + 1 < n else nodo + 8)))
        mem.append((it + 8, struct.pack("<I", arista)))
        mem.append((arista + 0x10, struct.pack("<I", cond)))
        mem.append((arista + 0x14, struct.pack("<I", u32())))
        mem += objeto_espia(cond, R.choice([0, 0, 0, 1, 2, R.getrandbits(32)]))
    return {"r": [self_], "mem": mem}


def gen_touch(sym):
    contactos = [(R.random() < 0.7, R.choice([0, 1, 2, 3, R.randint(-5, 50)]), [f32() for _ in range(3)])
                 for _ in range(R.randint(0, 6))]
    codigo = R.choice([0, 1, 2, 3, R.randint(-5, 50)])
    estado = {}

    def ini(uc, m):
        it = uc.reg_read(A.UC_ARM_REG_R0)
        estado["it"] = it
        estado["i"] = 0
        m.log.append(("ini", uc.reg_read(A.UC_ARM_REG_R1)))
        uc.mem_write(it, struct.pack("<II", 0xAAAA0000, 0))

    def fin(uc, m):
        m.log.append(("fin", estado["i"]))
        return int(estado["i"] >= len(contactos))

    def valido(uc, m):
        m.log.append(("valido", estado["i"]))
        return int(contactos[estado["i"]][0])

    def info(uc, m):
        dst = uc.reg_read(A.UC_ARM_REG_R1)
        v, cod, nrm = contactos[estado["i"]]
        m.log.append(("info", estado["i"]))
        uc.mem_write(dst, b"".join(pf(x) for x in nrm) + struct.pack("<i", cod))

    def sig(uc, m):
        m.log.append(("sig", estado["i"]))
        estado["i"] += 1

    stubs = {0x0026DD60: ini, 0x0026DD4C: fin, 0x0026DCF0: valido, 0x0026DC94: info, 0x0026DC84: sig}
    return {"r": [HEAP + 0x500, codigo], "stubs": stubs}


def gen_jump_ground():
    self_, ctrl, fis, col = HEAP + 0x100, HEAP + 0x1000, HEAP + 0x2000, HEAP + 0x3000
    fis = HEAP + 0x5000
    mem = [(self_ + 4, struct.pack("<III", ctrl, fis, col)),
           (fis, b"".join(pf(f32()) for _ in range(0x40 // 4)))]
    mem += objeto_espia(ctrl, R.choice([0, 1, 2, R.getrandbits(32)]))
    mem += objeto_espia(col, R.choice([0, 1, 2, R.getrandbits(32)]))
    return {"r": [self_], "mem": mem}


def gen_stopped():
    self_, fis = HEAP + 0x100, HEAP + 0x2000
    vals = [f32() for _ in range(0x80 // 4)]
    if R.random() < 0.3:  # largo EXACTO en el umbral: un eje = +-0.1f, el resto 0
        for k in list(range(9, 12)) + list(range(27, 30)):
            vals[k] = 0.0
        ulp = struct.unpack("<f", struct.pack("<I", 0x3DCCCCCD + R.randint(-4, 4)))[0]  # 0.1f +- 4 ulps
        vals[R.choice([9, 10, 11, 27, 28, 29])] = R.choice([ulp, -ulp])
    elif R.random() < 0.4:  # velocidades chicas cerca del umbral 0.1
        for k in range(9, 12):
            vals[k] = R.uniform(-0.08, 0.08)
        for k in range(27, 30):
            vals[k] = 0.0
    return {"r": [self_], "mem": [(self_ + 4, struct.pack("<I", fis)), (fis, b"".join(pf(x) for x in vals))]}


def gen_input():
    p = HEAP + 0x100
    return {"r": [p], "mem": [(p, bytes(R.getrandbits(8) for _ in range(0x60)))]}


JUEGO = None


def dir_(nombre):
    global JUEGO
    if JUEGO is None:
        JUEGO = simbolos_juego()
    return JUEGO[nombre]


def gen_kuribo():
    """Todas las llamadas del Goomba se reemplazan por stubs con guion: se verifica SU logica de decision."""
    nombres = ["isSensorPlayer", "isSensorEnemyAttack", "isSensorEnemy", "isSensorMapObj", "isNerve", "setNerve",
               "sendMsgPush", "sendMsgEnemyAttack", "sendMsgPushAndKillVelocityToTarget"]
    stubs = {dir_(n): stub_guion(n) for n in nombres}
    guion = [R.choice([0, 1, 1, 2, 0xFFFFFFFF]) if R.random() < 0.9 else 0 for _ in range(12)]
    return {"r": [HEAP + 0x100, HEAP + 0x200, HEAP + 0x300], "stubs": stubs, "guion": guion}


def gen_brake():
    self_, fis, ctrl, extra, param, stick = (HEAP + 0x100, HEAP + 0x1000, HEAP + 0x2000, HEAP + 0x3000,
                                             HEAP + 0x4000, HEAP + 0x6000)
    vals = [f32() for _ in range(0x40)]
    st = [f32(), f32(), f32()]
    if R.random() < 0.6:  # ramas profundas: stick fuerte (~1), velocidad grande alineada con el stick
        ang = R.uniform(0, 6.283)
        import math
        st = [math.cos(ang) * R.uniform(0.85, 1.05), 0.0, math.sin(ang) * R.uniform(0.85, 1.05)]
        for k in range(6, 9):          # arriba (+0x18)
            vals[k] = [0.0, 1.0, 0.0][k - 6]
        sign = R.choice([1, 1, -1])
        for k, c in zip(range(9, 12), st):  # velocidad (+0x24)
            vals[k] = sign * c * R.uniform(0.5, 30) + R.uniform(-0.2, 0.2)
        fr = R.choice([st, [-st[0], 0.0, -st[2]], [st[2], 0.0, -st[0]]])
        for k, c in zip(range(3, 6), fr):  # frente (+0xC)
            vals[k] = c
    mem = [(self_ + 4, struct.pack("<III", fis, ctrl, extra)), (self_ + 0x10, struct.pack("<i", R.randint(-2, 9))),
           (fis, b"".join(pf(x) for x in vals)), (stick, b"".join(pf(x) for x in st))]
    mem += objeto_espia(ctrl, stick)
    mem += objeto_espia(extra, R.choice([0, 1, 1, 2]))
    minimo = struct.unpack("<I", pf(R.choice([0.0, 0.5, 1.0, 5.0, f32()])))[0]
    mem += objeto_espia(param, 0, {0x2C8 // 4: minimo, 0x2C4 // 4: R.choice([0, 1, 7, 30, R.getrandbits(32)])})

    def tabla(uc, m):
        m.log.append(("tablaParam",))
        return param
    return {"r": [self_], "mem": mem, "stubs": {0x0026E1D4: tabla}}


CASOS = {
    "setFlagBit": gen_flags,
    "isMsg17": gen_msg, "isMsgPlayerTailAttack": gen_msg, "isMsgPlayerKick": gen_msg,
    "isActorRising": gen_actor_vec,
    "PlayerActionCondNot_evaluate": gen_cond_simple,
    "PlayerActionCondAnd_evaluate": gen_lista, "PlayerActionCondOr_evaluate": gen_lista,
    "PlayerActionExecutor_selectNext": gen_select,
    "PlayerCollider_isTouchCode": "touch",
    "PlayerActionCondJumpOnGround_evaluate": gen_jump_ground,
    "PlayerActionCondStopped_evaluate": gen_stopped,
    "PlayerInput_isJumpTriggerBuffered": gen_input, "PlayerInput_isJumpHold": gen_input,
    "PlayerInput_getStickDir3D": gen_input,
    "Kuribo_attackSensor": gen_kuribo,
    "PlayerActionCondBrake_evaluate": gen_brake,
}


def comparar(a, b):
    if a["err"] or b["err"]:
        return f"error original={a['err']} decomp={b['err']}"
    if a["r0"] != b["r0"]:
        return f"r0 {a['r0']:#x} != {b['r0']:#x}"
    if a["log"] != b["log"]:
        return f"llamadas distintas\n  orig  {a['log'][:12]}\n  decomp {b['log'][:12]}"
    if a["heap"] != b["heap"]:
        i = next(k for k in range(len(a["heap"])) if a["heap"][k] != b["heap"][k])
        return f"memoria distinta en 0x{HEAP + i:08X}"
    if a["datos"] != b["datos"]:
        return "globales del juego distintas"
    return None


def main():
    args = sys.argv[1:]
    n = 2000
    if "-n" in args:
        i = args.index("-n")
        n = int(args[i + 1])
        del args[i:i + 2]
    juego = simbolos_juego()
    propios = BUILD["funciones"]
    nombres = args or [k for k in CASOS if k in propios]
    m = Maquina()
    ext = {**BUILD["externos"]}
    total_ok = 0
    for nom in nombres:
        if nom not in propios or nom not in juego:
            print(f"--  {nom}: falta en decomp o en simbolos.txt")
            continue
        gen = CASOS[nom]
        orig, nuevo = juego[nom], propios[nom]
        fallo = None
        nt = 0
        for k in range(n):
            caso = gen_touch(ext) if gen == "touch" else gen()
            m.poner_stubs(caso.get("stubs", {}))
            a = m.correr(orig, caso)
            if a["err"] == NO_TERMINO:
                nt += 1
                continue
            b = m.correr(nuevo, caso)
            fallo = comparar(a, b)
            if fallo:
                fallo = f"prueba {k}: {fallo}\n  regs={[hex(x) for x in caso.get('r', [])]}"
                break
        if fallo:
            print(f"FALLA {nom} (0x{orig:08X}): {fallo}")
        elif nt == n:
            print(f"SIN DATOS {nom} (0x{orig:08X}): la original no termino en ninguna de las {n} pruebas")
        else:
            total_ok += 1
            print(f"OK    {nom} (0x{orig:08X}): {n - nt} pruebas iguales" + (f" ({nt} descartadas: no termino)" if nt else ""))
    print(f"\n{total_ok}/{len(nombres)} verificadas")


if __name__ == "__main__":
    main()
