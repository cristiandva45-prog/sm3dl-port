B = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B"
bs = chr(92)
p = B + r"\prueba_cache.c"
s = open(p, encoding="utf-8").read()
s = s.replace("*p = '\';", "*p = '" + bs + bs + "';")
open(p, "w", encoding="utf-8", newline="\n").write(s)
p = B + r"\shaders_d3d12.c"
s = open(p, encoding="utf-8").read()
for n in ("SD_DIR_CACHE  ", "SD_DIR_FALTAN "):
    i = s.index("#define " + n)
    j = s.index("\n", i)
    s = s[:i] + "#ifndef " + n.strip() + "\n" + s[i:j] + "\n#endif" + s[j:]
open(p, "w", encoding="utf-8", newline="\n").write(s)
