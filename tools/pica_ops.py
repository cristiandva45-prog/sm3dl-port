"""Semantica de las operaciones aritmeticas del shader PICA200 (compartida por shader_ref.py y shader_glsl.py).

Leida de Azahar (src\\video_core\\shader\\shader_interpreter.cpp y pica_types.h), reescrita:
  - mul: 0 * inf = 0 (el PICA no da NaN si ningun factor es NaN). Vale tambien dentro de dp3/dp4/dph y mad.
  - max/min: forma exacta (a > b ? a : b), que fija el resultado con NaN.
  - rcp/rsq/ex2/lg2: solo la componente x de la fuente, replicada a las 4.
  - Lectura de c[] con indice relativo: offset fuera de s8 -> 0; indice & 0x7F; >= 96 -> (1,1,1,1).
Floats de Python (doble precision): el PICA usa float24, la PC usara float32; aqui solo se compara la LOGICA.
"""
import math

NAN = float("nan")


def es_nan(x):
    return x != x


def pmul(a, b):
    r = a * b
    if es_nan(r) and not es_nan(a) and not es_nan(b):
        return 0.0
    return r


def rcp(x):
    if x == 0:
        return math.copysign(math.inf, x)
    return 1.0 / x


def rsq(x):
    if es_nan(x) or x < 0:
        return NAN
    if x == 0:
        return math.inf
    return 1.0 / math.sqrt(x)


def ex2(x):
    try:
        return 2.0 ** x
    except OverflowError:
        return math.inf


def lg2(x):
    if es_nan(x) or x < 0:
        return NAN
    if x == 0:
        return -math.inf
    return math.log2(x)


def flr(x):
    if es_nan(x) or math.isinf(x):
        return x
    return float(math.floor(x))


CMPS = [lambda a, b: a == b, lambda a, b: a != b, lambda a, b: a < b,
        lambda a, b: a <= b, lambda a, b: a > b, lambda a, b: a >= b]


def aritmetica(op, s):
    """Resultado (4 componentes) de una operacion aritmetica sobre las fuentes ya leidas."""
    a = s[0]
    b = s[1] if len(s) > 1 else None
    if op == "add":
        return [x + y for x, y in zip(a, b)]
    if op == "mul":
        return [pmul(x, y) for x, y in zip(a, b)]
    if op in ("dp3", "dp4", "dph", "dphi"):
        a = list(a)
        if op in ("dph", "dphi"):
            a[3] = 1.0
        n = 3 if op == "dp3" else 4
        d = 0.0
        for k in range(n):
            d = d + pmul(a[k], b[k])
        return [d] * 4
    if op == "max":
        return [x if x > y else y for x, y in zip(a, b)]
    if op == "min":
        return [x if x < y else y for x, y in zip(a, b)]
    if op in ("sge", "sgei"):
        return [1.0 if x >= y else 0.0 for x, y in zip(a, b)]
    if op in ("slt", "slti"):
        return [1.0 if x < y else 0.0 for x, y in zip(a, b)]
    if op == "flr":
        return [flr(x) for x in a]
    if op == "rcp":
        return [rcp(a[0])] * 4
    if op == "rsq":
        return [rsq(a[0])] * 4
    if op == "ex2":
        return [ex2(a[0])] * 4
    if op == "lg2":
        return [lg2(a[0])] * 4
    if op == "mov":
        return list(a)
    if op in ("mad", "madi"):
        return [pmul(x, y) + z for x, y, z in zip(a, b, s[2])]
    raise NotImplementedError(op)


class Estado:
    """Registros de una invocacion del shader."""

    def __init__(self, v, c, i, b):
        self.v = [list(x) for x in v]          # 16 entradas
        self.c = [list(x) for x in c]          # 96 uniforms float (ya con las constantes del DVLE)
        self.i = [list(x) for x in i]          # 4 uniforms int (x=cuenta, y=inicio, z=paso)
        self.b = list(b)                       # 16 uniforms bool
        self.r = [[0.0] * 4 for _ in range(16)]
        self.o = [[0.0] * 4 for _ in range(16)]
        self.a = [0, 0, 0]                     # a0.x, a0.y, aL
        self.cc = [False, False]

    def leer(self, f):
        reg, idx, sw, neg = f
        if reg < 0x10:
            base = self.v[reg]
        elif reg < 0x20:
            base = self.r[reg - 0x10]
        else:
            k = reg - 0x20
            if idx:
                off = self.a[idx - 1]
                if off < -128 or off > 127:
                    off = 0
                k = (k + off) & 0x7F
            base = self.c[k] if k < 96 else [1.0] * 4
        val = [base["xyzw".index(ch)] for ch in sw]
        return [-x for x in val] if neg else val

    def ejecutar(self, op, dst, mascara, fuentes, ins):
        s = [self.leer(f) for f in fuentes]
        if op == "cmp":
            self.cc = [CMPS[ins["cmpx"]](s[0][0], s[1][0]), CMPS[ins["cmpy"]](s[0][1], s[1][1])]
            return
        if op == "mova":
            for k in range(2):
                if mascara & (8 >> k):
                    x = s[0][k]
                    self.a[k] = 0 if es_nan(x) or math.isinf(x) else int(x)
            return
        res = aritmetica(op, s)
        if dst < 0x10:
            d = self.o[dst]
        elif dst < 0x20:
            d = self.r[dst - 0x10]
        else:
            return
        for k in range(4):
            if mascara & (8 >> k):
                d[k] = res[k]
