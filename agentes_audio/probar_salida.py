"""Prueba offline de la salida de audio (agente AU). Compila sim_salida.c con el audio_salida.c REAL y lo corre con un
seno de 1 kHz en el escenario "normal" (DSP 0,1 % lento + ticks en rafaga por el hilo del juego ocupado 5-25 ms/cuadro).
Verde = modo nuevo sin clics, sin huecos despues del cebado y latencia < 100 ms; el modo VIEJO debe mostrar el bug
(clics y ~200 ms) y el SABOTAJE (control de ritmo apagado) debe FALLAR.  Uso: py -I agentes_audio\probar_salida.py"""
import os, re, subprocess, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(AQUI, "sim_salida.exe")
cc = [sys.executable, "-m", "ziglang", "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
      os.path.join(AQUI, "sim_salida.c"), os.path.join(AQUI, "..", "recomp", "audio", "audio_salida.c"), "-o", EXE]
if subprocess.run(cc).returncode: sys.exit("no compila")

def correr(env_extra, nombre):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SM3DL_AUDIO")}
    env.update(env_extra)
    r = subprocess.run([EXE, "seno", os.path.join(AQUI, f"prueba_{nombre}.wav"), "normal", "60"], capture_output=True, text=True, env=env)
    linea = r.stdout.strip().splitlines()[-1]
    m = dict(re.findall(r"(\w+)=([-+\d.]+)", linea.replace("latencia media", "latencia_media")))
    print(f"{nombre:9s} {linea}")
    return float(m["clics_seno"]), float(m["huecos"]), float(m["latencia_media"])

def bueno(c, h, l): return c == 0 and h <= 45.0 and l < 100.0   # 45 ms = cebado inicial de 40 ms + redondeo
ok = True
c, h, l = correr({}, "nuevo");                              r = bueno(c, h, l); print("  nuevo   :", "OK" if r else "FALLA"); ok &= r
c, h, l = correr({"SM3DL_AUDIO_VIEJO": "1"}, "viejo");      r = not bueno(c, h, l); print("  viejo   :", "muestra el bug (OK)" if r else "NO muestra el bug"); ok &= r
c, h, l = correr({"SM3DL_AUDIO_SABOTAJE": "1"}, "sabotaje"); r = not bueno(c, h, l); print("  sabotaje:", "FALLA como debe (OK)" if r else "NO falla: la prueba no mira"); ok &= r
print("TODO VERDE" if ok else "HAY FALLOS"); sys.exit(0 if ok else 1)
