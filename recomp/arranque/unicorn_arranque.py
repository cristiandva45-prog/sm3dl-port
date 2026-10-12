r"""Arranque de SM3DL en Unicorn (codigo ARM ORIGINAL) hasta el primer SendSyncRequest (svc 0x32).

Sustituye a correr recomp\arranque\sm3dl.exe cuando Smart App Control bloquea el exe nuevo (8 oct): mismo mapa de
memoria que main.c, svcs con la misma semantica que recomp\sistema\sistema.c (un solo hilo), y ademas COMPRUEBA EL
TRADUCTOR: cada destino de un salto/llamada INDIRECTO (blx rX, bx rX, mov pc rX, ldr pc ... que no sea retorno ni
tabla de saltos) tiene que ser una funcion de recomp\arranque\todo.c; si no, el exe recompilado moriria ahi en
rt_externo. Asi cada obstaculo aparece antes de compilar.

Uso (desde la raiz del port):  py -I recomp\arranque\unicorn_arranque.py [--max N] [--seguir K]
  --quitar 0xA,0xB : SABOTAJE, quita funciones del conjunto traducido (el aviso tiene que aparecer)
  --seguir K : no parar en los primeros K SendSyncRequest (los responde con 0 y sigue)
"""
import os
import re
import struct
import sys

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR, UC_HOOK_BLOCK, UC_HOOK_MEM_UNMAPPED
from unicorn import arm_const as U
import capstone
from capstone import arm

A = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(A))
CODE_BASE, BSS_INI, BSS_TAM = 0x00100000, 0x003F39D4, 0x0003D684
PILA_TOPE, PILA_TAM = 0x10000000, 0x20000
TLS, TLS_TAM = 0x1FF82000, 0x200
HEAP, LINEAL = 0x08000000, 0x14000000
TEXT_FIN = CODE_BASE + 2758524

SVC_NOMBRE = {0x01: "ControlMemory", 0x08: "CreateThread", 0x0A: "SleepThread", 0x13: "CreateMutex",
              0x14: "ReleaseMutex", 0x17: "CreateEvent", 0x21: "CreateAddressArbiter", 0x22: "ArbitrateAddress",
              0x23: "CloseHandle", 0x27: "DuplicateHandle", 0x18: "SignalEvent", 0x19: "ClearEvent", 0x24: "WaitSynchronization1", 0x25: "WaitSynchronizationN", 0x28: "GetSystemTick",
              0x2D: "ConnectToPort", 0x32: "SendSyncRequest", 0x35: "GetProcessId", 0x37: "GetThreadId",
              0x38: "GetResourceLimit", 0x3A: "GetResourceLimitCurrentValues", 0x3C: "Break", 0x3D: "OutputDebugString"}


def funciones_traducidas():
    s = set()
    pat = re.compile(rb"^void f_([0-9A-F]{8})\(CPU \*c\);", re.M)
    with open(os.path.join(A, "todo.c"), "rb") as fh:
        cab = fh.read(4 << 20)  # las declaraciones van al principio
    for m in pat.finditer(cab):
        s.add(int(m.group(1), 16))
    return s


SITIOS_LLAMAR = set()


def saltos_a_externo():
    """Sitios donde todo.c llama rt_externo con destino CONSTANTE (salto directo a codigo que no es funcion)."""
    res, ult = {}, None
    global SITIOS_LLAMAR
    SITIOS_LLAMAR = set()
    pc = re.compile(r"/\* ([0-9A-F]{8}): ")
    pe = re.compile(r"rt_externo\(c, 0x([0-9A-F]{8})u\)")
    with open(os.path.join(A, "todo.c"), encoding="utf-8") as fh:
        for linea in fh:
            m = pc.search(linea)
            if m:
                ult = int(m.group(1), 16)
            m = pe.search(linea)
            if m and ult is not None:
                res[ult] = int(m.group(1), 16)
            if ult is not None and "rt_llamar(c, " in linea and "rt_llamar(c, 0x" not in linea:
                SITIOS_LLAMAR.add(ult)  # el exe salta por registro aqui: el destino tiene que ser funcion
    return res


def main():
    args = sys.argv[1:]
    maxi = int(args[args.index("--max") + 1]) if "--max" in args else 200_000_000
    seguir = int(args[args.index("--seguir") + 1]) if "--seguir" in args else 0
    code = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
    trad = funciones_traducidas()
    externos = saltos_a_externo()
    print(f"[uc] saltos directos a rt_externo en todo.c: {len(externos)}")
    if "--quitar" in args:  # sabotaje: fingir que una funcion no se tradujo
        trad -= {int(x, 16) for x in args[args.index("--quitar") + 1].split(",")}
    print(f"[uc] code.bin {len(code)} bytes; funciones en todo.c: {len(trad)}")

    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    try:
        uc.ctl_set_cpu_model(U.UC_CPU_ARM_1176)
    except Exception:
        pass
    fin = BSS_INI + BSS_TAM
    tam = (fin - CODE_BASE + 0xFFF) & ~0xFFF
    uc.mem_map(CODE_BASE, tam)
    uc.mem_write(CODE_BASE, code[:fin - CODE_BASE])
    uc.mem_map(PILA_TOPE - PILA_TAM, PILA_TAM)
    uc.mem_map(TLS, 32 * TLS_TAM)
    # como sis_iniciar: config memory (KERNEL_VERSION 2.34, APPMEMALLOC 64 MB), pagina compartida, VRAM
    uc.mem_map(0x1FF80000, 0x2000)
    uc.mem_write(0x1FF80002, bytes([0x22, 2]))
    uc.mem_write(0x1FF80040, struct.pack("<I", 64 << 20))
    uc.mem_map(0x1F000000, 0x00600000)
    # VFP: CPACR cp10/cp11 + FPEXC.EN
    uc.reg_write(U.UC_ARM_REG_C1_C0_2, uc.reg_read(U.UC_ARM_REG_C1_C0_2) | (0xF << 20))
    uc.reg_write(U.UC_ARM_REG_FPEXC, 0x40000000)
    uc.reg_write(U.UC_ARM_REG_C13_C0_3, TLS)
    uc.reg_write(U.UC_ARM_REG_SP, PILA_TOPE)

    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = True
    cache = {}

    def ins(a):
        if a not in cache:
            try:
                cache[a] = next(md.disasm(bytes(uc.mem_read(a, 4)), a))
            except (StopIteration, UcError):
                cache[a] = None
        return cache[a]

    st = {"heap": HEAP, "lineal": LINEAL, "h": 0x10, "handles": {}, "ipc": 0, "prev": None, "fallos": {},
          "n_svc": {}, "bloques": 0}

    def nuevo_handle(desc):
        st["h"] += 1
        st["handles"][st["h"]] = desc
        return st["h"]

    def indirecto(i):
        """Destino por registro que el traductor resuelve con rt_llamar (no retorno ni tabla de saltos)."""
        if i is None:
            return False
        ops = i.operands
        m = i.mnemonic
        if i.id in (arm.ARM_INS_BLX, arm.ARM_INS_BX) and ops and ops[0].type == arm.ARM_OP_REG:
            return i.reg_name(ops[0].reg) != "lr"
        if i.id == arm.ARM_INS_MOV and len(ops) == 2 and ops[0].type == arm.ARM_OP_REG and i.reg_name(ops[0].reg) == "pc":
            return ops[1].type == arm.ARM_OP_REG and i.reg_name(ops[1].reg) not in ("lr",)
        if i.id == arm.ARM_INS_LDR and ops and i.reg_name(ops[0].reg) == "pc":
            mem = ops[1]
            return mem.type == arm.ARM_OP_MEM and i.reg_name(mem.mem.base) not in ("pc", "sp")
        return False

    def bloque(uc_, a, size, _):
        st["bloques"] += 1
        p = st["prev"]
        st["prev"] = (a, size)
        if p is None:
            return
        u = ins(p[0] + p[1] - 4)
        if u is not None and externos.get(u.address) == a and ("x", a) not in st["fallos"]:
            st["fallos"][("x", a)] = 1
            print(f"[uc] !! salto DIRECTO a 0x{a:08X} desde 0x{u.address:08X} ({u.mnemonic} {u.op_str}): todo.c lo "
                  f"emite como rt_externo -> el exe moriria aqui")
        if (indirecto(u) or (u is not None and u.address in SITIOS_LLAMAR)) and a not in trad:
            k = (a, u.address)
            if k not in st["fallos"]:
                lr = uc_.reg_read(U.UC_ARM_REG_LR)
                print(f"[uc] !! destino indirecto SIN TRADUCIR 0x{a:08X} desde 0x{u.address:08X} "
                      f"({u.mnemonic} {u.op_str}) lr=0x{lr:08X}  -> el exe moriria aqui en rt_externo")
            st["fallos"][k] = st["fallos"].get(k, 0) + 1

    def r(n):
        return uc.reg_read(getattr(U, f"UC_ARM_REG_R{n}"))

    def w(n, v):
        uc.reg_write(getattr(U, f"UC_ARM_REG_R{n}"), v & 0xFFFFFFFF)

    def mapear(a, t):
        t = (t + 0xFFF) & ~0xFFF
        try:
            uc.mem_map(a, t)
        except UcError:
            pass

    def cadena(a, n=16):
        b = bytes(uc.mem_read(a, n))
        return b.split(b"\0")[0].decode("latin-1")

    def svc(uc_, intno, _):
        pc = uc_.reg_read(U.UC_ARM_REG_PC)
        num = struct.unpack("<I", bytes(uc_.mem_read(pc - 4, 4)))[0] & 0xFFFFFF
        st["n_svc"][num] = st["n_svc"].get(num, 0) + 1
        if st["n_svc"][num] <= 6:
            print(f"[svc] 0x{num:02X} {SVC_NOMBRE.get(num, '?')} en 0x{pc - 4:08X} "
                  f"(r0={r(0):08X} r1={r(1):08X} r2={r(2):08X} r3={r(3):08X})")
        if num == 0x01:
            op, t, a = r(0) & 0xFF, (r(3) + 0xFFF) & ~0xFFF, r(1)
            if op == 3:
                if r(0) & 0x10000:
                    a = st["lineal"]; st["lineal"] += t
                elif not a:
                    a = st["heap"]
                if a == st["heap"]:
                    st["heap"] += t
                mapear(a, t)
            w(0, 0); w(1, a)
        elif num in (0x21, 0x38, 0x13, 0x17):
            w(0, 0); w(1, nuevo_handle(SVC_NOMBRE[num]))
        elif num == 0x22:
            a, tipo, valor = r(1), r(2), struct.unpack("<i", struct.pack("<I", r(3)))[0]
            w(0, 0)
            if tipo != 0:
                actual = struct.unpack("<i", bytes(uc_.mem_read(a, 4)))[0]
                if actual < valor:
                    print(f"[uc] ArbitrateAddress esperaria (addr 0x{a:08X} = {actual} < {valor}): un solo hilo, alto")
                    uc_.emu_stop()
        elif num == 0x23:
            st["handles"].pop(r(0), None); w(0, 0)
        elif num == 0x3A:
            for i in range(r(3)):
                uc_.mem_write(r(0) + 8 * i, b"\0" * 8)
            w(0, 0)
        elif num == 0x2D:
            nombre = cadena(r(1))
            w(0, 0); w(1, nuevo_handle(f"puerto {nombre}"))
            print(f"[uc]   ConnectToPort(\"{nombre}\") -> handle 0x{st['h']:X}")
        elif num == 0x27:  # DuplicateHandle(r1) -> r1 (0xFFFF8000 = hilo actual)
            w(0, 0); w(1, nuevo_handle(f"duplicado de 0x{r(1):08X}"))
        elif num in (0x14, 0x18, 0x19, 0x24):  # ReleaseMutex, Signal/ClearEvent, WaitSynchronization1: sin espera
            w(0, 0)
        elif num == 0x3D:
            print(f"[uc]   OutputDebugString: {bytes(uc_.mem_read(r(0), min(r(1), 200))).decode('latin-1')!r}")
            w(0, 0)
        elif num == 0x28:
            w(0, 0); w(1, 0)
        elif num in (0x35, 0x37):
            w(0, 0); w(1, 0x28 if num == 0x35 else 1)
        elif num == 0x32:
            st["ipc"] += 1
            h = r(0)
            cmd = [struct.unpack("<I", bytes(uc_.mem_read(TLS + 0x80 + 4 * i, 4)))[0] for i in range(16)]
            cab = cmd[0]
            nn, nt = (cab >> 6) & 0x3F, cab & 0x3F
            print(f"[uc] === IPC #{st['ipc']} en 0x{pc - 4:08X} (lr=0x{uc_.reg_read(U.UC_ARM_REG_LR):08X}): handle 0x{h:X} = "
                  f"{st['handles'].get(h, '?')}; cabecera 0x{cab:08X} (comando 0x{cab >> 16:04X}, {nn} normales, "
                  f"{nt} traducidas)")
            print("[uc]     palabras: " + " ".join(f"{x:08X}" for x in cmd[:1 + nn + nt]))
            if nn >= 1:
                txt = bytes(uc_.mem_read(TLS + 0x84, 8)).split(b"\0")[0]
                if txt and all(32 <= c < 127 for c in txt):
                    print(f"[uc]     texto en los parametros: \"{txt.decode()}\"")
            if st["ipc"] > seguir:
                uc_.emu_stop()
                return
            uc_.mem_write(TLS + 0x80, struct.pack("<II", (cab & 0xFFFF0000) | 0x40, 0))
            w(0, 0)
        else:
            print(f"[uc] svc 0x{num:02X} {SVC_NOMBRE.get(num, '?')} sin stub: alto")
            uc_.emu_stop()

    def sin_mapa(uc_, acceso, a, t, v, _):
        print(f"[uc] acceso SIN MAPEAR a 0x{a:08X} (pc=0x{uc_.reg_read(U.UC_ARM_REG_PC):08X})")
        return False

    uc.hook_add(UC_HOOK_INTR, svc)
    uc.hook_add(UC_HOOK_BLOCK, bloque)
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, sin_mapa)
    try:
        uc.emu_start(CODE_BASE, 0xFFFFFFFF, count=maxi)
    except UcError as e:
        print(f"[uc] UcError {e} en pc=0x{uc.reg_read(U.UC_ARM_REG_PC):08X} lr=0x{uc.reg_read(U.UC_ARM_REG_LR):08X}")
    print(f"[uc] fin: pc=0x{uc.reg_read(U.UC_ARM_REG_PC):08X}, bloques {st['bloques']}, svcs "
          + ", ".join(f"0x{k:02X}x{v}" for k, v in sorted(st["n_svc"].items()))
          + f"; destinos indirectos sin traducir: {len(st['fallos'])}")


if __name__ == "__main__":
    main()
