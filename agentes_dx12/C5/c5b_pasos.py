"""C5b: diferencias por segmento (op 18 = lectura de la ventana 64x64) de e2.py pres_pasos_x2, gl_A vs d3d12_B.
Uso: py -I agentes_dx12\\C5\\c5b_pasos.py"""
import os
T = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\C5\e2\trabajo"
a = open(os.path.join(T, "pres_pasos_x2.gl_A.salida"), "rb").read()
b = open(os.path.join(T, "pres_pasos_x2.d3d12_B.salida"), "rb").read()
for l in open(os.path.join(T, "pres_pasos_x2.gl_A.salida.mapa")):
    c = l.split()
    if len(c) != 6:
        continue
    op, cod, ini, n = int(c[0]), int(c[1]), int(c[2]), int(c[3])
    if cod != 18:
        continue
    px = set()
    for k in range(ini, ini + n):
        if abs(a[k] - b[k]) > 1:
            px.add((k - ini) // 4)
    xs = sorted({p % 64 for p in px}); ys = sorted({p // 64 for p in px})
    print("op %d: %d px fuera; x=%s y=%s" % (op, len(px), xs[:20], ys[:20]))
