/* TEXTURAS DE REEMPLAZO / ALTA DEFINICION — implementacion (agente T4, 9 oct 2026). Contrato: texturas_hd.h.
 * - Indice de <raiz>\texturas_hd\tex_<w>x<h>_f<fmt>_<CLAVE %08X>.png al PRIMER uso (un solo listado de carpeta); despues una
 *   busqueda es un hash en memoria: las claves AUSENTES no tocan el disco (= "recuerdo de ausentes").
 * - PNG propio (inflate + filtros; gris/RGB/paleta/gris+alfa/RGBA, 1..16 bits, tRNS; sin entrelazado Adam7).
 * - Mips por caja 2x2 en espacio LINEAL con alfa premultiplicado (sin bordes oscuros). Dimension impar: se descarta la ultima
 *   fila/columna al reducir (nivel siguiente = max(1, n/2)).
 * - Cache LRU por bytes (SM3DL_TEX_HD_MB, 512 por defecto). Los punteros devueltos valen hasta la proxima texhd_buscar.
 * - CONVENCION DE FILAS: igual que texturas.c (`poner` escribe la fila PICA Y en la fila alto-1-Y) => buffer TOP-DOWN, fila 0 =
 *   arriba de la imagen vista = fila 0 de un PNG. No se voltea nada, ni al cargar ni al volcar.
 * - Sin hilo de precarga (decision: cargar al primer uso, una vez por textura, basta; evita carreras).
 * Variables: SM3DL_TEX_HD=0 apaga; SM3DL_TEX_HD_DIR=<carpeta>; SM3DL_TEX_VOLCAR=<carpeta>; SM3DL_TEX_HD_MB=<limite de cache>.
 * Prueba unitaria: agentes_tex\T4\prueba_texhd.c (incluye este .c; -DTEXHD_SABOTAJE=1..4 rompe a proposito). */
#include "texturas_hd.h"
#include <windows.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef TEXHD_SABOTAJE
#define TEXHD_SABOTAJE 0
#endif

/* ===================== inflate (zlib/deflate, estilo puff) ===================== */
typedef struct { const uint8_t *in; size_t n, pos; uint32_t buf; int cnt; uint8_t *out; size_t cap, op; int err; } Inf;
typedef struct { short count[16]; short symbol[320]; } Huf;

static int ibits(Inf *s, int need)
{
    uint32_t v = s->buf;
    while (s->cnt < need) {
        if (s->pos >= s->n) { s->err = 1; return 0; }
        v |= (uint32_t)s->in[s->pos++] << s->cnt;
        s->cnt += 8;
    }
    s->buf = v >> need;
    s->cnt -= need;
    return (int)(v & ((1u << need) - 1));
}

static int hconstruir(Huf *h, const short *len, int n)
{
    short offs[16];
    for (int i = 0; i < 16; i++) h->count[i] = 0;
    for (int i = 0; i < n; i++) h->count[len[i]]++;
    if (h->count[0] == n) return 0;
    int left = 1;
    for (int l = 1; l < 16; l++) { left <<= 1; left -= h->count[l]; if (left < 0) return left; }
    offs[1] = 0;
    for (int l = 1; l < 15; l++) offs[l + 1] = (short)(offs[l] + h->count[l]);
    for (int i = 0; i < n; i++) if (len[i]) h->symbol[offs[len[i]]++] = (short)i;
    return left;
}

static int hdecodificar(Inf *s, const Huf *h)
{
    int code = 0, first = 0, index = 0;
    for (int l = 1; l < 16; l++) {
        code |= ibits(s, 1);
        if (s->err) return -1;
        int count = h->count[l];
        if (code - count < first) return h->symbol[index + (code - first)];
        index += count; first += count; first <<= 1; code <<= 1;
    }
    return -1;
}

static const short LBASE[29] = {3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258};
static const short LEXT[29] = {0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0};
static const short DBASE[30] = {1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577};
static const short DEXT[30] = {0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13};

static int icodigos(Inf *s, const Huf *lc, const Huf *dc)
{
    for (;;) {
        int sym = hdecodificar(s, lc);
        if (sym < 0) return -1;
        if (sym < 256) {
            if (s->op >= s->cap) return -1;
            s->out[s->op++] = (uint8_t)sym;
        } else if (sym == 256) {
            return 0;
        } else {
            sym -= 257;
            if (sym >= 29) return -1;
            int len = LBASE[sym] + ibits(s, LEXT[sym]);
            int ds = hdecodificar(s, dc);
            if (ds < 0 || ds >= 30) return -1;
            size_t dist = (size_t)DBASE[ds] + (size_t)ibits(s, DEXT[ds]);
            if (s->err || dist > s->op || s->op + (size_t)len > s->cap) return -1;
            for (int k = 0; k < len; k++) { s->out[s->op] = s->out[s->op - dist]; s->op++; }
        }
    }
}

/* inflate de un flujo zlib; devuelve los bytes producidos (en out, tope cap) o -1 */
static long inflar_zlib(const uint8_t *in, size_t n, uint8_t *out, size_t cap)
{
    if (n < 2 || (in[0] & 15) != 8 || ((in[0] << 8) | in[1]) % 31) return -1;
    Inf s = { in + 2, n - 2, 0, 0, 0, out, cap, 0, 0 };
    int last;
    do {
        last = ibits(&s, 1);
        int tipo = ibits(&s, 2);
        if (s.err) return -1;
        if (tipo == 0) {
            s.buf = 0; s.cnt = 0;
            if (s.pos + 4 > s.n) return -1;
            unsigned len = s.in[s.pos] | (s.in[s.pos + 1] << 8), nlen = s.in[s.pos + 2] | (s.in[s.pos + 3] << 8);
            s.pos += 4;
            if ((len ^ 0xFFFFu) != nlen || s.pos + len > s.n || s.op + len > s.cap) return -1;
            memcpy(s.out + s.op, s.in + s.pos, len);
            s.pos += len; s.op += len;
        } else if (tipo == 1) {
            Huf lc, dc;
            short l[320];
            int i = 0;
            for (; i < 144; i++) l[i] = 8;
            for (; i < 256; i++) l[i] = 9;
            for (; i < 280; i++) l[i] = 7;
            for (; i < 288; i++) l[i] = 8;
            hconstruir(&lc, l, 288);
            for (i = 0; i < 30; i++) l[i] = 5;
            hconstruir(&dc, l, 30);
            if (icodigos(&s, &lc, &dc)) return -1;
        } else if (tipo == 2) {
            static const short orden[19] = {16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15};
            short l[320];
            int nlen = ibits(&s, 5) + 257, ndist = ibits(&s, 5) + 1, ncode = ibits(&s, 4) + 4;
            if (s.err || nlen > 286 || ndist > 30) return -1;
            int i;
            for (i = 0; i < ncode; i++) l[orden[i]] = (short)ibits(&s, 3);
            for (; i < 19; i++) l[orden[i]] = 0;
            Huf lc, dc;
            if (hconstruir(&lc, l, 19) != 0) return -1;
            i = 0;
            while (i < nlen + ndist) {
                int sym = hdecodificar(&s, &lc);
                if (sym < 0) return -1;
                if (sym < 16) l[i++] = (short)sym;
                else {
                    int rep, val = 0;
                    if (sym == 16) { if (i == 0) return -1; val = l[i - 1]; rep = 3 + ibits(&s, 2); }
                    else if (sym == 17) rep = 3 + ibits(&s, 3);
                    else rep = 11 + ibits(&s, 7);
                    if (i + rep > nlen + ndist) return -1;
                    while (rep--) l[i++] = (short)val;
                }
                if (s.err) return -1;
            }
            if (l[256] == 0) return -1;
            int e1 = hconstruir(&lc, l, nlen);
            if (e1 < 0 || (e1 > 0 && nlen - lc.count[0] != 1)) return -1;
            int e2 = hconstruir(&dc, l + nlen, ndist);
            if (e2 < 0 || (e2 > 0 && ndist - dc.count[0] != 1)) return -1;
            if (icodigos(&s, &lc, &dc)) return -1;
        } else return -1;
    } while (!last);
    return (long)s.op;
}

/* ===================== PNG: decodificar a RGBA8 ===================== */
static uint32_t be32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]; }

static int muestra(const uint8_t *fila, int k, int prof, int *escalada)
{
    if (prof == 8) { *escalada = fila[k]; return fila[k]; }
    if (prof == 16) { *escalada = fila[2 * k]; return (fila[2 * k] << 8) | fila[2 * k + 1]; }
    int por = 8 / prof, sh = 8 - prof * (k % por + 1), m = (1 << prof) - 1;
    int v = (fila[k / por] >> sh) & m;
    *escalada = v * 255 / m;
    return v;
}

/* devuelve RGBA8 (malloc) o NULL; w,h de salida. */
static uint8_t *png_decodificar(const uint8_t *d, size_t n, int *pw, int *ph)
{
    static const uint8_t firma[8] = {137, 80, 78, 71, 13, 10, 26, 10};
    if (n < 33 || memcmp(d, firma, 8)) return NULL;
    uint32_t w = 0, h = 0;
    int prof = 0, tipo = -1, entrelazado = 0, tengo_ihdr = 0;
    uint8_t pal[256][4];
    int npal = 0;
    for (int i = 0; i < 256; i++) { pal[i][0] = pal[i][1] = pal[i][2] = 0; pal[i][3] = 255; }
    int trns_gris = -1, trns_rgb[3] = {-1, -1, -1};
    uint8_t *idat = NULL;
    size_t nidat = 0, capidat = 0;
    size_t o = 8;
    int ok = 0, canales = 1;
    uint8_t *crudo = NULL, *rgba = NULL;
    size_t bits_px, fb, bpp, total;
    long got;
    while (o + 12 <= n) {
        uint32_t len = be32(d + o);
        const uint8_t *t = d + o + 4, *c = d + o + 8;
        if ((size_t)len > n - o - 12) goto fin;
        if (!memcmp(t, "IHDR", 4) && len >= 13) {
            w = be32(c); h = be32(c + 4); prof = c[8]; tipo = c[9]; entrelazado = c[12];
            if (c[10] || c[11]) goto fin;
            tengo_ihdr = 1;
        } else if (!memcmp(t, "PLTE", 4)) {
            npal = (int)(len / 3) > 256 ? 256 : (int)(len / 3);
            for (int i = 0; i < npal; i++) { pal[i][0] = c[3 * i]; pal[i][1] = c[3 * i + 1]; pal[i][2] = c[3 * i + 2]; }
        } else if (!memcmp(t, "tRNS", 4)) {
            if (tipo == 3) { for (uint32_t i = 0; i < len && i < 256; i++) pal[i][3] = c[i]; }
            else if (tipo == 0 && len >= 2) trns_gris = (c[0] << 8) | c[1];
            else if (tipo == 2 && len >= 6) for (int k = 0; k < 3; k++) trns_rgb[k] = (c[2 * k] << 8) | c[2 * k + 1];
        } else if (!memcmp(t, "IDAT", 4)) {
            if (nidat + len > capidat) {
                capidat = (nidat + len) * 2 + 1024;
                uint8_t *nb = (uint8_t *)realloc(idat, capidat);
                if (!nb) goto fin;
                idat = nb;
            }
            memcpy(idat + nidat, c, len);
            nidat += len;
        } else if (!memcmp(t, "IEND", 4)) break;
        o += 12 + (size_t)len;
    }
    if (!tengo_ihdr || !idat || entrelazado || w == 0 || h == 0 || w > 16384 || h > 16384) goto fin;
    switch (tipo) { case 0: canales = 1; break; case 2: canales = 3; break; case 3: canales = 1; break;
                    case 4: canales = 2; break; case 6: canales = 4; break; default: goto fin; }
    if (prof != 1 && prof != 2 && prof != 4 && prof != 8 && prof != 16) goto fin;
    if ((tipo == 2 || tipo == 4 || tipo == 6) && prof < 8) goto fin;
    if (tipo == 3 && prof == 16) goto fin;
    bits_px = (size_t)prof * canales; fb = (bits_px * w + 7) / 8; bpp = bits_px / 8 ? bits_px / 8 : 1;
    total = (fb + 1) * h;
    if (total > ((size_t)1 << 30)) goto fin;
    crudo = (uint8_t *)malloc(total);
    if (!crudo) goto fin;
    got = inflar_zlib(idat, nidat, crudo, total);
    if (got < 0 || (size_t)got != total) goto fin;
    /* quitar filtros en sitio */
    for (uint32_t y = 0; y < h; y++) {
        uint8_t *f = crudo + (size_t)y * (fb + 1), *x = f + 1;
        const uint8_t *prev = y ? crudo + (size_t)(y - 1) * (fb + 1) + 1 : NULL;
        int ft = f[0];
        for (size_t i = 0; i < fb; i++) {
            int a = i >= bpp ? x[i - bpp] : 0, b = prev ? prev[i] : 0, cc = (prev && i >= bpp) ? prev[i - bpp] : 0, v = x[i];
            switch (ft) {
            case 0: break;
            case 1: v += a; break;
            case 2: v += b; break;
            case 3: v += (a + b) >> 1; break;
            case 4: { int p = a + b - cc, pa = abs(p - a), pb = abs(p - b), pc = abs(p - cc);
#if TEXHD_SABOTAJE == 4   /* Paeth roto */
                      v += a; (void)pa; (void)pb; (void)pc; break; }
#else
                      v += (pa <= pb && pa <= pc) ? a : (pb <= pc ? b : cc); break; }
#endif
            default: goto fin;
            }
            x[i] = (uint8_t)v;
        }
    }
    rgba = (uint8_t *)malloc((size_t)w * h * 4);
    if (!rgba) goto fin;
    for (uint32_t y = 0; y < h; y++) {
        const uint8_t *fila = crudo + (size_t)y * (fb + 1) + 1;
        uint8_t *dst = rgba + (size_t)y * w * 4;
        for (uint32_t x = 0; x < w; x++, dst += 4) {
            int e0 = 0, e1 = 0, e2 = 0, e3 = 0, r, g, b, a = 255;
            if (tipo == 0) {
                int raw = muestra(fila, (int)x, prof, &e0);
                r = g = b = e0;
                if (trns_gris >= 0 && raw == trns_gris) a = 0;
            } else if (tipo == 2) {
                int r0 = muestra(fila, (int)x * 3, prof, &e0), g0 = muestra(fila, (int)x * 3 + 1, prof, &e1), b0 = muestra(fila, (int)x * 3 + 2, prof, &e2);
                r = e0; g = e1; b = e2;
                if (trns_rgb[0] >= 0 && r0 == trns_rgb[0] && g0 == trns_rgb[1] && b0 == trns_rgb[2]) a = 0;
            } else if (tipo == 3) {
                int idx = muestra(fila, (int)x, prof, &e0);
                if (idx >= 256) idx = 255;
                r = pal[idx][0]; g = pal[idx][1]; b = pal[idx][2]; a = pal[idx][3];
            } else if (tipo == 4) {
                muestra(fila, (int)x * 2, prof, &e0); muestra(fila, (int)x * 2 + 1, prof, &e1);
                r = g = b = e0; a = e1;
            } else {
                muestra(fila, (int)x * 4, prof, &e0); muestra(fila, (int)x * 4 + 1, prof, &e1);
                muestra(fila, (int)x * 4 + 2, prof, &e2); muestra(fila, (int)x * 4 + 3, prof, &e3);
                r = e0; g = e1; b = e2; a = e3;
            }
            dst[0] = (uint8_t)r; dst[1] = (uint8_t)g; dst[2] = (uint8_t)b; dst[3] = (uint8_t)a;
        }
    }
    *pw = (int)w; *ph = (int)h;
    ok = 1;
fin:
    free(idat);
    free(crudo);
    if (!ok) { free(rgba); return NULL; }
    return rgba;
}

/* ===================== PNG: escribir RGBA8 (deflate "almacenado": sin compresion, valido) ===================== */
static uint32_t crc_tab[256];
static void crc_init(void)
{
    if (crc_tab[1]) return;
    for (uint32_t i = 0; i < 256; i++) { uint32_t c = i; for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1; crc_tab[i] = c; }
}
static uint32_t crc_act(uint32_t c, const uint8_t *p, size_t n) { for (size_t i = 0; i < n; i++) c = crc_tab[(c ^ p[i]) & 255] ^ (c >> 8); return c; }
static void poner32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static int chunk(FILE *f, const char *tipo, const uint8_t *dat, size_t n)
{
    uint8_t cab[8], pie[4];
    poner32(cab, (uint32_t)n); memcpy(cab + 4, tipo, 4);
    uint32_t c = crc_act(0xFFFFFFFFu, (const uint8_t *)tipo, 4);
    if (n) c = crc_act(c, dat, n);
    poner32(pie, ~c);
    return fwrite(cab, 1, 8, f) == 8 && (!n || fwrite(dat, 1, n, f) == n) && fwrite(pie, 1, 4, f) == 4;
}

static int png_escribir(const char *ruta, const uint8_t *rgba, int w, int h)
{
    crc_init();
    size_t fb = (size_t)w * 4, raw = (fb + 1) * (size_t)h;
    size_t nbl = (raw + 65534) / 65535;
    size_t zn = 2 + raw + nbl * 5 + 4;
    uint8_t *z = (uint8_t *)malloc(zn);
    if (!z) return -1;
    size_t zp = 0;
    z[zp++] = 0x78; z[zp++] = 0x01;
    uint32_t a = 1, b = 0;
    size_t emit = 0;   /* bytes crudos ya emitidos */
    while (emit < raw) {
        size_t lote = raw - emit > 65535 ? 65535 : raw - emit;
        z[zp++] = (emit + lote >= raw) ? 1 : 0;
        z[zp++] = (uint8_t)lote; z[zp++] = (uint8_t)(lote >> 8); z[zp++] = (uint8_t)~lote; z[zp++] = (uint8_t)(~lote >> 8);
        for (size_t i = 0; i < lote; i++) {
            size_t q = emit + i;
#if TEXHD_SABOTAJE == 5   /* volcado con las filas al reves */
            uint8_t v = (q % (fb + 1) == 0) ? 0 : rgba[((size_t)h - 1 - q / (fb + 1)) * fb + (q % (fb + 1)) - 1];
#else
            uint8_t v = (q % (fb + 1) == 0) ? 0 : rgba[(q / (fb + 1)) * fb + (q % (fb + 1)) - 1];
#endif
            z[zp++] = v;
            a = (a + v) % 65521; b = (b + a) % 65521;
        }
        emit += lote;
    }
    poner32(z + zp, (b << 16) | a); zp += 4;
    char tmp[MAX_PATH * 2 + 8];
    snprintf(tmp, sizeof tmp, "%s.tmp", ruta);
    FILE *f = fopen(tmp, "wb");
    if (!f) { free(z); return -1; }
    static const uint8_t firma[8] = {137, 80, 78, 71, 13, 10, 26, 10};
    uint8_t ihdr[13];
    poner32(ihdr, (uint32_t)w); poner32(ihdr + 4, (uint32_t)h);
    ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = ihdr[11] = ihdr[12] = 0;
    int ok = fwrite(firma, 1, 8, f) == 8 && chunk(f, "IHDR", ihdr, 13) && chunk(f, "IDAT", z, zp) && chunk(f, "IEND", NULL, 0);
    ok = (fclose(f) == 0) && ok;
    free(z);
    if (!ok || !MoveFileExA(tmp, ruta, MOVEFILE_REPLACE_EXISTING)) { DeleteFileA(tmp); return -1; }
    return 0;
}

/* ===================== mips: caja 2x2 lineal, alfa premultiplicado ===================== */
static float g_lin[256];
static uint8_t g_srgb[1 << 14];
static int g_lut_ok;
static void lut_init(void)
{
    if (g_lut_ok) return;
    for (int i = 0; i < 256; i++) {
        double c = i / 255.0;
        g_lin[i] = (float)(c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4));
    }
    for (int i = 0; i < (1 << 14); i++) {
        double v = i / (double)((1 << 14) - 1);
        double s = v <= 0.0031308 ? v * 12.92 : 1.055 * pow(v, 1 / 2.4) - 0.055;
        int q = (int)(s * 255.0 + 0.5);
        g_srgb[i] = (uint8_t)(q < 0 ? 0 : q > 255 ? 255 : q);
    }
    g_lut_ok = 1;
}
static uint8_t a_srgb(float v) { if (v <= 0) return 0; if (v >= 1) return 255; return g_srgb[(int)(v * ((1 << 14) - 1) + 0.5f)]; }

static void reducir(const uint8_t *s, int sw, int sh, uint8_t *d, int dw, int dh)
{
    for (int y = 0; y < dh; y++) {
        int y0 = 2 * y, y1 = y0 + 1 < sh ? y0 + 1 : sh - 1;
        for (int x = 0; x < dw; x++) {
            int x0 = 2 * x, x1 = x0 + 1 < sw ? x0 + 1 : sw - 1;
            const uint8_t *p[4] = { s + ((size_t)y0 * sw + x0) * 4, s + ((size_t)y0 * sw + x1) * 4,
                                    s + ((size_t)y1 * sw + x0) * 4, s + ((size_t)y1 * sw + x1) * 4 };
            uint8_t *o = d + ((size_t)y * dw + x) * 4;
            int asum = p[0][3] + p[1][3] + p[2][3] + p[3][3];
#if TEXHD_SABOTAJE == 1   /* promedio en sRGB directo (sin pasar a lineal) */
            for (int c = 0; c < 3; c++) o[c] = (uint8_t)((p[0][c] + p[1][c] + p[2][c] + p[3][c] + 2) / 4);
#else
            float acc[3] = {0, 0, 0};
            for (int k = 0; k < 4; k++) {
#if TEXHD_SABOTAJE == 2   /* sin premultiplicar: el color de pixeles transparentes mancha */
                float wgt = 0.25f;
#else
                float wgt = asum ? p[k][3] / (float)asum : 0.25f;
#endif
                for (int c = 0; c < 3; c++) acc[c] += g_lin[p[k][c]] * wgt;
            }
            for (int c = 0; c < 3; c++) o[c] = a_srgb(acc[c]);
#endif
#if TEXHD_SABOTAJE == 3   /* alfa: se queda con el del primer texel */
            o[3] = p[0][3];
#else
            o[3] = (uint8_t)((asum + 2) / 4);
#endif
        }
    }
}

/* ===================== estado, indice, cache ===================== */
typedef struct Ent Ent;
struct Ent {
    uint32_t clave; int w, h, fmt;
    char *nombre;
    int mala;                 /* el archivo no sirvio: no se reintenta */
    /* cache (si cargada) */
    uint8_t *base; size_t bytes; int W, H, niveles; const uint8_t *lv[32]; uint64_t uso;
};

static SRWLOCK g_lock = SRWLOCK_INIT;
static int g_init, g_on = 1;
static char g_dir[MAX_PATH], g_dir_volcado[MAX_PATH];
static Ent *g_ents; static int g_nents;
static Ent **g_hash; static unsigned g_hmask;
static int g_indexado;
static size_t g_limite = (size_t)512 << 20, g_usado;
static uint64_t g_reloj;
static uint32_t g_buscadas, g_reemplazadas;
static uint32_t g_lecturas_disco;   /* diagnostico/prueba: cuantas veces se leyo un PNG */
static int g_indexados_n;            /* diagnostico/prueba: cuantos listados de carpeta */
static uint32_t *g_vistos; static int g_nvistos, g_capvistos;   /* claves ya volcadas */

static unsigned hz(uint32_t k) { k ^= k >> 16; k *= 0x7feb352du; k ^= k >> 15; k *= 0x846ca68bu; k ^= k >> 16; return k; }

static void liberar_cache(Ent *e) { if (e->base) { g_usado -= e->bytes; free(e->base); e->base = NULL; e->bytes = 0; } }
static void liberar_indice(void)
{
    for (int i = 0; i < g_nents; i++) { liberar_cache(&g_ents[i]); free(g_ents[i].nombre); }
    free(g_ents); free(g_hash); g_ents = NULL; g_hash = NULL; g_nents = 0; g_hmask = 0; g_indexado = 0; g_usado = 0;
}

static int dir_existe(const char *p) { DWORD a = GetFileAttributesA(p); return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY); }

static void buscar_carpeta(void)
{
    const char *e = getenv("SM3DL_TEX_HD_DIR");
    if (e && *e) { snprintf(g_dir, sizeof g_dir, "%s", e); return; }
    char base[MAX_PATH];
    DWORD n = GetModuleFileNameA(NULL, base, sizeof base);
    if (n && n < sizeof base) {
        char *s = strrchr(base, '\\');
        if (s) *s = 0;
        for (int up = 0; up < 6; up++) {
            snprintf(g_dir, sizeof g_dir, "%s\\texturas_hd", base);
            if (dir_existe(g_dir)) return;
            char *q = strrchr(base, '\\');
            if (!q) break;
            *q = 0;
        }
    }
    snprintf(g_dir, sizeof g_dir, "texturas_hd");   /* relativa al cwd */
}

static void asegurar_init(void)
{
    if (g_init) return;
    g_init = 1;
    const char *e = getenv("SM3DL_TEX_HD");
    if (e && e[0] == '0') g_on = 0;
    e = getenv("SM3DL_TEX_HD_MB");
    if (e && atoi(e) > 0) g_limite = (size_t)atoi(e) << 20;
    e = getenv("SM3DL_TEX_VOLCAR");
    if (e && *e) snprintf(g_dir_volcado, sizeof g_dir_volcado, "%s", e);
    buscar_carpeta();
    lut_init();
}

static void indexar(void)
{
    if (g_indexado) return;
    g_indexado = 1;
    g_indexados_n++;
    char pat[MAX_PATH + 16];
    snprintf(pat, sizeof pat, "%s\\tex_*.png", g_dir);
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pat, &fd);
    int cap = 0;
    if (h != INVALID_HANDLE_VALUE) {
        do {
            int w, hh, fmt; unsigned cl; char tail[8] = {0};
            if (sscanf(fd.cFileName, "tex_%dx%d_f%d_%8x.%7s", &w, &hh, &fmt, &cl, tail) != 5) continue;
            if (_stricmp(tail, "png") || w <= 0 || hh <= 0 || fmt < 0 || fmt > 13) continue;
            if (g_nents == cap) {
                cap = cap ? cap * 2 : 256;
                Ent *ne = (Ent *)realloc(g_ents, (size_t)cap * sizeof(Ent));
                if (!ne) break;
                g_ents = ne;
            }
            Ent *x = &g_ents[g_nents++];
            memset(x, 0, sizeof *x);
            x->clave = cl; x->w = w; x->h = hh; x->fmt = fmt;
            x->nombre = _strdup(fd.cFileName);
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
    unsigned sz = 16;
    while (sz < (unsigned)g_nents * 2) sz <<= 1;
    g_hash = (Ent **)calloc(sz, sizeof(Ent *));
    g_hmask = sz - 1;
    if (!g_hash) { g_nents = 0; return; }
    for (int i = 0; i < g_nents; i++) {
        unsigned j = hz(g_ents[i].clave) & g_hmask;
        while (g_hash[j]) j = (j + 1) & g_hmask;
        g_hash[j] = &g_ents[i];
    }
}

static Ent *encontrar(uint32_t clave, int w, int h, int fmt)
{
    if (!g_hash) return NULL;
    for (unsigned j = hz(clave) & g_hmask; g_hash[j]; j = (j + 1) & g_hmask) {
        Ent *e = g_hash[j];
        if (e->clave == clave && e->w == w && e->h == h && e->fmt == fmt) return e;
    }
    return NULL;
}

static void hacer_sitio(size_t necesito, const Ent *no_tocar)
{
    while (g_usado + necesito > g_limite) {
        Ent *v = NULL;
        for (int i = 0; i < g_nents; i++)
            if (g_ents[i].base && &g_ents[i] != no_tocar && (!v || g_ents[i].uso < v->uso)) v = &g_ents[i];
        if (!v) return;
        liberar_cache(v);
    }
}

/* carga el PNG de e y arma los mips; 1 si bien */
static int cargar(Ent *e)
{
    char ruta[MAX_PATH * 2];
    snprintf(ruta, sizeof ruta, "%s\\%s", g_dir, e->nombre);
    FILE *f = fopen(ruta, "rb");
    if (!f) return 0;
    g_lecturas_disco++;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = n > 0 ? (uint8_t *)malloc((size_t)n) : NULL;
    if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) { free(buf); fclose(f); return 0; }
    fclose(f);
    int W = 0, H = 0;
    uint8_t *px = png_decodificar(buf, (size_t)n, &W, &H);
    free(buf);
    if (!px) { fprintf(stderr, "[texhd] PNG invalido: %s\n", ruta); return 0; }
    if (W % e->w || H % e->h || W / e->w != H / e->h) {
        fprintf(stderr, "[texhd] %s: %dx%d no es multiplo entero de %dx%d\n", ruta, W, H, e->w, e->h);
        free(px);
        return 0;
    }
    int niv = 1, sw = W, sh = H;
    size_t total = (size_t)W * H * 4;
    while (sw > 1 || sh > 1) { sw = sw > 1 ? sw / 2 : 1; sh = sh > 1 ? sh / 2 : 1; total += (size_t)sw * sh * 4; niv++; }
    hacer_sitio(total, e);
    uint8_t *base = (uint8_t *)malloc(total);
    if (!base) { free(px); return 0; }
    memcpy(base, px, (size_t)W * H * 4);
    free(px);
    e->lv[0] = base;
    sw = W; sh = H;
    uint8_t *cur = base + (size_t)W * H * 4;
    for (int l = 1; l < niv; l++) {
        int dw = sw > 1 ? sw / 2 : 1, dh = sh > 1 ? sh / 2 : 1;
        reducir(e->lv[l - 1], sw, sh, cur, dw, dh);
        e->lv[l] = cur;
        cur += (size_t)dw * dh * 4;
        sw = dw; sh = dh;
    }
    e->base = base; e->bytes = total; e->W = W; e->H = H; e->niveles = niv;
    g_usado += total;
    return 1;
}

/* ===================== API ===================== */
int texhd_activo(void)
{
    AcquireSRWLockExclusive(&g_lock);
    asegurar_init();
    int r = g_on;
    ReleaseSRWLockExclusive(&g_lock);
    return r;
}

void texhd_fijar(int encendido)
{
    AcquireSRWLockExclusive(&g_lock);
    asegurar_init();
    encendido = encendido != 0;
    if (encendido && !g_on) liberar_indice();   /* al volver a encender se relee la carpeta (por si se agregaron PNG) */
    g_on = encendido;
    ReleaseSRWLockExclusive(&g_lock);
}

int texhd_buscar(uint32_t clave, int w, int h, int fmt, int *W, int *H, int *niveles, const uint8_t *const **rgba)
{
    int r = 0;
    AcquireSRWLockExclusive(&g_lock);
    asegurar_init();
    if (g_on) {
        g_buscadas++;
        indexar();
        Ent *e = encontrar(clave, w, h, fmt);
        if (e && !e->mala) {
            if (!e->base && !cargar(e)) e->mala = 1;
            if (e->base) {
                e->uso = ++g_reloj;
                if (W) *W = e->W;
                if (H) *H = e->H;
                if (niveles) *niveles = e->niveles;
                if (rgba) *rgba = (const uint8_t *const *)e->lv;
                g_reemplazadas++;
                r = 1;
            }
        }
    }
    ReleaseSRWLockExclusive(&g_lock);
    return r;
}

int texhd_volcando(void)
{
    AcquireSRWLockExclusive(&g_lock);
    asegurar_init();
    int r = g_dir_volcado[0] != 0;
    ReleaseSRWLockExclusive(&g_lock);
    return r;
}

void texhd_volcar(uint32_t clave, int w, int h, int fmt, const uint8_t *rgba_nivel0)
{
    if (!rgba_nivel0 || w <= 0 || h <= 0) return;
    AcquireSRWLockExclusive(&g_lock);
    asegurar_init();
    if (g_dir_volcado[0]) {
        /* una vez por clave (colision de clave con otro w/h/fmt: rarisima, se ignora) */
        int visto = 0;
        for (int i = 0; i < g_nvistos; i++) if (g_vistos[i] == clave) { visto = 1; break; }
        if (!visto) {
            if (g_nvistos == g_capvistos) {
                int nc = g_capvistos ? g_capvistos * 2 : 512;
                uint32_t *nv = (uint32_t *)realloc(g_vistos, (size_t)nc * 4);
                if (nv) { g_vistos = nv; g_capvistos = nc; }
            }
            if (g_nvistos < g_capvistos) {
                g_vistos[g_nvistos++] = clave;
                CreateDirectoryA(g_dir_volcado, NULL);
                char ruta[MAX_PATH * 2];
                snprintf(ruta, sizeof ruta, "%s\\tex_%dx%d_f%d_%08X.png", g_dir_volcado, w, h, fmt, clave);
                if (GetFileAttributesA(ruta) == INVALID_FILE_ATTRIBUTES) png_escribir(ruta, rgba_nivel0, w, h);
            }
        }
    }
    ReleaseSRWLockExclusive(&g_lock);
}

void texhd_estadisticas(uint32_t *reemplazadas, uint32_t *buscadas)
{
    AcquireSRWLockExclusive(&g_lock);
    if (reemplazadas) *reemplazadas = g_reemplazadas;
    if (buscadas) *buscadas = g_buscadas;
    ReleaseSRWLockExclusive(&g_lock);
}
