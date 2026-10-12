"""Compila en paralelo las unidades de recomp\\partir.py (x86-64 nativo, mismos flags que bateria.py) y las junta
en una biblioteca estatica.

Uso: py -I recomp\\compilar_todo.py [-d recomp\\gen\\partes] [-O2] [-j 16] [-o recomp\\build\\juego_todo.a]
Cada unidad va a <dir>\\obj\\<nombre>.o; al final, 'zig ar' arma la .a. Imprime el tiempo de cada unidad y el total.
"""
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

AQUI = os.path.dirname(os.path.abspath(__file__))
FLAGS = ["-target", "x86_64-windows-gnu", "-ffp-contract=off", "-fno-strict-aliasing", "-msse2",
         "-Wno-unused-label", "-Wno-unused-variable", "-Wno-parentheses-equality"]


def compilar(c_file, obj, opt, inc):
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "ziglang", "cc", *FLAGS, opt, "-I", os.path.join(AQUI, "runtime"),
                        "-I", inc, "-c", c_file, "-o", obj], capture_output=True, text=True)
    return c_file, r.returncode, r.stderr, time.time() - t0


def main():
    args = sys.argv[1:]

    def opcion(nombre, defecto):
        if nombre in args:
            k = args.index(nombre)
            v = args[k + 1]
            del args[k:k + 2]
            return v
        return defecto
    d = opcion("-d", os.path.join(AQUI, "gen", "partes"))
    j = int(opcion("-j", str(os.cpu_count() or 4)))
    salida = opcion("-o", os.path.join(AQUI, "build", "juego_todo.a"))
    opt = next((a for a in args if a.startswith("-O")), "-O2")
    fuentes = sorted(glob.glob(os.path.join(d, "parte_*.c"))) + [os.path.join(d, "tabla.c")]
    objdir = os.path.join(d, "obj")
    os.makedirs(objdir, exist_ok=True)
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    t0 = time.time()
    objs, fallas = [], 0
    with ProcessPoolExecutor(max_workers=j) as ex:
        fut = [ex.submit(compilar, f, os.path.join(objdir, os.path.basename(f)[:-2] + ".o"), opt, d) for f in fuentes]
        for f in as_completed(fut):
            c_file, rc, err, dt = f.result()
            nombre = os.path.basename(c_file)
            avisos = err.count("warning:")
            print(f"{nombre:14s} {dt:7.1f} s  {'ERROR' if rc else 'ok'}  avisos={avisos}", flush=True)
            if rc:
                fallas += 1
                print(err[-3000:])
            elif avisos:
                print(err[:1500])
    for fn in fuentes:
        objs.append(os.path.join(objdir, os.path.basename(fn)[:-2] + ".o"))
    t_comp = time.time() - t0
    if fallas:
        raise SystemExit(f"{fallas} unidades con error ({t_comp:.0f} s)")
    if os.path.exists(salida):
        os.remove(salida)
    r = subprocess.run([sys.executable, "-m", "ziglang", "ar", "rcs", salida, *objs], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ar fallo: " + r.stderr[-2000:])
    tam = sum(os.path.getsize(o) for o in objs)
    print(f"total: {len(fuentes)} unidades, {opt}, j={j}: compilar {t_comp:.0f} s, todo {time.time() - t0:.0f} s; "
          f"objetos {tam / 1e6:.0f} MB -> {salida}")


if __name__ == "__main__":
    main()
