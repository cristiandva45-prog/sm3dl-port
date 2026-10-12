def fnv_texto(b):
    """= fnv_texto() de raster_gl.c (FNV-1a 32 sobre los bytes del texto, sin el NUL)."""
    h = 2166136261
    for c in b:
        h = ((h ^ c) * 16777619) & 0xFFFFFFFF
    return h


def empaquetar():
    """Copia el DXIL de cada shader convertido a cache_d3d12\ con el nombre que buscara shaders_d3d12.c:
         V_<hash>.dxil  vertex shader (hash = fnv_texto del texto envuelto, el mismo 'hv' del cache de programas GL)
         F_<hash>.dxil  pixel shader (hash = 'hf')         F_UBER.dxil  el uber por uniforms (respaldo universal)
         G_FLIP.dxil    geometry shader (unico)             A_<nombre>.dxil  auxiliares (giro_alta.vs, pres_capa.fs, ...)
       y escribe cache_d3d12\indice.tsv (nombre del archivo, hash, origen GLSL, bytes). Version de la cadena en VERSION.txt."""
    dest = os.path.join(B, "cache_d3d12")
    os.makedirs(dest, exist_ok=True)
    filas, n = [], 0
    for r in csv.DictReader(open(os.path.join(OUT, "resultados.tsv"), encoding="utf-8"), delimiter="\t"):
        if r["dxil"] != "1":
            continue
        rel = r["archivo"]
        texto = open(os.path.join(GLSL, *rel.split("/")), "rb").read()
        h = fnv_texto(texto)
        if rel.startswith("vert/"): nom = f"V_{h:08X}.dxil"
        elif rel == "uber.frag": nom = "F_UBER.dxil"
        elif rel.startswith("frag/"): nom = f"F_{h:08X}.dxil"
        elif rel == "flip.geom": nom = "G_FLIP.dxil"
        elif rel.startswith("aux/"):
            b = os.path.basename(rel)
            nom = "A_" + b.replace(".vert", ".vs").replace(".frag", ".fs") + ".dxil"
        else:
            continue
        shutil.copyfile(os.path.join(OUT, rel.replace("/", "__") + ".dxil"), os.path.join(dest, nom))
        filas.append((nom, f"{h:08X}", rel, r["bytes_dxil"]))
        n += 1
    with open(os.path.join(dest, "indice.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("archivo\thash\tglsl\tbytes\n")
        for fi in filas:
            f.write("\t".join(fi) + "\n")
    open(os.path.join(dest, "VERSION.txt"), "w", newline="\n").write(CADENA_VERSION + "\n")
    colis = len(filas) - len({f[0] for f in filas})
    print(f"{n} DXIL en {dest} ({colis} colisiones de nombre); version: {CADENA_VERSION}")


