"""Convierte todos los niveles a JSON y cruza sus objetos con la tabla de fabrica del codigo.

Uso: py -I censo_niveles.py <raiz_del_port>
Escribe:
  extraido/niveles_json/<Nivel><Map|Design|Sound><n>.json
  extraido/objetos_por_nivel.tsv   (objeto, niveles, apariciones, tipo de info, create_ en el codigo?)
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import byml  # noqa: E402
import szs  # noqa: E402


def main():
    raiz = os.path.abspath(sys.argv[1])
    stage_dir = os.path.join(raiz, "extraido", "romfs", "StageData")
    out_dir = os.path.join(raiz, "extraido", "niveles_json")
    os.makedirs(out_dir, exist_ok=True)

    fabrica = {}
    for linea in open(os.path.join(raiz, "extraido", "tabla_actores.tsv"), encoding="utf-8").readlines()[1:]:
        tabla, nombre, funcion = linea.rstrip("\n").split("\t")
        fabrica[nombre] = funcion

    niveles_por_obj = collections.defaultdict(set)
    apariciones = collections.Counter()
    tipo_info = collections.defaultdict(collections.Counter)
    errores = []
    convertidos = 0
    niveles = set()
    for archivo in sorted(os.listdir(stage_dir)):
        if not archivo.endswith(".szs"):
            continue
        base = archivo[:-4]
        nivel = base.split("Stage")[0]
        niveles.add(nivel)
        try:
            contenido = dict(szs.sarc(szs.yaz0(open(os.path.join(stage_dir, archivo), "rb").read())))
        except Exception as ex:  # noqa: BLE001
            errores.append(f"{archivo}: {ex}")
            continue
        for interno, datos in contenido.items():
            if not interno.endswith(".byml"):
                continue
            try:
                arbol = byml.Byml(datos).raiz
            except Exception as ex:  # noqa: BLE001
                errores.append(f"{archivo}:{interno}: {ex}")
                continue
            destino = os.path.join(out_dir, f"{base}__{interno[:-5]}.json")
            with open(destino + ".tmp", "w", encoding="utf-8") as f:
                json.dump(arbol, f, ensure_ascii=False, indent=1)
            os.replace(destino + ".tmp", destino)
            convertidos += 1
            if interno == "StageData.byml" and isinstance(arbol, dict):
                for tipo, lista in (arbol.get("AllInfos") or {}).items():
                    for obj in lista or []:
                        nombre = obj.get("name") if isinstance(obj, dict) else None
                        if nombre:
                            niveles_por_obj[nombre].add(nivel)
                            apariciones[nombre] += 1
                            tipo_info[nombre][tipo] += 1

    filas = []
    for nombre, n in apariciones.most_common():
        filas.append((nombre, len(niveles_por_obj[nombre]), n, tipo_info[nombre].most_common(1)[0][0],
                      fabrica.get(nombre, "")))
    with open(os.path.join(raiz, "extraido", "objetos_por_nivel.tsv") + ".tmp", "w", encoding="utf-8") as f:
        f.write("objeto\tniveles\tapariciones\ttipo_info\tcreate_en_codigo\n")
        for fila in filas:
            f.write("\t".join(str(x) for x in fila) + "\n")
    os.replace(os.path.join(raiz, "extraido", "objetos_por_nivel.tsv") + ".tmp",
               os.path.join(raiz, "extraido", "objetos_por_nivel.tsv"))

    con = [f for f in filas if f[4]]
    sin = [f for f in filas if not f[4]]
    print(f"niveles: {len(niveles)}  byml convertidos: {convertidos}  errores: {len(errores)}")
    for e in errores[:5]:
        print("  ERROR", e)
    print(f"tipos de objeto distintos en los niveles: {len(filas)}")
    print(f"  con create_ en la tabla de fabrica: {len(con)}  ({sum(f[2] for f in con):,} apariciones)")
    print(f"  SIN create_ conocido:               {len(sin)}  ({sum(f[2] for f in sin):,} apariciones)")
    print("\nlos 25 mas usados (objeto · niveles · apariciones · tipo · create_):")
    for f in filas[:25]:
        print(f"  {f[0]:28} {f[1]:4} {f[2]:6}  {f[3]:15} {f[4] or '-- falta --'}")
    print("\nlos 20 mas usados SIN create_ conocido:")
    for f in sin[:20]:
        print(f"  {f[0]:28} {f[1]:4} {f[2]:6}  {f[3]}")


if __name__ == "__main__":
    main()
