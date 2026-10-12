"""Aplica extraido/simbolos.txt al proyecto Ghidra del port, sin re-analizar.

Por cada linea '0xDIRECCION nombre  # comentario':
  - crea la funcion si no existe y le pone el nombre,
  - si hay comentario, lo deja como comentario de cabecera (plate).

El proyecto no puede estar abierto en otro proceso (cerrar el MCP que lo use).
Uso: C:\\tools\\pyghidra-mcp-venv\\Scripts\\python.exe -I aplicar_simbolos.py <raiz_del_port>
"""
import os
import sys

os.environ.setdefault("GHIDRA_INSTALL_DIR", r"C:\tools\ghidra_12.1.4_PUBLIC")
os.environ.setdefault("JAVA_HOME", r"C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot")

import pyghidra  # noqa: E402


def leer_simbolos(ruta):
    out = []
    for linea in open(ruta, encoding="utf-8"):
        cuerpo, _, comentario = linea.partition("#")
        partes = cuerpo.split()
        if len(partes) == 2:
            out.append((int(partes[0], 16), partes[1], comentario.strip()))
    return out


def main():
    raiz = os.path.abspath(sys.argv[1])
    simbolos = leer_simbolos(os.path.join(raiz, "extraido", "simbolos.txt"))
    pyghidra.start()
    from ghidra.app.cmd.function import CreateFunctionCmd
    from ghidra.program.model.listing import CodeUnit
    from ghidra.program.model.symbol import SourceType

    proyecto = pyghidra.open_project(os.path.join(raiz, "ghidra"), "SM3DL")
    try:
        with pyghidra.program_context(proyecto, "/code.elf") as programa:
            fm = programa.getFunctionManager()
            af = programa.getAddressFactory()
            listing = programa.getListing()
            monitor = pyghidra.task_monitor()
            renombradas = creadas = comentarios = 0
            with pyghidra.transaction(programa, "aplicar simbolos.txt"):
                st = programa.getSymbolTable()
                bloque_text = programa.getMemory().getBlock(".text")
                for direccion, nombre, comentario in simbolos:
                    addr = af.getAddress(f"0x{direccion:08x}")
                    if not bloque_text.contains(addr):
                        # datos (vtables, tablas): etiqueta, no funcion
                        actual = st.getPrimarySymbol(addr)
                        if actual is None or actual.getName() != nombre:
                            st.createLabel(addr, nombre, SourceType.USER_DEFINED).setPrimary()
                            renombradas += 1
                        if comentario:
                            listing.setComment(addr, CodeUnit.PLATE_COMMENT, comentario)
                            comentarios += 1
                        continue
                    f = fm.getFunctionAt(addr)
                    if f is None:
                        CreateFunctionCmd(addr).applyTo(programa, monitor)
                        f = fm.getFunctionAt(addr)
                        creadas += f is not None
                    if f is None:
                        print(f"  no se pudo crear funcion en {addr} ({nombre})")
                        continue
                    if f.getName() != nombre:
                        f.setName(nombre, SourceType.USER_DEFINED)
                        renombradas += 1
                    if comentario:
                        listing.getCodeUnitAt(addr).setComment(CodeUnit.PLATE_COMMENT, comentario)
                        comentarios += 1
            programa.save("aplicar simbolos.txt", monitor)
            print(f"simbolos: {len(simbolos)}  renombradas: {renombradas}  creadas: {creadas}  comentarios: {comentarios}")
    finally:
        proyecto.close()


if __name__ == "__main__":
    main()
