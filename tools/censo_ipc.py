"""Censo estatico de IPC de SM3DL (capstone sobre code.bin). Uso: py -I tools/censo_ipc.py
Salidas: extraido/ipc_comandos.tsv y extraido/ipc_servicios.tsv (auxiliar).
"""
import os, re, struct, sys, bisect, collections
import capstone

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")
BASE = 0x100000
b = open(os.environ.get("CENSO_CODE_BIN", os.path.join(RAIZ, "extraido", "code.bin")), "rb").read()
SALIDA = os.environ.get("CENSO_SALIDA", os.path.join(RAIZ, "extraido"))
TEXT_END = 0x100000 + 2758524
nombres = {}
for l in open(os.path.join(RAIZ, "extraido", "simbolos.txt"), encoding="utf-8"):
    m = re.match(r"\s*(0x[0-9A-Fa-f]+)\s+(\S+)", l)
    if m:
        nombres[int(m.group(1), 16)] = m.group(2)
funcs = []
for l in open(os.path.join(RAIZ, "extraido", "funciones.tsv")):
    p = l.split()
    if len(p) >= 2 and re.fullmatch(r"[0-9A-Fa-f]{8}", p[0]):
        funcs.append(int(p[0], 16))
for l in open(os.path.join(RAIZ, "extraido", "funciones_extra.tsv")):
    p_ = l.split()
    if p_ and re.fullmatch(r"[0-9A-Fa-f]{8}", p_[0]):
        funcs.append(int(p_[0], 16))
funcs = sorted(set(funcs))


def func_de(a):
    i = bisect.bisect_right(funcs, a) - 1
    return funcs[i] if i >= 0 else 0


def u32(a):
    return struct.unpack_from("<I", b, a - BASE)[0]


md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
ins_all = []
_a = BASE
while _a < TEXT_END:
    _n = 0
    for _i in md.disasm(b[_a - BASE:TEXT_END - BASE], _a):
        ins_all.append(_i)
        _n += 1
    _a = (ins_all[-1].address + 4) if _n else _a
    if _n == 0 or _a < TEXT_END:
        _a += 4 if _n == 0 else 4
idx = {i.address: k for k, i in enumerate(ins_all)}

PCLIT = re.compile(r"^(r\d+|ip|lr|sp|sb|sl|fp), \[pc, #(-?0x[0-9a-f]+|-?\d+)\]$")
PCLIT0 = re.compile(r"^(r\d+|ip|lr|sb|sl|fp), \[pc\]$")


def lit_de(q):
    m = PCLIT.match(q.op_str)
    if m:
        return m.group(1), u32(q.address + 8 + int(m.group(2), 0))
    m = PCLIT0.match(q.op_str)
    if m:
        return m.group(1), u32(q.address + 8)
    return None


# ---------- 1. cadenas de servicio ----------
CONOC = set("srv: fs:USER fs:LDR APT:U APT:A APT:S hid:USER hid:SPVR gsp::Gpu gsp::Lcd dsp::DSP cfg:u cfg:i cfg:s ptm:u ptm:sysm ptm:play ptm:gets ptm:sets ndm:u frd:u frd:a frd:n ir:u ir:USER ir:rst mic:u cam:u ac:u ac:i boss:U boss:P news:u news:s y2r:u nim:aoc nim:u nim:s am:net am:u cecd:u cecd:s cecd:ndm err:f pm:app ps:ps http:C ssl:C soc:U csnd:SND ldr:ro nwm::UDS nwm::EXT nfc:u nfc:m dlp:FKCL dlp:CLNT dlp:SRVR mcu::HWC qtm:u qtm:s qtm:sp mvd:STD act:u act:a".split())
servs = {}
for m in re.finditer(rb"[\x21-\x7e]{3,12}\x00", b):
    s = m.group(0)[:-1].decode()
    if s in CONOC:
        servs[BASE + m.start()] = s

# ---------- 2. handles -> servicio ----------
GSH = (0x292114, 0x105798)
handle_serv = {}
filas_serv = []
for k, i in enumerate(ins_all):
    if i.mnemonic == "bl" and i.op_str.startswith("#") and int(i.op_str[1:], 0) in GSH:
        f = func_de(i.address)
        hv = None
        for j in range(k - 1, max(k - 40, 0), -1):
            q = ins_all[j]
            if q.address < f:
                break
            l = lit_de(q) if q.mnemonic == "ldr" else None
            if l and l[0] == "r0" and l[1] >= 0x3E1000:
                hv = l[1]
                break
        nom = []
        j = idx[f]
        fin = f + 0x400
        while j < len(ins_all) and ins_all[j].address < fin:
            q = ins_all[j]
            l = lit_de(q) if q.mnemonic == "ldr" else None
            if l:
                v = l[1]
                if v in servs:
                    nom.append(servs[v])
                elif BASE <= v < BASE + len(b) - 16:
                    for off in (0, 4, 8, 12):
                        c2 = u32(v + off)
                        if c2 in servs:
                            nom.append(servs[c2])
            if q.address > i.address and ((q.mnemonic == "pop" and "pc" in q.op_str) or (q.mnemonic == "bx" and q.op_str == "lr")):
                break
            j += 1
        filas_serv.append((i.address, f, hv, sorted(set(nom))))
sv = open(os.path.join(SALIDA, "ipc_servicios.tsv"), "w", encoding="utf-8", newline="\n")
sv.write("call_addr\tfunc\thandle_var\tservicios_en_la_funcion\n")
for a, f, hv, nom in filas_serv:
    sv.write(f"0x{a:08X}\t0x{f:08X}\t{('0x%X' % hv) if hv else ''}\t{','.join(nom)}\n")
    if hv and len(nom) == 1:
        handle_serv[hv] = nom[0]
sv.close()
for l in open(os.path.join(RAIZ, "extraido", "propuestas_servicios.txt"), encoding="utf-8"):
    m3 = re.search(r'GetServiceHandle\(\(?"?([\w:]+)"?.*handle (0x[0-9A-Fa-f]+)', l)
    if m3:
        handle_serv.setdefault(int(m3.group(2), 16), m3.group(1))


# ---------- 3. cabeceras IPC en cada svc 0x32 ----------
def decodificar(h):
    return (h >> 16) & 0xFFFF, (h >> 6) & 0x3F, h & 0x3F


ADD = re.compile(r"^(r\d+|ip|lr|sb|sl|fp), (r\d+|ip|lr|sb|sl|fp), #(0x[0-9a-f]+|\d+)$")
MOV = re.compile(r"^(r\d+|ip|lr|sb|sl|fp), #(0x[0-9a-f]+|\d+)$")
STR = re.compile(r"^(r\d+|ip|lr|sb|sl|fp), \[(r\d+|ip|lr|sb|sl|fp)(?:, #(0x[0-9a-f]+|\d+))?\]$")
LDR0 = re.compile(r"^(r\d+|ip|lr|sb|sl|fp), \[(r\d+|ip|lr|sb|sl|fp)\]$")
def parse_store(mn, op):
    """devuelve (lista_regs, base, off_de_la_primera, writeback_nuevo_off|None) o None"""
    if mn in ("stm", "stmia", "stmib"):
        m = re.match(r"^(r\d+|ip|lr|sb|sl|fp)(!?), \{(.*)\}$", op)
        if not m:
            return None
        regs_l = [x.strip() for x in m.group(3).split(",")]
        return regs_l, m.group(1), (4 if mn == "stmib" else 0), None
    m = re.match(r"^(.*?), \[(r\d+|ip|lr|sp|sb|sl|fp)(?:, #(-?0x[0-9a-f]+|-?\d+))?\](!?)$", op)
    if not m:
        return None
    regs_l = [x.strip() for x in m.group(1).split(",")]
    off = int(m.group(3), 0) if m.group(3) else 0
    return regs_l, m.group(2), off, (off if m.group(4) else None)


filas = []
for k, i in enumerate(ins_all):
    if not (i.mnemonic == "svc" and i.op_str in ("#0x32", "#50")):
        continue
    f = func_de(i.address)
    j0 = idx.get(f, max(0, k - 60))
    regs = {}
    cab = None
    hvar = None
    for j in range(j0, k):
        q = ins_all[j]
        op = q.op_str
        mn = q.mnemonic
        if mn == "ldr":
            l = lit_de(q)
            if l:
                regs[l[0]] = l[1]
                continue
        if mn == "mrc" and "c13, c0, #3" in op:
            regs[op.split(",")[2].strip()] = ("tls", 0)
            continue
        if mn == "add":
            m = ADD.match(op)
            if m and isinstance(regs.get(m.group(2)), tuple):
                regs[m.group(1)] = ("tls", regs[m.group(2)][1] + int(m.group(3), 0))
                continue
        if mn == "mov":
            m = MOV.match(op)
            if m:
                regs[m.group(1)] = int(m.group(2), 0)
                continue
        if mn in ("str", "strd", "stm", "stmia", "stmib"):
            r = parse_store(mn, op)
            if r:
                regs_l, rb_n, off, wb = r
                rb = regs.get(rb_n)
                if isinstance(rb, tuple) and rb[1] + off == 0x80 and isinstance(regs.get(regs_l[0]), int):
                    cab = regs[regs_l[0]]
                if wb is not None and isinstance(rb, tuple):
                    regs[rb_n] = ("tls", rb[1] + wb)
            continue
        if mn == "ldr":
            m = LDR0.match(op)
            if m:
                src = regs.get(m.group(2))
                if isinstance(src, int) and src >= 0x3E1000 and m.group(1) == "r0":
                    hvar = src
                regs.pop(m.group(1), None)
                continue
        if mn in ("str", "strd", "stm", "stmib", "stmia", "cmp", "tst", "b", "push", "svc", "strb", "strh"):
            continue
        if mn == "bl":
            for r in ("r0", "r1", "r2", "r3", "ip"):
                regs.pop(r, None)
            continue
        rd = op.split(",")[0].strip()
        regs.pop(rd, None)
    filas.append((i.address, f, cab, hvar))

# ---------- 4. nombres desde azahar ----------
AZ = os.path.join(RAIZ, "..", "azahar-src", "src", "core", "hle", "service")
TAB = {}
for d in sorted(os.listdir(AZ)):
    p = os.path.join(AZ, d)
    if not os.path.isdir(p):
        continue
    for r, _, fs in os.walk(p):
        for fn in fs:
            if not fn.endswith((".cpp", ".h")):
                continue
            t = open(os.path.join(r, fn), encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r'\{\s*(0x[0-9A-Fa-f]+)\s*,\s*[^,]+?\s*,\s*"(\w+)"\s*\}', t):
                TAB.setdefault((d, fn, int(m.group(1), 16)), m.group(2))


def nombre_az(dirs, cmd, pref=None):
    r = [f"{d}/{fn.split('.')[0]}:{n}" for (d, fn, c), n in TAB.items() if c == cmd and d in dirs]
    if pref:
        r = [x for x in r if x.split("/")[1].split(":")[0] in pref] or r
    return r


DIRS = {"srv:": ["sm"], "fs:USER": ["fs"], "APT:U": ["apt"], "hid:USER": ["hid"], "gsp::Gpu": ["gsp"], "dsp::DSP": ["dsp"],
        "cfg:u": ["cfg"], "ptm:u": ["ptm"], "ndm:u": ["ndm"], "frd:u": ["frd"], "mic:u": ["mic"], "cam:u": ["cam"], "ac:u": ["ac"],
        "boss:U": ["boss"], "news:u": ["news"], "y2r:u": ["y2r", "cam"], "cecd:u": ["cecd"], "err:f": ["err"], "am:u": ["am"],
        "ir:USER": ["ir"], "nim:u": ["nim"], "csnd:SND": ["csnd"], "ldr:ro": ["ldr_ro"], "nwm::UDS": ["nwm"], "gsp::Lcd": ["gsp"],
        "pm:app": ["pm"], "ps:ps": ["ps"], "mcu::HWC": ["mcu"], "nfc:u": ["nfc"]}
PREF = {"APT": "APT:U", "GSPGPU": "gsp::Gpu", "DSP": "dsp::DSP", "HIDUSER": "hid:USER", "HID": "hid:USER", "SRV": "srv:", "FSUSER": "fs:USER",
        "CFGU": "cfg:u", "NDMU": "ndm:u", "ERRF": "err:f"}

# ---------- 5. alcance desde la entrada (grafo estatico) ----------
fset = set(funcs)
directo = collections.defaultdict(set)    # f -> destinos por bl/b
punteros = collections.defaultdict(set)   # f -> funciones cuyo inicio aparece como literal
llamadores = collections.defaultdict(set)
for k, i in enumerate(ins_all):
    f = func_de(i.address)
    if i.mnemonic in ("bl", "b") and i.op_str.startswith("#"):
        t = int(i.op_str[1:], 0)
        tf = func_de(t)
        if t - tf in (0, 4) and tf != f:
            directo[f].add(tf)
            llamadores[tf].add(f)
        elif t != tf and tf != f and t in fset:
            pass
    elif i.mnemonic == "ldr":
        l = lit_de(i)
        if l and l[1] in fset and l[1] != f:
            punteros[f].add(l[1])
# thunk 0x292114 -> 0x105798 (salto)
def bfs(raices, con_punteros):
    dist = {}
    padre = {}
    cola = collections.deque()
    for r in raices:
        dist[r] = 0
        padre[r] = None
        cola.append(r)
    while cola:
        u = cola.popleft()
        vs = set(directo.get(u, ()))
        if con_punteros:
            vs |= punteros.get(u, set())
        for v in sorted(vs):
            if v not in dist:
                dist[v] = dist[u] + 1
                padre[v] = u
                cola.append(v)
    return dist, padre
# raices extra: .init_array (entradas relativas, ver BITACORA del agente J) -> solo se reportan aparte
dist_d, pad_d = bfs([0x100000], False)
dist_p, pad_p = bfs([0x100000], True)
def cadena(pad, x):
    c = []
    while x is not None:
        c.append(x)
        x = pad.get(x)
    return c[::-1]

# votacion: handle -> servicio por el prefijo del nombre de los wrappers que lo usan
voto = collections.defaultdict(collections.Counter)
for a_, f_, cab_, hv_ in filas:
    nm_ = nombres.get(f_, nombres.get(f_ + 4, ""))
    if hv_ and nm_ and nm_.split("_")[0] in PREF:
        voto[hv_][PREF[nm_.split("_")[0]]] += 1
for hv_, c in voto.items():
    handle_serv.setdefault(hv_, c.most_common(1)[0][0])
# inferidos a mano (ver reporte): handles sin GetServiceHandle visible en el censo
INFERIDOS = {0x3E26B4: "srv:", 0x3E3190: "cam:u", 0x3F0370: "cecd:s", 0x3F036C: "cecd:u"}
for h_, s_ in INFERIDOS.items():
    handle_serv.setdefault(h_, s_)
PREF.update({"CECDU": "cecd:u", "CECD2": "cecd:s", "SvcX3E3190": "cam:u", "FSFILE": "fs:USER(file)", "FSDIR": "fs:USER(dir)",
             "CFGU": "cfg:u", "MIC": "mic:u", "CECD": "cecd:u"})
DIRS.update({"cecd:s": ["cecd"], "fs:USER(file)": ["fs"], "fs:USER(dir)": ["fs"]})

out = open(os.path.join(SALIDA, "ipc_comandos.tsv"), "w", encoding="utf-8", newline="\n")
out.write("wrapper\tfuncion_nombre\tsvc_addr\tcabecera\tcmd_id\tn_normales\tn_traducidos\thandle_var\tservicio\tnombre_azahar\tnota\tn_llamadores\tprof_directa\tprof_con_punteros\n")
n_az = 0
for a, f, cab, hv in sorted(filas, key=lambda x: x[0]):
    nm = nombres.get(f, nombres.get(f + 4, "")) or ("SRV_GetServiceHandle" if f == 0x105798 else "")
    serv = handle_serv.get(hv, "") if hv else ""
    if not serv and nm:
        serv = PREF.get(nm.split("_")[0], "")
    if nm.startswith(("FSFILE", "FSDIR")):
        serv = PREF[nm.split("_")[0]]
    if cab is None:
        out.write(f"0x{f:08X}\t{nm}\t0x{a:08X}\t\t\t\t\t{('0x%X' % hv) if hv else ''}\t{serv}\t\tsin_cabecera_constante\t\t\t\n")
        continue
    cmd, n, t = decodificar(cab)
    stem = {"fs:USER(file)": ["file"], "fs:USER(dir)": ["directory"], "fs:USER": ["fs_user"], "cfg:u": ["cfg_u", "cfg_i", "cfg_s"], "gsp::Gpu": ["gsp_gpu"],
            "APT:U": ["apt_u"], "hid:USER": ["hid_user"], "cecd:u": ["cecd_u"], "cecd:s": ["cecd_s"], "cam:u": ["cam_u"], "mic:u": ["mic_u"]}.get(serv)
    az = nombre_az(DIRS.get(serv, []), cmd, stem) if serv in DIRS else []
    if n_az is not None and az:
        n_az += 1
    out.write(f"0x{f:08X}\t{nm}\t0x{a:08X}\t0x{cab:08X}\t0x{cmd:X}\t{n}\t{t}\t{('0x%X' % hv) if hv else ''}\t{serv}\t{'|'.join(az[:3])}\t\t{len(llamadores.get(f, ()))}\t{dist_d.get(f, '')}\t{dist_p.get(f, '')}\n")
out.close()
print("svc 0x32:", len(filas), "con cabecera:", sum(1 for x in filas if x[2] is not None),
      "handle resuelto a servicio:", sum(1 for x in filas if x[3] in handle_serv), "con nombre azahar:", n_az)
print("cadenas servicio:", sorted(servs.items()))
print("handles->serv:", {hex(k): v for k, v in sorted(handle_serv.items())})
print("tabla azahar:", len(TAB))

# ---------- 6. cadenas de arranque de los Initialize ----------
INITS = {"srvInit": 0x292EFC, "APT_OpenSession": 0x291A68, "APT_Initialize": 0x103080, "FS_Initialize": 0x103E8C, "FSUSER_Initialize": 0x10756C,
         "GSPGPU_Initialize": 0x107A24, "HID_Initialize": 0x1F3AC4, "DSP_Initialize": 0x1F2BD0, "CFGU_Initialize": 0x1012C8,
         "NDMU_Initialize": 0x291F78, "MIC_Initialize": 0x1F57A8, "CECD_Initialize": 0x1F1AB8, "ERRF_Throw": 0x28BC4C, "DSP_LoadComponent": 0x28BBD4}
print("--- cadenas desde 0x100000 ---")
for n, a in INITS.items():
    cd = cadena(pad_d, a) if a in dist_d else None
    cp = cadena(pad_p, a) if a in dist_p else None
    print(n, hex(a), "llamadores:", [hex(x) for x in sorted(llamadores.get(a, ()))][:6])
    print("   directa:", " > ".join(hex(x) for x in cd) if cd else "NO")
    print("   punteros:", " > ".join(hex(x) for x in cp) if cp else "NO")

# ---------- 7. subida por llamadores para los Initialize no alcanzables ----------
datos_ptr = collections.defaultdict(list)
for off in range(0x3A2000 - BASE, len(b) - 3, 4):
    v = struct.unpack_from("<I", b, off)[0]
    if v in fset:
        datos_ptr[v].append(BASE + off)
print("--- subida (llamadores hasta algo alcanzable / sin llamador / puntero en datos) ---")
for n in ("HID_Initialize", "DSP_Initialize", "MIC_Initialize", "CECD_Initialize"):
    a = INITS[n]
    print(n)
    vis = {a}
    nivel = [a]
    for d in range(1, 7):
        sig = []
        for x in nivel:
            for c in sorted(llamadores.get(x, ())):
                if c in vis: continue
                vis.add(c); sig.append(c)
                marca = ("ALCANZABLE d=%s" % dist_p[c]) if c in dist_p else ""
                dp = ("dato@" + hex(datos_ptr[c][0])) if c in datos_ptr else ""
                print(f"   nivel {d}: {hex(c)} (llama a {hex(x)}) {marca} {dp} llamadores={len(llamadores.get(c, ()))}")
        nivel = sig[:12]
        if not nivel: break
