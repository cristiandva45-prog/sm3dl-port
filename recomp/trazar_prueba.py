r"""Copia instrumentada de un C generado: cada funcion imprime su direccion al entrar (stderr, con tope).
Sirve para ver DONDE se cuelga o diverge la recompilada nativa (8 oct: printf colgado).

Uso: py -I recomp\trazar_prueba.py gen\prueba_printf.c build\prueba_printf_traza.exe [tope]
"""
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import bateria as B  # noqa: E402


def main():
    fuente, exe = sys.argv[1], sys.argv[2]
    tope = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    t = open(fuente, encoding="utf-8").read()
    cab = ("#include <stdio.h>\n"
           "static unsigned long long g_tr;\n"
           "static void traza(unsigned a) { if (g_tr++ < %dull) { fprintf(stderr, \"F %%08X\\n\", a); fflush(stderr); } }\n"
           % tope)
    t = re.sub(r"(void f_([0-9A-F]{8})\(CPU \*c\)\n\{)", lambda m: m.group(1) + f" traza(0x{m.group(2)}u);", t)
    t = t.replace('#include "recomp.h"\n', '#include "recomp.h"\n' + cab, 1)
    salida = os.path.splitext(fuente)[0] + "_traza.c"
    open(salida, "w", encoding="utf-8").write(t)
    B.compilar(salida, exe)
    print("ok ->", exe)


if __name__ == "__main__":
    main()
