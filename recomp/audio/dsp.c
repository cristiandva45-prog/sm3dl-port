/* dsp::DSP HLE (agente H, 8 oct 2026). Ver dsp.h. Reimplementacion; semantica de azahar-src/audio_core/hle.
 * Compilar con -ffp-contract=off: el mezclador usa float y hay que reproducir las cuentas sin fusionar mul+add. */
#include "dsp.h"
#include <stdlib.h>
#include <string.h>

/* ---------- acceso a la RAM del DSP (x86 little-endian) ---------- */
static uint8_t g_ram[DSP_RAM_TAM];
static dsp_host_t g_h;

static uint16_t rd16(const uint8_t *p) { uint16_t v; memcpy(&v, p, 2); return v; }
static uint32_t rd32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static float    rdf(const uint8_t *p)  { float v; memcpy(&v, p, 4); return v; }
static void wr16(uint8_t *p, uint16_t v) { memcpy(p, &v, 2); }
static void wr32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
/* u32 "middle-endian" del DSP: mitades de 16 bits intercambiadas */
static uint32_t rdd(const uint8_t *p) { return ((uint32_t)rd16(p) << 16) | rd16(p + 2); }
static void wrd(uint8_t *p, uint32_t v) { wr16(p, (uint16_t)(v >> 16)); wr16(p + 2, (uint16_t)v); }

/* Layout de una region (SharedMemory, 0x8000 B), en bytes desde el inicio de la region */
enum {
    OFF_DSP_STATUS = 0x0800, OFF_DSP_DEBUG = 0x0820, OFF_FINAL = 0x0A80, OFF_SRC_STATUS = 0x0D00,
    OFF_COMPRESSOR = 0x0E20, OFF_DSP_CFG = 0x2860, OFF_INTERMEDIO = 0x2924, OFF_SRC_CFG = 0x3D24,
    OFF_ADPCM = 0x4F24, OFF_UNK10 = 0x5224, OFF_UNK11 = 0x5424, OFF_UNK12 = 0x55A4, OFF_UNK13 = 0x58A4,
    OFF_UNK14 = 0x58B8, OFF_FRAME_CTR = 0x7FFE
};
#define CFG_TAM 192

/* ---------- estado ---------- */
typedef struct {
    uint32_t paddr, len; int16_t yn[2]; int adpcm_dirty, looping; uint16_t id;
    int mono_st, fmt, from_queue; uint32_t play_pos; int has_played;
} Buf;
#define QN 64

typedef struct { int16_t y1[2]; int a1, b0; } FSimple;
typedef struct { int16_t x1[2], x2[2], y1[2], y2[2]; int a1, a2, b0, b1, b2; } FBiquad;

typedef struct {
    int enabled; uint16_t sync;
    float gain[3][4], ramp_start[3][4]; int ramp_active[3];
    Buf q[QN]; int nq;
    int16_t (*cur)[2]; size_t cur_n, cur_cap, cur_off;     /* buffer decodificado actual */
    uint32_t cur_pa, cur_len, cur_sample; int cur_ms, cur_fmt, cur_loop; uint16_t cur_id, last_id; int upd;
    int16_t coef[16]; int yn1, yn2;
    float rate; int interp_mode; int mono_st, fmt;
    int16_t xn2[2], xn1[2]; uint64_t fpos;
    int simple_en, biquad_en; FSimple fs; FBiquad fb;
    int16_t frame[DSP_MUESTRAS][2];
} Src;

static Src g_src[DSP_FUENTES];
static struct { float vol[3]; int aux_en[2]; int fmt; int32_t imb[3][DSP_MUESTRAS][4]; } g_mix;
static int g_estado;          /* 0 Off, 1 On, 2 Sleeping */
static uint8_t g_pipe[4][4096]; static uint32_t g_pipe_n[4];
static uint32_t g_ev[3][4];   /* handle por (tipo, canal) */
static uint32_t g_ev_sem;
static uint32_t g_frames, g_desbordes;
static uint8_t g_backup[DSP_RAM_TAM];

/* ---------- filtros ---------- */
static void fs_reset(FSimple *f) { memset(f->y1, 0, sizeof f->y1); f->a1 = 0; f->b0 = 1 << 15; }
static void fb_reset(FBiquad *f) { memset(f, 0, sizeof *f); f->b0 = 1 << 14; }
static int16_t clamp16(int64_t v) { return (int16_t)(v < -32768 ? -32768 : v > 32767 ? 32767 : v); }
static void filtros_activar(Src *s, int simple, int biquad) {
    s->simple_en = simple; s->biquad_en = biquad;
    if (!simple) fs_reset(&s->fs);
    if (!biquad) fb_reset(&s->fb);
}
static void filtros_frame(Src *s) {
    if (s->simple_en)
        for (int i = 0; i < DSP_MUESTRAS; i++) for (int c = 0; c < 2; c++) {
            int32_t t = (s->fs.b0 * s->frame[i][c] + s->fs.a1 * s->fs.y1[c]) >> 15;
            s->frame[i][c] = s->fs.y1[c] = clamp16(t);
        }
    if (s->biquad_en)
        for (int i = 0; i < DSP_MUESTRAS; i++) for (int c = 0; c < 2; c++) {
            FBiquad *f = &s->fb; int16_t x0 = s->frame[i][c];
            int32_t t = (f->b0 * x0 + f->b1 * f->x1[c] + f->b2 * f->x2[c] + f->a1 * f->y1[c] + f->a2 * f->y2[c]) >> 14;
            int16_t y0 = clamp16(t);
            f->x2[c] = f->x1[c]; f->x1[c] = x0; f->y2[c] = f->y1[c]; f->y1[c] = y0;
            s->frame[i][c] = y0;
        }
}

/* ---------- codecs ---------- */
static int cur_reservar(Src *s, size_t n) {
    if (n > s->cur_cap || !s->cur) {
        size_t cap = n ? n : 1;
        void *p = realloc(s->cur, cap * sizeof *s->cur);
        if (!p) return 0;
        s->cur = p; s->cur_cap = cap;
    }
    return 1;
}
static void dec_pcm8(Src *s, int nch, const uint8_t *d, size_t n) {
    cur_reservar(s, n);
    for (size_t i = 0; i < n; i++) {
        /* fiel a Azahar: byte sin signo << 8 (no (b-128)<<8) */
        s->cur[i][0] = (int16_t)((uint16_t)d[i * nch] << 8);
        s->cur[i][1] = nch == 2 ? (int16_t)((uint16_t)d[i * 2 + 1] << 8) : s->cur[i][0];
    }
    s->cur_n = n; s->cur_off = 0;
}
static void dec_pcm16(Src *s, int nch, const uint8_t *d, size_t n) {
    cur_reservar(s, n);
    for (size_t i = 0; i < n; i++) {
        int16_t a, b; memcpy(&a, d + i * 2 * nch, 2);
        b = a; if (nch == 2) memcpy(&b, d + i * 4 + 2, 2);
        s->cur[i][0] = a; s->cur[i][1] = b;
    }
    s->cur_n = n; s->cur_off = 0;
}
static void dec_adpcm(Src *s, const uint8_t *d, size_t n) {
    static const int nib[16] = {0,1,2,3,4,5,6,7,-8,-7,-6,-5,-4,-3,-2,-1};
    size_t tam = (n % 2 == 0) ? n : n + 1;
    cur_reservar(s, tam);
    memset(s->cur, 0, tam * sizeof *s->cur);
    int yn1 = s->yn1, yn2 = s->yn2;
    size_t frames = (n + 13) / 14;
    for (size_t f = 0; f < frames; f++) {
        int hdr = d[f * 8], scale = 1 << (hdr & 15), idx = (hdr >> 4) & 7;
        int c1 = s->coef[idx * 2], c2 = s->coef[idx * 2 + 1];
        size_t o = f * 14, di = f * 8 + 1;
        for (int i = 0; i < 14 && o < n; i += 2) {
            for (int h = 0; h < 2 && !(h == 1 && o >= n); h++) {
                int x = nib[h == 0 ? d[di] >> 4 : d[di] & 15] * scale;
                int val = ((x << 11) + 0x400 + c1 * yn1 + c2 * yn2) >> 11;
                val = val < -32768 ? -32768 : val > 32767 ? 32767 : val;
                yn2 = yn1; yn1 = val;
                s->cur[o][0] = s->cur[o][1] = (int16_t)val; o++;
            }
            di++;
        }
    }
    s->yn1 = (int16_t)yn1; s->yn2 = (int16_t)yn2;
    s->cur_n = tam; s->cur_off = 0;
}

/* ---------- fuente ---------- */
static void src_reset(Src *s) {
    int16_t (*c)[2] = s->cur; size_t cap = s->cur_cap;
    memset(s, 0, sizeof *s);
    s->cur = c; s->cur_cap = cap;
    s->rate = 1.0f; s->interp_mode = 0; s->mono_st = 1; s->fmt = 0;
    fs_reset(&s->fs); fb_reset(&s->fb);
}
static void q_empujar(Src *s, const Buf *b) {
    if (s->nq >= QN) { g_desbordes++; return; }
    s->q[s->nq++] = *b;
}
static int src_dequeue(Src *s) {
    if (s->nq == 0) return 0;
    int m = 0;
    for (int i = 1; i < s->nq; i++) if (s->q[i].id < s->q[m].id) m = i;
    Buf b = s->q[m]; s->q[m] = s->q[--s->nq];
    if (b.adpcm_dirty) { s->yn1 = b.yn[0]; s->yn2 = b.yn[1]; }
    int nch = b.mono_st == 2 ? 2 : 1;
    uint32_t nbytes = b.fmt == 2 ? ((b.len + 13) / 14) * 8 : b.len * nch * (b.fmt == 1 ? 2 : 1);
    const uint8_t *mem = g_h.fis ? g_h.fis(g_h.ud, b.paddr & ~3u, nbytes) : NULL;
    if (!mem) { s->cur_n = s->cur_off = 0; return 1; }
    switch (b.fmt) {
    case 0: dec_pcm8(s, nch, mem, b.len); break;
    case 1: dec_pcm16(s, nch, mem, b.len); break;
    case 2: dec_adpcm(s, mem, b.len); break;
    default: s->cur_n = s->cur_off = 0; break;
    }
    s->cur_sample = b.has_played ? 0 : b.play_pos;
    s->cur_pa = b.paddr; s->cur_len = b.len; s->cur_ms = b.mono_st; s->cur_fmt = b.fmt;
    s->cur_loop = b.looping; s->cur_id = b.id; s->last_id = 0;
    s->upd = b.from_queue && !b.has_played;
    if (b.looping) { b.has_played = 1; q_empujar(s, &b); }
    s->cur_off = s->cur_sample < s->cur_n ? s->cur_sample : s->cur_n;   /* erase(begin, begin+cur_sample) */
    return 1;
}

#define ESC 16777216ull
static int16_t gets(const Src *s, size_t i, int c) {
    return i == 0 ? s->xn2[c] : i == 1 ? s->xn1[c] : s->cur[s->cur_off + i - 2][c];
}
/* modo 0/1 -> lineal (Polyphase = lineal, como Azahar), 2 -> ninguna. La entrada logica es [xn2, xn1, cur...] */
static void interpolar(Src *s, size_t *outi) {
    size_t nreal = s->cur_n - s->cur_off;
    if (nreal == 0) return;
    size_t tam = nreal + 2, inputi = 0;
    uint64_t step = (uint64_t)(s->rate * 16777216.0f), fpos = s->fpos;
    while (*outi < DSP_MUESTRAS) {
        inputi = (size_t)(fpos / ESC);
        if (inputi + 2 >= tam) { inputi = tam - 2; break; }
        uint64_t fr = fpos & (ESC - 1);
        for (int c = 0; c < 2; c++) {
            int16_t x0 = gets(s, inputi, c), x1 = gets(s, inputi + 1, c);
            if (s->interp_mode == 2) s->frame[*outi][c] = x0;
            else {
                int64_t d = (int64_t)x1 - x0; d = d < -32768 ? -32768 : d > 32767 ? 32767 : d;
                /* ojo: fr es u64 y d es s64 -> aritmetica sin signo (igual que el original; con delta negativo da -ceil, no -floor) */
                s->frame[*outi][c] = (int16_t)(x0 + fr * d / ESC);
            }
        }
        (*outi)++;
        fpos += step;
    }
    for (int c = 0; c < 2; c++) { s->xn2[c] = gets(s, inputi, c); s->xn1[c] = gets(s, inputi + 1, c); }
    s->fpos = fpos - inputi * ESC;
    s->cur_off += inputi;
}

static void src_generar(Src *s) {
    memset(s->frame, 0, sizeof s->frame);
    if (s->cur_n > s->cur_off && s->cur_loop && s->cur_fmt == 1 && s->cur_pa != 0 && s->cur_sample < s->cur_len) {
        int nch = s->cur_ms == 2 ? 2 : 1;
        uint32_t off = s->cur_sample * nch * 2, rem = s->cur_len - s->cur_sample;
        const uint8_t *mem = g_h.fis ? g_h.fis(g_h.ud, (s->cur_pa & ~3u) + off, rem * nch * 2) : NULL;
        if (mem) dec_pcm16(s, nch, mem, rem);
    }
    if (s->cur_n == s->cur_off) {
        if (src_dequeue(s)) return;
        s->enabled = 0; s->upd = 1; s->last_id = s->cur_id; s->cur_id = 0;
        return;
    }
    size_t pos = 0;
    while (pos < DSP_MUESTRAS) {
        if (s->cur_n == s->cur_off && !src_dequeue(s)) break;
        size_t antes = s->cur_n - s->cur_off;
        if (antes == 0) break;     /* guarda anti-cuelgue (el original no la tiene): direccion invalida */
        interpolar(s, &pos);
        s->cur_sample += (uint32_t)(antes - (s->cur_n - s->cur_off));
    }
    filtros_frame(s);
}

#define B(c, n) (((c) >> (n)) & 1u)
static void src_parse(Src *s, uint8_t *cfg, const uint8_t *coef) {
    uint32_t d = rd32(cfg);
    if (!d) return;
    if (B(d, 29)) src_reset(s);
    if (B(d, 4)) s->nq = 0;
    if (B(d, 16)) s->enabled = cfg[0xA0] != 0;
    if (B(d, 28)) s->sync = rd16(cfg + 0xA2);
    if (B(d, 18)) { s->rate = rdf(cfg + 0x34); if (s->rate <= 0) s->rate = 1.0f; }
    if (B(d, 2)) for (int i = 0; i < 16; i++) s->coef[i] = (int16_t)rd16(coef + 2 * i);
    for (int m = 0; m < 3; m++) if (B(d, 25 + m)) {
        memcpy(s->ramp_start[m], s->gain[m], 16); s->ramp_active[m] = 1;
        for (int k = 0; k < 4; k++) s->gain[m][k] = rdf(cfg + 4 + 16 * m + 4 * k);
    }
    if (B(d, 22)) { uint16_t fe = rd16(cfg + 0x3A); filtros_activar(s, fe & 1, (fe >> 1) & 1); }
    if (B(d, 23)) { s->fs.b0 = (int16_t)rd16(cfg + 0x3C); s->fs.a1 = (int16_t)rd16(cfg + 0x3E); }
    if (B(d, 24)) {
        s->fb.a2 = (int16_t)rd16(cfg + 0x40); s->fb.a1 = (int16_t)rd16(cfg + 0x42);
        s->fb.b2 = (int16_t)rd16(cfg + 0x44); s->fb.b1 = (int16_t)rd16(cfg + 0x46); s->fb.b0 = (int16_t)rd16(cfg + 0x48);
    }
    if (B(d, 17)) s->interp_mode = cfg[0x38];
    uint16_t f1 = rd16(cfg + 0xB4);
    if (B(d, 0) || B(d, 30)) s->fmt = (f1 >> 2) & 3;
    if (B(d, 1) || B(d, 30)) s->mono_st = f1 & 3;
    uint32_t play_pos = 0;
    if (B(d, 21)) play_pos = rdd(cfg + 0xA4);
    if (B(d, 3)) {          /* actualizacion parcial del buffer embebido: solo PCM16 (igual que el original) */
        int nch = s->mono_st == 2 ? 2 : 1;
        uint32_t len = rdd(cfg + 0xB0);
        const uint8_t *mem = g_h.fis ? g_h.fis(g_h.ud, s->cur_pa & ~3u, len * nch * 2) : NULL;
        if (mem && s->fmt == 1) {
            dec_pcm16(s, nch, mem, len);
            s->cur_len = len; s->cur_ms = s->mono_st; s->cur_fmt = s->fmt; s->cur_loop = (rd16(cfg + 0xBC) >> 1) & 1;
            if (s->cur_n < s->cur_sample) s->cur_sample = 0; else s->cur_off = s->cur_sample;
        }
    }
    if (B(d, 30)) {
        uint32_t len = rdd(cfg + 0xB0);
        if ((int32_t)len >= 0) {
            Buf b; memset(&b, 0, sizeof b);
            uint16_t f2 = rd16(cfg + 0xBC);
            b.paddr = rdd(cfg + 0xAC); b.len = len; b.yn[0] = (int16_t)rd16(cfg + 0xB8); b.yn[1] = (int16_t)rd16(cfg + 0xBA);
            b.adpcm_dirty = f2 & 1; b.looping = (f2 >> 1) & 1; b.id = rd16(cfg + 0xBE);
            b.mono_st = s->mono_st; b.fmt = s->fmt; b.from_queue = 0; b.play_pos = play_pos; b.has_played = 0;
            q_empujar(s, &b);
        }
    }
    if (B(d, 19)) {
        uint16_t bd = rd16(cfg + 0x4A);
        for (int i = 0; i < 4; i++) if (bd & (1u << i)) {
            const uint8_t *p = cfg + 0x4C + 20 * i;
            uint32_t len = rdd(p + 4);
            if ((int32_t)len < 0) continue;
            Buf b; memset(&b, 0, sizeof b);
            b.paddr = rdd(p); b.len = len; b.yn[0] = (int16_t)rd16(p + 0xA); b.yn[1] = (int16_t)rd16(p + 0xC);
            b.adpcm_dirty = p[0xE] != 0; b.looping = p[0xF] != 0; b.id = rd16(p + 0x10);
            b.mono_st = s->mono_st; b.fmt = s->fmt; b.from_queue = 1; b.play_pos = 0; b.has_played = 0;
            q_empujar(s, &b);
        }
        wr16(cfg + 0x4A, 0);
    }
    wr32(cfg, 0);
}

static void src_estado(Src *s, uint8_t *st) {
    st[0] = (uint8_t)s->enabled; st[1] = s->upd ? 1 : 0; s->upd = 0;
    wr16(st + 2, s->sync); wrd(st + 4, s->cur_sample); wr16(st + 8, s->cur_id); wr16(st + 10, s->last_id);
}

static int32_t f2i(float v) { return v >= 2147483520.0f ? 2147483647 : v <= -2147483648.0f ? INT32_MIN : (int32_t)v; }

static void src_mezclar(Src *s, int32_t (*dest)[4], int mix) {
    float *g = s->gain[mix];
    if (!s->enabled) { memcpy(s->ramp_start[mix], g, 16); s->ramp_active[mix] = 0; return; }
    int ra = s->ramp_active[mix]; const float *rs = s->ramp_start[mix];
    const float escala = 1.0f / (float)(DSP_MUESTRAS - 1);
    for (int i = 0; i < DSP_MUESTRAS; i++) {
        float prog = (float)i * escala, gg[4];
        for (int k = 0; k < 4; k++) gg[k] = ra ? rs[k] + (g[k] - rs[k]) * prog : g[k];
        dest[i][0] += f2i(gg[0] * s->frame[i][0]);
        dest[i][1] += f2i(gg[1] * s->frame[i][1]);
        dest[i][2] += f2i(gg[2] * s->frame[i][0]);
        dest[i][3] += f2i(gg[3] * s->frame[i][1]);
    }
    if (ra) { memcpy(s->ramp_start[mix], g, 16); s->ramp_active[mix] = 0; }
}

/* ---------- mezclador final ---------- */
static void mix_parse(uint8_t *cfg) {
    uint32_t d = rd32(cfg);
    if (!d) return;
    if (B(d, 8))  g_mix.aux_en[0] = rd16(cfg + 0x28) != 0;
    if (B(d, 9))  g_mix.aux_en[1] = rd16(cfg + 0x2A) != 0;
    if (B(d, 16)) g_mix.vol[0] = rdf(cfg + 4);
    if (B(d, 24)) g_mix.vol[1] = rdf(cfg + 8);
    if (B(d, 25)) g_mix.vol[2] = rdf(cfg + 12);
    if (B(d, 26)) g_mix.fmt = rd16(cfg + 0x16);
    /* delay/reverb (bits 10..13): sin implementar (el original tampoco implementa reverb) */
    wr32(cfg, 0);
}

static int dsp_region_actual(void) {
    uint16_t c0 = rd16(g_ram + DSP_REGION0 + OFF_FRAME_CTR), c1 = rd16(g_ram + DSP_REGION1 + OFF_FRAME_CTR);
    if (c0 == 0xFFFF && c1 != 0xFFFE) return 1;
    if (c1 == 0xFFFF && c0 != 0xFFFE) return 0;
    return c0 > c1 ? 0 : 1;
}

static void genera_frame(int16_t out[DSP_MUESTRAS][2]) {
    int ri = dsp_region_actual();
    uint8_t *rg = g_ram + (ri == 0 ? DSP_REGION0 : DSP_REGION1), *wg = g_ram + (ri == 0 ? DSP_REGION1 : DSP_REGION0);
    static int32_t entrada[3][DSP_MUESTRAS][4];
    memset(entrada, 0, sizeof entrada);
    for (int i = 0; i < DSP_FUENTES; i++) {
        src_parse(&g_src[i], rg + OFF_SRC_CFG + CFG_TAM * i, rg + OFF_ADPCM + 32 * i);
        if (g_src[i].enabled) src_generar(&g_src[i]);
        src_estado(&g_src[i], wg + OFF_SRC_STATUS + 12 * i);
        for (int m = 0; m < 3; m++) src_mezclar(&g_src[i], entrada[m], m);
    }
    mix_parse(rg + OFF_DSP_CFG);
    /* AuxReturn */
    for (int b = 0; b < 2; b++) if (g_mix.aux_en[b]) {
        const uint8_t *r = rg + OFF_INTERMEDIO + 2560 * b;
        for (int s = 0; s < DSP_MUESTRAS; s++) for (int c = 0; c < 4; c++)
            g_mix.imb[b + 1][s][c] = (int32_t)rd32(r + 4 * (c * DSP_MUESTRAS + s));
    }
    /* AuxSend */
    memcpy(g_mix.imb[0], entrada[0], sizeof entrada[0]);
    for (int b = 0; b < 2; b++) {
        if (g_mix.aux_en[b]) {
            uint8_t *w = wg + OFF_INTERMEDIO + 2560 * b;
            for (int s = 0; s < DSP_MUESTRAS; s++) for (int c = 0; c < 4; c++)
                wr32(w + 4 * (c * DSP_MUESTRAS + s), (uint32_t)entrada[b + 1][s][c]);
        } else memcpy(g_mix.imb[b + 1], entrada[b + 1], sizeof entrada[0]);
    }
    /* MixCurrentFrame */
    memset(out, 0, DSP_MUESTRAS * 4);
    for (int m = 0; m < 3; m++) {
        float g = g_mix.vol[m];
        for (int s = 0; s < DSP_MUESTRAS; s++) {
            const int32_t *x = g_mix.imb[m][s]; int16_t l, r;
            if (g_mix.fmt == 0) {
                l = r = clamp16(f2i((g * x[0] + g * x[1] + g * x[2] + g * x[3]) / 2));
            } else {
                l = clamp16(f2i(g * x[0] + g * x[2])); r = clamp16(f2i(g * x[1] + g * x[3]));
            }
            out[s][0] = clamp16((int32_t)out[s][0] + l); out[s][1] = clamp16((int32_t)out[s][1] + r);
        }
    }
    wr16(wg + OFF_DSP_STATUS, 0); wr16(wg + OFF_DSP_STATUS + 2, 0);
    for (int s = 0; s < DSP_MUESTRAS; s++) { wr16(wg + OFF_FINAL + 4 * s, (uint16_t)out[s][0]); wr16(wg + OFF_FINAL + 4 * s + 2, (uint16_t)out[s][1]); }
}

/* ---------- pipes y servicio ---------- */
static void pipe_u16(int p, uint16_t v) {
    if (g_pipe_n[p] + 2 > sizeof g_pipe[p]) return;
    g_pipe[p][g_pipe_n[p]++] = (uint8_t)v; g_pipe[p][g_pipe_n[p]++] = (uint8_t)(v >> 8);
}
static void senalar(int tipo, int canal) {
    uint32_t h = g_ev[tipo][canal];
    if (h && g_h.senal) g_h.senal(g_h.ud, h);
}
static void reset_todo(void) {
    memset(g_ram, 0, sizeof g_ram);
    memset(&g_mix, 0, sizeof g_mix); g_mix.fmt = 1;
    for (int i = 0; i < DSP_FUENTES; i++) src_reset(&g_src[i]);
    memset(g_pipe_n, 0, sizeof g_pipe_n);
}
static void escribir_direcciones(void) {
    static const uint32_t o[15] = { OFF_FRAME_CTR, OFF_SRC_CFG, OFF_SRC_STATUS, OFF_ADPCM, OFF_DSP_CFG, OFF_DSP_STATUS, OFF_FINAL,
        OFF_INTERMEDIO, OFF_COMPRESSOR, OFF_DSP_DEBUG, OFF_UNK10, OFF_UNK11, OFF_UNK12, OFF_UNK13, OFF_UNK14 };
    pipe_u16(DSP_PIPE_AUDIO, 15);
    for (int i = 0; i < 15; i++) pipe_u16(DSP_PIPE_AUDIO, (uint16_t)(0x8000 + o[i] / 2));
    senalar(DSP_INT_PIPE, DSP_PIPE_AUDIO);
}

#ifdef DSP_HILO_WIN32
#include <windows.h>
static CRITICAL_SECTION g_cs; static int g_cs_ok;
#define LOCK() EnterCriticalSection(&g_cs)
#define UNLOCK() LeaveCriticalSection(&g_cs)
#else
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
#endif

void dsp_iniciar(const dsp_host_t *h) {
    if (h) g_h = *h; else memset(&g_h, 0, sizeof g_h);
#ifdef DSP_HILO_WIN32
    if (!g_cs_ok) { InitializeCriticalSection(&g_cs); g_cs_ok = 1; }
#endif
    memset(g_ev, 0, sizeof g_ev); g_ev_sem = 0; g_estado = 0; g_frames = g_desbordes = 0;
    reset_todo();
}
uint8_t *dsp_ram(void) { return g_ram; }
uint32_t dsp_frames_generados(void) { return g_frames; }
uint32_t dsp_cola_desbordes(void) { return g_desbordes; }

int dsp_LoadComponent(uint32_t size, uint32_t pm, uint32_t dm, uint8_t *cargado) { (void)size; (void)pm; (void)dm; if (cargado) *cargado = 1; return 0; }
int dsp_UnloadComponent(void) { return 0; }
uint32_t dsp_GetSemaphoreEventHandle(void) { return g_ev_sem; }
void dsp_poner_evento_semaforo(uint32_t h) { g_ev_sem = h; }
int dsp_RegisterInterruptEvents(uint32_t h, uint32_t tipo, uint32_t canal) {
    if (tipo > 2 || canal > 3) return -1;
    g_ev[tipo][canal] = h; return 0;
}
int dsp_WriteProcessPipe(uint32_t canal, const uint8_t *b, uint32_t len) {
    LOCK();
    int rc = 0;
    if (canal == DSP_PIPE_AUDIO) {
        if (len != 4) { rc = -1; }
        else switch (b[0]) {
            case 0: reset_todo(); escribir_direcciones(); g_estado = 1; break;                          /* Initialize */
            case 1: g_estado = 0; break;                                                                 /* Shutdown */
            case 2: memcpy(g_ram, g_backup, sizeof g_ram); memset(g_pipe_n, 0, sizeof g_pipe_n);        /* Wakeup */
                    escribir_direcciones(); g_estado = 1; break;
            case 3: memcpy(g_backup, g_ram, sizeof g_ram); escribir_direcciones(); g_estado = 2; break;  /* Sleep */
            default: g_estado = 0; break;
        }
    } else rc = -1;       /* pipe Binary (decodificador AAC): no soportado todavia */
    UNLOCK();
    return rc;
}
int dsp_ReadPipeIfPossible(uint32_t canal, uint32_t peer, uint8_t *buf, uint32_t len, uint32_t *leidos) {
    (void)peer;
    LOCK();
    uint32_t n = 0;
    if (canal < 4) {
        n = len < g_pipe_n[canal] ? len : g_pipe_n[canal];
        memcpy(buf, g_pipe[canal], n);
        memmove(g_pipe[canal], g_pipe[canal] + n, g_pipe_n[canal] - n); g_pipe_n[canal] -= n;
    }
    UNLOCK();
    if (leidos) *leidos = n;
    return 0;
}
uint32_t dsp_ConvertProcessAddressFromDspDram(uint32_t a) { return (a << 1) + DSP_RAM_BASE + 0x40000u; }
int dsp_FlushDataCache(uint32_t va, uint32_t t) { (void)va; (void)t; return 0; }
int dsp_InvalidateDataCache(uint32_t va, uint32_t t) { (void)va; (void)t; return 0; }
int dsp_SetSemaphore(uint16_t v) { (void)v; return 0; }
int dsp_SetSemaphoreMask(uint16_t m) { (void)m; return 0; }
uint16_t dsp_RecvData(uint32_t reg) { (void)reg; return g_estado == 1 ? 0 : 1; }
int dsp_RecvDataIsReady(uint32_t reg) { (void)reg; return 1; }
uint32_t dsp_GetHeadphoneStatus(void) { return 0; }

extern void audio_salida(const int16_t *estereo, int n);

int dsp_tick(void) {
    LOCK();
    int on = g_estado == 1;
    if (on) {
        int16_t fr[DSP_MUESTRAS][2];
        genera_frame(fr);
        g_frames++;
        UNLOCK();
        if (g_h.salida) g_h.salida(g_h.ud, &fr[0][0], DSP_MUESTRAS); else audio_salida(&fr[0][0], DSP_MUESTRAS);
        senalar(DSP_INT_PIPE, DSP_PIPE_AUDIO);
        return 1;
    }
    UNLOCK();
    return 0;
}

#ifdef DSP_HILO_WIN32
static HANDLE g_th; static volatile int g_parar;
static DWORD WINAPI hilo(LPVOID p) {
    (void)p;
    LARGE_INTEGER f, t0, ahora; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&t0);
    long long n = 0;
    while (!g_parar) {
        n++;
        long long objetivo = t0.QuadPart + n * f.QuadPart * DSP_MUESTRAS / DSP_FS;
        for (;;) { QueryPerformanceCounter(&ahora); long long r = objetivo - ahora.QuadPart; if (r <= 0) break;
            if (r > f.QuadPart / 500) Sleep(1); else YieldProcessor(); }
        dsp_tick();
    }
    return 0;
}
void dsp_hilo_iniciar(void) { g_parar = 0; g_th = CreateThread(NULL, 0, hilo, NULL, 0, NULL); }
void dsp_hilo_parar(void) { g_parar = 1; if (g_th) { WaitForSingleObject(g_th, 1000); CloseHandle(g_th); g_th = NULL; } }
#endif
