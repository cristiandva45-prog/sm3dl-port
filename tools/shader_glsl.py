"""Traductor de shaders PICA200 (DVLB) a GLSL estructurado, para el renderer nativo del port.

Uso:
  py -I tools\\shader_glsl.py                 # traduce todos los extraido\\shaders\\*.shbin -> extraido\\shaders\\glsl\\
  py -I tools\\shader_glsl.py <archivo.shbin> # uno solo, a la salida estandar

Como funciona: el programa se convierte en un ARBOL (if/else, loop, llamadas a subrutina = funciones, y saltos
hacia adelante = 'if (!cond) { ... }'). Del mismo arbol salen el GLSL y un evaluador en Python (evaluar()), que
tools\\probar_shaders.py compara contra la maquina de pilas de tools\\shader_ref.py.
Lo que no encaja en un arbol se RECHAZA (NoEstructurable) en vez de adivinar. Casos del hardware que se rechazan:
  - salto a la direccion donde termina su ambito: el ambito no se cierra (se cierra por pc_viejo+1), sigue de largo;
  - salto como ultima instruccion de un ambito: el cierre del ambito pisa el salto;
  - 'end' dentro de una subrutina, o 'break' fuera de un loop de la misma funcion.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
import pica_ops  # noqa: E402
import shbin  # noqa: E402

COND_OPS = ["==", "!=", "<", "<=", ">", ">="]


class NoEstructurable(Exception):
    pass


# ---------------------------------------------------------------- arbol
class Programa:
    def __init__(self, sh, entrada):
        self.sh, self.e = sh, sh.entradas[entrada]
        self.subs = {}  # (dst, num) -> arbol
        pend = []
        self._en_sub = False
        self.arbol = self.bloque(self.e["main"], len(sh.codigo), "raiz", 0, pend)
        self._en_sub = True
        while pend:
            k = pend.pop()
            if k not in self.subs:
                self.subs[k] = None
                self.subs[k] = self.bloque(k[0], k[0] + k[1], "call", 0, pend)

    def cond(self, ins):
        if ins["op"] in ("ifu", "callu"):
            return ("u", ins["uni"], True)
        if ins["op"] == "jmpu":
            return ("u", ins["uni"], not (ins["num"] & 1))
        return ("c", ins["condop"], ins["refx"], ins["refy"])

    def bloque(self, s, e, tipo, en_loop, pend):
        """Arbol del rango [s, e). tipo: 'raiz', 'call', 'then', 'loop' (ambitos que el hardware CIERRA al llegar a
        e en secuencia) o 'else' (no hay pila: solo se sigue de largo). Los saltos hacia adelante se vuelven
        banderas: ('jset', id, cond) las prende y ('guard', ids, cuerpo) ejecuta el cuerpo si ninguna esta prendida."""
        cerrado = tipo in ("call", "then", "loop")
        items, saltos, pc = [], [], s   # items: (inicio, fin, nodo)
        while pc < e:
            ins = self.sh.instr(pc)
            op = ins["op"]
            en_sub = tipo == "call" or getattr(self, "_en_sub", False)
            if "desc" in ins:
                items.append((pc, pc + 1, ("ins", pc)))
                pc += 1
            elif op == "nop":
                pc += 1
            elif op == "end":
                if self._en_sub:
                    raise NoEstructurable(f"{pc}: end dentro de subrutina")
                items.append((pc, pc + 1, ("end",)))
                pc += 1
                if tipo == "raiz" and not any(j0 < pc - 1 < d for j0, d, _ in saltos):
                    break  # end incondicional en la raiz: aqui termina main
            elif op in ("ifu", "ifc"):
                d, n = ins["dst"], ins["num"]
                if not (pc < d <= e and d + n <= e):
                    raise NoEstructurable(f"{pc}: if [{pc + 1},{d}) else [{d},{d + n}) sale del ambito [{s},{e})")
                nodo = ("if", self.cond(ins), self.bloque(pc + 1, d, "then", en_loop, pend),
                        self.bloque(d, d + n, "else", en_loop, pend))
                items.append((pc, d + n, nodo))
                pc = d + n
            elif op == "loop":
                d = ins["dst"]
                if not (pc < d < e):
                    raise NoEstructurable(f"{pc}: loop hasta {d} sale del ambito [{s},{e})")
                items.append((pc, d + 1, ("loop", ins["uni"], self.bloque(pc + 1, d + 1, "loop", en_loop + 1, pend))))
                pc = d + 1
            elif op in ("call", "callu", "callc"):
                k = (ins["dst"], ins["num"])
                pend.append(k)
                items.append((pc, pc + 1, ("call", None if op == "call" else self.cond(ins), k)))
                pc += 1
            elif op in ("jmpc", "jmpu"):
                d = ins["dst"]
                if cerrado and pc == e - 1:
                    pc += 1  # el cierre del ambito pisa el salto: el hardware no lo toma
                    continue
                if d <= pc:
                    raise NoEstructurable(f"{pc}: salto hacia atras a {d}")
                if d > e or (d == e and cerrado):
                    raise NoEstructurable(f"{pc}: salto a {d} fuera de [{pc + 1},{e}) ({tipo})")
                saltos.append((pc, d, len(saltos)))
                items.append((pc, pc + 1, ("jset", self._nuevo_salto(), self.cond(ins))))
                pc += 1
            elif op in ("break", "breakc"):
                if not en_loop:
                    raise NoEstructurable(f"{pc}: break fuera de un loop de la misma funcion")
                items.append((pc, pc + 1, ("break", None if op == "break" else self.cond(ins))))
                pc += 1
            else:
                raise NoEstructurable(f"{pc}: {op} sin soporte")
        else:
            if tipo == "raiz":
                raise NoEstructurable("main sin end")
        # ids reales de cada salto (el nodo jset lleva el id global)
        ids = {}
        for (i0, i1, nodo) in items:
            if nodo[0] == "jset":
                ids[i0] = nodo[1]
        for j0, d, _ in saltos:  # un destino no puede caer en medio de un if/loop
            for i0, i1, nodo in items:
                if i0 < d < i1:
                    raise NoEstructurable(f"salto {j0}->{d} cae dentro de {nodo[0]} [{i0},{i1})")
        out, grupo, guarda = [], [], None
        if saltos:
            out.append(("jinit", [ids[j0] for j0, _, _ in saltos]))
        for i0, i1, nodo in items:
            g = tuple(ids[j0] for j0, d, _ in saltos if j0 < i0 < d)
            if g != guarda and grupo:
                out += [("guard", list(guarda), grupo)] if guarda else grupo
                grupo = []
            guarda = g
            grupo.append(nodo)
        if grupo:
            out += [("guard", list(guarda), grupo)] if guarda else grupo
        return out

    def _nuevo_salto(self):
        self._saltos = getattr(self, "_saltos", 0) + 1
        return self._saltos

    # ------------------------------------------------------------ evaluador (para la prueba)
    def evaluar(self, st):
        st.prof = 0
        st.saltos = {}
        self._lista(self.arbol, st)
        return st

    def _cond(self, c, st):
        if c is None:
            return True
        if c[0] == "u":
            return st.b[c[1]] == c[2]
        x, y = c[2] == st.cc[0], c[3] == st.cc[1]
        return [x or y, x and y, x, y][c[1]]

    def _lista(self, nodos, st):
        for n in nodos:
            t = n[0]
            if t == "ins":
                ins = self.sh.instr(n[1])
                fuentes, m = self.sh.operandos(ins)
                st.ejecutar(ins["op"], ins.get("dst"), m, fuentes, ins)
            elif t == "end":
                return "end"
            elif t == "if":
                r = self._lista(n[2] if self._cond(n[1], st) else n[3], st)
                if r:
                    return r
            elif t == "jinit":
                for j in n[1]:
                    st.saltos[j] = False
            elif t == "jset":
                if self._cond(n[2], st):
                    st.saltos[n[1]] = True
            elif t == "guard":
                if not any(st.saltos[j] for j in n[1]):
                    r = self._lista(n[2], st)
                    if r:
                        return r
            elif t == "call":
                if self._cond(n[1], st):
                    self._lista(self.subs[n[2]], st)
            elif t == "break":
                if self._cond(n[1], st):
                    return "break"
            elif t == "loop":
                p = st.i[n[1]]
                st.a[2] = p[1]
                previo, cuenta = p[1], p[0]
                st.prof += 1
                while True:
                    r = self._lista(n[2], st)
                    if r == "end":
                        return r
                    st.a[2] += p[2]
                    if r == "break" or cuenta == 0:
                        break
                    cuenta -= 1
                st.prof -= 1
                if st.prof > 0:
                    st.a[2] = previo
        return None

    # ------------------------------------------------------------ GLSL
    def constantes(self):
        c = {k: v for t, k, v in self.e["constantes"] if t == "c"}
        i = {k: v for t, k, v in self.e["constantes"] if t == "i"}
        b = {k: v for t, k, v in self.e["constantes"] if t == "b"}
        return c, i, b

    def glsl(self, nombre):
        cc, ci, cb = self.constantes()
        L = []
        L.append("#version 330 core")
        L.append(f"// GENERADO por tools/shader_glsl.py desde {nombre} (entrada en {self.e['main']}). No editar.")
        L.append("// Uniforms con el layout del PICA: pica_c = c0..c95, pica_i = i0..i3 (x cuenta, y inicio, z paso),")
        L.append("// pica_b = b0..b15. Las constantes del DVLE ya van escritas aqui y tapan el uniform.")
        usadas_v = set()
        for pc in range(len(self.sh.codigo)):
            ins = self.sh.instr(pc)
            if "desc" in ins:
                for f in self.sh.operandos(ins)[0]:
                    if f[0] < 0x10:
                        usadas_v.add(f[0])
        for k in sorted(usadas_v):
            L.append(f"layout(location = {k}) in vec4 v{k};")
        L.append("uniform vec4 pica_c[96];\nuniform ivec4 pica_i[4];\nuniform bool pica_b[16];")
        for nom, reg, masc in self.e["outmap"]:
            pass
        outs = sorted({reg for _, reg, _ in self.e["outmap"]})
        for k in outs:
            sem = ", ".join(f"{n}.{m}" for n, r, m in self.e["outmap"] if r == k)
            L.append(f"out vec4 pica_o{k};  // {sem}")
        L.append("""
vec4 r[16];
vec4 o[16];
ivec3 a;      // a0.x, a0.y, aL
bvec2 cc;     // banderas de cmp
int prof_loop;

// el PICA da 0 (no NaN) en 0 * inf
vec4 pmul(vec4 x, vec4 y) {
    vec4 p = x * y;
    bvec4 cero = bvec4(uvec4(isnan(p)) & uvec4(not(isnan(x))) & uvec4(not(isnan(y))));
    return mix(p, vec4(0.0), cero);
}
float pdot3(vec4 x, vec4 y) { vec4 p = pmul(x, y); return ((0.0 + p.x) + p.y) + p.z; }
float pdot4(vec4 x, vec4 y) { vec4 p = pmul(x, y); return (((0.0 + p.x) + p.y) + p.z) + p.w; }
vec4 pmax(vec4 x, vec4 y) { return mix(y, x, greaterThan(x, y)); }
vec4 pmin(vec4 x, vec4 y) { return mix(y, x, lessThan(x, y)); }
""")
        # lectura relativa de c[]: las constantes del DVLE tapan el uniform
        L.append("vec4 creg(int k) {")
        L.append("    k = k & 127;")
        L.append("    if (k >= 96) return vec4(1.0);")
        for k, v in sorted(cc.items()):
            L.append(f"    if (k == {k}) return {self.vec(v)};")
        L.append("    return pica_c[k];\n}")
        L.append("int rel(int off) { return (off < -128 || off > 127) ? 0 : off; }")
        for k in self.subs:
            L.append(f"void sub_{k[0]}_{k[1]}();")
        self._n = 0
        for k, cuerpo in self.subs.items():
            L.append(f"void sub_{k[0]}_{k[1]}() {{")
            self._g(cuerpo, L, 1, None)
            L.append("}")
        L.append("void pica_main() {")
        self._g(self.arbol, L, 1, None)
        L.append("}")
        L.append("void main() {")
        L.append("    for (int k = 0; k < 16; k++) { r[k] = vec4(0.0); o[k] = vec4(0.0); }")
        L.append("    a = ivec3(0); cc = bvec2(false); prof_loop = 0;")
        L.append("    pica_main();")
        for k in outs:
            L.append(f"    pica_o{k} = o[{k}];")
        pos = [r for n, r, m in self.e["outmap"] if n == "posicion"]
        if pos:
            L.append(f"    // PICA: z de clip en [-w, 0]; con glClipControl(GL_ZERO_TO_ONE) basta invertir el signo")
            L.append(f"    gl_Position = vec4(o[{pos[0]}].x, o[{pos[0]}].y, -o[{pos[0]}].z, o[{pos[0]}].w);")
        L.append("}")
        return "\n".join(L) + "\n"

    @staticmethod
    def num(x):
        if x != x:
            return "(0.0/0.0)"
        if x in (float("inf"), float("-inf")):
            return "(1.0/0.0)" if x > 0 else "(-1.0/0.0)"
        s = repr(float(x))
        return s if ("e" in s or "." in s) else s + ".0"

    def vec(self, v):
        return "vec4(" + ", ".join(self.num(x) for x in v) + ")"

    def src(self, f):
        reg, idx, sw, neg = f
        cc = self.constantes()[0]
        if reg < 0x10:
            s = f"v{reg}"
        elif reg < 0x20:
            s = f"r[{reg - 0x10}]"
        elif idx:
            s = f"creg({reg - 0x20} + rel(a.{'xyz'[idx - 1]}))"
        elif reg - 0x20 in cc:
            s = self.vec(cc[reg - 0x20])
        else:
            s = f"pica_c[{reg - 0x20}]"
        if sw != "xyzw":
            s = f"{s}.{sw}"
        return f"(-{s})" if neg else s

    def gcond(self, c):
        if c is None:
            return "true"
        if c[0] == "u":
            cb = self.constantes()[2]
            b = ("true" if cb[c[1]] else "false") if c[1] in cb else f"pica_b[{c[1]}]"
            return b if c[2] else f"!{b}"
        x = f"(cc.x == {'true' if c[2] else 'false'})"
        y = f"(cc.y == {'true' if c[3] else 'false'})"
        return [f"({x} || {y})", f"({x} && {y})", x, y][c[1]]

    def _g(self, nodos, L, nv, lazo):
        t0 = "    " * nv
        for n in nodos:
            t = n[0]
            if t == "ins":
                L.append(t0 + self.instr(n[1]))
            elif t == "end":
                L.append(t0 + "return;")
            elif t == "if":
                L.append(f"{t0}if ({self.gcond(n[1])}) {{")
                self._g(n[2], L, nv + 1, lazo)
                if n[3]:
                    L.append(f"{t0}}} else {{")
                    self._g(n[3], L, nv + 1, lazo)
                L.append(t0 + "}")
            elif t == "jinit":
                L.append(t0 + " ".join(f"bool j{j} = false;" for j in n[1]))
            elif t == "jset":
                L.append(f"{t0}if ({self.gcond(n[2])}) j{n[1]} = true;  // salto")
            elif t == "guard":
                L.append(f"{t0}if (!({' || '.join(f'j{j}' for j in n[1])})) {{")
                self._g(n[2], L, nv + 1, lazo)
                L.append(t0 + "}")
            elif t == "call":
                llamada = f"sub_{n[2][0]}_{n[2][1]}();"
                L.append(t0 + (llamada if n[1] is None else f"if ({self.gcond(n[1])}) {llamada}"))
            elif t == "break":
                L.append(f"{t0}if ({self.gcond(n[1])}) {{ a.z += {lazo}.z; break; }}")
            elif t == "loop":
                self._n += 1
                p = f"lp{self._n}"
                ci = self.constantes()[1]
                fuente = f"ivec4({', '.join(map(str, ci[n[1]]))})" if n[1] in ci else f"pica_i[{n[1]}]"
                L.append(f"{t0}{{ ivec4 {p} = {fuente}; a.z = {p}.y; prof_loop++;")
                L.append(f"{t0}  for (int n{self._n} = {p}.x; ; n{self._n}--) {{")
                self._g(n[2], L, nv + 1, p)
                L.append(f"{t0}    a.z += {p}.z; if (n{self._n} == 0) break;")
                L.append(f"{t0}  }}")
                L.append(f"{t0}  prof_loop--; if (prof_loop > 0) a.z = {p}.y; }}")

    def instr(self, pc):
        ins = self.sh.instr(pc)
        op = ins["op"]
        fuentes, m = self.sh.operandos(ins)
        s = [self.src(f) for f in fuentes]
        com = f"// {pc}: {self.sh.texto(pc)}"
        if op == "cmp":
            ox, oy = COND_OPS[ins["cmpx"]], COND_OPS[ins["cmpy"]]
            return (f"{{ vec4 s1 = {s[0]}; vec4 s2 = {s[1]}; cc = bvec2(s1.x {ox} s2.x, s1.y {oy} s2.y); }} {com}")
        if op == "mova":
            partes = []
            if m & 8:
                partes.append("a.x = int(s1.x);")
            if m & 4:
                partes.append("a.y = int(s1.y);")
            return f"{{ vec4 s1 = {s[0]}; {' '.join(partes)} }} {com}"
        e = {"add": f"{s[0]} + {s[1] if len(s) > 1 else ''}", "mul": f"pmul({', '.join(s)})",
             "dp3": f"vec4(pdot3({s[0]}, {s[1] if len(s) > 1 else ''}))",
             "max": f"pmax({', '.join(s)})", "min": f"pmin({', '.join(s)})",
             "flr": f"floor({s[0]})", "rcp": f"vec4(1.0 / ({s[0]}).x)", "rsq": f"vec4(inversesqrt(({s[0]}).x))",
             "ex2": f"vec4(exp2(({s[0]}).x))", "lg2": f"vec4(log2(({s[0]}).x))", "mov": s[0]}
        if op == "dp4":
            e[op] = f"vec4(pdot4({s[0]}, {s[1]}))"
        elif op in ("dph", "dphi"):
            e[op] = f"vec4(pdot4(vec4(({s[0]}).xyz, 1.0), {s[1]}))"
        elif op in ("sge", "sgei"):
            e[op] = f"vec4(greaterThanEqual({s[0]}, {s[1]}))"
        elif op in ("slt", "slti"):
            e[op] = f"vec4(lessThan({s[0]}, {s[1]}))"
        elif op in ("mad", "madi"):
            e[op] = f"pmul({s[0]}, {s[1]}) + {s[2]}"
        if op not in e:
            raise NoEstructurable(f"{pc}: {op} sin traduccion a GLSL")
        d = ins["dst"]
        if d >= 0x20:
            return f"/* destino descartado */ {com}"
        dst = f"o[{d}]" if d < 0x10 else f"r[{d - 0x10}]"
        mk = shbin.mascara(m)
        if mk == "xyzw":
            return f"{dst} = {e[op]}; {com}"
        if not mk:
            return f"/* sin mascara */ {com}"
        return f"{dst}.{mk} = ({e[op]}).{mk}; {com}"


def main():
    if len(sys.argv) > 1:
        sh = shbin.Shbin(open(sys.argv[1], "rb").read())
        for k in range(len(sh.entradas)):
            print(Programa(sh, k).glsl(os.path.basename(sys.argv[1])))
        return
    d = os.path.join(RAIZ, "extraido", "shaders")
    out = os.path.join(d, "glsl")
    os.makedirs(out, exist_ok=True)
    for f in sorted(os.listdir(d)):
        if not f.endswith(".shbin"):
            continue
        sh = shbin.Shbin(open(os.path.join(d, f), "rb").read())
        for k in range(len(sh.entradas)):
            nom = f"{f[:-6]}_e{k}.vert"
            try:
                p = Programa(sh, k)
                open(os.path.join(out, nom), "w", encoding="utf-8").write(p.glsl(f))
                print(f"{nom}: {len(p.subs)} subrutinas")
            except NoEstructurable as ex:
                print(f"{nom}: NO ESTRUCTURABLE: {ex}")


if __name__ == "__main__":
    main()
