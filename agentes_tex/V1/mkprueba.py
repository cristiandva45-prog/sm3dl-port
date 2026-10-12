from PIL import Image, ImageDraw
import os
d='agentes_tex/V1/texhd_prueba';os.makedirs(d,exist_ok=True)
def mk(nom,s,col,paso):
    im=Image.new('RGBA',(s,s),col);dr=ImageDraw.Draw(im)
    for i in range(0,s,paso): dr.line([(i,0),(i,s)],fill=(0,0,0,255),width=max(2,s//64)); dr.line([(0,i),(s,i)],fill=(0,0,0,255),width=max(2,s//64))
    dr.rectangle([0,0,s-1,s-1],outline=(255,255,255,255),width=max(2,s//32))
    im.save(d+'/'+nom)
mk('tex_128x128_f12_7ED58AB5.png',512,(255,0,255,255),64)   # pasto x4 magenta
mk('tex_128x128_f12_67FB2D6A.png',128,(0,255,255,255),16)   # mismo tamano cian
