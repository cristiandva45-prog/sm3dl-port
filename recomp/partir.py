"""Parte el C generado por recomp.py (una sola unidad de ~64 MB) en N unidades compilables por separado.

Uso: py -I recomp\\partir.py [entrada.c] [-n 32] [-o recomp\\gen\\partes]
Sale en el directorio:
  protos.h       #include "recomp.h" + FFN + las declaraciones void f_X(CPU *c); de TODAS las funciones
  parte_NN.c     #include "protos.h" + un tramo de funciones (repartidas por tamano, no por cantidad)
  tabla.c        rt_llamar (el switch de direccion -> funcion)
Las unidades viejas del directorio se borran antes, para que no se cuele una parte de otra corrida.
"""
import glob
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
INICIO_F = re.compile(r"^void f_[0-9A-F]{8}\(CPU \*c\)$")


def partir(entrada, n, salida):
    lineas = open(entrada, encoding="utf-8").read().split("\n")
    protos, define, cuerpos, tabla = [], [], [], []
    k = 0
    while k < len(lineas):
        l = lineas[k]
        if l.startswith("void f_") and l.endswith(";"):
            protos.append(l)
        elif l.startswith("#define"):
            define.append(l)
        elif INICIO_F.match(l):
            break
        k += 1
    actual = None
    while k < len(lineas):
        l = lineas[k]
        if l.startswith("void rt_llamar("):
            tabla = lineas[k:]
            break
        if INICIO_F.match(l):
            actual = [l]
            cuerpos.append(actual)
        elif actual is not None:
            actual.append(l)
        k += 1
    if not tabla:
        raise SystemExit("no encontre rt_llamar al final: el formato de recomp.py cambio")
    os.makedirs(salida, exist_ok=True)
    for viejo in glob.glob(os.path.join(salida, "parte_*.c")):
        os.remove(viejo)
    with open(os.path.join(salida, "protos.h"), "w", encoding="utf-8") as fh:
        fh.write("/* GENERADO por recomp/partir.py - no editar a mano */\n#pragma once\n#include \"recomp.h\"\n\n")
        fh.write("\n".join(protos) + "\n\n" + "\n".join(define) + "\n")
    # reparto por tamano: cada parte recibe ~total/n bytes de funciones consecutivas
    tam = [sum(len(x) + 1 for x in c) for c in cuerpos]
    meta = sum(tam) / n
    partes, cur, acum = [], [], 0
    for c, t in zip(cuerpos, tam):
        cur.append(c)
        acum += t
        if acum >= meta and len(partes) < n - 1:
            partes.append(cur)
            cur, acum = [], 0
    if cur:
        partes.append(cur)
    for j, p in enumerate(partes):
        with open(os.path.join(salida, f"parte_{j:02d}.c"), "w", encoding="utf-8") as fh:
            fh.write("/* GENERADO por recomp/partir.py - no editar a mano */\n#include \"protos.h\"\n\n")
            fh.write("\n".join("\n".join(c) for c in p) + "\n")
    with open(os.path.join(salida, "tabla.c"), "w", encoding="utf-8") as fh:
        fh.write("/* GENERADO por recomp/partir.py - no editar a mano */\n#include \"protos.h\"\n\n")
        # 7 oct: gancho de depuracion (arranque/sonda.c, p. ej. posicion de Mario); NULL = no hace nada.
        # El enlazador de Windows (lld COFF) no tiene --wrap, por eso va aqui.
        fh.write("void (*rt_sonda_llamar)(CPU *c, u32 addr);\n\n")
        assert tabla[1].strip() == "{", "rt_llamar cambio de forma"
        tabla = tabla[:2] + ["    if (rt_sonda_llamar) rt_sonda_llamar(c, addr);"] + tabla[2:]
        fh.write("\n".join(tabla) + "\n")
    print(f"ok: {len(cuerpos)} funciones ({len(protos)} declaradas) en {len(partes)} partes + tabla.c -> {salida}")
    if len(protos) != len(cuerpos):
        raise SystemExit("declaraciones y cuerpos no coinciden")
    return len(partes)


def main():
    args = sys.argv[1:]
    n, salida = 32, os.path.join(AQUI, "gen", "partes")
    if "-n" in args:
        k = args.index("-n")
        n = int(args[k + 1])
        del args[k:k + 2]
    if "-o" in args:
        k = args.index("-o")
        salida = args[k + 1]
        del args[k:k + 2]
    entrada = args[0] if args else os.path.join(AQUI, "gen", "todo.c")
    partir(entrada, n, salida)


if __name__ == "__main__":
    main()
