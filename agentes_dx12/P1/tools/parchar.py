r"""(P1) aplica reemplazos EXACTOS (cada uno debe aparecer 1 vez) a un archivo, respetando CRLF. Uso: py -I parchar.py <archivo> <reemplazos.py>
reemplazos.py define R = [(viejo, nuevo), ...] con saltos \n."""
import os, sys
p, rp = sys.argv[1], sys.argv[2]
ns = {}
exec(open(rp, encoding="utf-8").read(), ns)
s = open(p, encoding="utf-8", newline="").read()
CR = "\r\n" in s
s = s.replace("\r\n", "\n")
for a, b in ns["R"]:
    n = s.count(a)
    if n != 1:
        sys.exit("FALLA: %d apariciones de: %r" % (n, a[:80]))
    s = s.replace(a, b)
if CR:
    s = s.replace("\n", "\r\n")
open(p + ".tmp", "w", encoding="utf-8", newline="").write(s)
os.replace(p + ".tmp", p)
print("ok", len(ns["R"]), "reemplazos en", p)
