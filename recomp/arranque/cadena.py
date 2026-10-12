r"""Cadena de llamadas del JUEGO a partir de la pila del anfitrion que imprime sm3dl.exe al caer.

Cada 'bl' del juego es una llamada C de verdad, asi que la pila del anfitrion es la cadena de llamadas del juego.
El manejador de excepciones de main.c imprime "pila anfitrion (exe+): <offsets>"; esto los resuelve con el PDB
(dbghelp: archivo:linea) y traduce cada linea de partes\parte_NN.c a la funcion f_XXXXXXXX y la instruccion ARM.

Uso: py -I recomp\arranque\cadena.py [log]      (por defecto toma la ultima pila de recomp\arranque\log*.txt mas nuevo)
     py -I recomp\arranque\cadena.py --offsets A3EAD5 29913A ...
"""
import ctypes
import glob
import os
import re
import sys
from ctypes import wintypes as w

A = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(A, "sm3dl.exe")


class _Linea(ctypes.Structure):
    _fields_ = [("SizeOfStruct", w.DWORD), ("Key", ctypes.c_void_p), ("LineNumber", w.DWORD),
                ("FileName", ctypes.c_char_p), ("Address", ctypes.c_uint64)]


def resolver(offsets):
    dh = ctypes.WinDLL("dbghelp")
    proc = w.HANDLE(0x5EAD)
    dh.SymSetOptions(0x2 | 0x10)
    dh.SymInitialize(proc, A.encode(), False)
    dh.SymLoadModuleEx.restype = ctypes.c_uint64
    dh.SymLoadModuleEx.argtypes = [w.HANDLE, w.HANDLE, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint64, w.DWORD,
                                   ctypes.c_void_p, w.DWORD]
    base = 0x10000000
    dh.SymLoadModuleEx(proc, None, EXE.encode(), None, base, 0x4000000, None, 0)
    res = []
    for o in offsets:
        ln = _Linea()
        ln.SizeOfStruct = ctypes.sizeof(_Linea)
        d = w.DWORD()
        # la direccion de vuelta apunta DESPUES de la llamada: -1 cae en la linea de la llamada
        q = o if not res else o - 1
        if dh.SymGetLineFromAddr64(proc, ctypes.c_uint64(base + q), ctypes.byref(d), ctypes.byref(ln)):
            res.append((o, ln.FileName.decode(errors="replace"), ln.LineNumber))
        else:
            res.append((o, None, 0))
    return res


_CACHE = {}


def en_parte(ruta, linea):
    if ruta not in _CACHE:
        _CACHE[ruta] = open(ruta, encoding="utf-8").read().split("\n")
    ls = _CACHE[ruta]
    fn = ins = None
    for k in range(min(linea, len(ls)) - 1, -1, -1):
        if ins is None:
            m = re.match(r"\s*/\* ([0-9A-F]{8}: .*) \*/", ls[k])
            if m:
                ins = m.group(1)
        m = re.match(r"void (f_[0-9A-F]{8})\(CPU \*c\)$", ls[k])
        if m:
            fn = m.group(1)
            break
    return fn, ins


def main():
    args = sys.argv[1:]
    if args and args[0] == "--offsets":
        offs = [int(x, 16) for x in args[1:]]
    else:
        log = args[0] if args else max(glob.glob(os.path.join(A, "log*.txt")), key=os.path.getmtime)
        pilas = re.findall(r"pila anfitrion \(exe\+\):([0-9A-F ]+)", open(log, encoding="utf-8", errors="replace").read())
        if not pilas:
            sys.exit(f"{log}: no hay 'pila anfitrion' (el exe no cayo, o es anterior al 8 oct)")
        offs = [int(x, 16) for x in pilas[-1].split()]
        print(f"[{os.path.basename(log)}]")
    for o, archivo, linea in resolver(offs):
        if archivo is None:
            print(f"  exe+{o:X}  (sin linea)")
        elif os.path.basename(archivo).startswith("parte_"):
            fn, ins = en_parte(archivo, linea)
            print(f"  exe+{o:X}  {fn}  {ins}")
        else:
            print(f"  exe+{o:X}  {os.path.basename(archivo)}:{linea}")


if __name__ == "__main__":
    main()
