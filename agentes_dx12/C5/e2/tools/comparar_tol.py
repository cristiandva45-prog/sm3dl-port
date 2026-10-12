r"""Compara dos carpetas de capturas (PNG/BMP, lector de A: agentes_dx12\A\tools\comparar_capturas.py) con TOLERANCIA por
canal (GL vs D3D12: +-1 en caminos float). Por archivo: px distintos, px fuera de tolerancia, maximo.
Uso: py -I agentes_dx12\E2\tools\comparar_tol.py <carpetaA> <carpetaB> [--tol 1] [--umbral-px 0] [--esperar-diferencia]
  exit 0 si en todos los archivos comunes los px fuera de tolerancia <= umbral-px y no falta ninguno
  (con --esperar-diferencia: exit 0 solo si se detecta alguna diferencia fuera de tolerancia)."""
import importlib.util
import os
import sys

E2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("cmp_a", os.path.join(os.path.dirname(E2), "A", "tools", "comparar_capturas.py"))
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)


def main():
    a, b = sys.argv[1], sys.argv[2]
    tol = int(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 1
    umbral = int(sys.argv[sys.argv.index("--umbral-px") + 1]) if "--umbral-px" in sys.argv else 0
    esperar = "--esperar-diferencia" in sys.argv
    fa = {f for f in os.listdir(a) if f.lower().endswith((".png", ".bmp"))}
    fb = {f for f in os.listdir(b) if f.lower().endswith((".png", ".bmp"))}
    comunes = sorted(fa & fb)
    malos = 0
    for f in comunes:
        wa, ha, ba, da = ca.leer(os.path.join(a, f))
        wb, hb, bb, db = ca.leer(os.path.join(b, f))
        if (wa, ha, ba) != (wb, hb, bb):
            print("%-28s TAMANO distinto %dx%dx%d vs %dx%dx%d" % (f, wa, ha, ba, wb, hb, bb)); malos += 1; continue
        dist = fuera = maxd = 0
        for p in range(wa * ha):
            o = p * ba
            d = max(abs(da[o + k] - db[o + k]) for k in range(ba))
            if d:
                dist += 1
                maxd = max(maxd, d)
                if d > tol:
                    fuera += 1
        if fuera > umbral:
            malos += 1
        if dist:
            print("%-28s %7d px distintos, %7d fuera de +-%d (max %d)" % (f, dist, fuera, tol, maxd))
    solo = sorted(fa ^ fb)
    print("%d comunes, %d con px fuera de +-%d (umbral %d px), %d solo en una carpeta" % (len(comunes), malos, tol, umbral, len(solo)))
    if esperar:
        sys.exit(0 if malos and comunes else 1)   # sin nombres comunes NO hay deteccion (medido: 0 comunes daba falso verde)
    sys.exit(0 if malos == 0 and not solo and comunes else 1)


if __name__ == "__main__":
    main()
