"""Colision de un nivel completo: coloca el .kcl de cada objeto del StageData en el mundo y exporta un OBJ.

Transformacion (verificada, ver reportes\\colision.md):
  v_mundo = pos + R * (escala * v_local)
  R = Rz(dir_z) * Ry(dir_y) * Rx(dir_x)   (grados; se aplica X primero, luego Y, luego Z; mano derecha, Y arriba)
  Unidades: las del KCL = las de pos_* (1 bloque = 100).

Uso:
  py -I nivel_colision.py <StageData.json> <romfs> <salida_dir> [--previa] [--orden ZYX]
  py -I nivel_colision.py --probar-orden <niveles_json_dir> <romfs>     # puntua los 6 ordenes de Euler
"""
import glob
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcl  # noqa: E402

ORDEN_DEFECTO = "ZYX"   # R = Rz*Ry*Rx
SECCIONES = None        # todas las listas de AllInfos


def mat_eje(eje, grados):
    r = math.radians(grados)
    c, s = math.cos(r), math.sin(r)
    if eje == "X":
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if eje == "Y":
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def mm(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def matriz(dx, dy, dz, orden=ORDEN_DEFECTO):
    """orden 'ZYX' => R = Rz*Ry*Rx (el ultimo de la cadena se aplica primero)."""
    ang = {"X": dx, "Y": dy, "Z": dz}
    R = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    for e in orden:
        R = mm(R, mat_eje(e, ang[e]))
    return R


def transformar(v, pos, R, esc):
    x, y, z = v[0] * esc[0], v[1] * esc[1], v[2] * esc[2]
    return (pos[0] + R[0][0] * x + R[0][1] * y + R[0][2] * z,
            pos[1] + R[1][0] * x + R[1][1] * y + R[1][2] * z,
            pos[2] + R[2][0] * x + R[2][1] * y + R[2][2] * z)


_cache = {}


def colision_de(nombre, romfs):
    """[(base, tris, attrs, filas)] del .kcl principal del objeto (el que se llama como el archivo) o None."""
    if nombre in _cache:
        return _cache[nombre]
    ruta = os.path.join(romfs, "ObjectData", nombre + ".szs")
    res = None
    if os.path.exists(ruta):
        try:
            piezas = kcl.piezas_de_szs(ruta)
        except Exception:  # noqa: BLE001
            piezas = []
        if piezas:
            prin = [p for p in piezas if p[0] == nombre] or piezas[:1]
            base, cab, tris, attrs, pa, filas = prin[0]
            res = (base, tris, attrs, filas, [p[0] for p in piezas])
    _cache[nombre] = res
    return res


def objetos(stage_json):
    d = json.load(open(stage_json, encoding="utf-8"))
    for seccion, lista in d["AllInfos"].items():
        if seccion in ("AreaObjInfo", "CameraAreaInfo"):
            continue
        for o in lista:
            yield seccion, o


def colocar(stage_json, romfs, orden=ORDEN_DEFECTO):
    """[(etiqueta, nombre, [tri_mundo], attrs, filas, o)]"""
    out = []
    for i, (sec, o) in enumerate(objetos(stage_json)):
        c = colision_de(o["name"], romfs)
        if not c:
            continue
        base, tris, attrs, filas, todas = c
        R = matriz(o["dir_x"], o["dir_y"], o["dir_z"], orden)
        pos = (o["pos_x"], o["pos_y"], o["pos_z"])
        esc = (o["scale_x"], o["scale_y"], o["scale_z"])
        tw = []
        for v1, v2, v3, _ in tris:
            a, b, cc = (transformar(v, pos, R, esc) for v in (v1, v2, v3))
            # escala negativa (espejo) invierte el orden de los vertices
            if esc[0] * esc[1] * esc[2] < 0:
                b, cc = cc, b
            tw.append((a, b, cc))
        etiqueta = f"{o['name']}_{o.get('l_id', i)}"
        out.append((etiqueta, o["name"], tw, attrs, filas, o))
    return out


def exportar_nivel(stage_json, romfs, salida, orden=ORDEN_DEFECTO, previa=False):
    nivel = os.path.basename(stage_json).split("__")[0]
    colocados = colocar(stage_json, romfs, orden)
    w = kcl.EscritorOBJ()
    tris_all, cols, anot = [], [], []
    for etiqueta, nombre, tw, attrs, filas, o in colocados:
        for t, at in zip(tw, attrs):
            fila = filas[at] if filas is not None and at < len(filas) else None
            m = kcl.clave_material(fila)
            w.tri(m, etiqueta, *t)
            tris_all.append(t)
            cols.append(kcl.color_material(m))
        if nombre not in ("BlockBrick", "TransparentWall", "WoodBox"):
            anot.append(((o["pos_x"], o["pos_y"], o["pos_z"]), nombre))
    os.makedirs(salida, exist_ok=True)
    nv, nf = w.guardar(os.path.join(salida, nivel + ".obj"))
    print(f"{nivel}: objetos con colision {len(colocados)}  verts {nv}  tris {nf}")
    if previa:
        import colision_previa
        d = os.path.join(salida, "_previas")
        os.makedirs(d, exist_ok=True)
        colision_previa.render(tris_all, os.path.join(d, nivel + ".png"), cols, titulo=nivel, W=1400, H=700,
                               anotaciones=anot)
        # sin los muros invisibles, para ver el recorrido
        sel = [(t, c) for (t, c, n) in zip(tris_all, cols, _nombres(colocados)) if n != "TransparentWall"]
        colision_previa.render([t for t, _ in sel], os.path.join(d, nivel + "_sin_muros.png"), [c for _, c in sel],
                               titulo=nivel + " (sin TransparentWall)", W=1400, H=700, anotaciones=anot)
    return colocados


def _nombres(colocados):
    for etiqueta, nombre, tw, attrs, filas, o in colocados:
        for _ in tw:
            yield nombre


# ------------------------------------------------------------------ prueba del orden de rotacion
def puntuar_orden(niveles_dir, romfs):
    """Para cada objeto con >=2 ejes de rotacion, cuenta cuantos de sus vertices caen (<=2 u) sobre
    vertices de OTROS objetos del mismo nivel. El orden correcto debe maximizarlo."""
    ordenes = ["ZYX", "XYZ", "YXZ", "YZX", "XZY", "ZXY"]
    tot = {o: [0, 0] for o in ordenes}
    detalle = defaultdict(dict)
    for f in sorted(glob.glob(os.path.join(niveles_dir, "*StageMap*__StageData.json"))):
        objs = [(s, o) for s, o in objetos(f) if colision_de(o["name"], romfs)]
        multi = [k for k, (s, o) in enumerate(objs)
                 if sum(1 for a in ("dir_x", "dir_y", "dir_z") if abs(o[a]) > 0.01) >= 2]
        if not multi:
            continue
        for orden in ordenes:
            mundo = []
            for s, o in objs:
                base, tris, attrs, filas, _ = colision_de(o["name"], romfs)
                R = matriz(o["dir_x"], o["dir_y"], o["dir_z"], orden)
                pos = (o["pos_x"], o["pos_y"], o["pos_z"])
                esc = (o["scale_x"], o["scale_y"], o["scale_z"])
                vs = set()
                for t in tris:
                    for v in t[:3]:
                        vs.add(transformar(v, pos, R, esc))
                mundo.append(list(vs))
            celdas = defaultdict(set)
            for k, vs in enumerate(mundo):
                for v in vs:
                    celdas[(round(v[0] / 2), round(v[1] / 2), round(v[2] / 2))].add(k)
            for k in multi:
                hit = 0
                for v in mundo[k]:
                    c = (round(v[0] / 2), round(v[1] / 2), round(v[2] / 2))
                    ok = False
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            for dz in (-1, 0, 1):
                                if celdas.get((c[0] + dx, c[1] + dy, c[2] + dz), set()) - {k}:
                                    ok = True
                    hit += ok
                tot[orden][0] += hit
                tot[orden][1] += len(mundo[k])
                nom = objs[k][1]["name"]
                detalle[(os.path.basename(f).split("__")[0], nom, k)][orden] = hit
    return tot, detalle


def main():
    a = sys.argv[1:]
    if a and a[0] == "--probar-orden":
        tot, det = puntuar_orden(a[1], a[2])
        for o, (h, n) in sorted(tot.items(), key=lambda x: -x[1][0]):
            print(f"{o}: {h}/{n} vertices coinciden con otra pieza")
        print("objetos donde el orden cambia el resultado:")
        for k, d in det.items():
            if len(set(d.values())) > 1:
                print(" ", k, d)
        return
    if len(a) >= 3:
        orden = a[a.index("--orden") + 1] if "--orden" in a else ORDEN_DEFECTO
        exportar_nivel(a[0], a[1], a[2], orden, previa="--previa" in a)
        return
    print(__doc__)


if __name__ == "__main__":
    main()
