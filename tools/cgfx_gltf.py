"""Convierte modelos CGFX (.bcmdl, NW4C/CTR) a glTF 2.0 (.gltf + .bin).

Soporta: geometria de cada shape (posicion con escala del atributo + position offset,
normales, UV0 con la matriz del coordinador (V sin invertir, ver nota), color de vertice), indices
u8/u16 (triangulos y tiras), materiales con su textura base (PNG ya volcado por
texturas.py), esqueleto (jerarquia + TRS + inverse bind) y skinning (paleta de huesos
por face group, modos ninguno/rigido/suave).

Uso:
  py -I cgfx_gltf.py <archivo.szs|.bcmdl> <carpeta_salida> [--previa]
  py -I cgfx_gltf.py --todo <carpeta_romfs> <carpeta_salida> [--previa]
  py -I cgfx_gltf.py --previa-de <archivo.gltf> <salida.png>

Estructuras verificadas contra los bytes (offsets relativos al inicio de cada objeto):
  CMDL  +0xB4 n/ptr-tabla mallas, +0xBC n/DICT materiales, +0xC4 n/ptr-tabla shapes,
        +0xE0 ptr esqueleto (si flags & 0x80). Ver reportes/modelos.md.
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cgfx  # noqa: E402
import szs  # noqa: E402

u32 = cgfx.u32
rel = cgfx.rel
cadena = cgfx.cadena

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURAS_PNG = os.path.join(RAIZ, "extraido", "texturas_png")

# Nombres de atributo PICA
POS, NRM, TAN, COL, UV0, UV1, UV2, BIDX, BWGT = range(9)
# Tipos GL -> (struct, bytes)
TIPOS = {0x1400: ("b", 1), 0x1401: ("B", 1), 0x1402: ("h", 2), 0x1403: ("H", 2), 0x1406: ("f", 4)}


def f32(d, o, n=1):
    return struct.unpack_from("<%df" % n, d, o)


def ptabla(d, o_cuenta):
    """(cuenta, offset rel a tabla de offsets rel) -> lista de offsets absolutos."""
    n = u32(d, o_cuenta)
    t = rel(d, o_cuenta + 4)
    return [rel(d, t + 4 * i) for i in range(n)] if t else []


# ---------------------------------------------------------------- matrices 3x4 (filas)
def m34(d, o):
    v = f32(d, o, 12)
    return [list(v[0:4]), list(v[4:8]), list(v[8:12])]


def mul34(a, b):
    r = [[0.0] * 4 for _ in range(3)]
    for i in range(3):
        for j in range(4):
            r[i][j] = sum(a[i][k] * b[k][j] for k in range(3)) + (a[i][3] if j == 3 else 0.0)
    return r


def inv34(m):
    a, b, c = m[0][:3], m[1][:3], m[2][:3]
    det = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])
    if abs(det) < 1e-12:
        det = 1e-12
    inv = [[(b[1] * c[2] - b[2] * c[1]) / det, (a[2] * c[1] - a[1] * c[2]) / det, (a[1] * b[2] - a[2] * b[1]) / det],
           [(b[2] * c[0] - b[0] * c[2]) / det, (a[0] * c[2] - a[2] * c[0]) / det, (a[2] * b[0] - a[0] * b[2]) / det],
           [(b[0] * c[1] - b[1] * c[0]) / det, (a[1] * c[0] - a[0] * c[1]) / det, (a[0] * b[1] - a[1] * b[0]) / det]]
    t = [m[0][3], m[1][3], m[2][3]]
    return [inv[i] + [-sum(inv[i][k] * t[k] for k in range(3))] for i in range(3)]


def aplicar(m, p, w=1.0):
    return [m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] * w for i in range(3)]


def trs34(s, r, t):
    """Matriz local = T * Rz * Ry * Rx * S (convencion CGFX, euler XYZ en radianes)."""
    cx, sx, cy, sy, cz, sz = math.cos(r[0]), math.sin(r[0]), math.cos(r[1]), math.sin(r[1]), math.cos(r[2]), math.sin(r[2])
    rm = [[cy * cz, cz * sx * sy - cx * sz, cx * cz * sy + sx * sz],
          [cy * sz, cx * cz + sx * sy * sz, cx * sy * sz - cz * sx],
          [-sy, cy * sx, cx * cy]]
    return [[rm[i][0] * s[0], rm[i][1] * s[1], rm[i][2] * s[2], t[i]] for i in range(3)]


def quat_xyz(r):
    """Cuaternion (x,y,z,w) de Rz*Ry*Rx."""
    hx, hy, hz = r[0] / 2, r[1] / 2, r[2] / 2
    cx, sx, cy, sy, cz, sz = math.cos(hx), math.sin(hx), math.cos(hy), math.sin(hy), math.cos(hz), math.sin(hz)
    return [sx * cy * cz - cx * sy * sz, cx * sy * cz + sx * cy * sz, cx * cy * sz - sx * sy * cz, cx * cy * cz + sx * sy * sz]


def col4x4(m):
    """3x4 por filas -> lista 16 column-major para glTF."""
    return [m[0][0], m[1][0], m[2][0], 0.0, m[0][1], m[1][1], m[2][1], 0.0,
            m[0][2], m[1][2], m[2][2], 0.0, m[0][3], m[1][3], m[2][3], 1.0]


# ---------------------------------------------------------------- lectura CGFX
def leer_esqueleto(d, sk):
    """SOBJ tipo 0x02000000. +0x18 n huesos, +0x1C DICT. Hueso (0xE0 bytes):
    +0 nombre, +4 flags, +8 id, +0xC id padre (s32), +0x20 escala, +0x2C rot XYZ,
    +0x38 traslacion, +0x44 local 3x4, +0x74 world 3x4, +0xA4 inverse world 3x4."""
    huesos = []
    for nombre, o in cgfx.diccionario(d, rel(d, sk + 0x1C)):
        huesos.append({
            "nombre": nombre, "id": u32(d, o + 8), "padre": struct.unpack_from("<i", d, o + 0xC)[0],
            "s": list(f32(d, o + 0x20, 3)), "r": list(f32(d, o + 0x2C, 3)), "t": list(f32(d, o + 0x38, 3)),
            "local_arch": m34(d, o + 0x44), "world_arch": m34(d, o + 0x74),
        })
    huesos.sort(key=lambda h: h["id"])
    assert [h["id"] for h in huesos] == list(range(len(huesos))), "ids de hueso no consecutivos"
    for h in huesos:
        h["local"] = trs34(h["s"], h["r"], h["t"])
    for h in huesos:  # padres siempre antes (verificado: id padre < id)
        h["world"] = h["local"] if h["padre"] < 0 else mul34(huesos[h["padre"]]["world"], h["local"])
    return huesos


def leer_atributo(d, a, nverts_hint=None, base=None, stride=None):
    """Atributo de vertice. Devuelve dict con uso, formato, elementos, escala y lector."""
    tipo = u32(d, a)
    uso = u32(d, a + 4)
    if tipo == 0x80000000:  # atributo fijo: +0xC formato, +0x10 elementos, +0x18 n valores, +0x1C ptr floats
        n = u32(d, a + 0x18)
        vals = list(f32(d, rel(d, a + 0x1C), n)) if n else []
        return {"uso": uso, "fijo": vals}
    # 0x40000001: +0x14 largo, +0x18 ptr datos, +0x24 formato, +0x28 elementos, +0x2C escala, +0x30 offset en vertice
    fmt, elem, esc, off = u32(d, a + 0x24), u32(d, a + 0x28), f32(d, a + 0x2C)[0], u32(d, a + 0x30)
    if base is None:  # flujo propio, no entrelazado
        base = rel(d, a + 0x18)
        stride = elem * TIPOS[fmt][1]
        off = 0
        nv = u32(d, a + 0x14) // stride
    else:
        nv = nverts_hint
    return {"uso": uso, "fmt": fmt, "elem": elem, "esc": esc, "base": base + off, "stride": stride, "nv": nv}


def valores(d, at, i):
    c, tam = TIPOS[at["fmt"]]
    v = struct.unpack_from("<%d%s" % (at["elem"], c), d, at["base"] + at["stride"] * i)
    return [x * at["esc"] for x in v] if at["esc"] not in (0.0, 1.0) else list(v)


def leer_shape(d, s):
    """SOBJ tipo 0x10000001. +0x20 position offset, +0x2C/+0x30 face groups, +0x38/+0x3C vertex buffers."""
    shape = {"offset": list(f32(d, s + 0x20, 3)), "attrs": {}, "fijos": {}, "nv": 0, "grupos": []}
    for vb in ptabla(d, s + 0x38):
        t = u32(d, vb)
        if t == 0x40000002:  # entrelazado: +0x14 largo, +0x18 datos, +0x24 stride, +0x28/+0x2C atributos
            base, stride = rel(d, vb + 0x18), u32(d, vb + 0x24)
            nv = u32(d, vb + 0x14) // stride
            shape["nv"] = max(shape["nv"], nv)
            for a in ptabla(d, vb + 0x28):
                at = leer_atributo(d, a, nv, base, stride)
                if "fijo" in at:
                    shape["fijos"][at["uso"]] = at["fijo"]
                else:
                    shape["attrs"][at["uso"]] = at
        else:
            at = leer_atributo(d, vb)
            if "fijo" in at:
                shape["fijos"][at["uso"]] = at["fijo"]
            else:
                shape["attrs"][at["uso"]] = at
                shape["nv"] = max(shape["nv"], at["nv"])
    for fg in ptabla(d, s + 0x2C):
        # face group: +0 n huesos, +4 ptr u32[], +8 modo skinning (0 ninguno, 1 rigido, 2 suave), +0xC/+0x10 primitivas
        nb = u32(d, fg)
        pb = rel(d, fg + 4)
        paleta = [u32(d, pb + 4 * i) for i in range(nb)]
        modo = u32(d, fg + 8)
        tris = []
        for pr in ptabla(d, fg + 0xC):
            for ix in ptabla(d, pr):  # index stream: +0 formato, +4 modo primitiva, +8 largo, +0xC ptr
                fmt, modo_p, largo, p = u32(d, ix), d[ix + 4], u32(d, ix + 8), rel(d, ix + 0xC)
                c, tam = TIPOS[fmt]
                idx = list(struct.unpack_from("<%d%s" % (largo // tam, c), d, p))
                if modo_p == 0:
                    tris += idx[:len(idx) // 3 * 3]
                elif modo_p == 1:  # tira
                    for k in range(len(idx) - 2):
                        a, b, cc = idx[k], idx[k + 1], idx[k + 2]
                        if a != b and b != cc and a != cc:
                            tris += [a, b, cc] if k % 2 == 0 else [b, a, cc]
                else:  # abanico
                    for k in range(1, len(idx) - 1):
                        tris += [idx[0], idx[k], idx[k + 1]]
        shape["grupos"].append({"paleta": paleta, "modo": modo, "tris": tris})
    return shape


def leer_material(d, mo):
    """MTOB: +0x168 n coordinadores, +0x16C coordinadores (0x58 c/u: fuente, mapeo, camara,
    tipo transf., escala, rot, trasl., flags, matriz 3x4 en +0x28), +0x274 mappers[3]."""
    mat = {"textura": None, "envolver": (10497, 10497), "mapeo": 0, "uvmat": None}
    mp = rel(d, mo + 0x274)
    if not mp or u32(d, mp) != 0x80000000:
        return mat
    tx = rel(d, mp + 8)
    if tx and d[tx + 4:tx + 8] == b"TXOB":
        mat["textura"] = cadena(d, rel(d, tx + 0x18)) if u32(d, tx) == 0x20000004 else cadena(d, rel(d, tx + 0xC))
    if u32(d, mp + 0x1C) == 0x809F0081:  # comando PICA a TEXUNIT0 (0x81..): +0x24 = TEXUNIT0_PARAM
        param = u32(d, mp + 0x24)
        gl = {0: 33071, 1: 33071, 2: 10497, 3: 33648}
        mat["envolver"] = (gl.get((param >> 12) & 7, 10497), gl.get((param >> 8) & 7, 10497))
    if u32(d, mo + 0x168):
        c = mo + 0x16C
        mat["mapeo"] = u32(d, c + 4)
        mat["uv_fuente"] = u32(d, c)
        m = m34(d, c + 0x28)
        if m != [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]:
            mat["uvmat"] = m
    return mat


def leer_modelo(d, o):
    flags = u32(d, o)
    mallas = []
    for m in ptabla(d, o + 0xB4):  # malla SOBJ 0x01000000: +0x18 shape, +0x1C material, +0x24 visible
        mallas.append({"shape": u32(d, m + 0x18), "material": u32(d, m + 0x1C), "visible": d[m + 0x24],
                       "nombre": cadena(d, rel(d, m + 0xC))})
    materiales = [(n, leer_material(d, mo)) for n, mo in cgfx.diccionario(d, rel(d, o + 0xC0))]
    shapes = [leer_shape(d, s) for s in ptabla(d, o + 0xC4)]
    huesos = []
    if flags & 0x80:
        sk = rel(d, o + 0xE0)
        if sk and u32(d, sk) == 0x02000000 and d[sk + 4:sk + 8] == b"SOBJ":
            huesos = leer_esqueleto(d, sk)
    return {"mallas": mallas, "materiales": materiales, "shapes": shapes, "huesos": huesos}


# ---------------------------------------------------------------- glTF
class Bin:
    def __init__(self):
        self.datos = bytearray()
        self.vistas, self.accesores = [], []

    def agregar(self, fmt, lista, comp, tipo, n, objetivo=None, minmax=False, normalizado=False):
        while len(self.datos) % 4:
            self.datos.append(0)
        ini = len(self.datos)
        self.datos += struct.pack("<%d%s" % (len(lista), fmt), *lista)
        vista = {"buffer": 0, "byteOffset": ini, "byteLength": len(self.datos) - ini}
        if objetivo:
            vista["target"] = objetivo
        self.vistas.append(vista)
        acc = {"bufferView": len(self.vistas) - 1, "componentType": comp, "count": n, "type": tipo}
        if normalizado:
            acc["normalized"] = True
        if minmax:  # min/max sobre los valores ya redondeados a float32 (lo que leera el visor)
            lista = struct.unpack_from("<%d%s" % (len(lista), fmt), self.datos, ini)
            k = {"VEC3": 3, "VEC2": 2, "SCALAR": 1}[tipo]
            acc["min"] = [min(lista[i::k]) for i in range(k)]
            acc["max"] = [max(lista[i::k]) for i in range(k)]
        self.accesores.append(acc)
        return len(self.accesores) - 1


_indice_png = None


def buscar_png(textura, carpeta_szs):
    global _indice_png
    p = os.path.join(TEXTURAS_PNG, carpeta_szs, textura + ".png")
    if os.path.exists(p):
        return p
    if _indice_png is None:
        _indice_png = {}
        if os.path.isdir(TEXTURAS_PNG):
            for c in sorted(os.listdir(TEXTURAS_PNG)):
                cp = os.path.join(TEXTURAS_PNG, c)
                if os.path.isdir(cp):
                    for f in os.listdir(cp):
                        _indice_png.setdefault(f[:-4], os.path.join(cp, f))
    return _indice_png.get(textura)


def convertir(mod, nombre, carpeta_szs, dir_salida):
    """Arma el glTF de un modelo leido. Devuelve (ruta .gltf, estadisticas)."""
    huesos = mod["huesos"]
    b = Bin()
    g = {"asset": {"version": "2.0", "generator": "sm3dl-port cgfx_gltf.py"}, "scene": 0,
         "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "accessors": b.accesores,
         "bufferViews": b.vistas, "buffers": []}
    est = {"tris": 0, "verts": 0, "primitivas": 0, "huesos": len(huesos), "sin_textura": []}

    # materiales
    imagenes, texturas, muestreadores = {}, [], {}
    g_mats = []
    for mn, m in mod["materiales"]:
        gm = {"name": mn, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0,
                                                   "roughnessFactor": 1.0}, "doubleSided": False}
        png = buscar_png(m["textura"], carpeta_szs) if m["textura"] else None
        if m["textura"] and not png:
            est["sin_textura"].append(m["textura"])
        if png:
            if m["mapeo"] != 0:
                # mapa de entorno (esfera/cubo): no expresable en glTF; color medio de la textura
                gm["pbrMetallicRoughness"]["baseColorFactor"] = color_medio(png)
                gm["extras"] = {"textura_entorno": m["textura"]}
            else:
                if png not in imagenes:
                    uri = os.path.relpath(png, dir_salida).replace(os.sep, "/")
                    imagenes[png] = len(imagenes)
                    g.setdefault("images", []).append({"uri": uri.replace(" ", "%20"), "name": m["textura"]})
                clave = m["envolver"]
                if clave not in muestreadores:
                    muestreadores[clave] = len(muestreadores)
                    g.setdefault("samplers", []).append({"magFilter": 9729, "minFilter": 9729,
                                                         "wrapS": clave[0], "wrapT": clave[1]})
                texturas.append({"source": imagenes[png], "sampler": muestreadores[clave]})
                gm["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(texturas) - 1}
                if tiene_alfa(png):
                    gm["alphaMode"] = "MASK"
                    gm["alphaCutoff"] = 0.5
        g_mats.append(gm)
    g["materials"] = g_mats
    if texturas:
        g["textures"] = texturas

    # nodos de huesos
    base_huesos = 0
    if huesos:
        for h in huesos:
            nodo = {"name": h["nombre"], "translation": h["t"], "rotation": quat_xyz(h["r"]), "scale": h["s"]}
            hijos = [x["id"] for x in huesos if x["padre"] == h["id"]]
            if hijos:
                nodo["children"] = hijos
            g["nodes"].append(nodo)
        g["scenes"][0]["nodes"] += [h["id"] for h in huesos if h["padre"] < 0]
        ibm = []
        for h in huesos:
            ibm += col4x4(inv34(h["world"]))
        acc_ibm = b.agregar("f", ibm, 5126, "MAT4", len(huesos))
        g["skins"] = [{"joints": list(range(len(huesos))), "inverseBindMatrices": acc_ibm, "skeleton":
                       [h["id"] for h in huesos if h["padre"] < 0][0]}]

    # geometria: una primitiva glTF por face group de cada malla
    prims = []
    for malla in mod["mallas"]:
        sh = mod["shapes"][malla["shape"]]
        mat = mod["materiales"][malla["material"]][1] if malla["material"] < len(mod["materiales"]) else None
        A = sh["attrs"]
        if POS not in A:
            continue
        for grupo in sh["grupos"]:
            tris = [i for i in grupo["tris"]]
            if not tris:
                continue
            usados = sorted(set(tris))
            if usados[-1] >= sh["nv"]:
                raise ValueError("indice %d >= %d vertices" % (usados[-1], sh["nv"]))
            remap = {v: i for i, v in enumerate(usados)}
            pos, nrm, uv, col, jnt, wgt = [], [], [], [], [], []
            paleta = grupo["paleta"]
            for v in usados:
                p = valores(_d, A[POS], v)
                p = [p[0] + sh["offset"][0], p[1] + sh["offset"][1], p[2] + sh["offset"][2]]
                n = valores(_d, A[NRM], v) if NRM in A else None
                # huesos/pesos del vertice (indices a la paleta del face group)
                if BIDX in A:
                    bi = [int(x) for x in valores(_d, A[BIDX], v)]
                elif BIDX in sh["fijos"]:
                    bi = [int(x) for x in sh["fijos"][BIDX]]
                else:
                    bi = [0]
                if BWGT in A:
                    bw = valores(_d, A[BWGT], v)
                elif BWGT in sh["fijos"]:
                    bw = list(sh["fijos"][BWGT])
                else:
                    bw = [1.0]
                if grupo["modo"] != 2:  # ninguno/rigido: un hueso, vertice en espacio local del hueso
                    bi, bw = bi[:1], [1.0]
                    if huesos and paleta:
                        w = huesos[paleta[bi[0]]]["world"]
                        p = aplicar(w, p)
                        if n:
                            n = aplicar(w, n, 0.0)
                gb = [paleta[i] if i < len(paleta) else 0 for i in bi]
                pos += p
                if n:
                    ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
                    nrm += [n[0] / ln, n[1] / ln, n[2] / ln]
                if UV0 in A:
                    t = valores(_d, A[UV0], v)
                    if mat and mat.get("uvmat"):
                        m = mat["uvmat"]
                        t = [m[0][0] * t[0] + m[0][1] * t[1] + m[0][3], m[1][0] * t[0] + m[1][1] * t[1] + m[1][3]]
                    # SIN invertir V: los PNG de texturas.py ya salen volteados (FLIP_TOP_BOTTOM), asi que
                    # la V del 3DS coincide con la de glTF. Verificado en la previa de Mario (1-v lo deja al reves).
                    uv += [t[0], t[1]]
                if COL in A:
                    c = valores(_d, A[COL], v)
                    col += (c + [1.0] * 4)[:4]
                if huesos:
                    pares = sorted(zip(bw, gb), reverse=True)[:4]
                    tot = sum(x for x, _ in pares) or 1.0
                    pares = [(x / tot, j) for x, j in pares] + [(0.0, 0)] * (4 - len(pares))
                    wgt += [x for x, _ in pares]
                    jnt += [j for _, j in pares]
            nv = len(usados)
            at = {"POSITION": b.agregar("f", pos, 5126, "VEC3", nv, 34962, minmax=True)}
            if nrm:
                at["NORMAL"] = b.agregar("f", nrm, 5126, "VEC3", nv, 34962)
            if uv:
                at["TEXCOORD_0"] = b.agregar("f", uv, 5126, "VEC2", nv, 34962)
            if col:
                at["COLOR_0"] = b.agregar("f", [min(1.0, max(0.0, x)) for x in col], 5126, "VEC4", nv, 34962)
            if huesos:
                at["JOINTS_0"] = b.agregar("H", jnt, 5123, "VEC4", nv, 34962)
                at["WEIGHTS_0"] = b.agregar("f", wgt, 5126, "VEC4", nv, 34962)
            idx = [remap[i] for i in tris]
            ia = b.agregar("H" if nv < 65536 else "I", idx, 5123 if nv < 65536 else 5125, "SCALAR", len(idx), 34963)
            prim = {"attributes": at, "indices": ia, "mode": 4}
            if malla["material"] < len(g_mats):
                prim["material"] = malla["material"]
            prims.append(prim)
            est["tris"] += len(idx) // 3
            est["verts"] += nv
    est["primitivas"] = len(prims)
    if prims:
        g["meshes"].append({"name": nombre, "primitives": prims})
        nodo = {"name": nombre, "mesh": 0}
        if huesos:
            nodo["skin"] = 0
        g["nodes"].append(nodo)
        g["scenes"][0]["nodes"].append(len(g["nodes"]) - 1)
    for k in ("meshes", "skins"):
        if k in g and not g[k]:
            del g[k]

    os.makedirs(dir_salida, exist_ok=True)
    ruta = os.path.join(dir_salida, nombre + ".gltf")
    rbin = os.path.join(dir_salida, nombre + ".bin")
    g["buffers"] = [{"uri": os.path.basename(rbin).replace(" ", "%20"), "byteLength": len(b.datos)}]
    escribir(rbin, bytes(b.datos))
    escribir(ruta, json.dumps(g, indent=1).encode("utf-8"))
    return ruta, est


def escribir(ruta, datos):
    with open(ruta + ".tmp", "wb") as f:
        f.write(datos)
    os.replace(ruta + ".tmp", ruta)


_cache_img = {}


def _img(png):
    if png not in _cache_img:
        from PIL import Image
        _cache_img[png] = Image.open(png).convert("RGBA")
    return _cache_img[png]


def tiene_alfa(png):
    lo, _ = _img(png).getchannel("A").getextrema()
    return lo < 128


def color_medio(png):
    c = _img(png).resize((1, 1)).getpixel((0, 0))
    return [round(x / 255, 4) for x in c]


_d = b""


def archivos(ruta):
    if ruta.lower().endswith(".szs"):
        for n, x in szs.sarc(szs.yaz0(open(ruta, "rb").read())):
            if x[:4] == b"CGFX":
                yield n, x
    else:
        yield os.path.basename(ruta), open(ruta, "rb").read()


def convertir_archivo(ruta, dir_salida, previa=False):
    """Convierte todos los modelos de un .szs/.bcmdl. Devuelve lista de (gltf, est)."""
    global _d
    base = os.path.splitext(os.path.basename(ruta))[0]
    lista = list(archivos(ruta))
    out = []
    for n_arch, d in lista:
        _d = d
        modelos = cgfx.leer(d).get("modelos", [])
        for mn, o in modelos:
            if d[o + 4:o + 8] != b"CMDL":
                continue
            mod = leer_modelo(d, o)
            nombre = base if (len(lista) == 1 and len(modelos) == 1) else "%s__%s" % (base, mn)
            ruta_g, est = convertir(mod, nombre, base, dir_salida)
            if previa:
                dp = os.path.join(dir_salida, "_previas") if not previa_dir else previa_dir
                os.makedirs(dp, exist_ok=True)
                previa_png(ruta_g, os.path.join(dp, nombre + ".png"))
            out.append((ruta_g, est))
    return out


previa_dir = None


# ---------------------------------------------------------------- validacion y previa
def cargar_gltf(ruta):
    g = json.load(open(ruta, encoding="utf-8"))
    from urllib.parse import unquote
    binario = open(os.path.join(os.path.dirname(ruta), unquote(g["buffers"][0]["uri"])), "rb").read()
    return g, binario


def leer_acc(g, binario, i):
    a = g["accessors"][i]
    v = g["bufferViews"][a["bufferView"]]
    c = {5126: "f", 5123: "H", 5125: "I", 5121: "B"}[a["componentType"]]
    k = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
    n = a["count"] * k
    assert v["byteOffset"] + n * struct.calcsize(c) <= len(binario), "accessor fuera del buffer"
    plano = struct.unpack_from("<%d%s" % (n, c), binario, v["byteOffset"] + a.get("byteOffset", 0))
    return [plano[i:i + k] for i in range(0, n, k)] if k > 1 else list(plano)


def validar(ruta):
    """Chequeos estructurales. Devuelve lista de problemas (vacia = ok)."""
    g, binario = cargar_gltf(ruta)
    prob = []
    if g["buffers"][0]["byteLength"] != len(binario):
        prob.append("byteLength del buffer no coincide")
    for v in g["bufferViews"]:
        if v["byteOffset"] + v["byteLength"] > len(binario):
            prob.append("bufferView fuera del buffer")
    nj = len(g.get("skins", [{}])[0].get("joints", [])) if g.get("skins") else 0
    for m in g.get("meshes", []):
        for p in m["primitives"]:
            a = p["attributes"]
            pa = g["accessors"][a["POSITION"]]
            if "min" not in pa or "max" not in pa:
                prob.append("POSITION sin min/max")
            pos = leer_acc(g, binario, a["POSITION"])
            for k in range(3):
                if abs(min(x[k] for x in pos) - pa["min"][k]) > 1e-3 or abs(max(x[k] for x in pos) - pa["max"][k]) > 1e-3:
                    prob.append("min/max incorrecto")
            for nom, i in a.items():
                if g["accessors"][i]["count"] != pa["count"]:
                    prob.append("count de %s != POSITION" % nom)
            idx = leer_acc(g, binario, p["indices"])
            if len(idx) % 3:
                prob.append("indices no multiplo de 3")
            if idx and max(idx) >= pa["count"]:
                prob.append("indice >= count de vertices")
            if "JOINTS_0" in a:
                if max(max(j) for j in leer_acc(g, binario, a["JOINTS_0"])) >= nj:
                    prob.append("joint fuera de la skin")
                for w in leer_acc(g, binario, a["WEIGHTS_0"]):
                    if abs(sum(w) - 1) > 1e-3:
                        prob.append("pesos no suman 1")
                        break
            if "material" in p and p["material"] >= len(g["materials"]):
                prob.append("material inexistente")
    for im in g.get("images", []):
        from urllib.parse import unquote
        if not os.path.exists(os.path.join(os.path.dirname(ruta), unquote(im["uri"]))):
            prob.append("imagen no encontrada: " + im["uri"])
    return sorted(set(prob))


def _envolver(t, modo):
    if modo == 33071:  # clamp
        return min(max(t, 0.0), 0.99999)
    if modo == 33648:  # espejo
        t = t % 2.0
        return 2.0 - t - 1e-6 if t > 1.0 else t
    return t % 1.0


def previa_png(ruta, salida, tam=384):
    """Vista previa sin dependencias: rasteriza por pixel con z-buffer en ortografica (frente y lado),
    color = textura (UV interpolada, con el wrap del sampler) * color de vertice * Lambert."""
    from PIL import Image, ImageDraw
    from urllib.parse import unquote
    g, binario = cargar_gltf(ruta)
    texs = []
    for t in g.get("textures", []):
        im = g["images"][t["source"]]
        img_t = Image.open(os.path.join(os.path.dirname(ruta), unquote(im["uri"]))).convert("RGBA")
        smp = g["samplers"][t["sampler"]] if "sampler" in t else {}
        texs.append((img_t.load(), img_t.width, img_t.height, smp.get("wrapS", 10497), smp.get("wrapT", 10497)))
    tris = []
    for m in g.get("meshes", []):
        for p in m["primitives"]:
            a = p["attributes"]
            pos = leer_acc(g, binario, a["POSITION"])
            uv = leer_acc(g, binario, a["TEXCOORD_0"]) if "TEXCOORD_0" in a else None
            vc = leer_acc(g, binario, a["COLOR_0"]) if "COLOR_0" in a else None
            idx = leer_acc(g, binario, p["indices"])
            gm = g["materials"][p["material"]] if "material" in p else {}
            pbr = gm.get("pbrMetallicRoughness", {})
            base = pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1])
            tex = texs[pbr["baseColorTexture"]["index"]] if "baseColorTexture" in pbr and uv else None
            for k in range(0, len(idx), 3):
                ii = idx[k:k + 3]
                tris.append(([pos[i] for i in ii], [uv[i] for i in ii] if tex else None,
                             [vc[i] for i in ii] if vc else None, base, tex))
    img = Image.new("RGB", (tam * 2, tam), (40, 40, 48))
    if not tris:
        img.save(salida)
        return
    todos = [q for t in tris for q in t[0]]
    lo = [min(q[k] for q in todos) for k in range(3)]
    hi = [max(q[k] for q in todos) for k in range(3)]
    cen = [(lo[k] + hi[k]) / 2 for k in range(3)]
    esc = tam * 0.9 / (max(hi[k] - lo[k] for k in range(3)) or 1.0)
    px = img.load()
    luz = [0.4, 0.6, 0.7]
    ll = math.sqrt(sum(x * x for x in luz))
    luz = [x / ll for x in luz]
    for vista in range(2):
        zbuf = [[-1e30] * tam for _ in range(tam)]
        for ps, uvs, vcs, base, tex in tris:
            if vista == 0:  # frente: camara en +Z mirando a -Z
                q = [(p[0] - cen[0], p[1] - cen[1], p[2] - cen[2]) for p in ps]
            else:  # lado: camara en +X mirando a -X (el modelo mira a la derecha)
                q = [(cen[2] - p[2], p[1] - cen[1], p[0] - cen[0]) for p in ps]
            e1 = [q[1][i] - q[0][i] for i in range(3)]
            e2 = [q[2][i] - q[0][i] for i in range(3)]
            n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
            ln = math.sqrt(sum(x * x for x in n)) or 1.0
            f = 0.35 + 0.65 * abs(sum(n[i] / ln * luz[i] for i in range(3)))
            s = [(tam / 2 + v[0] * esc, tam / 2 - v[1] * esc, v[2]) for v in q]
            x0, x1 = max(0, int(min(v[0] for v in s))), min(tam - 1, int(max(v[0] for v in s)) + 1)
            y0, y1 = max(0, int(min(v[1] for v in s))), min(tam - 1, int(max(v[1] for v in s)) + 1)
            den = (s[1][1] - s[2][1]) * (s[0][0] - s[2][0]) + (s[2][0] - s[1][0]) * (s[0][1] - s[2][1])
            if abs(den) < 1e-9:
                continue
            for yy in range(y0, y1 + 1):
                for xx in range(x0, x1 + 1):
                    X, Y = xx + 0.5, yy + 0.5
                    w0 = ((s[1][1] - s[2][1]) * (X - s[2][0]) + (s[2][0] - s[1][0]) * (Y - s[2][1])) / den
                    w1 = ((s[2][1] - s[0][1]) * (X - s[2][0]) + (s[0][0] - s[2][0]) * (Y - s[2][1])) / den
                    w2 = 1 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    z = w0 * s[0][2] + w1 * s[1][2] + w2 * s[2][2]
                    if z <= zbuf[yy][xx]:
                        continue
                    c = [base[0] * 255, base[1] * 255, base[2] * 255]
                    if tex:
                        tp, tw, th, ws, wt = tex
                        u = _envolver(w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0], ws)
                        v = _envolver(w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1], wt)
                        t = tp[min(tw - 1, int(u * tw)), min(th - 1, int(v * th))]
                        if t[3] < 128:
                            continue
                        c = [t[0] * base[0], t[1] * base[1], t[2] * base[2]]
                    if vcs:
                        c = [c[i] * (w0 * vcs[0][i] + w1 * vcs[1][i] + w2 * vcs[2][i]) for i in range(3)]
                    zbuf[yy][xx] = z
                    px[tam * vista + xx, yy] = tuple(int(min(255, x * f)) for x in c)
    dr = ImageDraw.Draw(img)
    dr.line([(tam, 0), (tam, tam)], fill=(90, 90, 100))
    dr.text((6, 4), "frente (+Z)", fill=(200, 200, 200))
    dr.text((tam + 6, 4), "lado (+X)", fill=(200, 200, 200))
    img.save(salida + ".tmp.png")
    os.replace(salida + ".tmp.png", salida)


# ---------------------------------------------------------------- main
def lote(raiz, salida, previa):
    global previa_dir
    previa_dir = os.path.join(salida, "_previas") if previa else None
    ok, errores, sin_modelo, avisos = 0, [], 0, []
    faltan = set()
    tris = 0
    for carpeta, _, arch in os.walk(raiz):
        for a in sorted(arch):
            if not a.endswith(".szs"):
                continue
            ruta = os.path.join(carpeta, a)
            dsal = os.path.join(salida, os.path.relpath(carpeta, raiz))
            try:
                res = convertir_archivo(ruta, dsal, previa)
                if not res:
                    sin_modelo += 1
                for rg, est in res:
                    prob = validar(rg)
                    if prob:
                        avisos.append("%s: %s" % (os.path.relpath(rg, salida), "; ".join(prob)))
                    ok += 1
                    tris += est["tris"]
                    faltan.update(est["sin_textura"])
            except Exception as ex:  # noqa: BLE001
                errores.append("%s: %s: %s" % (os.path.relpath(ruta, raiz), type(ex).__name__, ex))
    resumen = ["modelos convertidos: %d" % ok, "triangulos totales: %d" % tris, "szs sin modelo CMDL: %d" % sin_modelo,
               "szs con error: %d" % len(errores), "modelos con avisos de validacion: %d" % len(avisos),
               "texturas referenciadas sin PNG: %d" % len(faltan)]
    texto = "\n".join(resumen + ["", "ERRORES:"] + errores + ["", "AVISOS:"] + avisos + ["", "TEXTURAS SIN PNG:"] + sorted(faltan)) + "\n"
    escribir(os.path.join(salida, "_lote.txt"), texto.encode("utf-8"))
    print("\n".join(resumen))
    for e in errores[:15]:
        print("  ERROR", e)
    for e in avisos[:10]:
        print("  AVISO", e)


def main():
    global previa_dir
    args = [a for a in sys.argv[1:] if a != "--previa"]
    previa = "--previa" in sys.argv
    if args[0] == "--todo":
        lote(args[1], args[2], previa)
    elif args[0] == "--previa-de":
        previa_png(args[1], args[2])
    else:
        if previa:
            previa_dir = os.path.join(RAIZ, "extraido", "modelos_gltf", "_previas")
        for rg, est in convertir_archivo(args[0], args[1], previa):
            print(rg, est, "validacion:", validar(rg) or "ok")


if __name__ == "__main__":
    main()
