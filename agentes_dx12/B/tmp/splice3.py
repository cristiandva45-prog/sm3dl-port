B = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port\agentes_dx12\B"
p = B + r"\cadena_shaders.py"
s = open(p, encoding="utf-8").read()
nueva = open(B + r"\tmp\nueva_emp.py", encoding="utf-8").read()
i1 = s.index('if __name__ == "__main__":')
s = s[:i1] + nueva + s[i1:]
s = s.replace("import hashlib\n", "import hashlib\nimport shutil\n")
s = s.replace('SHADERS = os.path.join(RAIZ, "extraido", "shaders")\n', 'SHADERS = os.path.join(RAIZ, "extraido", "shaders")\nCADENA_VERSION = "glslang-16.6.0+SPIRV-Cross-vulkan-sdk-1.4.363.0+dxc-1.9.2609.5+vulkanizar-1"   # sube con cualquier cambio de la cadena\n')
s = s.replace('    elif cmd == "layouts":', '    elif cmd == "empaquetar": empaquetar()\n    elif cmd == "layouts":')
s = s.replace("  py -I agentes_dx12\\B\\cadena_shaders.py sabotaje ", "  py -I agentes_dx12\\B\\cadena_shaders.py empaquetar             # copia el DXIL a cache_d3d12\\ con nombre = hash del texto (lo que busca shaders_d3d12.c)\n  py -I agentes_dx12\\B\\cadena_shaders.py layouts [--sabotaje]   # packoffset de los cbuffers == offsetof de RbCb* (raster_backend.h)\n  py -I agentes_dx12\\B\\cadena_shaders.py sabotaje ")
open(p, "w", encoding="utf-8", newline="\n").write(s)
