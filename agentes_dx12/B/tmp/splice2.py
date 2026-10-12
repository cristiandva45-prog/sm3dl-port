B = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B"
p = B + r"\cadena_shaders.py"
s = open(p, encoding="utf-8").read()
nueva = open(B + r"\tmp\nueva_layouts.py", encoding="utf-8").read()
i0 = s.index("def layouts():")
i1 = s.index('if __name__ == "__main__":')
s = s[:i0] + nueva + s[i1:]
s = s.replace('elif cmd == "layouts": layouts()', 'elif cmd == "layouts": sys.exit(layouts("--sabotaje" in sys.argv))')
open(p, "w", encoding="utf-8", newline="\n").write(s)
