r"""Parches sobre la COPIA del juego recompilado (recomp\arranque\todo.c) mientras el traductor no los tenga.

Uso: py -I recomp\arranque\parchear.py   (despues: partir.py + compilar_todo.py sobre recomp\arranque)

1. 'mov{cc} pc, lr' es un RETORNO (estilo pre-ARMv5 de 'bx lr'), pero recomp.py lo emite como salto indirecto
   rt_llamar(c, lr): "llama" a la direccion de vuelta, que no es una funcion -> rt_externo (0x001001A8, 1er arranque).
   Se cambia por 'return;' igual que 'bx lr' y 'pop {..., pc}'.
2. 'ldr pc, [sp], #k' (epilogo de las funciones VARIADICAS de armcc: 'push {r0-r3}; push {..., lr}' ... 'pop {...};
   ldr pc, [sp], #0x14') es un RETORNO que ademas descarta los argumentos guardados. recomp.py lo emitia como salto
   indirecto rt_llamar(c, v) a la direccion de vuelta -> rt_externo 0x00380444 (vuelta de 0x28E1DC, un vsnprintf).
   Se deja la carga y el ajuste de sp y se cambia rt_llamar por 'return;'. 28 sitios.
"""
import os
import re
import sys

A = os.path.dirname(os.path.abspath(__file__))


def main():
    p = os.path.join(A, "todo.c")
    t = open(p, encoding="utf-8").read()
    patron = re.compile(r"(/\* [0-9A-F]{8}: mov(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)? pc, lr \*/\n"
                        r"[^\n]*?)\{ u32 co = c->c; \(void\)co; u32 t = c->r\[14\]; rt_llamar\(c, t\); return; \}")
    t, n = patron.subn(lambda m: m.group(1) + "return; /* parche: mov pc, lr = retorno */", t)
    print(f"mov pc, lr -> return: {n}")
    patron2 = re.compile(r"(/\* [0-9A-F]{8}: ldr pc, \[sp\], #0x[0-9a-f]+ \*/\n"
                         r"\s*\{ u32 a = c->r\[13\]; u32 v = R32\(a\); c->r\[13\] = c->r\[13\] \+ 0x[0-9A-F]+u; )"
                         r"rt_llamar\(c, v\); return; \}")
    t, n2 = patron2.subn(lambda m: m.group(1) + "(void)v; return; /* parche: ldr pc, [sp], #k = retorno */ }", t)
    print(f"ldr pc, [sp], #k -> return: {n2}")
    if n == 0 and "parche: mov pc, lr" not in t:
        sys.exit("no encontre el patron: revisar la forma que emite recomp.py")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(t)
    os.replace(tmp, p)


if __name__ == "__main__":
    main()
