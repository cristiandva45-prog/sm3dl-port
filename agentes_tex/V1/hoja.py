import os,sys
from PIL import Image
v='agentes_tex/V1/volcado';f='texturas_hd_fuente'
n=sorted(x for x in os.listdir(v) if x.startswith('tex_') and x not in set(os.listdir(f)))
W=8;cell=132
sheet=Image.new('RGB',(W*cell,((len(n)+W-1)//W)*cell),(60,60,60))
for i,x in enumerate(n):
    im=Image.open(os.path.join(v,x)).convert('RGBA'); im.thumbnail((128,128))
    bg=Image.new('RGBA',im.size,(255,0,255,255)); bg.alpha_composite(im) if False else None
    sheet.paste(im.convert('RGB'),((i%W)*cell,(i//W)*cell))
sheet.save('agentes_tex/V1/no_coinciden.png')
import collections
# colores medios / uniformes
for x in n:
    im=Image.open(os.path.join(v,x)).convert('RGBA'); c=len(set(im.getdata())) if im.width*im.height<=16384 else len(set(list(im.getdata())[::7]))
    print(x[4:-4],c,end=' | ')
