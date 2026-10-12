p = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B\cadena_shaders.py"
L = open(p, encoding="utf-8").read().split("\n")
L = [l.replace('    """Copia el DXIL', '    r"""Copia el DXIL') for l in L]
i = next(k for k, l in enumerate(L) if "cadena_shaders.py sabotaje" in l)
B = chr(92) * 2
L[i:i] = ["  py -I agentes_dx12" + B + "B" + B + "cadena_shaders.py empaquetar            # DXIL -> cache_d3d12 con nombre = hash del texto (lo busca shaders_d3d12.c)",
          "  py -I agentes_dx12" + B + "B" + B + "cadena_shaders.py layouts [--sabotaje]  # packoffset de los cbuffers == offsetof de RbCb* (raster_backend.h)"]
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(L))
