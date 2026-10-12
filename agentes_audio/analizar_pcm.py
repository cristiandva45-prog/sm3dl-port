"""Analiza un PCM s16 estereo (32.728 Hz) crudo: recortes, clics por frontera de frame de 160, silencios.
Uso: py -I analizar_pcm.py <archivo.pcm|.wav> [fs]"""
import sys, array, math
ruta = sys.argv[1]; fs = float(sys.argv[2]) if len(sys.argv) > 2 else 32728.0
datos = open(ruta, 'rb').read()
if datos[:4] == b'RIFF':
    i = datos.find(b'data'); datos = datos[i + 8:]
a = array.array('h'); a.frombytes(datos[:len(datos) // 4 * 4])
L = a[0::2]; R = a[1::2]; n = len(L)
print(f"muestras={n} ({n/fs:.1f} s)")
for nom, c in (("L", L), ("R", R)):
    pico = max(abs(x) for x in c); rms = math.sqrt(sum(x * x for x in c) / n)
    rec = sum(1 for x in c if x >= 32767 or x <= -32768)
    # rachas de recorte (>=2 seguidas = aplanado)
    rach = 0; r = 0
    for x in c:
        if x >= 32767 or x <= -32768: r += 1
        else:
            if r >= 2: rach += 1
            r = 0
    # clic: |segunda diferencia| grande; contar por fase dentro del frame de 160
    fase = [0] * 160; tot = 0
    umbral = 6000
    for i in range(2, n):
        d2 = c[i] - 2 * c[i - 1] + c[i - 2]
        if abs(d2) > umbral: fase[i % 160] += 1; tot += 1
    top = sorted(range(160), key=lambda k: -fase[k])[:5]
    print(f"{nom}: pico={pico} rms={rms:.0f} recortadas={rec} ({100*rec/n:.3f}%) rachas>=2={rach} "
          f"saltos|d2|>{umbral}={tot} fases_top={[(k, fase[k]) for k in top]}")
corr = sum(L[i] * R[i] for i in range(n)) / (math.sqrt(sum(x*x for x in L) * sum(x*x for x in R)) or 1)
print(f"correlacion L/R={corr:.3f}  diferencia media |L-R|={sum(abs(L[i]-R[i]) for i in range(n))/n:.0f}")
