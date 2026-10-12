"""Referencia en Python del FRAGMENT LIGHTING del PICA200 (agente I, 8 oct 2026).

Reimplementa, en escalar y sin compartir codigo con luz_frag_glsl.py, la semantica del rasterizador por software
de Azahar (renderer_software/sw_lighting.cpp: ComputeFragmentsColors). Solo lectura de referencia (GPLv2).

Estado de entrada:
  cfg: dict de configs.json (cfg, clamp, geo0, geo1, fresnel, bump_modo, bump_tex, bump_renorm,
       luts = [[nombre, entrada, absoluta], ...] SOLO las activas)
  est: {"luces": [luz...], "ambiente_global": (r,g,b), "luts": {nombre: crudas256}, "escalas": {nombre: f},
        "sp": (entrada, absoluta, escala)}
       luz: {especular0, especular1, difusa, ambiente, posicion, spot_dir: vec3; direccional, dos_caras,
             usa_da, usa_sp: bool; da_escala, da_sesgo: float; da: crudas256; sp: crudas256}
  Las LUT van CRUDAS (palabras PICA de 32 bits): esta referencia las decodifica por su cuenta.
Salida: (primario rgba, secundario rgba) en u8 truncado (k/255), la convencion del TEV (agente G).
"""
import math

ENTRADAS = ("NH", "VH", "NV", "LN", "SP", "CP")


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _mul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return [a[0] / n, a[1] / n, a[2] / n] if n else [0.0, 0.0, 0.0]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def rotar(q, v):
    """Rotacion por cuaternion (x, y, z, w): v' = q v q*, escrita como producto de cuaterniones."""
    x, y, z, w = q
    # p = q * (v, 0)
    pw = -(x * v[0] + y * v[1] + z * v[2])
    px = w * v[0] + y * v[2] - z * v[1]
    py = w * v[1] + z * v[0] - x * v[2]
    pz = w * v[2] + x * v[1] - y * v[0]
    # p * conj(q), conj(q) = (-x, -y, -z, w)
    return [pw * -x + px * w + py * -z - pz * -y,
            pw * -y + py * w + pz * -x - px * -z,
            pw * -z + pz * w + px * -y - py * -x]


def entrada_lut(cruda):
    """Palabra PICA de LUT de luz -> (valor, diferencia). bits 0-11 valor 0.12, 12-22 |dif| 0.11, 23 signo."""
    v = (cruda & 0xFFF) / 4095.0
    d = ((cruda >> 12) & 0x7FF) / 2047.0
    return v, (-d if (cruda >> 23) & 1 else d)


def consultar(tabla, x, absoluta):
    if absoluta:
        f = math.floor(x * 256.0)
        i = min(max(f, 0), 255)
        delta = x * 256.0 - i
    else:
        f = math.floor(x * 128.0)
        s = min(max(f, -128), 127)
        delta = x * 128.0 - s
        i = s & 0xFF
    v, d = entrada_lut(tabla[i])
    return v + d * delta


def iluminar(cfg, est, normquat, vista, tex):
    c = cfg["cfg"]
    activas = {n: (e, a) for n, e, a in cfg["luts"]}
    # superficie
    if cfg["bump_modo"]:
        t = tex[cfg["bump_tex"]]
        pert = [t[0] * 2.0 - 1.0, t[1] * 2.0 - 1.0, t[2] * 2.0 - 1.0]
        if cfg["bump_modo"] == 1:
            if cfg["bump_renorm"]:
                pert[2] = math.sqrt(max(1.0 - pert[0] * pert[0] - pert[1] * pert[1], 0.0))
            sn, st = pert, [1.0, 0.0, 0.0]
        else:
            sn, st = [0.0, 0.0, 1.0], pert
    else:
        sn, st = [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]
    qn = math.sqrt(sum(k * k for k in normquat))
    q = [k / qn for k in normquat]
    normal, tangente = rotar(q, sn), rotar(q, st)
    nv = _norm(vista)
    dif = [0.0, 0.0, 0.0, 1.0]
    esp = [0.0, 0.0, 0.0, 1.0]
    luces = est["luces"]
    for idx, L in enumerate(luces):
        lv = list(L["posicion"]) if L["direccional"] else _add(L["posicion"], vista)
        dist = math.sqrt(_dot(lv, lv))
        lv = _norm(lv)
        h = _add(nv, lv)
        hn = _norm(h)

        def x_de(e):
            if e == "NH":
                return _dot(normal, hn)
            if e == "VH":
                return _dot(nv, hn)
            if e == "NV":
                return _dot(normal, nv)
            if e == "LN":
                return _dot(lv, normal)
            if e == "SP":
                return _dot(lv, L["spot_dir"])
            if e == "CP" and c == 8:
                proy = [hn[k] - normal[k] * _dot(normal, hn) for k in range(3)]
                return _dot(proy, tangente)
            return 0.0

        def lut(tabla, e, absoluta, escala):
            x = x_de(e)
            if absoluta:
                x = abs(x) if L["dos_caras"] else max(x, 0.0)
            return escala * consultar(tabla, x, absoluta)

        def mat_lut(n):
            e, a = activas[n]
            return lut(est["luts"][n], e, a, est["escalas"][n])

        da = 1.0
        if L["usa_da"]:
            s = min(max(L["da_escala"] * dist + L["da_sesgo"], 0.0), 1.0)
            da = consultar(L["da"], s, True)
        sp = 1.0
        if L["usa_sp"] and c not in (2, 3):
            e, a, esc = est["sp"]
            sp = lut(L["sp"], e, a, esc)
        d0 = mat_lut("D0") if "D0" in activas else 1.0
        rr = mat_lut("RR") if "RR" in activas else 1.0
        rg = mat_lut("RG") if "RG" in activas else rr
        rb = mat_lut("RB") if "RB" in activas else rr
        d1 = mat_lut("D1") if "D1" in activas else 1.0
        s0 = _mul(L["especular0"], d0)
        s1 = [d1 * rr * L["especular1"][0], d1 * rg * L["especular1"][1], d1 * rb * L["especular1"][2]]
        if idx == len(luces) - 1 and "FR" in activas and cfg["fresnel"]:
            fr = mat_lut("FR")
            if cfg["fresnel"] & 1:
                dif[3] = fr
            if cfg["fresnel"] & 2:
                esp[3] = fr
        nl = _dot(lv, normal)
        nl = abs(nl) if L["dos_caras"] else max(nl, 0.0)
        ch = (0.0 if nl == 0.0 else 1.0) if cfg["clamp"] else 1.0
        if cfg["geo0"] or cfg["geo1"]:
            g = _dot(h, h)
            g = 0.0 if g == 0.0 else min(nl / g, 1.0)
            if cfg["geo0"]:
                s0 = _mul(s0, g)
            if cfg["geo1"]:
                s1 = _mul(s1, g)
        for k in range(3):
            dif[k] += (L["difusa"][k] * nl + L["ambiente"][k]) * da * sp
            esp[k] += (s0[k] + s1[k]) * ch * da * sp
    for k in range(3):
        dif[k] += est["ambiente_global"][k]
    # u8 truncado: static_cast<u8>(clamp(x, 0, 1) * 255) del rasterizador por software
    cl = lambda v: [math.floor(min(max(k, 0.0), 1.0) * 255.0) / 255.0 for k in v]  # noqa: E731
    return cl(dif), cl(esp)
