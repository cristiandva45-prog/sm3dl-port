from PIL import Image, ImageChops
a=Image.open('agentes_tex/V1/corridas/aniso1/cap/v004616.png').convert('RGB');b=Image.open('agentes_tex/V1/corridas/aniso16/cap/v004616.png').convert('RGB')
d=ImageChops.difference(a,b);print(d.getbbox(), sum(sum(p) for p in d.getdata()))
box=(0,100,260,240)
w=Image.new('RGB',(520*2,280*1+0)); 
w.paste(a.crop(box).resize((520,280),Image.NEAREST),(0,0)); w.paste(b.crop(box).resize((520,280),Image.NEAREST),(520,0)); w.save('agentes_tex/V1/aniso_1_vs_16.png')
