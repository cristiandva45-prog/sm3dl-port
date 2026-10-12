"""P2 (10 oct): compila y corre prueba_p2.c normal (debe dar BIEN) y con -DP2_SABOTAJE_SIN_SELLO (debe dar FALLA).
Uso: py -I agentes_dx12\\P2\\p2.py     (exit 0 si normal BIEN y sabotaje FALLA). Sin GPU, sin el juego, segundos."""
import os, subprocess, sys

P2 = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(P2))
RD = os.path.join(RAIZ, "recomp", "render")
GD = os.path.join(RAIZ, "recomp", "gpu")
TRAB = os.path.join(P2, "trabajo")


def construir(exe, extra):
    base = [sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-O2", "-g", "-ffp-contract=off",
            "-fno-strict-aliasing", "-msse2", "-Wall", "-Wno-unused-function", "-DSM3DL_CON_D3D12"] + extra
    fuentes = [os.path.join(P2, "prueba_p2.c")] + [os.path.join(RD, n) for n in (
        "pica.c", "pica_dibujar.c", "texturas.c", "texturas_hd.c", "interp.c", "d3d12_base.c", "d3d12_recursos.c",
        "d3d12_presentador.c")] + [os.path.join(GD, "gsp.c")]
    libs = ["-lopengl32", "-lgdi32", "-luser32", "-ld3d12", "-ldxgi", "-ldxguid", "-ld3dcompiler_47"]
    r = subprocess.run(base + ["-I", RD, "-I", GD] + fuentes + libs + ["-o", exe], capture_output=True, text=True)
    sal = (r.stdout + r.stderr).strip()
    print(os.path.basename(exe), "compila rc", r.returncode)
    if sal:
        print(sal[:4000])
    return r.returncode == 0


def correr(exe):
    os.makedirs(TRAB, exist_ok=True)
    p = subprocess.run([exe], capture_output=True, text=True, cwd=TRAB, timeout=60)
    print(p.stdout.strip())
    return p.returncode


ok = True
n = os.path.join(P2, "prueba_p2.exe")
s = os.path.join(P2, "prueba_p2_sabotaje.exe")
if construir(n, []) and construir(s, ["-DP2_SABOTAJE_SIN_SELLO"]):
    rn = correr(n)
    rs = correr(s)
    print("normal rc %d (esperado 0), sabotaje rc %d (esperado 1)" % (rn, rs))
    ok = rn == 0 and rs == 1
else:
    ok = False
print("P2:", "TODO COMO SE ESPERA" if ok else "NO")
sys.exit(0 if ok else 1)
