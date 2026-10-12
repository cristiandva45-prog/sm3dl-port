# T5: escala la muestra con 2 modelos Real-ESRGAN (RGB y alfa por separado, envuelto en mosaico). Prioridad baja.
import os,subprocess,time,sys,csv
from PIL import Image
RAIZ=r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port"
T5=RAIZ+r"\agentes_tex\T5"
EXE=T5+r"\terceros\realesrgan-ncnn-vulkan-20220424-windows\bin\realesrgan-ncnn-vulkan.exe"
MODELOS=["realesrgan-x4plus","realesrgan-x4plus-anime"]
# (archivo, mosaico?)
M=[("lawn_xx01_Grass01_dif.png",1),("LawnA.png",1),("Grass.png",0),("tree_xx01_Bark01_dif.png",1),("tree_xx01_EnvTree01.png",1),
("Wall_xx01_BrickWall_dif.png",1),("KoopaCastleBrickA_dif.png",1),("object_sm01_BlockBrick001_dif.0.png",1),("object_sm01_BlockQuestion00_dif.png",0),
("player_dw01_MarioBody_dif.png",0),("enemy_xx01_Kuribo_dif.0.png",0),("WaterWave01.png",1),("Metal_my03_ShipParts001_dif.png",0),
("MetalPlate02.png",1),("Metal_xx01_MetalMesh_dif.png",1),("Sky_my03_Cloud001_dif.png",0),("SkyNightUniverse.png",1),
("Soil_xx01_RedSoil01_dif.png",1),("Lava05.png",1),("Wall_ms01_PeachCastle01.png",1)]
P={}
for l in open(T5+r"\catalogo.tsv"):
    f,s,m,p=l.rstrip("\n").split("\t");P[f]=RAIZ+"\\"+p.replace("/","\\")
sel=sys.argv[1:] 
os.makedirs(T5+r"\muestra\tmp",exist_ok=True)
tiempos=open(T5+r"\muestra\tiempos.tsv","a")
def rellenar(im,pad,mos):
    w,h=im.size;o=Image.new("RGBA",(w+2*pad,h+2*pad))
    if mos:
        for dx in(-1,0,1):
            for dy in(-1,0,1): o.paste(im,(pad+dx*w,pad+dy*h))
    else:
        o.paste(im,(pad,pad))
        for x in range(w+2*pad):
            for y in range(h+2*pad):
                if pad<=x<pad+w and pad<=y<pad+h: continue
                o.putpixel((x,y),im.getpixel((min(max(x-pad,0),w-1),min(max(y-pad,0),h-1))))
    return o
def correr(ent,sal,mod):
    t=time.time()
    r=subprocess.run([EXE,"-i",ent,"-o",sal,"-n",mod,"-s","4","-j","1:1:1","-f","png"],capture_output=True,text=True,creationflags=0x4000)  # BELOW_NORMAL
    if r.returncode: print(r.stderr[-300:])
    return time.time()-t
for f,mos in M:
    if sel and f not in sel: continue
    im=Image.open(P[f]).convert("RGBA");w,h=im.size;pad=min(16,w,h)
    pa=rellenar(im,pad,mos)
    rgb=pa.convert("RGB");al=pa.getchannel("A").convert("RGB")
    b=f[:-4];rgb.save(T5+rf"\muestra\tmp\{b}_rgb.png");al.save(T5+rf"\muestra\tmp\{b}_a.png")
    for mod in MODELOS:
        tt=0
        for k in("rgb","a"):
            o=T5+rf"\muestra\tmp\{b}_{k}_{mod}.png"
            tt+=correr(T5+rf"\muestra\tmp\{b}_{k}.png",o,mod)
        R=Image.open(T5+rf"\muestra\tmp\{b}_rgb_{mod}.png").convert("RGB")
        A=Image.open(T5+rf"\muestra\tmp\{b}_a_{mod}.png").convert("L")
        c=pad*4;box=(c,c,R.width-c,R.height-c)
        out=R.crop(box);out.putalpha(A.crop(box));out.save(T5+rf"\muestra\{b}__{mod}.png")
        tiempos.write(f"{f}\t{w}x{h}\t{mod}\t{tt:.2f}\n");tiempos.flush()
        print(f,mod,"%.2fs"%tt,flush=True)
