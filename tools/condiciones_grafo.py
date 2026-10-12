"""Vuelca las clases-condicion del grafo de acciones de Mario: ctor -> vtable -> metodos decompilados.

Uso (python del venv de pyghidra-mcp, con -I):
  condiciones_grafo.py <carpeta_proyecto> <nombre_proyecto> <salida.txt> <dir_ctor> [<dir_ctor> ...]

Para cada constructor busca la vtable que escribe (puntero en el literal pool que cae en
.rodata/.data), lee sus entradas hasta salir de .text y decompila cada metodo distinto.
Una sola JVM para todas las direcciones.
"""
import os
import re
import sys

os.environ.setdefault("GHIDRA_INSTALL_DIR", r"C:\tools\ghidra_12.1.4_PUBLIC")
os.environ.setdefault("JAVA_HOME", r"C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot")

import pyghidra  # noqa: E402

TEXT = (0x00100000, 0x00100000 + 2758524)
DATOS = (0x003A2000, 0x003F39D4)


def main():
    carpeta, nombre, salida, dirs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    pyghidra.start()
    from ghidra.app.decompiler import DecompInterface

    proyecto = pyghidra.open_project(carpeta, nombre)
    out = []
    try:
        with pyghidra.program_context(proyecto, "/code.elf") as prog:
            fm = prog.getFunctionManager()
            af = prog.getAddressFactory()
            mem = prog.getMemory()
            listing = prog.getListing()
            rm = prog.getReferenceManager()
            monitor = pyghidra.task_monitor()
            dec = DecompInterface()
            dec.openProgram(prog)

            def addr(v):
                return af.getAddress(hex(v))

            def u32(v):
                return mem.getInt(addr(v)) & 0xFFFFFFFF

            def decomp(f):
                r = dec.decompileFunction(f, 60, monitor)
                return r.getDecompiledFunction().getC().replace("\r", "") if r.decompileCompleted() else "(fallo)"

            ya = set()
            for t in dirs:
                a = addr(int(t, 16))
                f = fm.getFunctionContaining(a)
                if f is None:
                    out.append(f"##### {t}: sin funcion\n")
                    continue
                out.append(f"##### CTOR {f.getName()} @ {f.getEntryPoint()}")
                texto = decomp(f)
                out.append(texto)
                vtables = []
                for m in re.finditer(r"DAT_([0-9a-f]{8})", texto):
                    try:
                        v = u32(int(m.group(1), 16))
                    except Exception:
                        continue
                    if DATOS[0] <= v < DATOS[1] and v not in vtables:
                        vtables.append(v)
                for ins in listing.getInstructions(f.getBody(), True):
                    for ref in ins.getReferencesFrom():
                        d = ref.getToAddress().getOffset()
                        if DATOS[0] <= d < DATOS[1] or TEXT[0] <= d < TEXT[1]:
                            try:
                                v = u32(d)
                            except Exception:
                                continue
                            if DATOS[0] <= v < DATOS[1] and v not in vtables:
                                vtables.append(v)
                for vt in vtables:
                    slots = []
                    for i in range(8):
                        try:
                            slots.append(u32(vt + 4 * i))
                        except Exception:
                            break
                    if not slots:
                        continue
                    out.append(f"--- vtable 0x{vt:08X}: " + ", ".join(f"[{i}]0x{p:08X}" for i, p in enumerate(slots)))
                    for i, p in enumerate(slots):
                        if not (TEXT[0] <= (p & ~1) < TEXT[1]):
                            continue
                        g = fm.getFunctionAt(addr(p & ~1))
                        if g is None or p in ya:
                            continue
                        ya.add(p)
                        nrefs = rm.getReferenceCountTo(g.getEntryPoint())
                        cuerpo = decomp(g)
                        if len(cuerpo) > 3000:
                            cuerpo = cuerpo[:3000] + "\n  ...(recortado)"
                        out.append(f"  >> slot {i} {g.getName()} (refs {nrefs})")
                        out.append(cuerpo)
                out.append("")
            dec.dispose()
    finally:
        proyecto.close()
    with open(salida + ".tmp", "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    os.replace(salida + ".tmp", salida)
    print("ok", len(dirs), "ctors ->", salida)


if __name__ == "__main__":
    main()
