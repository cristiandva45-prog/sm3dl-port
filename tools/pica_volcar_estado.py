"""Prueba diferencial del interprete PICA en C (recomp\\render\\pica.c) contra un modelo en Python.

Arma casos (listas de comandos) y los guarda en un .bin; el modelo de aqui calcula el volcado esperado; el
ejecutable prueba_pica.exe ejecuta los mismos casos en C y vuelca su estado; se comparan linea a linea.

Casos:
  - materiales: los BYTES REALES de las cachés de comandos de cada material CGFX (cabecera + parametro0 + extras,
    tal como estan en el archivo; los localiza tools\\pica_cmd.py). Deduplicados por contenido.
  - shaders: subida de codigo, swizzles y constantes (bool/int/float24) reales de los DVLB extraidos
    (extraido\\shaders\\*.shbin), en modo consecutivo y no consecutivo, + uniforms float32.
  - sinteticos: mascaras de bytes, valores float24 especiales, saltos CMDBUF_JUMP, FINALIZE/IRQ, atributos fijos,
    LUTs, configuracion de vertices + DRAWELEMENTS / DRAWARRAYS.
El banco de registros tambien se contrasta con pica_cmd.parsear + pica_cmd.estado (fuera de los registros con
efecto lateral).

Uso:
  py -I tools\\pica_volcar_estado.py [--max N] [--exe ruta] [--compilar] [--sabotaje MASCARA|F24]
"""
import glob
import math
import os
import struct
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(RAIZ, "tools"))
import pica_cmd  # noqa: E402

RENDER = os.path.join(RAIZ, "recomp", "render")
SALIDA = os.path.join(RAIZ, "extraido", "pica_prueba")

# ---------------------------------------------------------------- utilidades
def u32(x):
    return x & 0xFFFFFFFF


def f32bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def f24bits(v):
    """float24 (1.7.16, sesgo 63) -> bits float32. Escrito por formula (no por desplazamiento de bits)."""
    v &= 0xFFFFFF
    s = v >> 23
    e = (v >> 16) & 0x7F
    m = v & 0xFFFF
    if e == 0x7F:  # inf / NaN: el payload pasa tal cual a la mantisa de float32
        return (s << 31) | (0xFF << 23) | (m << 7)
    if e == 0:
        val = m * 2.0 ** (1 - 63 - 16)  # denormal (0 si m == 0)
    else:
        val = (1 + m / 65536) * 2.0 ** (e - 63)
    return f32bits(-val if s else val)


def mult2bits(b):
    """bits de 2*x (para el viewport); x viene en bits float32."""
    x = struct.unpack("<f", struct.pack("<I", b))[0]
    if math.isnan(x):
        return b  # NaN*2 = el mismo NaN (silencioso; los payloads del juego no llegan aqui)
    return f32bits(2 * x)


def fnv(ws):
    h = 2166136261
    for w in ws:
        for j in range(4):
            h ^= (w >> (8 * j)) & 0xFF
            h = (h * 16777619) & 0xFFFFFFFF
    return h


def expandir(m):
    return sum(0xFF << 8 * k for k in range(4) if m >> k & 1)


def bits(v, lo, n):
    return (v >> lo) & ((1 << n) - 1)


def cmd(reg, valores, mask=0xF, consecutivo=False):
    """Un comando PICA en palabras (rellenado a 8 bytes)."""
    ext = len(valores) - 1
    assert 0 <= ext <= 255
    w = [valores[0], reg | (mask << 16) | (ext << 20) | (0x80000000 if consecutivo else 0)] + list(valores[1:])
    if len(w) & 1:
        w.append(0)
    return w


# ---------------------------------------------------------------- modelo
R_VSH, R_GSH = 0x2B0, 0x280


class Shader:
    def __init__(self):
        self.f = [(0, 0, 0, 0)] * 96
        self.i = [[0] * 4 for _ in range(4)]
        self.b = 0
        self.cod = [0] * 4096
        self.swz = [0] * 4096
        self.cola = []


class Modelo:
    def __init__(self, mem=None):
        self.r = [0] * 0x300
        self.vs, self.gs = Shader(), Shader()
        self.fijo = [(0, 0, 0, 0)] * 16
        self.cola_fijo = []
        self.luz = [[0] * 256 for _ in range(24)]
        self.niebla = [0] * 128
        self.dib = self.irq = self.cmds = self.err = 0
        self.mem = mem or {}
        self.out = []
        self.parar = False
        self.salto = None

    def sin_gs(self):
        return (self.r[0x244] & 1) == 0 and (self.r[0x229] & 3) != 2

    @staticmethod
    def desempacar(c):
        x = c[2] & 0xFFFFFF
        y = ((c[1] & 0xFFFF) << 8) | (c[2] >> 24)
        z = ((c[0] & 0xFF) << 16) | (c[1] >> 16)
        w = c[0] >> 8
        return tuple(f24bits(t) for t in (x, y, z, w))

    def shader(self, reg, valor):
        vs = reg >= R_VSH
        base = R_VSH if vs else R_GSH
        s = self.vs if vs else self.gs
        espejo = vs and self.sin_gs()
        k = reg - base
        if k == 0:
            s.b = self.r[reg] & 0xFFFF
            if espejo:
                self.gs.b = s.b
        elif 1 <= k <= 4:
            v = self.r[reg]
            s.i[k - 1] = [(v >> 8 * j) & 0xFF for j in range(4)]
            if espejo:
                self.gs.i[k - 1] = list(s.i[k - 1])
        elif k == 0xD:
            if espejo:
                self.r[R_GSH + 0xD] = self.r[reg]
        elif 0x11 <= k <= 0x18:
            ir = base + 0x10
            f32 = self.r[ir] >> 31
            s.cola.append(valor)
            if len(s.cola) < (4 if f32 else 3):
                return
            c, s.cola = s.cola, []
            v = (c[3], c[2], c[1], c[0]) if f32 else self.desempacar(c)
            idx = self.r[ir] & 0x7F
            if idx >= 96:
                return
            s.f[idx] = v
            if espejo:
                self.gs.f[idx] = v
            self.r[ir] = (self.r[ir] & ~0x7F) | ((idx + 1) & 0x7F)
        elif 0x1C <= k <= 0x23 or 0x26 <= k <= 0x2D:
            swz = k >= 0x26
            oreg = base + (0x25 if swz else 0x1B)
            lim = 4096 if swz or not vs else 512
            off = self.r[oreg]
            if off >= lim:
                self.err += 1
                return
            (s.swz if swz else s.cod)[off] = valor
            if espejo:
                (self.gs.swz if swz else self.gs.cod)[off] = valor
            self.r[oreg] = u32(off + 1)

    def escribir(self, reg, valor, mask):
        if reg >= 0x300:
            self.err += 1
            return
        m = expandir(mask)
        self.r[reg] = (self.r[reg] & ~m & 0xFFFFFFFF) | (valor & m)
        self.cmds += 1
        r = self.r
        if reg == 0x010:
            a, b = r[0x010], r[0x020]
            if any(((a ^ b) >> 8 * j) & 0xFF == 0 for j in range(4)):
                self.irq += 1
                if r[0x034] & 1:
                    self.parar = True
        elif 0x0E8 <= reg <= 0x0EF:
            i = r[0x0E6] & 0xFFFF
            self.niebla[i % 128] = valor
            r[0x0E6] = (r[0x0E6] & ~0xFFFF) | ((i + 1) & 0xFFFF)
        elif 0x1C8 <= reg <= 0x1CF:
            i, t = r[0x1C5] & 0xFF, (r[0x1C5] >> 8) & 0x1F
            if t < 24:
                self.luz[t][i] = valor
            else:
                self.err += 1
            r[0x1C5] = (r[0x1C5] & ~0xFF) | ((i + 1) & 0xFF)
        elif reg == 0x232:
            self.cola_fijo = []
        elif 0x233 <= reg <= 0x235:
            self.cola_fijo.append(valor)
            if len(self.cola_fijo) == 3:
                c, self.cola_fijo = self.cola_fijo, []
                i = r[0x232] & 0xF
                if i < 15:
                    self.fijo[i] = self.desempacar(c)
                    r[0x232] = (r[0x232] & ~0xF) | (i + 1)
                else:
                    self.err += 1
        elif reg in (0x22E, 0x22F):
            self.dib += 1
            self.out.append(f"== dibujo {self.dib}")
            self.out += self.volcado()
        elif reg in (0x23C, 0x23D):
            c = reg - 0x23C
            dir_ = (r[0x23A + c] & 0x0FFFFFFF) * 8
            tam = (r[0x238 + c] & 0xFFFFF) * 8
            if dir_ in self.mem and tam <= 4 * len(self.mem[dir_]):
                self.salto = self.mem[dir_][:tam // 4]
            else:
                self.err += 1
                self.parar = True
        elif 0x280 <= reg < 0x2E0:
            k = (reg - 0x280) % 0x30
            if k == 0 or 1 <= k <= 4 or (k == 0xD and reg >= R_VSH) or 0x11 <= k <= 0x18 or 0x1C <= k <= 0x23 \
                    or 0x26 <= k <= 0x2D:
                self.shader(reg, valor)

    def ejecutar(self, w):
        k = 0
        while not self.parar:
            if self.salto is not None:
                w, self.salto, k = self.salto, None, 0
            if k + 2 > len(w):
                break
            p0, h = w[k], w[k + 1]
            reg, mask, ext, seq = h & 0xFFFF, (h >> 16) & 0xF, (h >> 20) & 0xFF, h >> 31
            if k + 2 + ext > len(w):
                self.err += 1
                break
            ex = w[k + 2:k + 2 + ext]
            n = 2 + ext
            k += n + (n & 1)
            self.escribir(reg, p0, mask)
            for j, v in enumerate(ex):
                if self.parar or self.salto is not None:
                    break
                self.escribir(reg + 1 + j if seq else reg, v, mask)
        return 1 if self.parar else 0

    # ---------------- volcado (mismo texto que prueba_pica.c) ----------------
    def volcado(self):
        r, o = self.r, []
        sx = lambda v, n: v - (1 << n) if v >> (n - 1) & 1 else v  # noqa: E731
        o.append(f"rast cull={r[0x40] & 3} vp={mult2bits(f24bits(r[0x41])):08X},{mult2bits(f24bits(r[0x43])):08X} "
                 f"xy={sx(bits(r[0x68], 0, 10), 10)},{sx(bits(r[0x68], 16, 10), 10)} "
                 f"dz={f24bits(r[0x4D]):08X},{f24bits(r[0x4E]):08X} dmap={r[0x6D] & 1} sc={r[0x65] & 3} "
                 f"{r[0x66] & 0x3FF},{bits(r[0x66], 16, 10)},{r[0x67] & 0x3FF},{bits(r[0x67], 16, 10)}")
        esc = [1, 2, 4, 1]
        for k, b in enumerate((0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8)):
            s, op, c, col, e = r[b:b + 5]
            o.append(f"tev{k} src={''.join('%X' % bits(s, 4 * j, 4) for j in range(3))}/"
                     f"{''.join('%X' % bits(s, 16 + 4 * j, 4) for j in range(3))} "
                     f"op={''.join('%X' % bits(op, 4 * j, 4) for j in range(3))}/"
                     f"{''.join('%X' % bits(op, 12 + 4 * j, 3) for j in range(3))} "
                     f"comb={c & 0xF:X}/{bits(c, 16, 4):X} k={col:08X} esc={esc[e & 3]}/{esc[bits(e, 16, 2)]}")
        o.append(f"buf niebla={r[0xE0] & 7} rgb={bits(r[0xE0], 8, 4):X} a={bits(r[0xE0], 12, 4):X} color={r[0xFD]:08X}")
        b1, at, st, so, dc = r[0x101], r[0x104], r[0x105], r[0x106], r[0x107]
        o.append(f"frag modo={r[0x100] & 3} blend={bits(r[0x100], 8, 1)} eq={b1 & 7}/{bits(b1, 8, 3)} "
                 f"f={bits(b1, 16, 4)},{bits(b1, 20, 4)},{bits(b1, 24, 4)},{bits(b1, 28, 4)} lop={r[0x102] & 0xF} "
                 f"bc={r[0x103]:08X} at={at & 1},{bits(at, 4, 3)},{bits(at, 8, 8)} "
                 f"st={st & 1},{bits(st, 4, 3)},{bits(st, 16, 8)},{bits(st, 8, 8):02X},{bits(st, 24, 8):02X} "
                 f"op={so & 7},{bits(so, 4, 3)},{bits(so, 8, 3)} dt={dc & 1},{bits(dc, 4, 3)},{bits(dc, 12, 1)} "
                 f"cm={bits(dc, 8, 4):X}")
        o.append(f"fb c={(r[0x11D] & 0x0FFFFFFF) * 8 & 0xFFFFFFFF:08X} d={(r[0x11C] & 0x0FFFFFFF) * 8 & 0xFFFFFFFF:08X} "
                 f"fmt={bits(r[0x117], 16, 3)}/{r[0x116] & 3} {r[0x11E] & 0x7FF}x{bits(r[0x11E], 12, 10) + 1} "
                 f"flip={bits(r[0x11E], 24, 1)} rw={int(r[0x112] & 0xF != 0)}{int(r[0x113] & 0xF != 0)}"
                 f"{int(r[0x114] & 3 != 0)}{int(r[0x115] & 3 != 0)}")
        for k, (bd, dm, pa, lo, ad, ti) in enumerate(((0x81, 0x82, 0x83, 0x84, 0x85, 0x8E),
                                                     (0x91, 0x92, 0x93, 0x94, 0x95, 0x96),
                                                     (0x99, 0x9A, 0x9B, 0x9C, 0x9D, 0x9E))):
            p = r[pa]
            o.append(f"tex{k} act={bits(r[0x80], k, 1)} dir={(r[ad] & 0x0FFFFFFF) * 8 & 0xFFFFFFFF:08X} "
                     f"{bits(r[dm], 16, 11)}x{r[dm] & 0x7FF} fmt={r[ti] & 0xF} "
                     f"filt={bits(p, 1, 1)}{bits(p, 2, 1)}{bits(p, 24, 1)} wrap={bits(p, 12, 3)},{bits(p, 8, 3)} "
                     f"tipo={bits(p, 28, 3)} borde={r[bd]:08X} lod={sx(r[lo] & 0x1FFF, 13)},{bits(r[lo], 24, 4)},"
                     f"{bits(r[lo], 16, 4)}")
        o.append(f"luz act={r[0x8F] & 1} n={(r[0x1C2] & 7) + 1} tex2c1={bits(r[0x80], 13, 1)} "
                 f"lut={fnv([x for t in self.luz for x in t]):08X} niebla={fnv(self.niebla):08X}")
        lo_, hi = r[0x201], r[0x202]
        fmt = "".join(f"{bits(lo_ if k < 8 else hi, 4 * (k & 7), 2)}{bits(lo_ if k < 8 else hi, 4 * (k & 7) + 2, 2) + 1}"
                      for k in range(12))
        o.append(f"vtx base={(r[0x200] & 0x1FFFFFFE) * 8 & 0xFFFFFFFF:08X} fijos={bits(hi, 16, 12):03X} "
                 f"total={bits(hi, 28, 4) + 1} fmt={fmt}")
        for k in range(12):
            a, c1, c2 = r[0x203 + 3 * k:0x206 + 3 * k]
            off, stride, n = a & 0x0FFFFFFF, bits(c2, 16, 8), bits(c2, 28, 4)
            if not off and not stride and not n:
                continue
            comp = "".join("%X" % bits(c1, 4 * j, 4) for j in range(8)) + \
                   "".join("%X" % bits(c2, 4 * j, 4) for j in range(4))
            o.append(f"loader{k} off={off:08X} stride={stride} n={n} comp={comp}")
        o.append(f"idx off={r[0x227] & 0x0FFFFFFF:08X} u16={r[0x227] >> 31} nv={r[0x228]} voff={r[0x22A]} "
                 f"topo={bits(r[0x25E], 8, 2)} gs={int(not self.sin_gs())}")
        for nom, s, base in (("vs", self.vs, R_VSH), ("gs", self.gs, R_GSH)):
            perm = "".join("%X" % bits(r[base + 0xB + (k >> 3)], 4 * (k & 7), 4) for k in range(16))
            ii = "".join(f"{a:02X}{b:02X}{c:02X}{d:02X} " for a, b, c, d in s.i)
            o.append(f"{nom} entrada={r[base + 0xA] & 0xFFFF} nent={(r[base + 9] & 0xF) + 1} "
                     f"omask={r[base + 0xD] & 0xFFFF:04X} b={s.b:04X} perm={perm} i={ii}"
                     f"cod={fnv(s.cod):08X} swz={fnv(s.swz):08X}")
            for k, v in enumerate(s.f):
                if any(v):
                    o.append(f"{nom} c{k} " + " ".join(f"{x:08X}" for x in v))
        for k, v in enumerate(self.fijo):
            if any(v):
                o.append(f"fijo{k} " + " ".join(f"{x:08X}" for x in v))
        return o


# ---------------------------------------------------------------- casos
def casos_materiales(maximo):
    """[(nombre, palabras)] con los bytes reales de las cachés de cada material (deduplicados)."""
    from concurrent.futures import ProcessPoolExecutor
    raiz = os.path.join(RAIZ, "extraido", "romfs")
    rutas = sorted(os.path.join(c, a) for sub in ("ObjectData", "StageData") for c, _, arch in
                   os.walk(os.path.join(raiz, sub)) for a in arch if a.endswith(".szs"))
    vistos, out = set(), []
    with ProcessPoolExecutor() as ex:
        for lote in ex.map(_listas_archivo, rutas, chunksize=8):
            for nom, w in lote:
                t = tuple(w)
                if t in vistos:
                    continue
                vistos.add(t)
                out.append((nom, w))
                if maximo and len(out) >= maximo:
                    return out
    return out


def _listas_archivo(ruta):
    out = []
    try:
        for narch, b in pica_cmd.cgfx_de(ruta):
            for nmod, nmat, m in pica_cmd.materiales(b):
                cmds = pica_cmd.comandos_material(b, m)
                w, vistos = [], set()
                for k, *_ in cmds:
                    if k in vistos:
                        continue
                    vistos.add(k)
                    h = struct.unpack_from("<I", b, k)[0]
                    ext = (h >> 20) & 0xFF
                    pal = [struct.unpack_from("<I", b, k - 4)[0], h] + \
                          [struct.unpack_from("<I", b, k + 4 + 4 * j)[0] for j in range(ext)]
                    if len(pal) & 1:
                        pal.append(0)
                    w += pal
                out.append((f"{os.path.basename(ruta)}/{nmat}", w))
    except Exception:  # noqa: BLE001
        pass
    return out


def constantes_crudas(d, o):
    c_off, c_n = struct.unpack_from("<2I", d, o + 0x18)
    out = []
    for k in range(c_n):
        e = o + c_off + 0x14 * k
        out.append((d[e], d[e + 2], struct.unpack_from("<4I", d, e + 4), bytes(d[e + 4:e + 8])))
    return out


def casos_shaders():
    import shbin
    out = []
    for p in sorted(glob.glob(os.path.join(RAIZ, "extraido", "shaders", "*.shbin"))):
        d = open(p, "rb").read()
        s = shbin.Shbin(d)
        n = struct.unpack_from("<I", d, 4)[0]
        offs = struct.unpack_from(f"<{n}I", d, 8)
        for j, (ent, o) in enumerate(zip(s.entradas, offs)):
            for consecutivo in (False, True):
                base = R_GSH if ent["tipo"] == "geometry" else R_VSH
                w = []
                w += cmd(base + 0x1B, [0])
                cod = s.codigo
                for a in range(0, len(cod), 128):  # trozos: no consecutivo = mismo registro DATA0
                    trozo = cod[a:a + 128]
                    w += cmd(base + 0x1C, trozo, consecutivo=consecutivo and len(trozo) <= 8)
                w += cmd(base + 0xF, [1])  # CODETRANSFER_END
                w += cmd(base + 0x25, [0])
                for a in range(0, len(s.desc), 100):
                    w += cmd(base + 0x26, s.desc[a:a + 100])
                w += cmd(base + 0xA, [0x7FFF0000 | ent["main"]])
                w += cmd(base + 0x9, [0xA0000000 | 7])
                w += cmd(base + 0xB, [0x76543210, 0xFEDCBA98], consecutivo=True)
                w += cmd(base + 0xD, [0x1F])
                bools = 0
                for t, reg, raw, by in constantes_crudas(d, o):
                    if t == 2:  # float24: 4 valores de 24 bits -> 3 palabras empaquetadas (w arriba)
                        x, y, z, ww = (v & 0xFFFFFF for v in raw)
                        pk = [u32((ww << 8) | (z >> 16)), u32(((z & 0xFFFF) << 16) | (y >> 8)),
                              u32(((y & 0xFF) << 24) | x)]
                        w += cmd(base + 0x10, [reg])
                        w += cmd(base + 0x11, pk, consecutivo=consecutivo)
                    elif t == 1:
                        w += cmd(base + 1 + (reg & 3), [by[0] | by[1] << 8 | by[2] << 16 | by[3] << 24])
                    else:
                        bools |= (by[0] != 0) << reg
                w += cmd(base + 0, [0x7FFF0000 | bools])
                out.append((f"shader {os.path.basename(p)} DVLE{j} cons={int(consecutivo)}", w))
    return out


def packf24(x, y, z, w):
    return [u32((w << 8) | (z >> 16)), u32(((z & 0xFFFF) << 16) | (y >> 8)), u32(((y & 0xFF) << 24) | x)]


def casos_sinteticos():
    out = []
    # 1) mascaras: el mismo registro escrito por partes
    w = []
    for m in range(16):
        w += cmd(0x101, [0x11223344 * (m + 1) & 0xFFFFFFFF], mask=m)
        w += cmd(0x0C0 + (m % 5), [0xA5A5A5A5 ^ (m * 0x01010101)], mask=m)
    w += cmd(0x0C0, [0x12345678, 0x9ABCDEF0, 0x0F0F0F0F, 0xCAFEBABE, 0x00010002], mask=0x5, consecutivo=True)
    w += cmd(0x0FD, [0xDEADBEEF, 0x11111111, 0x22222222], mask=0xA)  # no consecutivo: 3 veces el mismo
    out.append(("mascaras", w))
    # 2) float24 especiales por uniforms (+0, -0, inf, -inf, NaN, denormal, max, min normal, 1.0, -2.5)
    esp = [0x000000, 0x800000, 0x7F0000, 0xFF0000, 0x7F1234, 0x000001, 0x00FFFF, 0x7EFFFF, 0x010000,
           0x3F0000, 0xC04000, 0x800001, 0x3E8000, 0x123456, 0xABCDEF, 0x7FFFFF]
    w = cmd(R_VSH + 0x10, [0])
    for a in range(0, len(esp), 4):
        w += cmd(R_VSH + 0x11, packf24(*esp[a:a + 4]))
    w += cmd(R_VSH + 0x10, [0x80000000 | 10])  # modo float32: palabra 0 = w
    w += cmd(R_VSH + 0x11, [f32bits(4.0), f32bits(3.0), f32bits(2.0), f32bits(1.0)])
    w += cmd(R_VSH + 0x10, [95])
    w += cmd(R_VSH + 0x11, packf24(0x3F0000, 0x3F0000, 0x3F0000, 0x3F0000) + packf24(1, 2, 3, 4))  # 96: se ignora
    w += cmd(R_VSH + 0x10, [0x7F])
    w += cmd(R_VSH + 0x11, packf24(0x3F0000, 0, 0, 0))
    w += cmd(0x041, [0x46E000])  # viewport (f24 de 240/2 = 120)
    w += cmd(0x043, [0x474000])  # 200
    w += cmd(0x04D, [0xBF0000])
    w += cmd(0x04E, [0x000000])
    w += cmd(0x068, [0x03FF0200])  # x negativo en 10 bits
    out.append(("float24_especiales", w))
    # 3) GS separado: con use_gs = 2 lo del VS NO se copia al GS
    w = cmd(0x229, [2]) + cmd(R_VSH + 0x10, [3]) + cmd(R_VSH + 0x11, packf24(0x3F0000, 0x400000, 0x410000, 0x420000))
    w += cmd(R_VSH + 0x0, [0x0000A5A5]) + cmd(R_GSH + 0x0, [0x00005A5A])
    w += cmd(R_GSH + 0x10, [7]) + cmd(R_GSH + 0x11, packf24(1, 2, 3, 4))
    out.append(("gs_separado", w))
    # 4) LUTs de luz y de niebla, atributos fijos
    w = cmd(0x1C5, [(3 << 8) | 250]) + cmd(0x1C8, list(range(1000, 1012)))  # da la vuelta en 256
    w += cmd(0x1C5, [(25 << 8)]) + cmd(0x1C8, [7])  # tabla 25: invalida
    w += cmd(0x0E6, [126]) + cmd(0x0E8, [0xAAAA0000 + k for k in range(5)], consecutivo=True)
    w += cmd(0x232, [2]) + cmd(0x233, packf24(0x3F0000, 0x400000, 0x3E0000, 0x3D0000), consecutivo=True)
    w += cmd(0x233, packf24(0x3F8000, 0, 0x800000, 0x3F0000))
    w += cmd(0x232, [15]) + cmd(0x233, packf24(1, 1, 1, 1))  # modo inmediato: no implementado -> error
    out.append(("luts_y_fijos", w))
    # 5) vertices + dibujo indexado y no indexado + estado de fragmentos sintetico
    w = cmd(0x200, [(0x20000000 // 16) << 1])  # base (se lee bits 1-28 * 16)
    w += cmd(0x201, [0xBF3B], consecutivo=False)
    w += cmd(0x202, [(3 << 28) | (0x008 << 16)])
    w += cmd(0x203, [0x100, 0x3210, (2 << 28) | (24 << 16)], consecutivo=True)
    w += cmd(0x206, [0x200, 0x0000000C, (1 << 28) | (8 << 16) | 0x0], consecutivo=True)
    w += cmd(0x227, [0x80000400]) + cmd(0x228, [36]) + cmd(0x25E, [1 << 8], mask=0x2)
    w += cmd(0x080, [0x2007]) + cmd(0x082, [0x01000080]) + cmd(0x083, [0x20002206]) + cmd(0x084, [0x0F001FF0])
    w += cmd(0x085, [0x18000000 >> 3]) + cmd(0x08E, [12])
    w += cmd(0x11C, [0x18400000 >> 3]) + cmd(0x11D, [0x18000000 >> 3]) + cmd(0x116, [3]) + cmd(0x117, [0x00000002])
    w += cmd(0x11E, [0x010EF190]) + cmd(0x112, [0xF, 0xF, 0x3, 0x3], consecutivo=True)
    w += cmd(0x22F, [1])
    w += cmd(0x228, [6]) + cmd(0x22A, [10]) + cmd(0x22E, [1])
    out.append(("dibujos", w))
    # 6) saltos de lista: principal -> 0x20000000 -> 0x20001000 ; FINALIZE con autostop corta el resto
    ter = cmd(0x103, [0x77777777]) + cmd(0x020, [0x12345678]) + cmd(0x034, [1]) + cmd(0x010, [0x12345678]) + \
        cmd(0x103, [0x88888888])  # tras FINALIZE con autostop: no se ejecuta
    ter_n = len(ter)
    seg = cmd(0x0FD, [0x55555555]) + cmd(0x23B, [0x20001000 >> 3]) + cmd(0x239, [ter_n * 4 // 8]) + \
        cmd(0x23D, [1]) + cmd(0x0FD, [0x66666666])
    w = cmd(0x0E1, [0x01020304]) + cmd(0x23A, [0x20000000 >> 3]) + cmd(0x238, [len(seg) * 4 // 8]) + \
        cmd(0x23C, [1]) + cmd(0x0E1, [0x99999999])
    out.append(("saltos", w, {0x20000000: seg, 0x20001000: ter}))
    # 7) FINALIZE sin coincidencia / sin autostop, cabecera que se sale del final
    w = cmd(0x020, [0x11111111]) + cmd(0x010, [0x22222222]) + cmd(0x010, [0x22222211]) + cmd(0x0C3, [5])
    w += [0x1, 0x00F00101 | (5 << 20)]  # pide 5 extra que no estan
    out.append(("finalize_y_corte", w))
    return out


# ---------------------------------------------------------------- main
def escribir_bin(casos, ruta):
    with open(ruta + ".tmp", "wb") as f:
        f.write(b"PICA" + struct.pack("<I", len(casos)))
        for c in casos:
            w = c[1]
            mem = c[2] if len(c) > 2 else {}
            f.write(struct.pack(f"<I{len(w)}I", len(w), *w))
            f.write(struct.pack("<I", len(mem)))
            for d, ws in mem.items():
                f.write(struct.pack(f"<II{len(ws)}I", d, len(ws), *ws))
    os.replace(ruta + ".tmp", ruta)


contrastados = [0]


def esperado(casos):
    lin, malos_banco = [], 0
    contrastados[0] = 0
    especiales = {0x010, 0x0E6, 0x1C5, 0x232, R_VSH + 0x10, R_VSH + 0x1B, R_VSH + 0x25, R_GSH + 0x10, R_GSH + 0x1B,
                  R_GSH + 0x25, R_GSH + 0xD}
    for n, c in enumerate(casos):
        m = Modelo(c[2] if len(c) > 2 else None)
        fin = m.ejecutar(list(c[1]))
        lin += m.out
        lin.append(f"=== caso {n} fin={fin} dib={m.dib} irq={m.irq} cmds={m.cmds} err={m.err}")
        lin += [f"r{k:03X}={v:08X}" for k, v in enumerate(m.r) if v]
        lin += m.volcado()
        lin.append(f"--- fin caso {n}")
        # contraste del banco con pica_cmd (solo listas sin saltos ni cortes)
        if len(c) <= 2 and not m.err and not m.parar:
            try:
                st = pica_cmd.estado([(0, r, mk, v) for r, mk, v in pica_cmd.parsear(list(c[1]))])
            except ValueError:  # pica_cmd rechaza mascara 0 (el caso sintetico de mascaras la usa a proposito)
                continue
            contrastados[0] += 1
            for r, v in st.items():
                if r not in especiales and m.r[r] != v:
                    malos_banco += 1
    return lin, malos_banco


def main():
    a = sys.argv[1:]
    maximo = int(a[a.index("--max") + 1]) if "--max" in a else 0
    sab = a[a.index("--sabotaje") + 1] if "--sabotaje" in a else None
    os.makedirs(SALIDA, exist_ok=True)
    exe = os.path.join(SALIDA, f"prueba_pica{'_' + sab.lower() if sab else ''}.exe")
    if "--compilar" in a or not os.path.exists(exe):
        fuentes = [os.path.join(RENDER, x) for x in ("pica.c", "prueba_pica.c")]
        extra = [f"-DPICA_SABOTAJE_{sab}"] if sab else []
        r = subprocess.run([sys.executable, "-m", "ziglang", "cc", "-O2", "-std=c11", "-Wall", "-Wextra",
                            "-target", "x86_64-windows-gnu", *extra, "-o", exe, *fuentes], capture_output=True,
                           text=True)
        if r.returncode:
            print(r.stdout, r.stderr)
            sys.exit(1)
        if r.stderr.strip():
            print("avisos del compilador:\n" + r.stderr[:3000])
    mats = casos_materiales(maximo)
    shs = casos_shaders()
    sint = casos_sinteticos()
    casos = sint + shs + mats
    print(f"casos: {len(sint)} sinteticos + {len(shs)} shaders + {len(mats)} materiales (listas distintas)")
    ruta_bin = os.path.join(SALIDA, "casos.bin")
    escribir_bin(casos, ruta_bin)
    esp, malos_banco = esperado(casos)
    r = subprocess.run([exe, ruta_bin], capture_output=True, text=True)
    if r.returncode:
        print("prueba_pica fallo:", r.returncode, r.stderr[:500])
        sys.exit(1)
    obt = r.stdout.splitlines()
    open(os.path.join(SALIDA, "esperado.txt"), "w").write("\n".join(esp) + "\n")
    open(os.path.join(SALIDA, "obtenido.txt"), "w").write("\n".join(obt) + "\n")
    total = len(casos)

    def partir(lin):
        d, cur = {}, []
        for x in lin:
            if x.startswith("--- fin caso "):
                d[int(x.split()[3])] = cur
                cur = []
            else:
                cur.append(x)
        return d
    e_c, o_c = partir(esp), partir(obt)
    malos = [k for k in range(total) if e_c.get(k) != o_c.get(k)]
    print(f"casos identicos C vs Python: {total - len(malos)}/{total}")
    print(f"banco vs pica_cmd.estado (registros sin efecto lateral, {contrastados[0]} casos): {malos_banco} diferencias")
    for k in malos[:5]:
        print(f"  distinto: caso {k} ({casos[k][0]})")
    if malos:
        import difflib
        print("\n".join(list(difflib.unified_diff(esp, obt, "python", "c", n=0, lineterm=""))[:30]))
    sys.exit(1 if malos or malos_banco else 0)


if __name__ == "__main__":
    main()
