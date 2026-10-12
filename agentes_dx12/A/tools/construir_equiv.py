r"""Compila los dos arneses de equivalencia (sin correr nada): agentes_dx12\A\equiv_antes.exe (respaldos .antes_dx12_A)
y agentes_dx12\A\equiv_nuevo.exe (codigo nuevo). Uso (desde la raiz): py -I agentes_dx12\A\tools\construir_equiv.py"""
import subprocess, sys, os
RAIZ = os.getcwd()
A = os.path.join(RAIZ, "agentes_dx12", "A")
RD = os.path.join(RAIZ, "recomp", "render")
GD = os.path.join(RAIZ, "recomp", "gpu")
base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
        "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function"]
fuentes = [os.path.join(A, "prueba_equiv.c"), os.path.join(RD, "pica.c"), os.path.join(RD, "pica_dibujar.c"), os.path.join(RD, "texturas.c"),
           os.path.join(GD, "gsp.c")]
libs = ["-lopengl32", "-lgdi32", "-luser32"]
rc = 0
for nombre, extra in (("equiv_antes.exe", ["-DVERSION_ANTES", "-I", os.path.join(A, "antes")]), ("equiv_nuevo.exe", [])):
    cmd = base + extra + ["-I", RD, "-I", GD] + fuentes + libs + ["-o", os.path.join(A, nombre)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(nombre, "rc", r.returncode)
    if r.stdout.strip() or r.stderr.strip():
        print((r.stdout + r.stderr)[:3000])
    rc |= r.returncode
sys.exit(rc)
