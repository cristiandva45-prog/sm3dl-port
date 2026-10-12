r"""Genera recomp\render\interp_programas.h: por cada programa de vertices de los DVLB del juego, sus primeras 16
palabras de codigo + main (para reconocerlo en vs.codigo) y la CLASE de cada uniform float c0-c95 segun su NOMBRE en
la tabla de simbolos del DVLE (8 oct). Asi la interpolacion sabe que es cada registro en vez de adivinarlo.
Ademas: que registros empiezan una MATRIZ 3x4 (se mezclan como rotacion, no valor por valor) y que uniforms bool dicen
si el objeto tiene esqueleto (IsSmoSk/IsRgdSk) y si los huesos van en cuaterniones (IsQuate).
Uso: py -I tools\gen_interp_programas.py"""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shbin import Shbin
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# clases: 0 = mezclar si hay pareja (matriz del objeto, colores), 1 = CAMARA (se mezcla siempre, tambien sin pareja),
# 2 = REAL (animacion de textura: nunca se mezcla), 3 = TIEMPO (se mezcla si avanza; si da la vuelta, real),
# 4 = sin nombre (mezcla ciega, como antes), 5 = HUESOS (UnivReg: huesos si el objeto tiene esqueleto; si no, real)
def clase(nombre):
    n = nombre.split(".")[0]
    if n in ("ViewMtx", "ProjMtx", "view", "proj", "uProjMtx"): return 1
    if n.startswith(("TexMtx", "uTexMtx", "TexTran", "TexcMap", "UvMap", "IrScale", "uv_src", "uv_size", "uFrameSpec", "uRcpTexSize")): return 2
    if n in ("time",): return 3
    if n == "UnivReg": return 5
    return 0
MATRICES_3X4 = ("WrldMtx", "NormMtx", "ViewMtx", "view", "uPosMtx", "uNrmMtx", "user")
progs = []
for f in sorted(glob.glob(os.path.join(R, "extraido", "shaders", "**", "*.shbin"), recursive=True)):
    s = Shbin(open(f, "rb").read())
    for k, e in enumerate(s.entradas):
        if e["tipo"] != "vertex": continue
        cl = [4] * 96
        bloque = [0] * 96
        piel = quat = 0
        for nombre, ini, fin in e["uniforms"]:
            n = nombre.split(".")[0]
            if 0x10 <= ini < 0x70:
                for r in range(ini - 0x10, min(fin, 0x6F) - 0x10 + 1): cl[r] = clase(nombre)
                if n in MATRICES_3X4 and fin - ini + 1 == 3: bloque[ini - 0x10] = 1
                if n == "UnivReg":
                    for r in range(ini - 0x10, fin - 0x10 - 1, 3): bloque[r] = 1
            elif 0x78 <= ini <= 0x87:
                if n in ("IsSmoSk", "IsRgdSk"): piel |= 1 << (ini - 0x78)
                if n == "IsQuate": quat |= 1 << (ini - 0x78)
        # EFECTOS (8 oct, nubes del veneno y hojas): code_2AC800 dibuja MUCHAS particulas por dibujo, una matriz 3x4
        # por particula en c28-c84 (visto en el diagnostico F9 del 1-1); entre cuadros nacen, mueren y se reordenan:
        # clase 6 = PARTICULA (pareja por cercania mutua). Lo demas de los efectos (parametros del emisor, sin nombre)
        # va REAL. code_2ACC00 / code_2ACE80: sin datos todavia -> solo la camara se mezcla.
        base = os.path.basename(f)
        if base == "code_2AC800.shbin":
            cl = [c if c == 1 else (6 if 28 <= r <= 84 else 2) for r, c in enumerate(cl)]
        elif base in ("code_2ACC00.shbin", "code_2ACE80.shbin"):
            cl = [c if c == 1 else 2 for c in cl]
        progs.append((os.path.relpath(f, R), k, s.codigo[:16] + [0] * (16 - len(s.codigo[:16])), e["main"], cl, bloque, piel, quat))
with open(os.path.join(R, "recomp", "render", "interp_programas.h"), "w", newline="\n") as o:
    o.write("/* GENERADO por tools/gen_interp_programas.py (no editar a mano). */\n")
    o.write("typedef struct { const char *nombre; uint32_t cod[16]; uint32_t main; uint8_t clase[96]; uint8_t bloque[96]; "
            "uint16_t piel, quat; } InterpPrograma;\n")
    o.write(f"#define N_INTERP_PROGRAMAS {len(progs)}\nstatic const InterpPrograma g_programas[N_INTERP_PROGRAMAS] = {{\n")
    for nombre, k, cod, main, cl, bloque, piel, quat in progs:
        o.write('    { "%s#%d", { %s }, %d, { %s }, { %s }, 0x%04X, 0x%04X },\n' % (
            nombre.replace("\\", "/"), k, ", ".join("0x%08X" % c for c in cod), main, ",".join(map(str, cl)),
            ",".join(map(str, bloque)), piel, quat))
    o.write("};\n")
print(len(progs), "programas")
for nombre, k, cod, main, cl, bloque, piel, quat in progs:
    print(f"  {nombre}#{k} main={main} camara={cl.count(1)} real={cl.count(2)} tiempo={cl.count(3)} objeto={cl.count(0)} "
          f"huesos={cl.count(5)} particula={cl.count(6)} ciego={cl.count(4)} matrices={sum(bloque)} piel={piel:#x} quat={quat:#x}")
