"""Lector y desensamblador de shaders del PICA200 (formato DVLB / .shbin) de Super Mario 3D Land.

Uso:
  py -I tools\\shbin.py extraer            # saca todos los DVLB del RomFS a extraido\\shaders\\*.shbin
  py -I tools\\shbin.py dis <archivo.shbin>  # desensambla: entradas (DVLE), uniforms, constantes, outmap y codigo

Formato (3dbrew, "SHBIN" y "Shader Instruction Set"):
  DVLB: 'DVLB', n_dvle, n x offset(DVLE). DVLP va justo despues de la cabecera: el codigo (palabras de 32 bits)
  y la tabla de descriptores de operandos (swizzle, negacion, mascara). Cada DVLE es un punto de entrada
  (vertex o geometry) con sus constantes, su outmap (registro de salida -> semantica) y sus uniforms con nombre.
"""
import os
import struct
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

OPS = {0x00: "add", 0x01: "dp3", 0x02: "dp4", 0x03: "dph", 0x04: "dst", 0x05: "ex2", 0x06: "lg2", 0x07: "litp",
       0x08: "mul", 0x09: "sge", 0x0A: "slt", 0x0B: "flr", 0x0C: "max", 0x0D: "min", 0x0E: "rcp", 0x0F: "rsq",
       0x12: "mova", 0x13: "mov", 0x18: "dphi", 0x19: "dsti", 0x1A: "sgei", 0x1B: "slti",
       0x20: "break", 0x21: "nop", 0x22: "end", 0x23: "breakc", 0x24: "call", 0x25: "callc", 0x26: "callu",
       0x27: "ifu", 0x28: "ifc", 0x29: "loop", 0x2A: "emit", 0x2B: "setemit", 0x2C: "jmpc", 0x2D: "jmpu",
       0x2E: "cmp", 0x2F: "cmp"}
UNARIOS = {"ex2", "lg2", "litp", "flr", "rcp", "rsq", "mova", "mov"}
INVERTIDOS = {"dphi", "dsti", "sgei", "slti"}
IDX = ["", "a0.x", "a0.y", "aL"]
CMP = ["==", "!=", "<", "<=", ">", ">="]
CONDOP = ["or", "and", "x", "y"]
OUTMAP = {0: "posicion", 1: "normquat", 2: "color", 3: "texcoord0", 4: "texcoord0w", 5: "texcoord1",
          6: "texcoord2", 8: "vista"}


def bits(w, lo, n):
    return (w >> lo) & ((1 << n) - 1)


def reg_src(r):
    if r < 0x10:
        return f"v{r}"
    if r < 0x20:
        return f"r{r - 0x10}"
    return f"c{r - 0x20}"


def reg_dst(r):
    return f"o{r}" if r < 0x10 else f"r{r - 0x10}"


def swz(s):
    return "".join("xyzw"[bits(s, 6 - 2 * k, 2)] for k in range(4))


def mascara(m):
    return "".join(c for k, c in enumerate("xyzw") if m & (8 >> k))


def f24(v):
    """float24 del PICA (1 signo, 7 exponente con sesgo 63, 16 mantisa) -> float."""
    if v & 0x7FFFFF == 0:
        return -0.0 if v & 0x800000 else 0.0
    s = (v >> 23) & 1
    e = (v >> 16) & 0x7F
    m = v & 0xFFFF
    if e == 0x7F:
        return float("nan") if m else (-1) ** s * float("inf")
    if e == 0:  # denormal (Azahar pica_types.h lo convierte sin pérdida): m·2^-78
        return (-1) ** s * m * 2.0 ** -78
    return (-1) ** s * (1 + m / 65536) * 2.0 ** (e - 63)


class Shbin:
    def __init__(self, d):
        assert d[:4] == b"DVLB", "no es DVLB"
        self.d = d
        n = struct.unpack_from("<I", d, 4)[0]
        offs = struct.unpack_from(f"<{n}I", d, 8)
        p = 8 + 4 * n  # DVLP
        assert d[p:p + 4] == b"DVLP"
        cod_off, cod_n, desc_off, desc_n = struct.unpack_from("<4I", d, p + 8)
        self.codigo = list(struct.unpack_from(f"<{cod_n}I", d, p + cod_off))
        self.desc = [struct.unpack_from("<I", d, p + desc_off + 8 * k)[0] for k in range(desc_n)]
        self.entradas = [self.dvle(o) for o in offs]

    def dvle(self, o):
        d = self.d
        assert d[o:o + 4] == b"DVLE"
        tipo = d[o + 6]
        main, endmain = struct.unpack_from("<2I", d, o + 8)
        (c_off, c_n, l_off, l_n, om_off, om_n, u_off, u_n, s_off, s_n) = struct.unpack_from("<10I", d, o + 0x18)
        sim = d[o + s_off:o + s_off + s_n]

        def nombre(k):
            return sim[k:sim.index(b"\0", k)].decode("ascii", "replace")
        constantes = []
        for k in range(c_n):
            e = o + c_off + 0x14 * k
            t, r = d[e], d[e + 2]
            if t == 2:
                vals = tuple(f24(x) for x in struct.unpack_from("<4I", d, e + 4))
                constantes.append(("c", r, vals))
            elif t == 1:
                constantes.append(("i", r, tuple(d[e + 4:e + 8])))
            else:
                constantes.append(("b", r, d[e + 4] != 0))
        outmap = []
        for k in range(om_n):
            t, r, m = struct.unpack_from("<3H", d, o + om_off + 8 * k)
            outmap.append((OUTMAP.get(t, f"?{t}"), r, "".join(c for k, c in enumerate("xyzw") if m >> k & 1)))  # aqui bit0 = x
        uniforms = []
        for k in range(u_n):
            so, ini, fin = struct.unpack_from("<I2H", d, o + u_off + 8 * k)
            uniforms.append((nombre(so), ini, fin))
        etiquetas = {}
        for k in range(l_n):
            e = o + l_off + 0x10 * k
            pos, so = struct.unpack_from("<I", d, e + 4)[0], struct.unpack_from("<I", d, e + 12)[0]
            etiquetas[pos] = nombre(so)
        return {"tipo": "geometry" if tipo else "vertex", "main": main, "endmain": endmain,
                "constantes": constantes, "outmap": outmap, "uniforms": uniforms, "etiquetas": etiquetas}

    def instr(self, pc):
        """Decodifica una instruccion -> dict con nombre y campos."""
        w = self.codigo[pc]
        op = bits(w, 26, 6)
        if op >= 0x30:  # mad / madi (formato 5): opcode de 3 bits
            inv = op < 0x38
            dsc = self.desc[bits(w, 0, 5)]
            r = {"op": "madi" if inv else "mad", "dst": bits(w, 24, 5), "idx": bits(w, 22, 2),
                 "src1": bits(w, 17, 5), "desc": dsc}
            if inv:
                r.update(src2=bits(w, 12, 5), src3=bits(w, 5, 7))
            else:
                r.update(src2=bits(w, 10, 7), src3=bits(w, 5, 5))
            return r
        nom = OPS.get(op, f"?{op:02X}")
        r = {"op": nom, "w": w}
        if op < 0x20:  # aritmeticas (formato 1 / 1i / 1u)
            r.update(dst=bits(w, 21, 5), idx=bits(w, 19, 2), desc=self.desc[bits(w, 0, 7)])
            if nom in INVERTIDOS:
                r.update(src1=bits(w, 14, 5), src2=bits(w, 7, 7))
            else:
                r.update(src1=bits(w, 12, 7), src2=bits(w, 7, 5))
        elif nom == "cmp":  # formato 1c
            r.update(cmpx=bits(w, 24, 3), cmpy=bits(w, 21, 3), idx=bits(w, 19, 2), src1=bits(w, 12, 7),
                     src2=bits(w, 7, 5), desc=self.desc[bits(w, 0, 7)])
        elif nom in ("ifu", "callu", "jmpu", "loop"):  # formato 3
            r.update(uni=bits(w, 22, 4), dst=bits(w, 10, 12), num=bits(w, 0, 8))
        elif nom == "setemit":
            r.update(vtx=bits(w, 24, 2), winding=bits(w, 23, 1), prim=bits(w, 22, 1))
        else:  # formato 2
            r.update(refx=bits(w, 25, 1), refy=bits(w, 24, 1), condop=bits(w, 22, 2), dst=bits(w, 10, 12),
                     num=bits(w, 0, 8))
        return r

    def operandos(self, i):
        """Fuentes normalizadas [(registro, indice_relativo, swizzle 'xyzw', negado)] y mascara de destino.
        El indice relativo (a0.x/a0.y/aL) va en el operando de 7 bits: src1 en las normales, src2 en las
        invertidas y en mad, src3 en madi (Azahar, shader_interpreter.cpp: LookupSourceRegister)."""
        op, dsc = i["op"], i["desc"]
        n = 1 if op in UNARIOS else 3 if op in ("mad", "madi") else 2
        rel = {"mad": 1, "madi": 2}.get(op, 1 if op in INVERTIDOS else 0)
        fuentes = []
        for k in range(n):
            r = i[f"src{k + 1}"]
            fuentes.append((r, i["idx"] if k == rel else 0, swz(bits(dsc, 5 + 9 * k, 8)), bits(dsc, 4 + 9 * k, 1)))
        return fuentes, dsc & 0xF

    def texto(self, pc):
        i = self.instr(pc)
        op = i["op"]
        if "desc" in i:
            fuentes, m = self.operandos(i)

            def src(f):
                r, idx, sw, neg = f
                s = reg_src(r) + (f"[{IDX[idx]}]" if idx and r >= 0x20 else "")
                return ("-" if neg else "") + s + ("" if sw == "xyzw" else "." + sw)
            if op == "cmp":
                return f"cmp {src(fuentes[0])}, {CMP[i['cmpx']]}, {CMP[i['cmpy']]}, {src(fuentes[1])}"
            dst = "a0" if op == "mova" else reg_dst(i["dst"])
            m = mascara(m)
            d = f"{dst}.{m}" if m != "xyzw" else dst
            return f"{op} {d}, " + ", ".join(src(f) for f in fuentes)
        if op == "jmpu":  # salta si b == !(num & 1)
            return f"jmpu {'!' if i['num'] & 1 else ''}b{i['uni']}, dst={i['dst']}"
        if op in ("ifu", "callu"):
            return f"{op} b{i['uni']}, dst={i['dst']}, num={i['num']}"
        if op == "loop":
            return f"loop i{i['uni']}, fin={i['dst']}"
        if op in ("ifc", "callc", "jmpc", "breakc"):
            c = {0: f"cmp.x=={i['refx']} or cmp.y=={i['refy']}", 1: f"cmp.x=={i['refx']} and cmp.y=={i['refy']}",
                 2: f"cmp.x=={i['refx']}", 3: f"cmp.y=={i['refy']}"}[i["condop"]]
            return f"{op} ({c}), dst={i['dst']}, num={i['num']}"
        if op == "call":
            return f"call dst={i['dst']}, num={i['num']}"
        if op == "setemit":
            return f"setemit vtx={i['vtx']}, winding={i['winding']}, prim={i['prim']}"
        return op

    def listado(self):
        out = [f"; {len(self.codigo)} instrucciones, {len(self.desc)} descriptores, {len(self.entradas)} entradas"]
        for k, e in enumerate(self.entradas):
            out.append(f"; entrada {k}: {e['tipo']} main={e['main']} endmain={e['endmain']}")
            for u in e["uniforms"]:
                out.append(f";   uniform {u[0]}: {u[1]:#x}..{u[2]:#x}")
            for c in e["constantes"]:
                out.append(f";   const {c[0]}{c[1]} = {c[2]}")
            for o in e["outmap"]:
                out.append(f";   out o{o[1]}.{o[2]} = {o[0]}")
        etiq = {}
        for e in self.entradas:
            etiq.update(e["etiquetas"])
        for pc in range(len(self.codigo)):
            if pc in etiq:
                out.append(f"{etiq[pc]}:")
            out.append(f"  {pc:4d}  {self.codigo[pc]:08X}  {self.texto(pc)}")
        return "\n".join(out)


def todos_los_dvlb():
    """(nombre, bytes) de cada DVLB del RomFS: sueltos en LayoutData\\shaders.szs y dentro del CGFX de Shader.szs."""
    import szs
    for rel in ("LayoutData/shaders.szs", "ObjectData/Shader.szs"):
        d = open(os.path.join(RAIZ, "extraido", "romfs", rel), "rb").read()
        if d[:4] == b"Yaz0":
            d = szs.yaz0(d)
        cont = szs.sarc(d)
        for nom, b in (cont.items() if isinstance(cont, dict) else cont):
            if b[:4] == b"DVLB":
                yield os.path.splitext(os.path.basename(nom))[0], b
                continue
            k = 0
            while (k := b.find(b"DVLB", k)) >= 0:  # embebidos en el CGFX
                yield f"{os.path.splitext(os.path.basename(nom))[0]}_{k:06X}", b[k:]
                k += 4
    # 7 oct: el raster encontro 5 programas fuera de la tabla. 4 son DVLB metidos en code.bin (los de los efectos y
    # el renderer de primitivas del motor) y 1 es SystemData\primitive_renderer_ctr.bsm (un DVLB suelto).
    d = open(os.path.join(RAIZ, "extraido", "code.bin"), "rb").read()
    k = 0
    while (k := d.find(b"DVLB", k)) >= 0:
        yield f"code_{k:06X}", d[k:k + 0x10000]   # codigo <= 4096 palabras: 64 KB sobran
        k += 4
    sd = os.path.join(RAIZ, "extraido", "romfs", "SystemData")
    for f in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        b = open(os.path.join(sd, f), "rb").read()
        if b[:4] == b"DVLB":
            yield os.path.splitext(f)[0], b


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "extraer":
        dest = os.path.join(RAIZ, "extraido", "shaders")
        os.makedirs(dest, exist_ok=True)
        for nom, b in todos_los_dvlb():
            s = Shbin(b)
            with open(os.path.join(dest, nom + ".shbin"), "wb") as fh:
                fh.write(b)
            with open(os.path.join(dest, nom + ".txt"), "w", encoding="utf-8") as fh:
                fh.write(s.listado() + "\n")
            print(f"{nom}: {len(s.codigo)} instr, {len(s.entradas)} entradas "
                  f"({', '.join(e['tipo'] for e in s.entradas)})")
    elif len(sys.argv) >= 3 and sys.argv[1] == "dis":
        print(Shbin(open(sys.argv[2], "rb").read()).listado())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
