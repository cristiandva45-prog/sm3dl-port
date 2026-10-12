import csv
from PIL import Image,ImageDraw
C="lawn_xx01_Grass01_dif.png LawnA.png Grass.png TreeLeaf.png tree_xx01_Bark01_dif.png tree_xx01_EnvTree01.png Wall_xx01_BrickWall_dif.png KoopaCastleBrickA_dif.png object_sm01_BlockBrick001_dif.0.png object_sm01_BlockQuestion00_dif.png object_dw01_Coin_dif.png player_dw01_MarioBody_dif.png enemy_xx01_Kuribo_dif.0.png WaterWave01.png WaterDust.png Metal_my03_ShipParts001_dif.png MetalPlate02.png Metal_xx01_MetalMesh_dif.png Sky_my03_Cloud001_dif.png SkyNightUniverse.png Rock09.png Soil_xx01_RedSoil01_dif.png Snow00.png SandPattern00.png Lava05.png Wall_ms01_PeachCastle01.png Fence.png Flag_twotone.png Cloth_patch_dif.png Floor_xx01_grid03_dif.png WallKousi.png Lattice00.png".split()
P={}
for l in open("agentes_tex/T5/catalogo.tsv"):
    f,s,m,p=l.rstrip("\n").split("\t");P[f]=p
S=128;cols=6;rows=(len(C)+cols-1)//cols
sh=Image.new("RGB",(cols*S,rows*(S+14)),(60,60,60));d=ImageDraw.Draw(sh)
for i,c in enumerate(C):
    if c not in P: print("falta",c);continue
    im=Image.open(P[c]).convert("RGBA");k=max(1,S//max(im.size));im=im.resize((im.width*k,im.height*k),Image.NEAREST)
    bg=Image.new("RGBA",im.size,(255,0,255,255));bg.alpha_composite(im)
    x=(i%cols)*S;y=(i//cols)*(S+14);sh.paste(bg.convert("RGB"),(x,y));d.text((x+1,y+S),"%d %s"%(i,c[:22]),fill=(255,255,255))
sh.save("agentes_tex/T5/muestra/candidatas.png")
