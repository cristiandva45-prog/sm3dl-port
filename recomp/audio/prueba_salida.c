/* Prueba en vivo: hilo del DSP a ritmo real (4,889 ms/tick) -> cola -> 48 kHz -> backend. Un seno de 440 Hz muy bajo durante ~1,2 s.
 * Compilar con -DDSP_HILO_WIN32 y, para oir, -DAUDIO_BACKEND_WASAPI. Mide si el hilo mantiene el ritmo y si la cola se vacia. */
#include "dsp.h"
#include "audio_salida.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>
static int16_t onda[4091]; static int g_n;
static const uint8_t *fis(void *u, uint32_t pa, uint32_t n) { (void)u; return pa == 0x20000000u && n <= sizeof onda ? (const uint8_t *)onda : NULL; }
static void w16(uint8_t *p, uint16_t v) { memcpy(p, &v, 2); }
static void wd(uint8_t *p, uint32_t v) { w16(p, v >> 16); w16(p + 2, (uint16_t)v); }
static void wf(uint8_t *p, float v) { memcpy(p, &v, 4); }
int main(void) {
    for (int i = 0; i < 4091; i++) onda[i] = (int16_t)(8000 * sin(2 * 3.14159265358979 * 55.0 * i / 4091.0));
    dsp_host_t h = { fis, NULL, NULL, NULL };
    dsp_iniciar(&h);
    uint8_t init[4] = {0, 0, 0, 0}; dsp_WriteProcessPipe(2, init, 4);
    uint8_t *r0 = dsp_ram() + DSP_REGION0, *r1 = dsp_ram() + DSP_REGION1;
    uint8_t *c = r0 + 0x3D24, *dc = r0 + 0x2860;
    wd(dc + 0, 0); *(uint32_t *)dc = (1u << 16) | (1u << 26); wf(dc + 4, 0.25f); w16(dc + 0x16, 1);
    wf(c + 4, 0.7f); wf(c + 8, 0.7f); wf(c + 0x34, 1.0f); c[0x38] = 1; c[0xA0] = 1;
    w16(c + 0xB4, 1 | (1 << 2)); wd(c + 0xAC, 0x20000000u); wd(c + 0xB0, 4091); w16(c + 0xBC, 2); w16(c + 0xBE, 1);
    *(uint32_t *)c = (1u << 0) | (1u << 1) | (1u << 16) | (1u << 17) | (1u << 18) | (1u << 25) | (1u << 30);
    w16(r0 + 0x7FFE, 1); w16(r1 + 0x7FFE, 0);
    int rc = audio_salida_iniciar();
    printf("backend iniciar rc=%d\n", rc);
    LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
    dsp_hilo_iniciar();
    Sleep(1200);
    dsp_hilo_parar();
    QueryPerformanceCounter(&b);
    double s = (double)(b.QuadPart - a.QuadPart) / f.QuadPart;
    printf("ticks=%u en %.3f s -> %.1f ticks/s (esperado 204,5); descartes=%u, vacia=%u\n", dsp_frames_generados(), s, dsp_frames_generados() / s,
           audio_cola_descartes(), audio_cola_vacia());
    audio_salida_cerrar();
    return 0;
}
