# H3: linea de tiempo del log D3D12 por bloques de [gsp-est] (solo lectura)
import re, sys
ruta = sys.argv[1]
L = open(ruta, encoding='utf-8', errors='replace').read().splitlines()
vb = 0; prev = None
ev = []          # eventos de cada bloque
dib = 0; tdib = 0.0
rows = []
cur = {'sin':0,'pso':0,'rt':0,'bajar':0,'ipc':0,'cap':[],'otros':[], 'dib0':0,'tdib0':0.0}
pso_prev = 0
for i, s in enumerate(L, 1):
    m = re.match(r'\[gsp-est\] vblanks=(\d+) listas=(\d+).*swaps=(\d+) presentaciones=(\d+)', s)
    if m:
        v, li, sw, pr = map(int, m.groups())
        if prev:
            dv = v - prev[0]; dsw = sw - prev[2]; dli = li - prev[1]
            rows.append((i, v, dv, dsw, dli, dib - cur['dib0'], tdib - cur['tdib0'], cur))
        prev = (v, li, sw, pr)
        cur = {'sin':0,'pso':0,'rt':0,'bajar':0,'ipc':0,'cap':[],'otros':[], 'dib0':dib,'tdib0':tdib}
        continue
    m = re.match(r'\[raster\] dibujo (\d+):.*tiempo dibujar ([\d.]+) s', s)
    if m: dib = int(m.group(1)); tdib = float(m.group(2)); continue
    if 'sin DXIL' in s: cur['sin'] += 1
    elif s.startswith('[d3d12] cache de PSO guardada'):
        n = int(re.search(r'(\d+) PSO nuevos', s).group(1)); cur['pso'] += n - pso_prev; pso_prev = n
    elif 'render target' in s: cur['rt'] += 1
    elif 'bajar sincrono' in s: cur['bajar'] += 1
    elif s.startswith('[ipc]'): cur['ipc'] += 1
    elif s.startswith('[captura] pantalla 0'): cur['cap'].append(re.search(r'rgba0=(\w+)', s).group(1))
    elif s.startswith(('[alto]','[ritmo]','[interp-costo]','[pres-crono]','[ventana]','[raster] resol','[alto-paso]','[alto-desglose]')):
        cur['otros'].append(s[:150])
for (i, v, dv, dsw, dli, dd, td, c) in rows:
    flag = ''.join([f" SIN{c['sin']}" if c['sin'] else '', f" PSO+{c['pso']}" if c['pso'] else '',
                    f" RT{c['rt']}" if c['rt'] else '', f" BAJ{c['bajar']}" if c['bajar'] else '', f" IPC{c['ipc']}" if c['ipc'] else ''])
    print(f"L{i:5d} vb{v:6d} dv{dv:4d} sw{dsw:4d} listas{dli:4d} dib{dd:7d} tdib{td*1000:6.0f}ms cap{','.join(c['cap'])}{flag}")
    for o in c['otros']: print('      ', o)
