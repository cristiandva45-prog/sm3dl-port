"""Decodifica un .bcstm (CSTM de la 3DS: PCM8, PCM16 o DSP-ADPCM) a WAV, para revisar la musica del port.
Uso personal: los WAV no se comparten.

Uso: py -I tools\\audio_bcstm.py <entrada.bcstm> <salida.wav>
Formato: cabecera CSTM con 3 bloques (INFO 0x4000, SEEK 0x4001, DATA 0x4002). INFO+8 tiene 3 referencias
(u16 tipo, u16 relleno, s32 offset relativo a INFO+8): info de stream, tabla de pistas, tabla de canales.
Los datos van en bloques intercalados: por bloque, block_size bytes de cada canal (el ultimo, padded).
DSP-ADPCM: frames de 8 bytes = 1 byte de cabecera (predictor<<4 | escala) + 14 muestras de 4 bits.
"""
import struct
import sys
import wave


def leer(d):
    assert d[:4] == b"CSTM", "no es CSTM"
    nb = struct.unpack_from("<H", d, 0x10)[0]
    bloques = {}
    for k in range(nb):
        t, o, s = struct.unpack_from("<H2xII", d, 0x14 + 12 * k)
        bloques[t] = (o, s)
    info = bloques[0x4000][0] + 8
    refs = [struct.unpack_from("<Hxxi", d, info + 8 * k) for k in range(3)]
    si = info + refs[0][1]
    codec, loop, nch = d[si], d[si + 1], d[si + 2]
    (rate, loop_ini, loop_fin, n_bloques, tam_bloque, mu_bloque, tam_ult, mu_ult, tam_ult_pad) = \
        struct.unpack_from("<9I", d, si + 4)
    ct = info + refs[2][1]
    n = struct.unpack_from("<I", d, ct)[0]
    canales = []
    for k in range(n):
        t, o = struct.unpack_from("<Hxxi", d, ct + 4 + 8 * k)
        ci = ct + o
        t2, o2 = struct.unpack_from("<Hxxi", d, ci)
        coef = ps = yn = None
        if codec == 2 and o2 != -1:
            a = ci + o2
            coef = struct.unpack_from("<16h", d, a)
            ps = struct.unpack_from("<H", d, a + 32)[0]
            yn = list(struct.unpack_from("<2h", d, a + 34))
        canales.append((coef, ps, yn))
    datos = bloques[0x4002][0] + 0x20
    return dict(codec=codec, loop=loop, nch=nch, rate=rate, loop_ini=loop_ini, loop_fin=loop_fin,
                n_bloques=n_bloques, tam_bloque=tam_bloque, mu_bloque=mu_bloque, tam_ult=tam_ult,
                mu_ult=mu_ult, tam_ult_pad=tam_ult_pad, canales=canales, datos=datos)


def adpcm(b, coef, yn, n):
    out = []
    y1, y2 = yn
    for f in range(0, len(b), 8):
        h = b[f]
        esc, pred = 1 << (h & 0xF), h >> 4
        c1, c2 = coef[2 * pred], coef[2 * pred + 1]
        for k in range(14):
            if len(out) >= n:
                return out
            byte = b[f + 1 + k // 2]
            nib = (byte >> 4) if k % 2 == 0 else (byte & 0xF)
            if nib >= 8:
                nib -= 16
            s = ((nib * esc) << 11) + 1024 + c1 * y1 + c2 * y2
            s >>= 11
            s = max(-32768, min(32767, s))
            y2, y1 = y1, s
            out.append(s)
    yn[0], yn[1] = y1, y2
    return out


def decodificar(d):
    h = leer(d)
    pcm = [[] for _ in range(h["nch"])]
    p = h["datos"]
    estados = [list(c[2]) if c[2] else [0, 0] for c in h["canales"]]
    for b in range(h["n_bloques"]):
        ult = b == h["n_bloques"] - 1
        tam = h["tam_ult_pad"] if ult else h["tam_bloque"]
        mu = h["mu_ult"] if ult else h["mu_bloque"]
        for c in range(h["nch"]):
            trozo = d[p:p + tam]
            p += tam
            if h["codec"] == 2:
                pcm[c] += adpcm(trozo, h["canales"][c][0], estados[c], mu)
            elif h["codec"] == 1:
                pcm[c] += list(struct.unpack_from(f"<{mu}h", trozo))
            else:
                pcm[c] += [((x ^ 0x80) - 128) << 8 for x in trozo[:mu]]
    return h, pcm


def main():
    d = open(sys.argv[1], "rb").read()
    h, pcm = decodificar(d)
    n = min(len(x) for x in pcm)
    with wave.open(sys.argv[2], "wb") as w:
        w.setnchannels(h["nch"])
        w.setsampwidth(2)
        w.setframerate(h["rate"])
        w.writeframes(b"".join(struct.pack(f"<{h['nch']}h", *(pcm[c][i] for c in range(h["nch"]))) for i in range(n)))
    print(f"codec={h['codec']} canales={h['nch']} {h['rate']} Hz, {n} muestras ({n / h['rate']:.1f} s), "
          f"loop={h['loop']} [{h['loop_ini']}, {h['loop_fin']})")


if __name__ == "__main__":
    main()
