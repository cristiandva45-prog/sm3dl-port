"""Auditoria en ejecucion de las funciones que descubrio tools\\descubrir_funciones.py.

Toma una muestra de extraido\\funciones_extra.tsv, traduce CADA una sola (sus llamadas salientes quedan como stubs
con guion, iguales en los dos lados) y la compara: original en Unicorn contra recompilada nativa x86-64.
Entradas genericas: un monticulo de objetos espia (decomp\\verificar.py) cuyos campos son punteros a otros objetos,
enteros chicos o floats. Las pruebas en que la ORIGINAL falla (memoria no mapeada, etc.) se descartan: la entrada no
era valida para esa funcion. Lo que se compara es lo demas.

Uso: py -I tools\\auditar_descubiertas.py [-k 30] [-n 300] [-s semilla] [dir ...]
"""
import os
import random
import struct
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "recomp"))
sys.path.insert(0, os.path.join(RAIZ, "decomp"))
import recomp  # noqa: E402
import verificar as V  # noqa: E402
import verificar_recomp as VR  # noqa: E402
from unicorn import arm_const as A  # noqa: E402

TMP = os.path.join(RAIZ, "recomp", "build", "auditoria")
N_OBJ = 64  # objetos espia de 0x1000 bytes en el monticulo (0x900 los usa el espia)


def salientes(a):
    tam = recomp.tamanos()
    fin = recomp.limite(tam, sorted(tam), a)
    t = recomp.Traductor(a, fin, set())
    ins = t.recorrer()
    out = {d for d in recomp.llamadas_de(ins) if not (a <= d < fin)}
    sin = sum(1 for i in ins.values() if i is None)
    return out, ins, sin


def stub(nombre):
    def fn(uc, m):
        m.log.append((nombre, uc.reg_read(A.UC_ARM_REG_R0), uc.reg_read(A.UC_ARM_REG_R1),
                      uc.reg_read(A.UC_ARM_REG_R2)))
        return m.guion.pop(0) if m.guion else 0
    return fn


def palabra(R):
    x = R.random()
    if x < 0.35:
        return V.HEAP + 0x1000 * R.randrange(N_OBJ)                 # puntero a objeto espia
    if x < 0.45:
        return V.HEAP + 0x1000 * R.randrange(N_OBJ) + 0x900 + 4 * R.randrange(0x1C0)  # puntero dentro de un objeto
    if x < 0.7:
        return R.choice([0, 1, 2, 3, 0xFFFFFFFF, R.randrange(64)])
    if x < 0.9:
        return struct.unpack("<I", struct.pack("<f", R.uniform(-100, 100)))[0]
    return R.getrandbits(32)


def caso(R, stubs):
    # la zona de espias: Unicorn la llena con 'bx lr' y el anfitrion nativo con ceros; 0x330754 la LEE como dato
    # (obj->+0x28->vt->+0x24 apunta a un espia) y daba una falla falsa. Se escribe igual en los dos lados.
    mem = [(V.ESPIA, b"\x1e\xff\x2f\xe1" * V.N_ESPIAS)]
    for k in range(N_OBJ):
        base = V.HEAP + 0x1000 * k
        ret = palabra(R)
        mem += V.objeto_espia(base, ret)
        campos = b"".join(struct.pack("<I", palabra(R)) for _ in range(4, 0x44, 4))
        mem.append((base + 4, campos))
        mem.append((base + 0x48, b"".join(struct.pack("<I", palabra(R)) for _ in range(0x48, 0x100, 4))))
        mem.append((base + 0x900, b"".join(struct.pack("<I", palabra(R)) for _ in range(0x900, 0x1000, 4))))
    regs = [V.HEAP + 0x1000 * R.randrange(N_OBJ)] + [palabra(R) for _ in range(3)]
    return {"r": regs, "s": [R.uniform(-10, 10) for _ in range(4)], "mem": mem, "stubs": stubs,
            "guion": [palabra(R) for _ in range(64)]}


def compilar(a, excluir):
    os.makedirs(TMP, exist_ok=True)
    c = os.path.join(TMP, f"f_{a:08X}.c")
    exe = os.path.join(TMP, f"f_{a:08X}.exe")
    args = [sys.executable, "-I", os.path.join(RAIZ, "recomp", "recomp.py"), f"{a:X}", "-o", c]
    if excluir:
        args += ["--excluir", ",".join(f"{x:X}" for x in excluir)]
    g = subprocess.run(args, capture_output=True, text=True)
    if g.returncode:
        return None, g.stderr[-300:]
    if os.environ.get("AUDITAR_SABOTEAR"):  # candado: el auditor tiene que ver FALLAR una traduccion mala
        t = open(c, encoding="utf-8").read()
        k = t.find("c->r[0] = ", t.find(f"void f_{a:08X}(CPU *c)\n{{"))
        if k < 0:
            return None, "sabotaje: la funcion no escribe r0"
        open(c, "w", encoding="utf-8").write(t[:k] + "c->r[0] = 0x5A5A0000u ^ " + t[k + len("c->r[0] = "):])
    r = subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O1", "-s",
                        "-ffp-contract=off", "-fno-strict-aliasing", "-msse2", "-Wno-unused-label",
                        "-Wno-unused-variable", "-Wno-parentheses-equality",
                        "-I", os.path.join(RAIZ, "recomp", "runtime"), "-o", exe, c,
                        os.path.join(RAIZ, "recomp", "runtime", "runtime.c"),
                        os.path.join(RAIZ, "recomp", "runtime", "anfitrion_pipe.c")], capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr[-400:]
    return exe, None


def auditar(a, n, R):
    sal, ins, sin = salientes(a)
    if sin:
        return "SALTA", "tiene bytes que no decodifican"
    exe, err = compilar(a, sal)
    if not exe:
        return "NO COMPILA", err
    if "rt_desconocida(c, 0x" in open(exe[:-4] + ".c", encoding="utf-8").read():
        return "SALTA", "instruccion sin soporte (la trabaja otro agente)"
    VR.EXE = exe
    stubs = {d: stub(f"ext_{d:08X}") for d in sal}
    orig, anf = V.Maquina(), VR.AnfitrionPipe()
    validas = descartadas = 0
    try:
        for k in range(n * 4):
            if validas >= n:
                break
            cs = caso(R, stubs)
            orig.poner_stubs(stubs)
            x = orig.correr(a, cs)
            # emu_start(count=2M) se detiene SIN error al agotar el tope: si no volvio a la trampa, no termino
            # (0x12EDBC: bucle con un contador al azar enorme; Unicorn "terminaba bien" y el nativo seguia y caia)
            if not x["err"] and orig.uc.reg_read(A.UC_ARM_REG_PC) != V.TRAMPA:
                x["err"] = "tope de instrucciones"
            if x["err"]:
                descartadas += 1
                continue
            x["heap_h"], x["datos_h"] = VR.fnv_rapido(x["heap"]), VR.fnv_rapido(x["datos"])
            try:
                y = anf.correr(a, cs, x)
            except RuntimeError as e:
                return "FALLA", f"prueba {k}: nativa se cayo ({e}); la original termino bien"
            f = V.comparar(x, y)
            if f:
                return "FALLA", f"prueba {k}: {f}"
            validas += 1
    finally:
        anf.p.kill()
    if validas == 0:
        return "SIN DATOS", f"las {descartadas} entradas hicieron fallar a la original"
    return "OK", f"{validas} iguales ({descartadas} entradas descartadas)"


def main():
    args = sys.argv[1:]
    opt = {"-k": 30, "-n": 300, "-s": 7}
    for o in list(opt):
        if o in args:
            i = args.index(o)
            opt[o] = int(args[i + 1])
            del args[i:i + 2]
    R = random.Random(opt["-s"])
    extra = [l.split() for l in open(os.path.join(RAIZ, "extraido", "funciones_extra.tsv"))]
    if args:
        muestra = [(int(x, 16), "pedida", 0) for x in args]
    else:
        por = {}
        for a, t, o in extra:
            por.setdefault(o, []).append((int(a, 16), o, int(t)))
        muestra, cupo = [], {"rodata": 12, "salto": 7, "derivada": 5, "literal": 4, "data": 2}
        for o, lst in por.items():
            muestra += R.sample(lst, min(cupo.get(o, 2), len(lst)))
        muestra = muestra[:opt["-k"]]
    res = {}
    for a, o, t in sorted(muestra):
        est, det = auditar(a, opt["-n"], R)
        res[est] = res.get(est, 0) + 1
        print(f"{est:10} 0x{a:08X} [{o}, {t} B]: {det}", flush=True)
    print("\nresumen:", res)


if __name__ == "__main__":
    main()
