"""Lector de colision KCL (+ atributos .pa) de Super Mario 3D Land -> OBJ.

Formato verificado contra los bytes (ver reportes\\colision.md):
  KCL little-endian, cabecera 0x38:
    0x00 u32 off_posiciones   (vec3 f32)
    0x04 u32 off_normales     (vec3 f32)
    0x08 u32 off_prismas - 0x10  (los prismas son 1-indexados: el 1o esta en +0x10)
    0x0C u32 off_octree
    0x10 f32 grosor del prisma
    0x14 vec3 f32 minimo del area (origen del octree)
    0x20 u32 x3 mascaras X,Y,Z
    0x2C u32 x3 shifts (coord, y, z)
  Prisma (0x10): f32 altura, u16 i_pos, u16 i_normal_cara, u16 x3 i_normales_arista, u16 atributo
  El atributo es el indice de fila en el .pa.

  PA = tabla tipo BCSV/JMap (linaje Galaxy), little-endian:
    0x00 u32 n_filas, 0x04 u32 n_campos, 0x08 u32 off_datos, 0x0C u32 tam_fila
    campo (0x0C): u32 hash(nombre), u32 mascara, u16 offset_en_fila, u8 shift, u8 tipo (0 = entero)
    hash JMap: h = h*31 + c. Campos vistos: Sound_code, Floor_code, Floor2_code, Wall_code, Camera_through.

Uso:
  py -I kcl.py pieza <archivo.szs> <salida_dir> [--previa]
  py -I kcl.py --todo <romfs> <salida_dir>
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import szs  # noqa: E402

NOMBRES_CAMPO = ["Sound_code", "Floor_code", "Floor2_code", "Wall_code", "Camera_through",
                 "Camera_code", "Shadow_through", "Line_through", "Obj_through", "Player_through"]


def hash_jmap(s):
    h = 0
    for c in s.encode():
        h = (h * 31 + c) & 0xFFFFFFFF
    return h


HASH_A_NOMBRE = {hash_jmap(n): n for n in NOMBRES_CAMPO}


# ---------------------------------------------------------------- vectores
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    l = math.sqrt(dot(a, a))
    return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-12 else (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- KCL
def leer_kcl(b):
    po, no, pr, oc = struct.unpack_from("<4I", b, 0)
    grosor = struct.unpack_from("<f", b, 0x10)[0]
    minimo = struct.unpack_from("<3f", b, 0x14)
    mascaras = struct.unpack_from("<3I", b, 0x20)
    shifts = struct.unpack_from("<3I", b, 0x2C)
    assert po == 0x38 and po < no < pr + 0x10 <= oc <= len(b), "offsets KCL incoherentes"
    n_pos = (no - po) // 12
    n_nrm = (pr + 0x10 - no) // 12
    n_pri = (oc - pr - 0x10) // 0x10
    pos = [struct.unpack_from("<3f", b, po + 12 * i) for i in range(n_pos)]
    nrm = [struct.unpack_from("<3f", b, no + 12 * i) for i in range(n_nrm)]
    prismas = [struct.unpack_from("<f6H", b, pr + 0x10 + 0x10 * i) for i in range(n_pri)]
    cab = dict(off_pos=po, off_nrm=no, off_prismas=pr, off_octree=oc, grosor=grosor, minimo=minimo,
               mascaras=mascaras, shifts=shifts, n_pos=n_pos, n_nrm=n_nrm, n_prismas=n_pri, tam=len(b))
    tris, attrs, malos = [], [], 0
    for L, ip, fn, a, bb, c, at in prismas:
        P, N, A, B, C = pos[ip], nrm[fn], nrm[a], nrm[bb], nrm[c]
        ca, cb = cross(A, N), cross(B, N)
        db, da = dot(cb, C), dot(ca, C)
        if abs(da) < 1e-9 or abs(db) < 1e-9:
            malos += 1
            continue
        v1 = P
        v2 = add(P, mul(cb, L / db))
        v3 = add(P, mul(ca, L / da))
        # orientacion: que la normal geometrica coincida con la de la cara
        if dot(cross(sub(v2, v1), sub(v3, v1)), N) < 0:
            v2, v3 = v3, v2
        tris.append((v1, v2, v3, N))
        attrs.append(at)
    cab["prismas_degenerados"] = malos
    return cab, tris, attrs


# ---------------------------------------------------------------- PA
def leer_pa(b):
    n_filas, n_campos, off_datos, tam_fila = struct.unpack_from("<4I", b, 0)
    campos = []
    for i in range(n_campos):
        h, m, off, sh, ti = struct.unpack_from("<IIHBB", b, 0x10 + 0x0C * i)
        campos.append(dict(hash=h, nombre=HASH_A_NOMBRE.get(h, f"0x{h:08x}"), mascara=m, offset=off, shift=sh, tipo=ti))
    filas = []
    for r in range(n_filas):
        o = off_datos + tam_fila * r
        fila = {}
        for c in campos:
            if c["tipo"] == 0:  # entero u32 empaquetado (mascara + shift), como en BCSV de Galaxy
                v = struct.unpack_from("<I", b, o + c["offset"])[0]
                fila[c["nombre"]] = (v & c["mascara"]) >> c["shift"]
            else:
                fila[c["nombre"]] = None
        filas.append(fila)
    return dict(n_filas=n_filas, n_campos=n_campos, off_datos=off_datos, tam_fila=tam_fila, campos=campos), filas


def clave_material(fila):
    if fila is None:
        return "sin_pa"
    partes = []
    for corto, nombre in (("S", "Sound_code"), ("F", "Floor_code"), ("F2", "Floor2_code"),
                          ("W", "Wall_code"), ("C", "Camera_through")):
        if nombre in fila:
            partes.append(f"{corto}{fila[nombre]}")
    return "_".join(partes) or "pa_vacio"


def color_material(clave):
    """Color estable por material (para .mtl y previas)."""
    h = hash_jmap(clave)
    return ((h & 0xFF) / 255 * 0.7 + 0.3, ((h >> 8) & 0xFF) / 255 * 0.7 + 0.3, ((h >> 16) & 0xFF) / 255 * 0.7 + 0.3)


# ---------------------------------------------------------------- piezas
def piezas_de_szs(ruta_szs):
    """Devuelve [(nombre_base, cab, tris, attrs, pa_info, filas)] por cada .kcl del .szs."""
    arch = dict(szs.sarc(szs.yaz0(open(ruta_szs, "rb").read())))
    out = []
    for nombre, datos in sorted(arch.items()):
        if not nombre.endswith(".kcl"):
            continue
        base = nombre[:-4]
        cab, tris, attrs = leer_kcl(datos)
        pa_info, filas = (None, None)
        if base + ".pa" in arch:
            pa_info, filas = leer_pa(arch[base + ".pa"])
        out.append((base, cab, tris, attrs, pa_info, filas))
    return out


class EscritorOBJ:
    """Acumula triangulos agrupados por material, deduplicando vertices."""

    def __init__(self, decimales=2):
        self.v, self.idx, self.grupos, self.dec = [], {}, {}, decimales

    def vert(self, p):
        k = (round(p[0], self.dec), round(p[1], self.dec), round(p[2], self.dec))
        i = self.idx.get(k)
        if i is None:
            i = len(self.v) + 1
            self.idx[k] = i
            self.v.append(k)
        return i

    def tri(self, mat, objeto, a, b, c):
        self.grupos.setdefault((objeto, mat), []).append((self.vert(a), self.vert(b), self.vert(c)))

    def guardar(self, ruta_obj):
        ruta_mtl = ruta_obj[:-4] + ".mtl"
        mats = sorted(set(m for _, m in self.grupos))
        tmp = ruta_mtl + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for m in mats:
                r, g, b = color_material(m)
                f.write(f"newmtl {m}\nKd {r:.3f} {g:.3f} {b:.3f}\n\n")
        os.replace(tmp, ruta_mtl)
        tmp = ruta_obj + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"# colision SM3DL (kcl.py)\nmtllib {os.path.basename(ruta_mtl)}\n")
            for x, y, z in self.v:
                f.write(f"v {x:g} {y:g} {z:g}\n")
            for (obj, m), caras in sorted(self.grupos.items()):
                f.write(f"g {obj}\nusemtl {m}\n")
                for a, b, c in caras:
                    f.write(f"f {a} {b} {c}\n")
        os.replace(tmp, ruta_obj)
        return len(self.v), sum(len(c) for c in self.grupos.values())


def validar(tris):
    """Bordes compartidos (soldado de vertices) -> mide continuidad de la malla."""
    from collections import Counter
    def k(p): return (round(p[0], 1), round(p[1], 1), round(p[2], 1))
    aristas = Counter()
    for v1, v2, v3, _ in tris:
        a, b, c = k(v1), k(v2), k(v3)
        for e in ((a, b), (b, c), (c, a)):
            aristas[tuple(sorted(e))] += 1
    compartidas = sum(1 for n in aristas.values() if n >= 2)
    return dict(aristas=len(aristas), compartidas=compartidas,
                pct_compartidas=round(100 * compartidas / max(1, len(aristas)), 1))


def exportar_pieza(ruta_szs, dir_salida):
    res = []
    for base, cab, tris, attrs, pa_info, filas in piezas_de_szs(ruta_szs):
        w = EscritorOBJ()
        for (v1, v2, v3, _), at in zip(tris, attrs):
            fila = filas[at] if filas is not None and at < len(filas) else None
            w.tri(clave_material(fila), base, v1, v2, v3)
        szs_base = os.path.basename(ruta_szs)[:-4]
        nombre_obj = base if base == szs_base else f"{szs_base}__{base}"  # evita choques (MoveLimit.kcl en varios .szs)
        nv, nf = w.guardar(os.path.join(dir_salida, nombre_obj + ".obj"))
        fuera = sum(1 for a in attrs if filas is None or a >= len(filas))
        res.append(dict(pieza=base, szs=os.path.basename(ruta_szs), verts=nv, tris=nf, cab=cab,
                        pa=pa_info, attr_fuera_pa=fuera, tris_obj=tris, attrs=attrs, filas=filas))
    return res


def main():
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "--todo":
        romfs, salida = a[1], a[2]
        dir_piezas = os.path.join(salida, "piezas")
        os.makedirs(dir_piezas, exist_ok=True)
        od = os.path.join(romfs, "ObjectData")
        filas_tsv = ["szs\tpieza\tprismas\ttris\tverts\tdegenerados\tpa_filas\tpa_campos\tattr_fuera_pa\tpct_aristas_compartidas\tmateriales"]
        from collections import Counter
        campos_tot, errores, total_tris = Counter(), [], 0
        valores = {}
        for fn in sorted(os.listdir(od)):
            if not fn.endswith(".szs"):
                continue
            try:
                for r in exportar_pieza(os.path.join(od, fn), dir_piezas):
                    pa = r["pa"]
                    if pa:
                        for c in pa["campos"]:
                            campos_tot[c["nombre"]] += 1
                        for f in r["filas"]:
                            for k2, v in f.items():
                                valores.setdefault(k2, Counter())[v] += 1
                    val = validar(r["tris_obj"])
                    mats = len(set(clave_material(r["filas"][x]) if r["filas"] and x < len(r["filas"]) else "sin_pa"
                                   for x in r["attrs"]))
                    total_tris += r["tris"]
                    filas_tsv.append("\t".join(map(str, (
                        r["szs"], r["pieza"], r["cab"]["n_prismas"], r["tris"], r["verts"],
                        r["cab"]["prismas_degenerados"], pa["n_filas"] if pa else "-", pa["n_campos"] if pa else "-",
                        r["attr_fuera_pa"], val["pct_compartidas"], mats))))
            except Exception as e:  # noqa: BLE001
                errores.append(f"{fn}: {e!r}")
        tmp = os.path.join(salida, "resumen_piezas.tsv.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(filas_tsv) + "\n")
        os.replace(tmp, tmp[:-4])
        print(f"piezas: {len(filas_tsv) - 1}  triangulos: {total_tris}  errores: {len(errores)}")
        for e in errores[:20]:
            print("  ERROR", e)
        print("campos PA:", dict(campos_tot))
        for k2, c in valores.items():
            print(f"  {k2}: {dict(sorted(c.items()))}")
        return
    if len(a) >= 3 and a[0] == "pieza":
        os.makedirs(a[2], exist_ok=True)
        for r in exportar_pieza(a[1], a[2]):
            print(r["pieza"], {k: r["cab"][k] for k in ("n_pos", "n_nrm", "n_prismas", "grosor", "prismas_degenerados")},
                  "tris", r["tris"], "verts", r["verts"], validar(r["tris_obj"]),
                  "pa:", r["pa"] and [c["nombre"] for c in r["pa"]["campos"]])
            if "--previa" in a:
                import colision_previa
                d = os.path.join(a[2], "_previas")
                os.makedirs(d, exist_ok=True)
                cols = [color_material(clave_material(r["filas"][x])) if r["filas"] and x < len(r["filas"]) else None
                        for x in r["attrs"]]
                colision_previa.render([t[:3] for t in r["tris_obj"]], os.path.join(d, r["pieza"] + ".png"),
                                       cols, titulo=r["pieza"])
                print("previa:", os.path.join(d, r["pieza"] + ".png"))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
