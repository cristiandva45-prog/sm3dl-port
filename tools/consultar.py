"""Consulta un proyecto Ghidra del port sin MCP: decompila, desensambla y busca referencias.

Uso (python del venv de pyghidra-mcp, con -I):
  consultar.py <carpeta_proyecto> <nombre_proyecto> decomp <dir|nombre> [<dir|nombre> ...]
  consultar.py <carpeta_proyecto> <nombre_proyecto> xrefs  <dir|nombre> [...]
  consultar.py <carpeta_proyecto> <nombre_proyecto> asm    <dir> [cantidad]
  consultar.py <carpeta_proyecto> <nombre_proyecto> buscar <regex_de_nombre_de_funcion>

Una direccion dentro de una funcion sirve: se usa la funcion que la contiene.
Cada llamada arranca la JVM (~20 s): agrupar varias direcciones en una sola llamada.
"""
import os
import re
import sys

os.environ.setdefault("GHIDRA_INSTALL_DIR", r"C:\tools\ghidra_12.1.4_PUBLIC")
os.environ.setdefault("JAVA_HOME", r"C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot")

import pyghidra  # noqa: E402


def main():
    carpeta, nombre, accion, args = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    timeout = 60
    if "--timeout" in args:  # p. ej. decomp --timeout 900 0x001a956c
        i = args.index("--timeout")
        timeout = int(args[i + 1])
        del args[i:i + 2]
    sys.stdout.reconfigure(encoding="utf-8")
    pyghidra.start()
    from ghidra.app.decompiler import DecompInterface
    from ghidra.program.model.symbol import RefType

    proyecto = pyghidra.open_project(carpeta, nombre)
    try:
        with pyghidra.program_context(proyecto, "/code.elf") as prog:
            fm = prog.getFunctionManager()
            af = prog.getAddressFactory()
            listing = prog.getListing()
            monitor = pyghidra.task_monitor()

            def funcion(texto):
                if re.fullmatch(r"(0x)?[0-9a-fA-F]+", texto):
                    a = af.getAddress(texto if texto.startswith("0x") else "0x" + texto)
                    return fm.getFunctionContaining(a), a
                for f in fm.getFunctions(True):
                    if f.getName() == texto:
                        return f, f.getEntryPoint()
                return None, None

            if accion == "decomp":
                dec = DecompInterface()
                dec.openProgram(prog)
                for t in args:
                    f, _ = funcion(t)
                    if f is None:
                        print(f"=== {t}: no hay funcion\n")
                        continue
                    r = dec.decompileFunction(f, timeout, monitor)
                    codigo = r.getDecompiledFunction().getC() if r.decompileCompleted() else f"(fallo: {r.getErrorMessage()})"
                    llamadas = sorted({c.getName() for c in f.getCalledFunctions(monitor)})
                    print(f"=== {f.getName()} @ {f.getEntryPoint()}  (llama a: {', '.join(llamadas)})")
                    print(codigo.replace("\r", ""))
                dec.dispose()
            elif accion == "xrefs":
                rm = prog.getReferenceManager()
                for t in args:
                    f, a = funcion(t)
                    destino = f.getEntryPoint() if f else a
                    refs = list(rm.getReferencesTo(destino))
                    print(f"=== {t} @ {destino}: {len(refs)} referencias")
                    for ref in refs[:200]:
                        desde = ref.getFromAddress()
                        g = fm.getFunctionContaining(desde)
                        print(f"   {desde}  {ref.getReferenceType()}  en {g.getName() if g else '(sin funcion)'}")
            elif accion == "asm":
                a = af.getAddress(args[0] if args[0].startswith("0x") else "0x" + args[0])
                n = int(args[1]) if len(args) > 1 else 40
                ins = listing.getInstructionAt(a) or listing.getInstructionAfter(a)
                for _ in range(n):
                    if ins is None:
                        break
                    print(f"   {ins.getAddress()}  {ins}")
                    ins = ins.getNext()
            elif accion == "buscar":
                patron = re.compile(args[0], re.I)
                for f in fm.getFunctions(True):
                    if patron.search(f.getName()):
                        print(f"   {f.getEntryPoint()}  {f.getName()}")
            else:
                print("accion desconocida:", accion)
    finally:
        proyecto.close()


if __name__ == "__main__":
    main()
