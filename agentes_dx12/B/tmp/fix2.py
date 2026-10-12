p = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B\cadena_shaders.py"
L = open(p, encoding="utf-8").read().split("\n")
for i, l in enumerate(L):
    if l.lstrip().startswith("hlsl = re.sub(r\"gl_in"):
        L[i] = '        hlsl = re.sub(r"gl_in\\[(\\w+)\\]\\.gl_Position", lambda m: "gl_PositionIn[" + m.group(1) + "]", hlsl)'
        print("arreglada", i + 1)
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(L))
