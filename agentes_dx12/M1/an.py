import csv,sys,collections
for pas in ('real','turbo'):
    d=collections.defaultdict(list)
    for r in csv.DictReader(open(f'{pas}/hilos.csv')): d[r['tid']].append(float(r['pct'].replace(',','.')))
    top=sorted(d.items(),key=lambda kv:-sum(kv[1]))[:5]
    print(pas,'muestras',max(len(v) for v in d.values()))
    for t,v in top:
        v2=v[len(v)//4:]
        print('  hilo',t,'media %.0f%% max %.0f%% p90 %.0f%%'%(sum(v2)/len(v2),max(v2),sorted(v2)[int(len(v2)*.9)]))
    g=[int(l.split(',')[0].replace('%','').strip()) for l in open(f'{pas}/gpu.csv') if l.strip() and l[0].isdigit()]
    g2=g[len(g)//4:]
    print('  GPU n',len(g),'media %.0f max %d p90 %d'%(sum(g2)/len(g2),max(g2),sorted(g2)[int(len(g2)*.9)]))
