r"""Genera el juego recompilado para el arranque (recomp\arranque\todo.c) con el traductor PRINCIPAL (recomp\recomp.py).

Uso: py -I recomp\arranque\generar.py   (despues: reconstruir.sh, o partir + compilar_todo + compilar)

Hasta el 8 oct esto era una copia congelada del traductor (recomp_base.py) con los arreglos del arranque encima
(limite con solapadas, llamadas manuales, constructores, cierre sobre constructores, punteros PC-relativos, saltos
directos a codigo sin funcion, punteros de vtable dentro de rangos de Ghidra) + parchear.py ('mov pc, lr' y
'ldr pc, [sp], #k' = retorno). Todo eso vive ahora en recomp.py; la version vieja quedo en generar_copia_8oct.py y
parchear_copia_8oct.py (y recomp_base.py) solo como referencia.
"""
import os
import subprocess
import sys

A = os.path.dirname(os.path.abspath(__file__))
R = os.path.dirname(A)

if __name__ == "__main__":
    sys.exit(subprocess.run([sys.executable, "-I", os.path.join(R, "recomp.py"), "--todo",
                             "-o", os.path.join(A, "todo.c")]).returncode)
