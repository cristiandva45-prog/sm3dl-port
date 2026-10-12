"""F1 (9 oct): parche de tools\\precompilar_d3d12.py (subcomandos desconocidos y cobertura). Uso: py -I este.py <ruta>"""
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a
    s = s.replace(a, b)


rep('''FIJOS = ("indice.tsv", "VERSION.txt")
''', '''FIJOS = ("indice.tsv", "VERSION.txt")
# (F1, 9 oct) textos de PS que el juego armo DE VERDAD y el inventario no genera (los vuelca D1 en DESCONOCIDOS al caer al
# uber). `desconocidos` los convierte, los instala y los guarda en PARTIDA, que desde entonces es parte del inventario
# (frag/partida/F_<hash>.frag): verificar/instalar/regenerar los esperan igual que a los de las recetas.
SHADERS = os.path.join(RAIZ, "extraido", "shaders")
PARTIDA = os.path.join(SHADERS, "frag_partida")
DESCONOCIDOS = os.path.join(SHADERS, "desconocidos_d3d12")
ARCHIVO_DESC = os.path.join(SHADERS, "desconocidos_d3d12_archivo")
CACHE_GL = os.path.join(SHADERS, "cache_gl")
''')

rep('''def inventariar(trabajo):
    utilitarios(trabajo)
    t0 = time.perf_counter()
    cad.inventario()
    if cad.comparar_c():
        raise SystemExit("comparar-c: FRAG_UBER/GEOM_FLIP del volcador != raster_uber.c")
''', '''def agregar_textos(rutas):
    """Copia textos GLSL ya armados (F_<hash>.frag/.glsl) a glsl/frag/partida/ y los agrega a INDICE.tsv. Devuelve los rel."""
    d = os.path.join(cad.GLSL, "frag", "partida")
    os.makedirs(d, exist_ok=True)
    rels = []
    with open(os.path.join(cad.GLSL, "INDICE.tsv"), "a", encoding="utf-8", newline="\\n") as f:
        for r in rutas:
            b = open(r, "rb").read()
            n = f"F_{cad.fnv_texto(b):08X}.frag"
            open(os.path.join(d, n), "wb").write(b)
            rel = "frag/partida/" + n
            f.write(f"{rel}\\tfrag\\ttexto real de una partida ({os.path.basename(r)})\\t{len(b)}\\n")
            rels.append(rel)
    return rels


def inventariar(trabajo, partida=None):
    utilitarios(trabajo)
    t0 = time.perf_counter()
    cad.inventario()
    if cad.comparar_c():
        raise SystemExit("comparar-c: FRAG_UBER/GEOM_FLIP del volcador != raster_uber.c")
    partida = PARTIDA if partida is None else partida
    if os.path.isdir(partida):   # los PS que ya aparecieron en partidas reales (ver `desconocidos`)
        agregar_textos(sorted(os.path.join(partida, f) for f in os.listdir(partida) if f.endswith(".frag")))
''')

rep('''def instalar_desde(origen, dest, esp):''', '''def instalar_desde(origen, dest, esp, respaldo=None):''')
rep('''    for n in esp:
        p = os.path.join(origen, n)
        e = validar_dxbc(open(p, "rb").read()) if os.path.exists(p) else "falta en el origen"''',
'''    fuente = {}
    for n in esp:
        p = os.path.join(origen, n)
        if not os.path.exists(p) and respaldo and os.path.exists(os.path.join(respaldo, n)):
            p = os.path.join(respaldo, n)   # p. ej. los PS de partida: B no los tiene, la cache instalada si
        fuente[n] = p
        e = validar_dxbc(open(p, "rb").read()) if os.path.exists(p) else "falta en el origen"''')
rep('''            shutil.copyfile(os.path.join(origen, n), os.path.join(nuevo, n))''',
    '''            shutil.copyfile(fuente[n], os.path.join(nuevo, n))''')
rep('''    instalar_desde(a.desde, a.dest, esp)
    return verificar_carpeta_e_informar(a.dest, esp)''', '''    instalar_desde(a.desde, a.dest, esp, respaldo=a.dest)
    return verificar_carpeta_e_informar(a.dest, esp)''')
rep('''    instalar_desde(os.path.join(a.trabajo, "cache_d3d12"), a.dest, esp)
    rc = verificar_carpeta_e_informar(a.dest, esp)''', '''    instalar_desde(os.path.join(a.trabajo, "cache_d3d12"), a.dest, esp, respaldo=a.dest)
    rc = verificar_carpeta_e_informar(a.dest, esp)''')

rep('''def sabotaje(a):''', '''def desconocidos(a):
    r"""PS que el juego armo y no estaban en la cache (D1 los vuelca en desconocidos_d3d12\\F_<hash>.glsl al caer al uber):
    1) cada texto debe tener el hash de su nombre (= el hsrc que busca D1; si no, se rechaza: no es el texto del juego);
    2) los que ya cubre la cache solo se archivan; 3) el resto: glslang -> SPIRV-Cross -> DXC con la cadena de B;
    4) una sola instalacion atomica (instalar_desde: .nuevo + os.replace) con la cache de hoy + los nuevos, y verificacion;
    5) recien entonces los textos pasan a frag_partida\\ (parte del inventario desde ahora) y la carpeta de desconocidos
    se archiva en desconocidos_d3d12_archivo\\<fecha>\\. Si algo falla en 1-4 no cambia nada."""
    t0 = time.perf_counter()
    esp = inventariar(a.trabajo, a.partida)
    if deriva():
        raise SystemExit("deriva C <-> volcador: correr verificar primero")
    if not os.path.isdir(a.desconocidos):
        print("no hay", a.desconocidos, "(nada que convertir)")
        return 0
    entradas = sorted(f for f in os.listdir(a.desconocidos) if re.fullmatch(r"F_[0-9A-F]{8}\\.glsl", f))
    malos, nuevos, cubiertos = [], [], 0
    for f in entradas:
        b = open(os.path.join(a.desconocidos, f), "rb").read()
        h = cad.fnv_texto(b)
        if f"F_{h:08X}.glsl" != f:
            malos.append(f"{f}: el texto tiene hash {h:08X} (alterado o truncado: no es lo que busca el juego)")
        elif f"F_{h:08X}.dxil" in esp:
            cubiertos += 1
        else:
            nuevos.append(os.path.join(a.desconocidos, f))
    print(f"desconocidos: {len(entradas)} textos -> {len(nuevos)} nuevos, {cubiertos} ya cubiertos, {len(malos)} rechazados")
    for m in malos[:10]:
        print("RECHAZADO:", m)
    if malos:
        raise SystemExit("hay textos rechazados: no se instala nada")
    if nuevos:
        for herr in (cad.GLSLANG, cad.XCROSS, cad.DXC):
            if not os.path.exists(herr):
                raise SystemExit(f"falta {herr}")
        rels = agregar_textos(nuevos)
        shutil.rmtree(cad.OUT, ignore_errors=True)
        patron = "^(" + "|".join(re.escape(r) for r in rels) + ")$"
        cad.convertir(["--hilos", str(a.hilos), "--solo", patron])
        filas = list(csv.DictReader(open(os.path.join(cad.OUT, "resultados_parcial.tsv"), encoding="utf-8"), delimiter="\\t"))
        fallos = [r for r in filas if r["dxil"] != "1"]
        for r in fallos[:10]:
            print("FALLO:", r["archivo"], r["fallo_en"], r["causa"])
        if fallos or len(filas) != len(rels):
            raise SystemExit(f"{len(fallos)} de {len(rels)} no llegaron a DXIL: no se instala nada")
        origen = os.path.join(a.trabajo, "cache_partida")
        shutil.rmtree(origen, ignore_errors=True)
        os.makedirs(origen)
        for rel in rels:
            shutil.copyfile(os.path.join(cad.OUT, rel.replace("/", "__") + ".dxil"),
                            os.path.join(origen, os.path.basename(rel)[:-5] + ".dxil"))
            h = int(os.path.basename(rel)[2:10], 16)
            esp[f"F_{h:08X}.dxil"] = (h, rel)
        open(os.path.join(origen, "VERSION.txt"), "w", newline="\\n").write(cad.CADENA_VERSION + "\\n")
        instalar_desde(origen, a.dest, esp, respaldo=a.dest)
        if verificar_carpeta_e_informar(a.dest, esp):
            raise SystemExit("la cache instalada no verifica: los textos se quedan en desconocidos (no se archivan)")
        os.makedirs(a.partida, exist_ok=True)
        for r in nuevos:
            shutil.copyfile(r, os.path.join(a.partida, os.path.basename(r)[:-5] + ".frag"))
    arch = os.path.join(a.archivo, time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(arch, exist_ok=True)
    for f in os.listdir(a.desconocidos):
        os.replace(os.path.join(a.desconocidos, f), os.path.join(arch, f))
    print(f"desconocidos: {len(nuevos)} PS nuevos instalados en {os.path.relpath(a.dest, RAIZ)} y guardados en "
          f"{os.path.relpath(a.partida, RAIZ)}; carpeta archivada en {os.path.relpath(arch, RAIZ)} "
          f"({time.perf_counter() - t0:.0f} s)")
    return 0


def cobertura(a):
    r"""Que parte de los PS que el juego YA uso en GL tiene DXIL. cache_gl\\ guarda binarios del DRIVER (sin el texto: no se
    puede reconstruir el GLSL desde ahi; el nombre lleva solo hv_hf_gs_driver), pero el hf dice que textos aparecieron."""
    esp = inventariar(a.trabajo, a.partida)
    hs = {f"{h:08X}" for n, (h, rel) in esp.items() if n.startswith("F_")}
    gl = [f[:-4].split("_") for f in os.listdir(CACHE_GL) if f.endswith(".bin")] if os.path.isdir(CACHE_GL) else []
    hf = {q[1] for q in gl if len(q) == 4}
    hv = {q[0] for q in gl if len(q) == 4}
    hvs = {f"{h:08X}" for n, (h, rel) in esp.items() if n.startswith("V_")}
    print(f"cache_gl: {len(gl)} programas, {len(hf)} PS distintos -> {len(hf & hs)} con DXIL, {len(hf - hs)} sin "
          f"(o de un texto de una version vieja del C); {len(hv)} VS -> {len(hv & hvs)} con DXIL")
    return 0


def sabotaje(a):''')

rep('''    ap.add_argument("cmd", choices=["verificar", "instalar", "regenerar", "sabotaje"])''',
    '''    ap.add_argument("cmd", choices=["verificar", "instalar", "regenerar", "sabotaje", "desconocidos", "cobertura"])''')
rep('''    ap.add_argument("--solo", default=None)
    a = ap.parse_args()
    a.trabajo, a.dest, a.desde = (os.path.abspath(x) for x in (a.trabajo, a.dest, a.desde))''',
'''    ap.add_argument("--solo", default=None)
    ap.add_argument("--desconocidos", default=DESCONOCIDOS)
    ap.add_argument("--partida", default=PARTIDA)
    ap.add_argument("--archivo", default=ARCHIVO_DESC)
    a = ap.parse_args()
    a.trabajo, a.dest, a.desde, a.desconocidos, a.partida, a.archivo = (
        os.path.abspath(x) for x in (a.trabajo, a.dest, a.desde, a.desconocidos, a.partida, a.archivo))''')
rep('''    sys.exit({"verificar": verificar, "instalar": instalar, "regenerar": regenerar, "sabotaje": sabotaje}[a.cmd](a))''',
    '''    sys.exit({"verificar": verificar, "instalar": instalar, "regenerar": regenerar, "sabotaje": sabotaje,
              "desconocidos": desconocidos, "cobertura": cobertura}[a.cmd](a))''')
rep('''  py -I tools\\precompilar_d3d12.py sabotaje ''', '''  py -I tools\\precompilar_d3d12.py desconocidos [--hilos N]  # (F1) convierte e instala los PS volcados en desconocidos_d3d12
  py -I tools\\precompilar_d3d12.py cobertura          # (F1) PS de cache_gl (los que el juego uso en GL) con / sin DXIL
  py -I tools\\precompilar_d3d12.py sabotaje ''')
open(p, "w", encoding="utf-8", newline="").write(s)
print("ok")
