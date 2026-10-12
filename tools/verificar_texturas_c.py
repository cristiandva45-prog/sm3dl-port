"""Compara byte a byte el decodificador de texturas en C (recomp\\render\\texturas.c) contra el de Python
(tools\\texturas.py) sobre texturas reales del juego: hasta K por formato, las mas chicas de cada uno.

Uso: py -I tools\\verificar_texturas_c.py [--exe recomp\\render\\texdec.exe] [-k 4] [--archivos 400]
Sale con 1 si alguna no coincide (usar --exe recomp\\render\\texdec_sabotaje.exe para VER el fallo).
"""
import os
import struct
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(RAIZ, "tools"))  # al final: tools\dis.py taparia el modulo estandar 'dis'
import szs  # noqa: E402
import texturas  # noqa: E402


def cgfx_de(ruta):
    d = open(ruta, "rb").read()
    if d[:4] == b"Yaz0":
        d = szs.yaz0(d)
    if d[:4] == b"CGFX":
        yield d
        return
    try:
        cont = szs.sarc(d)
    except Exception:
        return
    for _, b in (cont.items() if isinstance(cont, dict) else cont):
        if b[:4] == b"CGFX":
            yield b


def main():
    a = sys.argv[1:]
    exe = a[a.index("--exe") + 1] if "--exe" in a else os.path.join(RAIZ, "recomp", "render", "texdec.exe")
    k = int(a[a.index("-k") + 1]) if "-k" in a else 4
    max_arch = int(a[a.index("--archivos") + 1]) if "--archivos" in a else 400
    candidatas = {}  # fmt -> [(pixeles, nombre, ancho, alto, datos)]
    raiz = os.path.join(RAIZ, "extraido", "romfs")
    rutas = []
    for d, _, fs in os.walk(raiz):
        rutas += [os.path.join(d, f) for f in fs if f.endswith((".szs", ".bcmdl", ".bcres"))]
    rutas.sort()
    paso = max(1, len(rutas) // max_arch)
    for ruta in rutas[::paso]:
        for b in cgfx_de(ruta):
            try:
                tx = texturas.texturas_de(b)
            except Exception:
                continue
            for nom, w, h, fmt, datos in tx:
                if datos is None or fmt not in texturas.FORMATOS:
                    continue
                if len(datos) < w * h * texturas.FORMATOS[fmt][1] // 8:
                    continue
                candidatas.setdefault(fmt, []).append((w * h, f"{os.path.basename(ruta)}:{nom}", w, h, datos))
    # 7 oct: las texturas de los LAYOUTS (BCLIM) traen los formatos que en los modelos no salen (A4, A8, LA4...):
    # sin esto la verificacion cubria 6 de 14 y no vio el blanco de A4/A8. El formato de BCLIM tiene OTRA numeracion.
    BCLIM_A_PICA = {0: 7, 1: 8, 2: 9, 3: 5, 4: 6, 5: 3, 6: 1, 7: 2, 8: 4, 9: 0, 10: 12, 11: 13, 12: 10, 13: 11}
    for d, _, fs in os.walk(os.path.join(raiz, "LayoutData")):
        for f in sorted(fs)[:max_arch]:
            if not f.endswith(".szs"):
                continue
            b = open(os.path.join(d, f), "rb").read()
            if b[:4] == b"Yaz0":
                b = szs.yaz0(b)
            try:
                cont = szs.sarc(b)
            except Exception:
                continue
            for nom, c in cont:
                i = c.rfind(b"imag")
                if not nom.endswith(".bclim") or i < 0:
                    continue
                w, h, fb = struct.unpack_from("<HHI", c, i + 8)
                fmt = BCLIM_A_PICA.get(fb)
                if fmt is None:
                    continue
                n = w * h * texturas.FORMATOS[fmt][1] // 8
                if len(c) - 0x28 < n:
                    continue
                candidatas.setdefault(fmt, []).append((w * h, f"{f}:{nom}", w, h, c[:n]))
    total = ok = 0
    tmp = tempfile.mkdtemp()
    for fmt in sorted(candidatas):
        lista = sorted(candidatas[fmt], key=lambda t: t[0])
        # las mas chicas y alguna grande, sin repetir tamano
        elegidas = lista[:k - 1] + lista[-1:] if len(lista) >= k else lista
        bien = 0
        for _, nom, w, h, datos in elegidas:
            esperado = texturas.decodificar(datos, w, h, fmt).convert("RGBA").tobytes()
            ent, sal = os.path.join(tmp, "e.bin"), os.path.join(tmp, "s.bin")
            open(ent, "wb").write(struct.pack("<3I", w, h, fmt) + datos)
            r = subprocess.run([exe, ent, sal])
            obtenido = open(sal, "rb").read() if r.returncode == 0 and os.path.exists(sal) else b""
            if os.path.exists(sal):
                os.remove(sal)
            total += 1
            if obtenido == esperado:
                bien += 1
            else:
                dif = sum(1 for x, y in zip(obtenido, esperado) if x != y) if obtenido else -1
                print(f"  FALLA {nom} {w}x{h}: {dif} bytes distintos (salida C {len(obtenido)} B, rc={r.returncode})")
        ok += bien
        print(f"{texturas.FORMATOS[fmt][0]:9s}: {bien}/{len(elegidas)} iguales  (en el juego: {len(lista)} en la muestra)")
    print(f"TOTAL: {ok}/{total}  | formatos presentes: {len(candidatas)} de 14")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
