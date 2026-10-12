import os
from PIL import Image
v='agentes_tex/V1/volcado'
L=[]
for x in sorted(os.listdir(v)):
    if not x.startswith('tex_'): continue
    im=Image.open(v+'/'+x).convert('RGB');w,h=im.size
    if w<32 or h<32: continue
    s=im.resize((1,1),Image.BOX).getpixel((0,0))
    L.append((s[1]-max(s[0],s[2]),x,s,im.size))
L.sort(reverse=True)
for g,x,s,sz in L[:12]: print(x,s,sz)
sel=[l[1] for l in L[:16]]
sheet=Image.new('RGB',(8*132,2*132),(80,80,80))
for i,x in enumerate(sel):
    im=Image.open(v+'/'+x).convert('RGB');im.thumbnail((128,128));sheet.paste(im,((i%8)*132,(i//8)*132))
sheet.save('agentes_tex/V1/verdes.png')
