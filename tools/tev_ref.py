"""Modelo de referencia del combinador TEV del PICA200 (6 etapas), escrito desde la semantica del rasterizador por
software de Azahar (renderer_software/sw_texturing.cpp + sw_rasterizer.cpp WriteTevConfig) y regs_texturing.h.
NO deriva de tev_glsl.py: es la otra mitad del verificador diferencial (tools/probar_tev.py).

Todo en enteros u8 (0..255), como el hardware:
  - modificadores: x o 255-x por canal (rgb, aaa, rrr, ggg, bbb / a, r, g, b)
  - operaciones con su propia saturacion (ADD min 255, SUB max 0, ADDS clamp(a+b-128), MULADD min(.,255) ...),
    divisiones /255 TRUNCADAS
  - escala x1/x2/x4 (3 = x1) aplicada despues y saturada a 255
  - DOT3_RGB/RGBA: suma de ((2a-255)(2b-255)+128)/256 por canal, clamp 0..255; RGBA copia el resultado al alfa
  - buffer del combinador: 'buffer' (lo que lee la fuente 0xD) arranca en 0; 'siguiente' arranca en tev_buffer_color.
    Tras cada etapa: buffer = siguiente; luego si la etapa (0..3) tiene su bit en 0x0E0 (rgb bits 8-11, alfa 12-15)
    siguiente.{rgb|a} = salida. => la etapa k lee lo que dejaron las etapas 0..k-2; la etapa 0 lee 0, la 1 lee el color.
  - etapa 0: si la fuente de color 1 o 2 es "previo", se usa la fuente 3 (peculiaridad copiada por Azahar del hw).
  - previo arranca en (0,0,0,0).
modo='real': misma semantica sin truncar las divisiones (para separar errores de semantica de los de redondeo).
"""

MOD_RGB = {0: ("rgb", False), 1: ("rgb", True), 2: ("aaa", False), 3: ("aaa", True), 4: ("rrr", False),
           5: ("rrr", True), 8: ("ggg", False), 9: ("ggg", True), 0xC: ("bbb", False), 0xD: ("bbb", True)}
MOD_A = {0: ("a", False), 1: ("a", True), 2: ("r", False), 3: ("r", True), 4: ("g", False), 5: ("g", True),
         6: ("b", False), 7: ("b", True)}
IDX = {"r": 0, "g": 1, "b": 2, "a": 3}


class NoModelado(Exception):
    pass


def _div(x, d, real):
    return x / d if real else int(x) // d


def mod_color(m, v):
    if m not in MOD_RGB:
        raise NoModelado(f"modificador rgb {m}")
    sw, inv = MOD_RGB[m]
    out = [v[IDX[c]] for c in sw]
    return [255 - x for x in out] if inv else out


def mod_alfa(m, v):
    c, inv = MOD_A[m & 7]
    x = v[IDX[c]]
    return 255 - x if inv else x


def op_canal(op, a, b, c, real):
    """Una operacion sobre un canal (sirve igual para rgb y alfa salvo DOT3, que va aparte)."""
    if op == 0:
        return a
    if op == 1:
        return _div(a * b, 255, real)
    if op == 2:
        return min(255, a + b)
    if op == 3:
        return max(0, min(255, a + b - 128))
    if op == 4:
        return _div(a * c + b * (255 - c), 255, real)
    if op == 5:
        return max(0, a - b)
    if op == 8:
        return min(255, _div(a * b + 255 * c, 255, real))
    if op == 9:
        return _div(min(255, a + b) * c, 255, real)
    raise NoModelado(f"operacion {op}")


def dot3(a, b, real):
    if real:
        s = sum(4 * (x - 127.5) * (y - 127.5) / 255 for x, y in zip(a, b))
    else:
        s = 0
        for x, y in zip(a, b):
            p = (x * 2 - 255) * (y * 2 - 255) + 128
            s += int(p / 256)  # division entera de C (trunca hacia 0)
    return max(0, min(255, s))


def escala(e):
    return 1 << e if e < 3 else 1


def correr(firma, ent, modo="int", trazar=None, variante=()):
    """firma: 6 tuplas (fuente, operando, combinador, escala) (registros 0xC0+8k .. como pica_cmd.firma_tev).
    ent: dict con listas u8 de 4: vtx, prim, sec, t0, t1, t2, t3, buf (tev_buffer_color), const (6 de 4);
         update: int (registro 0x0E0, se usan bits 8-15).
    Devuelve [r,g,b,a] (int en modo 'int', float 0..255 en modo 'real').
    variante: SOLO diagnostico (probar_tev clasifica diferencias), hipotesis alternativas que NO son la semantica:
      'buf0_color' la etapa 0 lee tev_buffer_color;  'sin_peculiaridad0' sin la sustitucion previo->fuente3;
      'paso_salta' una etapa REPLACE(previo) no aplica escala ni actualiza el buffer."""
    real = modo == "real"
    salida = [0, 0, 0, 0]
    buffer = list(ent["buf"]) if "buf0_color" in variante else [0, 0, 0, 0]
    siguiente = list(ent["buf"])
    for k, (s, o, c, e) in enumerate(firma):
        def fuente(n):
            if n == 0:
                return ent["vtx"]
            if n == 1:
                return ent["prim"]
            if n == 2:
                return ent["sec"]
            if 3 <= n <= 6:
                return ent[f"t{n - 3}"]
            if n == 0xD:
                return buffer
            if n == 0xE:
                return ent["const"][k]
            if n == 0xF:
                return salida
            raise NoModelado(f"fuente {n:X}")
        src_c = [(s >> sh) & 0xF for sh in (0, 4, 8)]
        src_a = [(s >> sh) & 0xF for sh in (16, 20, 24)]
        paso = (c & 0xF == 0 and (c >> 16) & 0xF == 0 and s & 0xF == 0xF and (s >> 16) & 0xF == 0xF
                and o & 0xF == 0 and (o >> 12) & 7 == 0)
        if paso and "paso_salta" in variante:
            buffer = list(siguiente)
            continue
        if k == 0 and "sin_peculiaridad0" not in variante:
            src_c = [src_c[2] if (j < 2 and src_c[j] == 0xF) else src_c[j] for j in range(3)]
        mc = [(o >> sh) & 0xF for sh in (0, 4, 8)]
        ma = [(o >> sh) & 0x7 for sh in (12, 16, 20)]
        op_c, op_a = c & 0xF, (c >> 16) & 0xF
        ac = [mod_color(mc[j], fuente(src_c[j])) for j in range(3)]
        if op_c in (6, 7):
            v = dot3(ac[0], ac[1], real)
            col = [v, v, v]
        else:
            col = [op_canal(op_c, ac[0][i], ac[1][i], ac[2][i], real) for i in range(3)]
        if op_c == 7:
            alf = col[0]
        else:
            if op_a in (6, 7):
                raise NoModelado("dot3 en el combinador de alfa (Azahar: UNIMPLEMENTED)")
            aa = [mod_alfa(ma[j], fuente(src_a[j])) for j in range(3)]
            alf = op_canal(op_a, aa[0], aa[1], aa[2], real)
        ec, ea = escala(e & 3), escala((e >> 16) & 3)
        salida = [min(255, x * ec) for x in col] + [min(255, alf * ea)]
        buffer = list(siguiente)
        if k < 4:
            if ent["update"] >> (8 + k) & 1:
                siguiente[0:3] = salida[0:3]
            if ent["update"] >> (12 + k) & 1:
                siguiente[3] = salida[3]
        if trazar is not None:
            trazar.append((k, list(salida), list(buffer)))
    return salida


if __name__ == "__main__":
    # autoprueba minima: MODULATE(t0, vtx) en rgb y alfa, resto paso
    paso = (0x00F000F, 0, 0, 0)
    f = [(0x0030003 | (0x0000000), 0, 1 | (1 << 16), 0)] + [paso] * 5
    f[0] = (0x3 | (0x0 << 4) | (0x3 << 16) | (0x0 << 20), 0, 1 | (1 << 16), 0)
    ent = dict(vtx=[255, 128, 0, 255], prim=[0] * 4, sec=[0] * 4, t0=[128, 128, 128, 64], t1=[0] * 4, t2=[0] * 4,
               t3=[0] * 4, buf=[0] * 4, const=[[0] * 4] * 6, update=0)
    print(correr(f, ent), correr(f, ent, "real"))
