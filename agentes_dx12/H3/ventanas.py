# H3: metricas por ventana de vblanks emulados (solo lectura del log)
import re, sys
L = open(sys.argv[1], encoding='utf-8', errors='replace').read().splitlines()
W = int(sys.argv[2]) if len(sys.argv) > 2 else 600
vb = 0; sw = 0
acc = {}
def get(k): return acc.setdefault(k, {})
last = {}
def delta(w, k, v):
    p = last.get(k)
    if p is not None: get(w)[k] = get(w).get(k, 0) + (v - p)
    last[k] = v
def add(w, k, v=1): get(w)[k] = get(w).get(k, 0) + v
for s in L:
    m = re.match(r'\[gsp-est\] vblanks=(\d+).*swaps=(\d+)', s)
    if m:
        vb = int(m.group(1)); w = vb // W
        delta(w, 'vb', vb); delta(w, 'sw', int(m.group(2))); continue
    w = vb // W
    m = re.match(r'\[raster\] dibujo (\d+):.*tiempo dibujar ([\d.]+) s, bajar ([\d.]+)', s)
    if m: delta(w, 'dib', int(m.group(1))); delta(w, 'tdib', float(m.group(2))); delta(w, 'tbaj', float(m.group(3))); continue
    m = re.match(r'\[raster\]\s+tramos: programa ([\d.]+) vertices ([\d.]+) texturas ([\d.]+) luts ([\d.]+).*uniforms ([\d.]+) envio ([\d.]+);.*texturas subidas (\d+), fs (\d+), programas (\d+); bajar (\d+) veces.*diferidos (\d+) \(esperaron (\d+): leer (\d+) escribir (\d+) transfer (\d+) llena (\d+).*\) ([\d.]+) s', s)
    if m:
        g = m.groups()
        for k, v in zip(['prog','vert','tex','lut','unif','envio'], g[:6]): delta(w, k, float(v))
        for k, v in zip(['texsub','fs','progs','bajar','dif','esp','espL','espE','espT','llena'], g[6:16]): delta(w, k, int(v))
        delta(w, 'ttot', float(g[16])); continue
    m = re.search(r'rechazados: (\d+) por alineacion, (\d+) por subida', s)
    if m: delta(w, 'rechA', int(m.group(1))); delta(w, 'rechS', int(m.group(2))); continue
    if 'sin DXIL' in s: add(w, 'sin'); continue
    m = re.search(r'(\d+) PSO nuevos esta corrida', s)
    if m: delta(w, 'pso', int(m.group(1))); continue
    m = re.match(r'\[alto-pres\] \d+ refrescos .*: (\d+) con imagen repetida', s)
    if m: delta(w, 'rep', int(m.group(1))); continue
    m = re.match(r'\[alto-pres\] (\d+) tics sin presentar', s)
    if m: delta(w, 'tics', int(m.group(1))); continue
    m = re.match(r'\[alto-paso\] refrescos .*error medio del paso ([\d.]+) %, repetidas (\d+), dobles (\d+)', s)
    if m: get(w)['paso'] = m.group(1)+'/'+m.group(2)+'/'+m.group(3); continue
    m = re.match(r'\[alto\] (\d+) cuadros.*, (\d+) sin intermedios; tanda media ([\d.]+) ms', s)
    if m: delta(w, 'sinint', int(m.group(2))); continue
    m = re.match(r'\[ritmo\] (\d+) vblanks: ([\d.]+) %', s)
    if m:
        n = int(m.group(1)); nuevos = float(m.group(2)) * n / 100; delta(w, 'rit_n', n); delta(w, 'rit_new', nuevos); continue
    if s.startswith('[captura] pantalla 0'):
        get(w).setdefault('cap', []).append(re.search(r'rgba0=(\w{6})', s).group(1))
cols = ['vb','dib','tdib','ttot','tex','lut','envio','texsub','progs','sin','pso','espL','espE','llena','rechA','rep','tics','sinint']
print('ventana  ' + ' '.join(f'{c:>7}' for c in cols) + '  ritmo  paso(err/rep/dob)  colores')
for w in sorted(acc):
    a = acc[w]
    def f(c):
        v = a.get(c, 0)
        return f'{v:7.2f}' if isinstance(v, float) else f'{v:7d}'
    rit = (a.get('rit_new', 0) / a['rit_n'] * 100) if a.get('rit_n') else 0
    print(f'{w*W:6d}+  ' + ' '.join(f(c) for c in cols) + f'  {rit:5.1f}  {a.get("paso",""):>14}  {",".join(sorted(set(a.get("cap",[]))))[:60]}')
