import os,sys,collections
v=sys.argv[1];f='texturas_hd_fuente'
a={x for x in os.listdir(v) if x.startswith('tex_')}
b=set(os.listdir(f))
c=a&b;n=a-b
print(len(a),'volcadas',len(c),'coinciden',round(100*len(c)/max(1,len(a)),1),'%')
# mapa
mp={}
for l in open(f+'/mapa.tsv',encoding='utf8'):
    p=l.rstrip('\n').split('\t')
    if len(p)>=5: mp[p[0].upper()]=p
cl=collections.Counter()
for x in sorted(n):
    s=x[:-4].split('_'); w,h=s[1].split('x'); fm=s[2]; k=s[3]
    cl[(fm,w+'x'+h)]+=1
print('no coinciden',len(n)); 
for k,vv in cl.most_common(25): print(k,vv)
print(sorted(n)[:15])
# misma clave distinta w/h/fmt
ks={x[:-4].split('_')[3] for x in b if x.startswith('tex_')}
print('claves de no-coincidentes presentes en fuente con otro nombre:',sum(1 for x in n if x[:-4].split('_')[3] in ks))
fm=collections.Counter(x.split('_')[2] for x in a); fc=collections.Counter(x.split('_')[2] for x in c)
print('por fmt volcado/coinc',{k:(fm[k],fc[k]) for k in fm})
