p = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B\cadena_shaders.py"
s = open(p, encoding="utf-8").read()
a = "    for _ in range(3):   # varias declaraciones en una linea (aux): una por linea\n"
assert a in s
s = s.replace(a, "    for _ in range(12):   # varias declaraciones en una linea (aux): una por linea (una por pasada)\n")
open(p, "w", encoding="utf-8", newline="\n").write(s)
