/* Ver texturas.h. Referencia y verificacion: tools/texturas.py, tools/verificar_texturas_c.py */
#include "texturas.h"
#include <string.h>

static const int BPP[14] = {32, 24, 16, 16, 16, 16, 16, 8, 8, 8, 4, 4, 4, 8};
static const int ETC[8][2] = {{2, 8}, {5, 17}, {9, 29}, {13, 42}, {18, 60}, {24, 80}, {33, 106}, {47, 183}};

#ifndef SABOTAJE
#define SABOTAJE 0
#endif

/* indice i dentro del mosaico 8x8 -> (x, y): bits pares = x, impares = y */
static void morton(int i, int *x, int *y)
{
    *x = (i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4);
    *y = ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4);
#if SABOTAJE == 1
    *x ^= 1;
#endif
}

static uint8_t sat(int v) { return (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v); }

static uint64_t le64(const uint8_t *p)
{
    uint64_t v = 0;
    for (int k = 7; k >= 0; k--) v = (v << 8) | p[k];
    return v;
}

/* escribe en la imagen ya enderezada: fila Y de la PICA = fila (alto-1-Y) de la salida */
static void poner(uint8_t *s, int ancho, int alto, int X, int Y, int r, int g, int b, int a)
{
    if (X >= ancho || Y >= alto) return;
    uint8_t *p = s + ((size_t)(alto - 1 - Y) * ancho + X) * 4;
    p[0] = (uint8_t)r; p[1] = (uint8_t)g; p[2] = (uint8_t)b; p[3] = (uint8_t)a;
}

static void etc1(uint64_t bloque, const uint64_t *alfa, uint8_t *s, int ancho, int alto, int X0, int Y0)
{
    uint32_t hi = (uint32_t)(bloque >> 32), lo = (uint32_t)bloque;
    int flip = hi & 1, diff = (hi >> 1) & 1;
    int t1 = (hi >> 5) & 7, t2 = (hi >> 2) & 7;
    int c1[3], c2[3];
    if (diff) {
        int b1[3] = {(hi >> 27) & 31, (hi >> 19) & 31, (hi >> 11) & 31};
        int dd[3] = {(hi >> 24) & 7, (hi >> 16) & 7, (hi >> 8) & 7};
        for (int k = 0; k < 3; k++) {
            int d = dd[k] & 4 ? dd[k] - 8 : dd[k];
            int v1 = b1[k] & 31, v2 = (b1[k] + d) & 31;
            c1[k] = (v1 << 3) | (v1 >> 2);
            c2[k] = (v2 << 3) | (v2 >> 2);
        }
    } else {
        int sh1[3] = {28, 20, 12}, sh2[3] = {24, 16, 8};
        for (int k = 0; k < 3; k++) {
            c1[k] = ((hi >> sh1[k]) & 15) * 17;
            c2[k] = ((hi >> sh2[k]) & 15) * 17;
        }
    }
    for (int x = 0; x < 4; x++)
        for (int y = 0; y < 4; y++) {
            int p = x * 4 + y;
            int seg = flip ? (y >= 2) : (x >= 2);
            const int *base = seg ? c2 : c1;
            const int *tab = ETC[seg ? t2 : t1];
            int idx = ((lo >> (p + 16)) & 1) * 2 + ((lo >> p) & 1);
            int mod = idx == 0 ? tab[0] : idx == 1 ? tab[1] : idx == 2 ? -tab[0] : -tab[1];
            int a = alfa ? (int)((*alfa >> (4 * p)) & 15) * 17 : 255;
            poner(s, ancho, alto, X0 + x, Y0 + y, sat(base[0] + mod), sat(base[1] + mod), sat(base[2] + mod), a);
        }
}

size_t tex_tamano(int ancho, int alto, int fmt)
{
    if (fmt < 0 || fmt > 13 || ancho <= 0 || alto <= 0) return 0;
    size_t tw = (size_t)(ancho + 7) / 8, th = (size_t)(alto + 7) / 8;
    return tw * th * 64 * BPP[fmt] / 8;
}

int tex_decodificar(const uint8_t *d, size_t largo, int ancho, int alto, int fmt, uint8_t *s)
{
    size_t necesario = tex_tamano(ancho, alto, fmt);
    if (!necesario || largo < necesario) return -1;
    memset(s, 0, (size_t)ancho * alto * 4);
    size_t o = 0;
    for (int ty = 0; ty < alto; ty += 8)
        for (int tx = 0; tx < ancho; tx += 8) {
            if (fmt >= 12) {
#if SABOTAJE == 2
                static const int BX[4] = {0, 0, 4, 4}, BY[4] = {0, 4, 0, 4};
#else
                static const int BX[4] = {0, 4, 0, 4}, BY[4] = {0, 0, 4, 4};
#endif
                for (int k = 0; k < 4; k++) {
                    uint64_t alfa = 0;
                    if (fmt == 13) { alfa = le64(d + o); o += 8; }
                    uint64_t bl = le64(d + o); o += 8;
                    etc1(bl, fmt == 13 ? &alfa : NULL, s, ancho, alto, tx + BX[k], ty + BY[k]);
                }
                continue;
            }
            for (int i = 0; i < 64; i++) {
                int x, y, r, g, b, a;
                morton(i, &x, &y);
                if (fmt == 0) {
                    a = d[o]; b = d[o + 1]; g = d[o + 2]; r = d[o + 3]; o += 4;
                } else if (fmt == 1) {
                    b = d[o]; g = d[o + 1]; r = d[o + 2]; a = 255; o += 3;
                } else if (BPP[fmt] == 16) {
                    int v = d[o] | (d[o + 1] << 8);
                    o += 2;
                    if (fmt == 2) {
                        r = ((v >> 11) & 31) * 255 / 31; g = ((v >> 6) & 31) * 255 / 31;
                        b = ((v >> 1) & 31) * 255 / 31; a = v & 1 ? 255 : 0;
                    } else if (fmt == 3) {
                        r = ((v >> 11) & 31) * 255 / 31; g = ((v >> 5) & 63) * 255 / 63;
                        b = (v & 31) * 255 / 31; a = 255;
                    } else if (fmt == 4) {
                        r = ((v >> 12) & 15) * 17; g = ((v >> 8) & 15) * 17;
                        b = ((v >> 4) & 15) * 17; a = (v & 15) * 17;
                    } else if (fmt == 5) {
                        r = g = b = v >> 8; a = v & 255;
                    } else { /* HILO8 */
                        r = v >> 8; g = v & 255; b = 255; a = 255;
                    }
                } else if (BPP[fmt] == 8) {
                    int v = d[o];
                    o += 1;
                    if (fmt == 7) { r = g = b = v; a = 255; }
                    else if (fmt == 8) { r = g = b = 0; a = v; }   /* A8: la PICA da (0,0,0,a) (Azahar texture_decode) */
                    else { r = g = b = (v >> 4) * 17; a = (v & 15) * 17; } /* LA4 */
                } else { /* 4 bits: primero el nibble bajo */
                    int v = (d[o] >> (4 * (i & 1))) & 15;
                    if (i & 1) o += 1;
                    if (fmt == 10) { r = g = b = v * 17; a = 255; }
                    else { r = g = b = 0; a = v * 17; } /* A4: (0,0,0,a) como la PICA. 7 oct: con blanco, los iconos
                                                             de boton de los globos-guia (MyGuideLButton, A4) salian
                                                             blanco sobre el globo blanco = invisibles */
                }
                poner(s, ancho, alto, tx + x, ty + y, r, g, b, a);
            }
        }
    return 0;
}

#ifdef TEX_PRINCIPAL
/* prueba: texdec <entrada> <salida>; entrada = u32 ancho, u32 alto, u32 fmt, datos. salida = RGBA8 */
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv)
{
    if (argc < 3) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 2;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = malloc((size_t)n);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) return 2;
    fclose(f);
    uint32_t w, h, fmt;
    memcpy(&w, buf, 4); memcpy(&h, buf + 4, 4); memcpy(&fmt, buf + 8, 4);
    uint8_t *s = malloc((size_t)w * h * 4);
    if (tex_decodificar(buf + 12, (size_t)n - 12, (int)w, (int)h, (int)fmt, s)) return 3;
    f = fopen(argv[2], "wb");
    if (!f) return 2;
    fwrite(s, 1, (size_t)w * h * 4, f);
    fclose(f);
    return 0;
}
#endif
