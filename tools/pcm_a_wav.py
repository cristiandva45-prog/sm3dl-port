r"""Convierte el volcado crudo de SM3DL_WAV (s16 estéreo a 32.728 Hz) en .wav y resume dónde hay sonido.
Uso: py -I tools\pcm_a_wav.py <entrada.pcm> [salida.wav]"""
import array, math, sys, wave

FS = 32728
ent = sys.argv[1]
sal = sys.argv[2] if len(sys.argv) > 2 else ent.rsplit(".", 1)[0] + ".wav"
datos = open(ent, "rb").read()
datos = datos[: len(datos) // 4 * 4]
with wave.open(sal, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS); w.writeframes(datos)
m = array.array("h", datos)
n = len(m) // 2
print("%d muestras = %.2f s de audio -> %s" % (n, n / FS, sal))
# pico y RMS por segundo de audio
for s in range(0, n, FS):
    tramo = m[2 * s: 2 * min(n, s + FS)]
    pico = max((abs(v) for v in tramo), default=0)
    rms = math.sqrt(sum(v * v for v in tramo) / max(1, len(tramo)))
    print("  s%3d  pico=%5d  rms=%7.1f %s" % (s // FS, pico, rms, "#" * int(rms / 100)))
