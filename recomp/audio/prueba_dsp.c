/* Prueba del DSP HLE: hace de "juego" (protocolo de pipe, regiones, fuentes) con un escenario armado por
 * tools/audio_vector.py (bcstm reales) y vuelca la mezcla a un .bin que el script compara con su mezclador de referencia.
 * Uso: prueba_dsp escenario.bin salida.bin [-s predictor]
 *   -s predictor : SABOTAJE, corrompe el predictor de un frame ADPCM; la comparacion DEBE fallar. */
#include "dsp.h"
#include "audio_salida.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define FCRAM_BASE 0x20000000u
static uint8_t *g_fcram; static uint32_t g_fcram_n;
static int g_senales;
static int16_t (*g_out)[160][2]; static int g_nout;

static const uint8_t *host_fis(void *ud, uint32_t pa, uint32_t n) {
    (void)ud; if (pa < FCRAM_BASE || pa - FCRAM_BASE + n > g_fcram_n) return NULL; return g_fcram + (pa - FCRAM_BASE);
}
static void host_senal(void *ud, uint32_t h) { (void)ud; if (h == 0x1234) g_senales++; }
static void host_salida(void *ud, const int16_t *e, int n) {
    (void)ud; if (n == 160 && g_nout < 4096) memcpy(g_out[g_nout++], e, 640);
}

static void w16(uint8_t *p, uint16_t v) { memcpy(p, &v, 2); }
static void w32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static void wd(uint8_t *p, uint32_t v) { w16(p, v >> 16); w16(p + 2, (uint16_t)v); }
static void wf(uint8_t *p, float v) { memcpy(p, &v, 4); }
static uint16_t r16(const uint8_t *p) { uint16_t v; memcpy(&v, p, 2); return v; }

static int fallos;
#define CHECK(c, ...) do { if (!(c)) { printf("  FALLA: " __VA_ARGS__); printf("\n"); fallos++; } } while (0)

typedef struct { uint32_t id, n, nbytes, dirty; int16_t yn[2]; uint32_t off; } EBuf;
typedef struct {
    uint32_t slot, fmt, ch, interp; float rate, gain[4]; uint8_t loop, queue; int16_t coef[16];
    uint32_t nbuf; EBuf b[4]; uint32_t chg_tick; float chg[4];
} EFuente;

static uint8_t *ram_de(uint32_t va) { return dsp_ram() + (va - DSP_RAM_BASE); }

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "uso: prueba_dsp escenario.bin salida.bin [-s predictor]\n"); return 2; }
    int sab = argc > 4 && !strcmp(argv[3], "-s") && !strcmp(argv[4], "predictor");
    FILE *f = fopen(argv[1], "rb"); if (!f) { perror("escenario"); return 2; }
    fseek(f, 0, SEEK_END); long tam = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *esc = malloc(tam); if (fread(esc, 1, tam, f) != (size_t)tam) return 2; fclose(f);
    g_fcram_n = 8u << 20; g_fcram = calloc(1, g_fcram_n);
    g_out = calloc(4096, sizeof *g_out);

    const uint8_t *p = esc + 4; uint32_t ticks, nf; memcpy(&ticks, p, 4); memcpy(&nf, p + 4, 4); p += 8;
    EFuente fu[8]; uint32_t off = 0;
    for (uint32_t i = 0; i < nf; i++) {
        EFuente *s = &fu[i];
        memcpy(&s->slot, p, 16); memcpy(&s->rate, p + 16, 4); memcpy(s->gain, p + 20, 16);
        s->loop = p[36]; s->queue = p[37]; p += 40;
        memcpy(s->coef, p, 32); p += 32;
        memcpy(&s->nbuf, p, 4); p += 4;
        for (uint32_t k = 0; k < s->nbuf; k++) {
            EBuf *b = &s->b[k]; memcpy(&b->id, p, 16); memcpy(b->yn, p + 16, 4); p += 20;
            b->off = off; memcpy(g_fcram + off, p, b->nbytes); p += b->nbytes; off += (b->nbytes + 63) & ~63u;
        }
        memcpy(&s->chg_tick, p, 4); memcpy(s->chg, p + 4, 16); p += 20;
    }
    float master; memcpy(&master, p, 4);
    if (sab) {      /* frame 3 del 1.er buffer ADPCM de la fuente 0: predictor ^ 1 */
        g_fcram[fu[0].b[0].off + 3 * 8] ^= 0x10;
        printf("SABOTAJE: predictor del frame 3 alterado\n");
    }

    dsp_host_t h = { host_fis, host_senal, host_salida, NULL };
    dsp_iniciar(&h);

    /* --- arranque como nn::snd --- */
    uint8_t cargado = 0;
    CHECK(dsp_LoadComponent(0xBE44, 0xFF, 0xFF, &cargado) == 0 && cargado == 1, "LoadComponent debe responder cargado=1");
    CHECK(dsp_RegisterInterruptEvents(0x1234, DSP_INT_PIPE, DSP_PIPE_AUDIO) == 0, "RegisterInterruptEvents");
    CHECK(dsp_RecvData(0) == 1, "antes de Initialize el DSP debe decir 1 (apagado)");
    uint8_t init[4] = { 0, 0, 0, 0 }, rd[64]; uint32_t got = 0;
    dsp_WriteProcessPipe(DSP_PIPE_AUDIO, init, 4);
    CHECK(g_senales == 1, "Initialize debe senalar el evento del pipe 2 (senales=%d)", g_senales);
    dsp_ReadPipeIfPossible(DSP_PIPE_AUDIO, 0, rd, 2, &got);
    CHECK(got == 2 && r16(rd) == 15, "el pipe debe traer 15 direcciones");
    uint16_t dir[15]; dsp_ReadPipeIfPossible(DSP_PIPE_AUDIO, 0, (uint8_t *)dir, 30, &got);
    CHECK(got == 30, "30 bytes de direcciones");
    /* esperadas: frame_counter, source_cfg, source_status, adpcm, dsp_cfg... (offset/2 + 0x8000) */
    CHECK(dir[0] == 0xBFFF && dir[1] == 0x9E92 && dir[2] == 0x8680 && dir[3] == 0xA792 && dir[4] == 0x9430 && dir[6] == 0x8540,
          "direcciones del pipe: %04X %04X %04X %04X %04X %04X", dir[0], dir[1], dir[2], dir[3], dir[4], dir[6]);
    CHECK(dsp_ConvertProcessAddressFromDspDram(dir[0]) == DSP_RAM_BASE + DSP_REGION0 + 0x7FFE, "ConvertAddr del frame_counter");
    CHECK(dsp_ConvertProcessAddressFromDspDram(dir[0] | 0x10000) == DSP_RAM_BASE + DSP_REGION1 + 0x7FFE, "ConvertAddr region 1");
    CHECK(dsp_RecvData(0) == 0, "tras Initialize el DSP esta encendido (0)");

    uint32_t reg_cfg[2], reg_coef[2], reg_st[2], reg_dsp[2], reg_ctr[2];
    for (int r = 0; r < 2; r++) {
        uint32_t m = r ? 0x10000u : 0;
        reg_ctr[r] = dsp_ConvertProcessAddressFromDspDram(dir[0] | m); reg_cfg[r] = dsp_ConvertProcessAddressFromDspDram(dir[1] | m);
        reg_st[r] = dsp_ConvertProcessAddressFromDspDram(dir[2] | m); reg_coef[r] = dsp_ConvertProcessAddressFromDspDram(dir[3] | m);
        reg_dsp[r] = dsp_ConvertProcessAddressFromDspDram(dir[4] | m);
    }

    int vistos_id1 = 0, vistos_id2 = 0, fin0 = -1;
    clock_t t0 = clock();
    for (uint32_t t = 0; t < ticks; t++) {
        int w = t & 1;                       /* region donde el "juego" escribe este tick */
        if (t == 0) {
            uint8_t *dc = ram_de(reg_dsp[w]);
            w32(dc, (1u << 16) | (1u << 26)); wf(dc + 4, master); w16(dc + 0x16, 1);
            for (uint32_t i = 0; i < nf; i++) {
                EFuente *s = &fu[i]; uint8_t *c = ram_de(reg_cfg[w]) + 192 * s->slot;
                uint32_t d = (1u << 0) | (1u << 1) | (1u << 16) | (1u << 17) | (1u << 18) | (1u << 25);
                if (s->fmt == 2) { d |= 1u << 2; memcpy(ram_de(reg_coef[w]) + 32 * s->slot, s->coef, 32); }
                if (sab) { }
                for (int k = 0; k < 4; k++) wf(c + 4 + 4 * k, s->gain[k]);
                wf(c + 0x34, s->rate); c[0x38] = (uint8_t)s->interp;
                c[0xA0] = 1; w16(c + 0xA2, 0);
                uint16_t f1 = (uint16_t)((s->ch == 2 ? 2 : 1) | (s->fmt << 2));
                w16(c + 0xB4, f1);
                if (s->queue) {
                    d |= 1u << 19; w16(c + 0x4A, (1u << s->nbuf) - 1);
                    for (uint32_t k = 0; k < s->nbuf; k++) {
                        uint8_t *b = c + 0x4C + 20 * k; EBuf *e = &s->b[k];
                        wd(b, FCRAM_BASE + e->off); wd(b + 4, e->n); w16(b + 0xA, (uint16_t)e->yn[0]); w16(b + 0xC, (uint16_t)e->yn[1]);
                        b[0xE] = (uint8_t)e->dirty; b[0xF] = s->loop; w16(b + 0x10, (uint16_t)e->id);
                    }
                } else {
                    EBuf *e = &s->b[0]; d |= 1u << 30;
                    wd(c + 0xAC, FCRAM_BASE + e->off); wd(c + 0xB0, e->n);
                    w16(c + 0xB8, (uint16_t)e->yn[0]); w16(c + 0xBA, (uint16_t)e->yn[1]);
                    w16(c + 0xBC, (uint16_t)((e->dirty & 1) | (s->loop << 1))); w16(c + 0xBE, (uint16_t)e->id);
                }
                w32(c, d);
            }
        }
        for (uint32_t i = 0; i < nf; i++) if (fu[i].chg_tick == t) {      /* cambio de ganancia con rampa */
            uint8_t *c = ram_de(reg_cfg[w]) + 192 * fu[i].slot;
            for (int k = 0; k < 4; k++) wf(c + 4 + 4 * k, fu[i].chg[k]);
            w32(c, 1u << 25);
        }
        w16(ram_de(reg_ctr[w]), (uint16_t)(t + 1));
        CHECK(dsp_tick() == 1, "tick %u", t);
        /* estado de la fuente 0 en la region de escritura del DSP (la otra) */
        const uint8_t *st = ram_de(reg_st[w ^ 1]);
        uint16_t cur = r16(st + 8), last = r16(st + 10);
        if (cur == 1) vistos_id1++;
        if (cur == 2) vistos_id2++;
        if (st[0] == 0 && fin0 < 0 && t > 2) { fin0 = (int)t; CHECK(last == 2, "al terminar, last_buffer_id debe ser 2 (es %u)", last); }
    }
    double ms = 1000.0 * (clock() - t0) / CLOCKS_PER_SEC;
    printf("ticks=%u senales=%d frames=%u  %.2f ms total (%.3f ms/tick; presupuesto 4,889)\n", ticks, g_senales, dsp_frames_generados(), ms, ms / ticks);
    CHECK(vistos_id1 > 10 && vistos_id2 > 10, "el estado debe pasar por buffer 1 y buffer 2 (%d, %d)", vistos_id1, vistos_id2);
    CHECK(fin0 > 0, "la fuente 0 debe terminar y deshabilitarse");
    CHECK((uint32_t)g_senales >= ticks + 1, "una senal por tick");
    /* la fuente 1 (bucle) sigue viva */
    CHECK(ram_de(reg_st[((ticks - 1) & 1) ^ 1])[12] == 1, "la fuente 1 (bucle) debe seguir habilitada");
    /* cola de salida a 48 kHz: nada se pierde ni desborda */
    uint8_t apagar[4] = { 1, 0, 0, 0 };
    dsp_WriteProcessPipe(DSP_PIPE_AUDIO, apagar, 4);
    CHECK(dsp_RecvData(0) == 1 && dsp_tick() == 0, "tras Shutdown: RecvData=1 y sin ticks");

    FILE *o = fopen(argv[2], "wb"); fwrite(g_out, 640, g_nout, o); fclose(o);
    printf("PROTOCOLO: %s (%d fallos)\n", fallos ? "FALLO" : "OK", fallos);
    return fallos ? 1 : 0;
}
