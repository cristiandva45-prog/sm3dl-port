# G1 (9 oct): rafagas de lo PRESENTADO (SM3DL_PRES_VIDEO) -> mp4 + PNG sueltos + cuantas imagenes cambian.
# Uso: py -I video.py <carpeta_raw> <salida.mp4> [rafaga=0] [--refresco]
#   --refresco: un cuadro de video POR REFRESCO (nombre r<refresco>): los refrescos sin presentacion nueva repiten la
#   imagen anterior, como se ve en el monitor; el video va a 144 cuadros/s. Sin eso: una imagen por presentacion, a 60.
import os, re, subprocess, sys

src, mp4 = sys.argv[1], sys.argv[2]
raf = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 0
por_refresco = '--refresco' in sys.argv
pat = re.compile(r'v%d_(\d+)_r(\d+)_(\d+)x(\d+)\.raw$' % raf)
fs = []
for n in os.listdir(src):
    m = pat.match(n)
    if m: fs.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), n))
fs.sort()
if not fs: sys.exit('sin capturas de la rafaga %d en %s' % (raf, src))
w, h = fs[0][2], fs[0][3]
datos = [open(os.path.join(src, f[4]), 'rb').read() for f in fs]

def distintos(a, b):   # pixeles (muestreo 1 de cada 7) con algun canal > 16 niveles distinto
    n = 0
    for i in range(0, len(a) - 3, 28):
        if abs(a[i] - b[i]) > 16 or abs(a[i + 1] - b[i + 1]) > 16 or abs(a[i + 2] - b[i + 2]) > 16: n += 1
    return n

total = len(a := datos[0]) // 28
iguales = 0
cambios = []
for k in range(1, len(datos)):
    d = distintos(datos[k - 1], datos[k])
    cambios.append(d)
    iguales += d == 0
print('%d presentaciones capturadas (%dx%d), %d IGUALES a la anterior (%.1f %%); px distintos (muestra de %d): media %.0f, max %d'
      % (len(datos), w, h, iguales, 100.0 * iguales / max(1, len(datos) - 1), total, sum(cambios) / max(1, len(cambios)), max(cambios or [0])))
# secuencia de video
sec = []
if por_refresco and fs[0][1] > 0:
    r0 = fs[0][1]
    for k, f in enumerate(fs):
        sig = fs[k + 1][1] if k + 1 < len(fs) else f[1] + 1
        sec += [k] * max(1, sig - f[1])
    print('refrescos cubiertos: %d (%d sin imagen nueva)' % (len(sec), len(sec) - len(fs)))
else:
    sec = list(range(len(fs)))
raw = mp4 + '.tmp.raw'
with open(raw, 'wb') as o:
    for k in sec: o.write(datos[k])
fps = '144' if por_refresco else '60'
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', '%dx%d' % (w, h), '-framerate', fps,
                '-i', raw, '-vf', 'vflip', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', mp4], check=True)
# PNG sueltos para mirar: 6 seguidos del medio + el primero y el ultimo
pngs = os.path.splitext(mp4)[0] + '_png'
os.makedirs(pngs, exist_ok=True)
mid = len(sec) // 2
for k in [0] + list(range(mid, min(mid + 6, len(sec)))) + [len(sec) - 1]:
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', '%dx%d' % (w, h), '-i', '-',
                    '-vf', 'vflip', '-frames:v', '1', os.path.join(pngs, 'c%04d.png' % k)], input=datos[sec[k]], check=True)
os.remove(raw)
print('video:', mp4, '| png:', pngs)
