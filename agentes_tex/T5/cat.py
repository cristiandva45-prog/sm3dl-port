import os,sys
from PIL import Image
R="extraido/texturas_png"
seen={}
for d,_,fs in os.walk(R):
    for f in fs:
        if f.endswith(".png") and not f.startswith("_"):
            seen.setdefault(f,os.path.join(d,f))
import re
out=[]
for f,p in sorted(seen.items()):
    try:
        im=Image.open(p); out.append((f,im.size,im.mode,p))
    except: pass
print(len(out))
open("agentes_tex/T5/catalogo.tsv","w").write("\n".join("%s\t%dx%d\t%s\t%s"%(f,s[0],s[1],m,p) for f,s,m,p in out))
