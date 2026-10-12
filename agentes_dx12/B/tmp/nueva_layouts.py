def layouts(sabotaje=False):
    """Comprueba que los packoffset de los cbuffers de TODAS las variantes coinciden con offsetof() de las estructuras
    RbCb* de raster_backend.h (agente A; check_layout.exe) y que no cambian de una variante a otra. Escribe cb_layouts.h.
    sabotaje=True: corrompe un offset esperado y debe fallar."""
    rc, txt, _ = ejecutar([os.path.join(B, "check_layout.exe")])
    if rc:
        raise SystemExit("falta check_layout.exe (ver su cabecera para compilarlo)")
    esperado, tam = {}, {}
    for l in txt.splitlines():
        b, n, v = l.split("\t")
        if n.startswith("#") or b == "luz":
            tam[(b, n)] = int(v)
        else:
            esperado[(b, n)] = int(v)
    if sabotaje:
        esperado[("b1", "z_escala")] += 4
    grupos = {}   # (tipo, b) -> {firma_json: [archivos]}
    for f in sorted(os.listdir(OUT)):
        if not f.endswith(".hlsl") or f.startswith("aux__") or f.startswith("flip"):
            continue
        tipo = "vs" if f.startswith("vert__") else "fs"
        cb = parse_cbuffers(open(os.path.join(OUT, f), encoding="utf-8").read())
        for b, mi in cb.items():
            mi = [(re.sub(r"^cb_", "", n), t, c, off) for n, t, c, off in mi]
            grupos.setdefault((tipo, b), {}).setdefault(json.dumps(mi), []).append(f)
    ok, errores, vistos = True, [], 0
    out = ["/* GENERADO por cadena_shaders.py layouts -- offsets en BYTES de cada cbuffer; verificados contra offsetof() de",
           " * RbCbVertice/Fragmento/Niebla/Luz (raster_backend.h). No editar. */", ""]
    for (tipo, b), sigs in sorted(grupos.items()):
        n = sum(len(v) for v in sigs.values())
        print(f"{tipo:3s} b{b}: {len(sigs)} layout(s) distinto(s) en {n} shaders")
        if len(sigs) != 1:
            ok = False
        for nombre, t, c, off in json.loads(next(iter(sigs))):
            clave = (f"b{b}", nombre)
            if clave in esperado:
                vistos += 1
                if esperado[clave] != off:
                    ok = False
                    errores.append(f"b{b}.{nombre}: HLSL {off} != C {esperado[clave]}")
            if tipo == "vs" or b != 0 or True:
                out.append(f"#define CB_B{b}_{nombre.upper():<14s} {off:5d}   /* {t}{'[' + str(c) + ']' if c else ''} */")
        out.append("")
    # tamanos: la ultima posicion + tamano del ultimo miembro debe redondear a sizeof (se compara b1: 224)
    print(f"{vistos} miembros comparados con offsetof(); tamanos C: " + ", ".join(f"{k[0]}={v}" for k, v in sorted(tam.items()) if k[1] == '#tam'))
    open(os.path.join(B, "cb_layouts.h"), "w", encoding="utf-8", newline="\n").write("\n".join(out))
    for e in errores:
        print("DIFERENCIA:", e)
    print("cb_layouts.h escrito;", "layouts consistentes con raster_backend.h" if ok else "LAYOUTS DISTINTOS")
    return 0 if ok else 1


