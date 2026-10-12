p='cadena_shaders.py'
s=open(p,encoding='utf-8').read()   # newline=None: normaliza \r\n
a='newline="\n").write(arreglar_hlsl'
assert a in s
s=s.replace(a,'newline="\n").write(arreglar_hlsl')
s=s.replace(chr(1),'\1')
open(p,'w',encoding='utf-8',newline='\n').write(s)
