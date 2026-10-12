"""Escenario de prueba + mezclador de REFERENCIA en Python para el DSP HLE (recomp/audio/dsp.c). Agente H.
Uso:
  py -I tools/audio_vector.py gen   <escenario.bin>             # arma el escenario con bcstm reales (uso personal)
  py -I tools/audio_vector.py comparar <escenario.bin> <salida.bin> [--esperar-fallo]
El mezclador de referencia esta escrito aparte (flujo continuo + float32 de numpy), NO es una traduccion linea a linea de dsp.c.
Decodifica ADPCM con tools/audio_bcstm.py (decodificador distinto del de C).
Escenario (little-endian): "SCN1", u32 ticks, u32 nfuentes; por fuente: <IIIIf4fBB2x> slot,fmt,canales,interp,rate,gain0[4],loop,cola;
s16 coef[16]; u32 nbufs; por buffer <IIIIhh> id,n,nbytes,adpcm_dirty,yn0,yn1 + datos (relleno a 4); <I4f> tick_cambio_gain,gain nueva; f32 master.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audio_bcstm as bc  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STM = os.path.join(RAIZ, "extraido", "romfs", "SoundData", "stream")
TICKS = 220
MASTER = 0.9
NOCHG = 0xFFFFFFFF
FMT_FUENTE = "<IIIIf4fBB2x"


def raw_adpcm_canal(d, h, canal, bloque):
    """Bytes crudos ADPCM del canal `canal` en el bloque `bloque` (bloques intercalados por canal)."""
    p = h["datos"] + bloque * h["tam_bloque"] * h["nch"] + canal * h["tam_bloque"]
    return d[p:p + h["tam_bloque"]]


def armar():
    dB = open(os.path.join(STM, "STM_BGM_BEACH.bcstm"), "rb").read()
    hB, pcmB = bc.decodificar(dB)
    dA = open(os.path.join(STM, "STM_BGM_ATHLETIC.bcstm"), "rb").read()
    hA, pcmA = bc.decodificar(dA)
    fuentes = []
    # 0: ADPCM mono, 2 buffers en cola (el 2.o continua el estado), lineal, rate 32000/32728, gain cambia en el tick 60
    c = hB["canales"][0]
    mu = hB["mu_bloque"]
    fuentes.append(dict(slot=0, fmt=2, ch=1, interp=1, rate=32000.0 / 32728.0, gain=[0.8, 0.6, 0.1, 0.2], loop=0, queue=1,
                        coef=list(c[0]),
                        bufs=[dict(id=1, n=mu, data=raw_adpcm_canal(dB, hB, 0, 0), dirty=1, yn=list(c[2])),
                              dict(id=2, n=mu, data=raw_adpcm_canal(dB, hB, 0, 1), dirty=0, yn=[0, 0])],
                        chg=(60, [0.2, 0.9, 0.5, 0.0])))
    # 1: PCM16 estereo en bucle (buffer embebido), lineal, rate 1.0
    n = 1000
    s16 = b"".join(struct.pack("<hh", pcmA[0][100000 + i], pcmA[1][100000 + i]) for i in range(n))
    fuentes.append(dict(slot=1, fmt=1, ch=2, interp=1, rate=1.0, gain=[0.3, 0.3, 0.05, 0.05], loop=1, queue=0, coef=[0] * 16,
                        bufs=[dict(id=7, n=n, data=s16, dirty=0, yn=[0, 0])], chg=(NOCHG, [0] * 4)))
    # 2: PCM8 mono, sin interpolacion, rate 0.5, buffer embebido
    n8 = 500
    p8 = bytes(((pcmB[2][50000 + i] >> 8) & 0xFF) for i in range(n8))
    fuentes.append(dict(slot=2, fmt=0, ch=1, interp=2, rate=0.5, gain=[0.5, 0.5, 0.0, 0.0], loop=0, queue=0, coef=[0] * 16,
                        bufs=[dict(id=3, n=n8, data=p8, dirty=0, yn=[0, 0])], chg=(NOCHG, [0] * 4)))
    return fuentes


def escribir(fuentes, ruta):
    o = bytearray(b"SCN1" + struct.pack("<II", TICKS, len(fuentes)))
    for f in fuentes:
        o += struct.pack(FMT_FUENTE, f["slot"], f["fmt"], f["ch"], f["interp"], f["rate"], *f["gain"], f["loop"], f["queue"])
        o += struct.pack("<16h", *f["coef"])
        o += struct.pack("<I", len(f["bufs"]))
        for b in f["bufs"]:
            dat = b["data"] + b"\0" * (-len(b["data"]) % 4)
            o += struct.pack("<IIIIhh", b["id"], b["n"], len(dat), b["dirty"], *b["yn"]) + dat
        o += struct.pack("<I4f", f["chg"][0], *f["chg"][1])
    o += struct.pack("<f", MASTER)
    open(ruta, "wb").write(bytes(o))


def leer_escenario(ruta):
    d = open(ruta, "rb").read()
    assert d[:4] == b"SCN1"
    ticks, n = struct.unpack_from("<II", d, 4)
    p = 12
    fuentes = []
    for _ in range(n):
        slot, fmt, ch, interp, rate, g0, g1, g2, g3, loop, queue = struct.unpack_from(FMT_FUENTE, d, p)
        p += struct.calcsize(FMT_FUENTE)
        coef = list(struct.unpack_from("<16h", d, p))
        p += 32
        nb = struct.unpack_from("<I", d, p)[0]
        p += 4
        bufs = []
        for _ in range(nb):
            bid, bn, nbytes, dirty, y0, y1 = struct.unpack_from("<IIIIhh", d, p)
            p += 20
            bufs.append(dict(id=bid, n=bn, data=d[p:p + nbytes], dirty=dirty, yn=[y0, y1]))
            p += nbytes
        ct, c0, c1, c2, c3 = struct.unpack_from("<I4f", d, p)
        p += 20
        fuentes.append(dict(slot=slot, fmt=fmt, ch=ch, interp=interp, rate=rate, gain=[g0, g1, g2, g3], loop=loop,
                            queue=queue, coef=coef, bufs=bufs, chg=(ct, [c0, c1, c2, c3])))
    return fuentes


# ------------------------------------------------------------------ referencia
def decodificar_buf(f, b, estado):
    """Lista de pares (L,R) de un buffer."""
    if f["fmt"] == 2:
        if b["dirty"]:
            estado[:] = b["yn"]
        out = bc.adpcm(b["data"], f["coef"], estado, b["n"])   # estado = [yn1, yn2]
        if len(out) % 2:
            out.append(0)
        return [(x, x) for x in out]
    if f["fmt"] == 1:
        v = struct.unpack("<%dh" % (2 * b["n"]), b["data"][:4 * b["n"]])
        return [(v[2 * i], v[2 * i + 1]) for i in range(b["n"])]
    r = []
    for x in b["data"][:b["n"]]:           # PCM8 del DSP: byte sin signo << 8, leido como s16
        s = (x << 8) - (0x10000 if x >= 128 else 0)
        r.append((s, s))
    return r


def frames_fuente(f):
    """Frames de 160 pares que produce la fuente por tick, como flujo continuo [xn2=0, xn1=0, muestras...]."""
    estado = [0, 0]
    flujo = [(0, 0), (0, 0)]
    for b in sorted(f["bufs"], key=lambda b: b["id"]):
        flujo += decodificar_buf(f, b, estado)
    L = len(flujo)
    nbuf = L - 2
    paso = int(f32(f["rate"]) * f32(16777216.0))
    ESC = 1 << 24

    def S(j):
        if f["loop"] and j >= 2:
            return flujo[2 + (j - 2) % nbuf]
        return flujo[j]

    salidas = []
    pos = 0
    while len(salidas) < (TICKS + 2) * 160:
        i = pos >> 24
        if not f["loop"] and i + 2 >= L:      # hace falta una muestra mas alla de x1 (condicion del original)
            break
        fr = pos & (ESC - 1)
        if f["interp"] == 2:
            y = [S(i)[0], S(i)[1]]
        else:
            y = []
            for c in range(2):
                x0, x1 = S(i)[c], S(i + 1)[c]
                d = max(-32768, min(32767, x1 - x0))
                # el original hace la cuenta en u64: con delta negativo da x0 - ceil(fr*|d|/2^24), no floor
                v = x0 + (fr * d >> 24) if d >= 0 else x0 - ((fr * -d + ESC - 1) >> 24)
                y.append(((v + 32768) & 0xFFFF) - 32768)
        salidas.append(y)
        pos += paso
    frames = [[[0, 0]] * 160]   # el 1.er tick solo desencola el buffer y entrega un frame vacio
    k = 0
    while len(frames) < TICKS:
        fr = salidas[k:k + 160]
        fr = fr + [[0, 0]] * (160 - len(fr))
        k += 160
        frames.append(fr)
    return frames


def f32(x):
    """Redondea a float32 (+,-,* en double y luego a float32 dan el resultado IEEE exacto de float32)."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def trunc(v):
    return int(v)   # trunca hacia cero, como el (int32_t) de C


def clamp16(v):
    return max(-32768, min(32767, v))


def referencia(fuentes):
    out = []
    master = f32(MASTER)
    todos = [(f, frames_fuente(f)) for f in fuentes]
    escala = f32(f32(1.0) / f32(159.0))
    prog = [f32(f32(i) * escala) for i in range(160)]
    for t in range(TICKS):
        dest = [[0, 0, 0, 0] for _ in range(160)]
        for f, frs in todos:
            g = [f32(v) for v in f["gain"]]
            ramp = None
            if f["chg"][0] != NOCHG:
                if t >= f["chg"][0]:
                    g = [f32(v) for v in f["chg"][1]]
                if t == f["chg"][0]:
                    ramp = [f32(v) for v in f["gain"]]
            for i in range(160):
                if ramp is None:
                    gg = g
                else:
                    gg = [f32(ramp[k] + f32(f32(g[k] - ramp[k]) * prog[i])) for k in range(4)]
                L, R = frs[t][i]
                d = dest[i]
                d[0] += trunc(f32(gg[0] * L))
                d[1] += trunc(f32(gg[1] * R))
                d[2] += trunc(f32(gg[2] * L))
                d[3] += trunc(f32(gg[3] * R))
        fr = []
        for i in range(160):
            x = [f32(v) for v in dest[i]]
            l = clamp16(trunc(f32(f32(master * x[0]) + f32(master * x[2]))))
            r = clamp16(trunc(f32(f32(master * x[1]) + f32(master * x[3]))))
            fr.append((l, r))
        out.append(fr)
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "gen":
        escribir(armar(), sys.argv[2])
        print("escenario escrito:", sys.argv[2])
    elif sys.argv[1] == "comparar":
        ref = referencia(leer_escenario(sys.argv[2]))
        raw = open(sys.argv[3], "rb").read()
        assert len(raw) >= TICKS * 640, "salida corta: %d ticks" % (len(raw) // 640)
        got = struct.unpack("<%dh" % (TICKS * 320), raw[:TICKS * 640])
        n_mal, maxd, primero, pot2 = 0, 0, None, 0.0
        for t in range(TICKS):
            for i in range(160):
                for c in range(2):
                    e = ref[t][i][c]
                    g = got[t * 320 + i * 2 + c]
                    pot2 += e * e
                    if e != g:
                        n_mal += 1
                        maxd = max(maxd, abs(e - g))
                        if primero is None:
                            primero = (t, i, c)
        pot = (pot2 / (TICKS * 320)) ** 0.5
        print(f"ticks={TICKS} muestras={TICKS * 320} difieren={n_mal} max|dif|={maxd} rms_ref={pot:.1f} "
              f"primero(tick,mu,canal)={primero}")
        espera_fallo = "--esperar-fallo" in sys.argv
        ok = (n_mal == 0) != espera_fallo
        if pot < 100:
            print("ATENCION: referencia casi muda, la prueba no demuestra nada")
            ok = False
        print("RESULTADO:", "OK" if ok else "FALLO", "(se esperaba fallo)" if espera_fallo else "")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
