import os
from PIL import Image, ImageChops
v='agentes_tex/V1/volcado';f='texturas_hd_fuente'
ok=dif=difv=0;ej=[]
for x in os.listdir(v):
    if not x.startswith('tex_') or not os.path.exists(f+'/'+x): continue
    a=Image.open(v+'/'+x).convert('RGBA');b=Image.open(f+'/'+x).convert('RGBA')
    if a.size!=b.size: dif+=1;ej.append((x,'tam',a.size,b.size));continue
    d=ImageChops.difference(a,b).getbbox()
    if d is None: ok+=1
    else:
        if ImageChops.difference(a.transpose(Image.FLIP_TOP_BOTTOM),b).getbbox() is None: difv+=1
        else: dif+=1;ej.append(x)
print('identicas',ok,'iguales volteadas',difv,'distintas',dif,ej[:8])
# no coincidentes: origen en mapa por tamaño/fmt
