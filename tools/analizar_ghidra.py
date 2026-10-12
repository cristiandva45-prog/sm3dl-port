"""Crea (o rehace) el proyecto Ghidra del port con la configuracion correcta.

- Procesador ARM:LE:32:v6 (ARM11 del 3DS), no el v8 que elige Ghidra solo.
- Apaga "Non-Returning Functions - Discovered": en este binario marco como
  'no regresa' getters triviales (p. ej. 0x00277248) y corto el codigo de
  ~90 funciones que los llaman.
- Importa extraido/code.elf (con los nombres de simbolos.txt ya dentro).

Uso (con el python del venv de pyghidra-mcp):
  C:\\tools\\pyghidra-mcp-venv\\Scripts\\python.exe -I analizar_ghidra.py <raiz_del_port>
El proyecto queda en <raiz>/ghidra/SM3DL.gpr. Si ya existe, se borra el programa y se rehace.
"""
import os
import sys
import time

os.environ.setdefault("GHIDRA_INSTALL_DIR", r"C:\tools\ghidra_12.1.4_PUBLIC")
os.environ.setdefault("JAVA_HOME", r"C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot")

import pyghidra  # noqa: E402

LENGUAJE = "ARM:LE:32:v6"
COMPILADOR = "default"
APAGAR = ["Non-Returning Functions - Discovered"]


def main():
    raiz = os.path.abspath(sys.argv[1])
    elf = os.path.join(raiz, "extraido", "code.elf")
    carpeta = os.path.join(raiz, "ghidra")
    os.makedirs(carpeta, exist_ok=True)

    pyghidra.start()
    from java.io import File
    from ghidra.program.model.lang import LanguageID, CompilerSpecID

    proyecto = pyghidra.open_project(carpeta, "SM3DL", create=True)
    try:
        datos = proyecto.getProjectData()
        viejo = datos.getFile("/code.elf")
        if viejo is not None:
            viejo.delete()

        monitor = pyghidra.task_monitor()
        cargador = (
            pyghidra.program_loader()
            .source(File(elf))
            .project(proyecto)
            .projectFolderPath("/")
            .language(LanguageID(LENGUAJE))
            .compiler(CompilerSpecID(COMPILADOR))
        )
        resultados = cargador.load()
        try:
            resultados.save(monitor)
            programa = resultados.getPrimaryDomainObject()

            opciones = pyghidra.analysis_properties(programa)
            with pyghidra.transaction(programa, "opciones"):
                for nombre in APAGAR:
                    opciones.setBoolean(nombre, False)

            t0 = time.time()
            print(f"analizando con {LENGUAJE}, sin {APAGAR} ...", flush=True)
            pyghidra.analyze(programa, monitor)
            print(f"analisis: {time.time() - t0:.0f} s", flush=True)

            fm = programa.getFunctionManager()
            total = fm.getFunctionCount()
            sin_retorno = [f for f in fm.getFunctions(True) if f.hasNoReturn()]
            print(f"funciones: {total}")
            print(f"marcadas 'no regresa': {len(sin_retorno)}")
            for f in sin_retorno[:40]:
                print(f"   {f.getEntryPoint()}  {f.getName()}")
            prueba = fm.getFunctionAt(programa.getAddressFactory().getAddress("0x00277248"))
            print(f"0x00277248 no regresa? {prueba.hasNoReturn() if prueba else 'sin funcion'}")
            programa.save("analisis inicial", monitor)
        finally:
            resultados.close()
    finally:
        proyecto.close()


if __name__ == "__main__":
    main()
