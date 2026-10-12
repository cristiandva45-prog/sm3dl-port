import os,sys
from PIL import Image,ImageDraw,ImageChops,ImageStat
RAIZ=r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port"
T5=RAIZ+r"\agentes_tex\T5"
exec(open(T5+r"\escalar_muestra.py",encoding="utf8").read().split("P={}")[0].split("MODELOS=")[1].join(["MODELOS=",""]) if False else "")
MOD=["realesrgan-x4plus","realesrgan-x4plus-anime"]
src=open(T5+r"\escalar_muestra.py",encoding="utf8").read()
M=eval("["+src.split("M=[")[1].split("]\nP={}")[0]+"]")
P={}
for l in open(T5+r"\catalogo.tsv"):
    f,s,m,p=l.rstrip("\n").split("\t");P[f]=RAIZ+"\\"+p.replace("/","\\")
def fondo(im):
    b=Image.new("RGBA",im.size,(0,0,0,255))
    for y in range(0,im.height,16):
        for x in range(0,im.width,16):
            if (x//16+y//16)%2==0: b.paste((70,70,70,255),(x,y,x+16,y+16))
    b.alpha_composite(im.convert("RGBA"));return b.convert("RGB")
def seam(im):  # diferencia media de la costura envuelta vs. diferencia media entre columnas vecinas
    g=im.convert("RGB");w,h=g.size
    c=lambda x:g.crop((x,0,x+1,h))
    d=lambda a,b:sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3
    junta=d(c(w-1),c(0));interior=sum(d(c(x),c(x+1)) for x in range(0,w-1,max(1,w//16)))/len(range(0,w-1,max(1,w//16)))
    return junta,interior
filas=[];lab=["ORIGINAL (vecino mas cercano x4)","A: realesrgan-x4plus","B: realesrgan-x4plus-anime"]
costuras=open(T5+r"\muestra\costuras.tsv","w")
for f,mos in M:
    b=f[:-4];o=Image.open(P[f]).convert("RGBA")
    ims=[o.resize((o.width*4,o.height*4),Image.NEAREST)]+[Image.open(T5+rf"\muestra\{b}__{m}.png") for m in MOD]
    if mos:
        r=[seam(i) for i in ims]
        costuras.write(f+"\t"+"\t".join("%.1f/%.1f"%x for x in r)+"\n")
    filas.append((f,o.size,mos,[fondo(i) for i in ims]))
def hoja(grupo,nombre):
    W=max(sum(i.width for i in fl[3])+40 for fl in grupo);Wc=max(fl[3][0].width for fl in grupo)
    H=sum(fl[3][0].height+40 for fl in grupo)+30
    S=Image.new("RGB",(Wc*3+80,H),(25,25,25));d=ImageDraw.Draw(S);y=26
    for j,t in enumerate(lab): d.text((10+j*(Wc+20),6),t,fill=(255,230,120))
    for f,sz,mos,ims in grupo:
        d.text((10,y),"%s  %dx%d  %s"%(f,sz[0],sz[1],"MOSAICO(borde envuelto)" if mos else "no mosaico"),fill=(255,255,255))
        for j,i in enumerate(ims): S.paste(i,(10+j*(Wc+20),y+14))
        y+=ims[0].height+40
    S.save(T5+rf"\muestra\{nombre}.png");print(nombre,S.size)
for k in range(0,len(filas),5): hoja(filas[k:k+5],"hoja_%d"%(k//5+1))
