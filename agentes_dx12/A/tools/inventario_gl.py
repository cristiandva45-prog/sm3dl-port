r"""Inventario de llamadas GL: antes (raster_gl.c + presentador_gl.inc respaldados) vs despues (raster_backend_gl.c).
Cuenta cada gl.X / glX. Con --por-funcion lista tambien la funcion C que la contiene.
Uso (desde la raiz): py -I agentes_dx12\A\tools\inventario_gl.py [--por-funcion]"""
import re, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from util import rd
R = 'recomp/render/'


def llamadas(texto):
    t = re.sub(r'/\*.*?\*/', '', texto, flags=re.S)           # comentarios
    t = re.sub(r'//[^\n]*', '', t)
    t = re.sub(r'"(?:\\.|[^"\\])*"', '""', t)                 # cadenas
    cont = collections.Counter()
    por_fn = collections.defaultdict(collections.Counter)
    fn = '(global)'
    for linea in t.split('\n'):
        m = re.match(r'^(?:static\s+|const\s+|struct\s+)*[A-Za-z_][\w \*]*?\b([A-Za-z_]\w*)\(.*\)\s*\{?\s*$', linea)
        if m and not linea.startswith((' ', '\t', '#')) and not linea.rstrip().endswith(';'):
            fn = m.group(1)
        for a, b in re.findall(r'\bgl\.([A-Z]\w*)\(|\b(gl[A-Z]\w*)\(', linea):
            n = a or b[2:]
            cont[n] += 1
            por_fn[fn][n] += 1
    return cont, por_fn


antes = rd(R + 'raster_gl.c.antes_dx12_A') + '\n' + rd(R + 'presentador_gl.inc.antes_dx12_A')
despues = rd(R + 'raster_backend_gl.c')
a, fa = llamadas(antes)
d, fd = llamadas(despues)
print('%-26s %6s %6s' % ('llamada GL', 'antes', 'despues'))
for n in sorted(set(a) | set(d)):
    print('%-26s %6d %6d%s' % (n, a[n], d[n], '' if a[n] == d[n] else '   <- distinto'))
print('TOTAL antes %d (%d distintas), despues %d (%d distintas)' % (sum(a.values()), len(a), sum(d.values()), len(d)))
print('\nSolo en antes:', sorted(set(a) - set(d)), '\nSolo en despues:', sorted(set(d) - set(a)))
if '--por-funcion' in sys.argv:
    print('\n== ANTES por funcion')
    for f, c in fa.items():
        print(f, dict(c))
    print('\n== DESPUES por funcion')
    for f, c in fd.items():
        print(f, dict(c))
