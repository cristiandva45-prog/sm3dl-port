"""Compila y corre prueba_gsp.c: la version buena debe pasar y CADA sabotaje (-DSABOTAJE=n en gsp.c) debe fallar.
Uso:  py recomp\\gpu\\probar_gsp.py      (desde cualquier carpeta)"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SABOTAJES = {
    1: "Morton con x/y cambiados",
    2: "marca dirty ignorada (FrameBufferUpdate se aplica siempre)",
    3: "RGB565 con verde a 5 bits",
    4: "cola de relevo sin vuelta en 0x34",
    5: "heap lineal sin traducir a fisica",
    6: "volteo vertical del DisplayTransfer ignorado",
}


def compilar(n):
    exe = os.path.join(AQUI, "build", f"prueba_gsp_s{n}.exe")
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    cmd = [sys.executable, "-m", "ziglang", "cc", "-std=c11", "-O2", "-Wall", "-Wextra", f"-DSABOTAJE={n}",
           os.path.join(AQUI, "gsp.c"), os.path.join(AQUI, "prueba_gsp.c"), "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        print(r.stderr)
    if r.returncode != 0:
        sys.exit(f"no compila (SABOTAJE={n})")
    return exe


def correr(exe):
    r = subprocess.run([exe], capture_output=True, text=True)
    lineas = r.stdout.strip().splitlines()
    return r.returncode, lineas


def main():
    rc, lineas = correr(compilar(0))
    print("buena:", lineas[-1] if lineas else "(sin salida)")
    for l in lineas[:-1]:
        print("  ", l)
    ok = rc == 0
    detectados = 0
    for n, desc in SABOTAJES.items():
        rc_s, l_s = correr(compilar(n))
        fallas = [l for l in l_s if l.startswith("FALLA")]
        det = rc_s != 0 and fallas
        detectados += bool(det)
        print(f"sabotaje {n} ({desc}): {'DETECTADO' if det else 'NO DETECTADO'} - {len(fallas)} fallas"
              + (f", p. ej. {fallas[0][:110]}" if fallas else ""))
    print(f"resumen: buena {'OK' if ok else 'FALLA'}; sabotajes detectados {detectados}/{len(SABOTAJES)}")
    sys.exit(0 if ok and detectados == len(SABOTAJES) else 1)


if __name__ == "__main__":
    main()
