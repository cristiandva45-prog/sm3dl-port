r"""Respaldo del código del port (el proyecto no es git): zip en Desktop\Decopilar\respaldos\.
Uso: py -I tools\respaldar.py <etiqueta>   -> sm3dl-port-codigo-<etiqueta>.zip
Sin ROM, assets extraídos ni C generado (se regeneran con los scripts)."""
import os, sys, zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(os.path.dirname(RAIZ), "respaldos", "sm3dl-port-codigo-%s.zip" % sys.argv[1])
EXT = {".c", ".h", ".py", ".md", ".tsv", ".txt", ".glsl", ".vert", ".frag", ".json", ".bat", ".sh"}
SALTAR = {"gen", "partes", "ghidra", "__pycache__", "build", "texturas", "modelos", "colisiones", "niveles", "romfs", "capturas", ".venv_gl", ".venv"}

n = 0
with zipfile.ZipFile(DEST, "w", zipfile.ZIP_DEFLATED) as z:
    for d, subs, fs in os.walk(RAIZ):
        subs[:] = [s for s in subs if s not in SALTAR]
        for f in fs:
            p = os.path.join(d, f)
            if os.path.splitext(f)[1].lower() in EXT and os.path.getsize(p) <= 3_000_000:
                z.write(p, os.path.relpath(p, RAIZ))
                n += 1
print(n, "archivos", os.path.getsize(DEST) // 1024, "KB ->", DEST)
