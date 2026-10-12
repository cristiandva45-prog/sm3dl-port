import re
B = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B"
p = B + r"\cadena_shaders.py"
s = open(p, encoding="utf-8").read()
nueva = open(B + r"\tmp\nueva_vulk.py", encoding="utf-8").read()
# aux: uniforms fuera de BLOQUES -> un bloque b0 propio (orden de aparicion)
nueva = nueva.replace('''    sobran = set(decl) - usados
    assert not sobran, f"uniforms sin bloque en BLOQUES: {sorted(sobran)} (raster_uber.c cambio? actualizar la tabla)"
    if "@@BLOQUES@@" in res:
        # los uniforms de un shader auxiliar (no estan en BLOQUES) ya no pasan por aqui: ver rama siguiente
        pass
''', '''    sobran = [n for n in decl if n not in usados]
    if sobran:   # shader auxiliar (giro_alta, pres_capa): no es de los RbCb*; un bloque b0 con sus uniforms en orden
        assert not usados, f"mezcla de uniforms conocidos y desconocidos {sobran}: raster_uber.c cambio? actualizar BLOQUES"
        txt_bloques.append("layout(std140, set = 0, binding = 0) uniform CB0 {")
        for n in sobran:
            t, c, resto = decl[n]
            txt_bloques.append(f"    {t} {n}{'[' + c + ']' if c else ''};")
        txt_bloques.append("};")
''')
nueva = nueva.replace('''            if punto is None or "@@BLOQUES@@" not in res:
                pass
''', '')
i0 = s.index("_DECL = re.compile")
i1 = s.index("# ----", s.index("def vulkanizar"))
i1 = s.rindex("\n\n\n", 0, i1) + 3 if False else s.index("\n\n\n# ------", s.index("def vulkanizar")) + 3
s = s[:i0] + nueva + "\n\n" + s[i1:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok", len(s))
