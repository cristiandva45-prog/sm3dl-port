p = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B\cadena_shaders.py"
s = open(p, encoding="utf-8").read()
a = '"luz_on", "luz_n", "luz_mues", "luz_c0"'
assert a in s
s = s.replace(a, '"luz_on", "luz_n", "luz_mues", "_pad0", "luz_c0"')
b = "        for n in orden:\n            if n not in decl:\n                continue\n"
assert b in s
s = s.replace(b, "        for n in orden:\n            if n.startswith('_pad'):   # relleno explicito: RbCbLuz deja un hueco tras luz_mues (std140 lo taparia con luz_c0)\n                if any(x in decl for x in orden):\n                    miembros.append(f'    int {n};')\n                continue\n            if n not in decl:\n                continue\n")
open(p, "w", encoding="utf-8", newline="\n").write(s)
