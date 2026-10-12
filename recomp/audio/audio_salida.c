#include "audio_salida.h"
#include <string.h>
#ifdef _WIN32
#include <windows.h>
static CRITICAL_SECTION g_cs; static int g_cs_ok;
static void lock(void) { if (!g_cs_ok) { InitializeCriticalSection(&g_cs); g_cs_ok = 1; } EnterCriticalSection(&g_cs); }
static void unlock(void) { LeaveCriticalSection(&g_cs); }
#else
static void lock(void) {} static void unlock(void) {}
#endif

#define CAP 16384                                  /* ~0,5 s a 32.728 Hz */
static int16_t g_buf[CAP][2];
static uint32_t g_r, g_w;                          /* contadores crecientes */
static uint32_t g_vacia, g_desc;
static double g_fase;                              /* posicion fraccionaria de lectura (en muestras de 32.728) */
static int16_t g_ult[2];
#define FS_IN 32728.0
#define FS_OUT 48000.0

/* ---- salida con colchon y control de ritmo (agente AU, 9 oct) ----
 * Antes (SM3DL_AUDIO_VIEJO=1 lo devuelve tal cual): el hilo WASAPI llenaba el bufer ENTERO (200 ms) en cada vuelta
 * -> el sonido iba ~200 ms detras de la imagen; y la cola de 32.728 vivia casi vacia (nadie la dejaba crecer), asi que
 * cada vez que el DSP llegaba tarde (los ticks salen en rafagas del planificador, hasta 8 = 39 ms) se sostenia la
 * ultima muestra A MITAD del bloque (tramo plano = clic) sin que `vacia=` lo contara (solo miraba la muestra 0).
 * Ahora: (1) WASAPI se llena solo hasta g_pad_obj (SM3DL_AUDIO_PAD_MS, 30 ms); (2) la cola apunta a g_cola_obj
 * (SM3DL_AUDIO_COLA_MS, 40 ms) cebandose antes de sonar; (3) el paso del remuestreo se corrige +-0,8 % segun el nivel
 * filtrado de la cola (constante ~0,5 s; 0,8 % = 14 cents, no se oye) -> ni huecos por deriva de relojes ni
 * descartes muestra a muestra; (4) `huecos=` cuenta TODA muestra de 48 kHz sostenida y `recortes=` las muestras
 * del DSP en +-32767/-32768. Latencia total ~ 30 + 40 = 70 ms (antes ~200-215). */
static int g_viejo = -1;                           /* -1 = sin leer el entorno */
static int g_sin_ctrl;                             /* SM3DL_AUDIO_SABOTAJE=1: sin control de ritmo (prueba) */
static double g_cola_obj = 40.0 * FS_IN / 1000.0;  /* muestras de 32.728 */
static uint32_t g_pad_obj = 30 * 48;               /* cuadros de 48 kHz en el bufer del backend */
static int g_cebando = 1;
static double g_nivel_f = -1.0, g_ajuste;          /* nivel filtrado (muestras de entrada), ajuste relativo del paso */
static uint64_t g_huecos, g_huecos_rep;            /* muestras de 48 kHz sostenidas: total / desde el ultimo reporte */
static uint32_t g_saltos;                          /* saltos de la cola desbordada (cada uno = 1 discontinuidad) */
static uint64_t g_total;                           /* muestras entregadas por el DSP */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
static void leer_entorno(void) {
    if (g_viejo >= 0) return;
    const char *v = getenv("SM3DL_AUDIO_VIEJO"); g_viejo = v && *v && *v != '0';
    v = getenv("SM3DL_AUDIO_SABOTAJE"); g_sin_ctrl = v && *v && *v != '0';
    v = getenv("SM3DL_AUDIO_COLA_MS"); if (v && atoi(v) > 0) g_cola_obj = atoi(v) * FS_IN / 1000.0;
    v = getenv("SM3DL_AUDIO_PAD_MS"); if (v && atoi(v) > 0) g_pad_obj = (uint32_t)atoi(v) * 48u;
}
int audio_modo_viejo(void) { leer_entorno(); return g_viejo; }
void audio_reiniciar_estado(void) {               /* para las pruebas: vuelve todo al arranque y relee el entorno */
    lock();
    g_r = g_w = 0; g_vacia = g_desc = 0; g_fase = 0; g_ult[0] = g_ult[1] = 0; g_total = 0;
    g_viejo = -1; g_sin_ctrl = 0; g_cola_obj = 40.0 * FS_IN / 1000.0; g_pad_obj = 30 * 48;
    g_cebando = 1; g_nivel_f = -1.0; g_ajuste = 0; g_huecos = g_huecos_rep = 0; g_saltos = 0;
    leer_entorno();
    unlock();
}
uint32_t audio_cuadros_a_llenar(uint32_t pad, uint32_t tam_bufer) {
    leer_entorno();
    if (pad >= tam_bufer) return 0;
    if (g_viejo) return tam_bufer - pad;
    uint32_t obj = g_pad_obj < tam_bufer ? g_pad_obj : tam_bufer;
    return pad >= obj ? 0 : obj - pad;
}

/* Diagnostico (noche 8 oct): SM3DL_WAV=<archivo.pcm> vuelca lo que entrega el DSP (s16 estereo a 32.728 Hz,
   crudo; convertir con tools/pcm_a_wav.py) y cada ~2 s se imprime pico/RMS en stderr, para saber si suena
   sin escucharlo. */
static FILE *g_pcm; static int g_pcm_ini;
static uint32_t g_est_n, g_est_rec; static int g_est_pico; static double g_est_suma;
static void diagnostico(const int16_t *e, int n) {
    if (!g_pcm_ini) {
        const char *r = getenv("SM3DL_WAV"); g_pcm_ini = 1; if (r && *r) g_pcm = fopen(r, "wb");
        /* nadie llamaba a audio_salida_iniciar: la cola se llenaba y se descartaba entera (noche 8 oct).
           Se abre el backend con el primer frame del DSP; SM3DL_SIN_AUDIO=1 lo deja mudo. */
        lock(); unlock();   /* la seccion critica se crea aqui, antes de que exista el hilo de WASAPI */
        leer_entorno();
        if (!getenv("SM3DL_SIN_AUDIO")) fprintf(stderr, "[audio] backend iniciado rc=%d (salida %s)\n", audio_salida_iniciar(),
                                                 g_viejo ? "VIEJA" : "con colchon");
    }
    if (g_pcm) { fwrite(e, 4, (size_t)n, g_pcm); fflush(g_pcm); }
    for (int i = 0; i < 2 * n; i++) {
        int v = abs(e[i]); if (v > g_est_pico) g_est_pico = v; g_est_suma += (double)e[i] * e[i];
        if (v >= 32767) g_est_rec++;
    }
    g_est_n += (uint32_t)n; g_total += (uint64_t)n;
    if (g_est_n >= 65456) {
        /* los campos viejos quedan igual (hay guiones que los leen); los nuevos van al final */
        fprintf(stderr, "[audio] muestras=%llu pico=%d rms=%.1f vacia=%u descartes=%u huecos=%llu cola=%.1fms ajuste=%+.0fppm recortes=%u saltos=%u\n",
                (unsigned long long)g_total, g_est_pico, sqrt(g_est_suma / (2.0 * g_est_n)), g_vacia, g_desc,
                (unsigned long long)g_huecos_rep, g_nivel_f < 0 ? 0.0 : g_nivel_f * 1000.0 / FS_IN, g_ajuste * 1e6, g_est_rec, g_saltos);
        g_est_n = 0; g_est_pico = 0; g_est_suma = 0; g_est_rec = 0; g_huecos_rep = 0;
    }
}

void audio_salida(const int16_t *e, int n) {
    diagnostico(e, n);
    lock();
    for (int i = 0; i < n; i++) {
        if (g_w - g_r >= CAP) { g_r++; g_desc++; }   /* cola llena: tirar la mas vieja */
        g_buf[g_w % CAP][0] = e[2 * i]; g_buf[g_w % CAP][1] = e[2 * i + 1]; g_w++;
    }
    unlock();
}

static void leer48_viejo(int16_t *out, int n) {
    const double paso = FS_IN / FS_OUT;
    for (int i = 0; i < n; i++) {
        /* interpolacion lineal entre g_r y g_r+1; necesita 2 muestras disponibles */
        if (g_w - g_r < 2) {
            out[2 * i] = g_ult[0]; out[2 * i + 1] = g_ult[1];
            if (i == 0) g_vacia++;
            if (g_total) { g_huecos++; g_huecos_rep++; }
            continue;
        }
        const int16_t *a = g_buf[g_r % CAP], *b = g_buf[(g_r + 1) % CAP];
        for (int c = 0; c < 2; c++) out[2 * i + c] = g_ult[c] = (int16_t)(a[c] + (b[c] - a[c]) * g_fase);
        g_fase += paso;
        while (g_fase >= 1.0) { g_fase -= 1.0; g_r++; }
    }
}

static void leer48_colchon(int16_t *out, int n) {
    double nivel = (double)(g_w - g_r) - g_fase;
    /* desborde grande (el DSP corrio sin nadie que leyera): un solo salto hasta el objetivo, no miles de descartes */
    if (nivel > g_cola_obj * 4.0 && nivel > 4096.0) {
        g_r = g_w - (uint32_t)g_cola_obj; g_fase = 0; nivel = (double)(g_w - g_r); g_nivel_f = nivel; g_saltos++;
    }
    if (g_nivel_f < 0) g_nivel_f = nivel;
    double alfa = (double)n / ((double)n + 0.5 * FS_OUT);           /* paso bajo de ~0,5 s */
    g_nivel_f += alfa * (nivel - g_nivel_f);
    if (g_cebando) {
        /* al arrancar se ceba el objetivo entero; tras quedarse sin datos, la mitad (hueco mas corto) y el control sube */
        if (nivel < (g_cebando == 2 ? 0.5 : 1.0) * g_cola_obj) {    /* todavia sin colchon: sostener (como Azahar) */
            for (int i = 0; i < n; i++) { out[2 * i] = g_ult[0]; out[2 * i + 1] = g_ult[1]; }
            if (g_total) { g_huecos += (uint64_t)n; g_huecos_rep += (uint64_t)n; }
            if (n) g_vacia++;
            return;
        }
        g_cebando = 0; g_nivel_f = nivel;
    }
    double err = (g_nivel_f - g_cola_obj) / g_cola_obj;
    double aj = g_sin_ctrl ? 0.0 : 0.005 * err;
    if (aj > 0.008) aj = 0.008; else if (aj < -0.008) aj = -0.008;
    g_ajuste = aj;
    const double paso = FS_IN / FS_OUT * (1.0 + aj);
    for (int i = 0; i < n; i++) {
        if (g_w - g_r < 2) {
            /* se acabo el colchon: sostener y volver a cebar (un hueco largo y limpio en vez de muchos clics) */
            for (; i < n; i++) { out[2 * i] = g_ult[0]; out[2 * i + 1] = g_ult[1]; g_huecos++; g_huecos_rep++; }
            g_cebando = 2;
            break;
        }
        const int16_t *a = g_buf[g_r % CAP], *b = g_buf[(g_r + 1) % CAP];
        for (int c = 0; c < 2; c++) out[2 * i + c] = g_ult[c] = (int16_t)lrint(a[c] + (b[c] - a[c]) * g_fase);
        g_fase += paso;
        while (g_fase >= 1.0) { g_fase -= 1.0; g_r++; }
    }
}

void audio_leer48(int16_t *out, int n) {
    lock();
    leer_entorno();
    if (g_viejo) leer48_viejo(out, n); else leer48_colchon(out, n);
    unlock();
}
uint32_t audio_cola_vacia(void) { return g_vacia; }
uint32_t audio_cola_descartes(void) { return g_desc; }
uint64_t audio_huecos48(void) { return g_huecos; }
double audio_cola_ms(void) { return g_nivel_f < 0 ? 0.0 : g_nivel_f * 1000.0 / FS_IN; }
double audio_ajuste(void) { return g_ajuste; }
uint32_t audio_saltos(void) { return g_saltos; }

/* ---------------------------------------------------------------- backends */
#if defined(AUDIO_BACKEND_WASAPI) && defined(_WIN32)
#define COBJMACROS
#include <initguid.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
DEFINE_GUID(CLSID_MMDeviceEnumerator_, 0xBCDE0395, 0xE52F, 0x467C, 0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E);
DEFINE_GUID(IID_IMMDeviceEnumerator_, 0xA95664D2, 0x9614, 0x4F35, 0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6);
DEFINE_GUID(IID_IAudioClient_, 0x1CB9AD4C, 0xDBFA, 0x4C32, 0xB1, 0x78, 0xC2, 0xF5, 0x68, 0xA7, 0x03, 0xB2);
DEFINE_GUID(IID_IAudioRenderClient_, 0xF294ACFC, 0x3146, 0x4483, 0xA7, 0xBF, 0xAD, 0xDC, 0xA7, 0xC2, 0x60, 0xE2);
static IAudioClient *g_ac; static IAudioRenderClient *g_rc; static HANDLE g_th; static volatile int g_stop; static UINT32 g_buf_frames;
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
static DWORD WINAPI hilo_wasapi(LPVOID p) {
    (void)p;
    /* modo nuevo: espera de 2 ms con temporizador de alta resolucion (Windows 10 1803+; si no hay, Sleep(1)).
       Sleep(5) sin timeBeginPeriod dura ~15,6 ms: con un relleno de 30 ms eso seria casi vaciar el bufer. */
    HANDLE tm = NULL;
    if (!audio_modo_viejo()) {
        tm = CreateWaitableTimerExW(NULL, NULL, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
    }
    while (!g_stop) {
        UINT32 pad = 0; IAudioClient_GetCurrentPadding(g_ac, &pad);
        UINT32 libre = audio_cuadros_a_llenar(pad, g_buf_frames);
        if (libre > 0) {
            BYTE *d = NULL;
            if (SUCCEEDED(IAudioRenderClient_GetBuffer(g_rc, libre, &d))) {
                audio_leer48((int16_t *)d, (int)libre);
                IAudioRenderClient_ReleaseBuffer(g_rc, libre, 0);
            }
        }
        if (audio_modo_viejo()) Sleep(5);
        else if (tm) { LARGE_INTEGER t; t.QuadPart = -20000; SetWaitableTimer(tm, &t, 0, NULL, NULL, FALSE); WaitForSingleObject(tm, 10); }
        else Sleep(1);
    }
    if (tm) CloseHandle(tm);
    return 0;
}
int audio_salida_iniciar(void) {
    IMMDeviceEnumerator *en = NULL; IMMDevice *dev = NULL;
    if (FAILED(CoInitializeEx(NULL, COINIT_MULTITHREADED)) ) { /* ya inicializado en otro modo: seguir */ }
    if (FAILED(CoCreateInstance(&CLSID_MMDeviceEnumerator_, NULL, CLSCTX_ALL, &IID_IMMDeviceEnumerator_, (void **)&en))) return -1;
    if (FAILED(IMMDeviceEnumerator_GetDefaultAudioEndpoint(en, eRender, eConsole, &dev))) return -2;
    if (FAILED(IMMDevice_Activate(dev, &IID_IAudioClient_, CLSCTX_ALL, NULL, (void **)&g_ac))) return -3;
    WAVEFORMATEX wf = {0};
    wf.wFormatTag = WAVE_FORMAT_PCM; wf.nChannels = 2; wf.nSamplesPerSec = 48000; wf.wBitsPerSample = 16;
    wf.nBlockAlign = 4; wf.nAvgBytesPerSec = 48000 * 4;
    /* AUTOCONVERTPCM + SRC_DEFAULT_QUALITY: el motor mezcla a su formato nativo. 0x80000000 | 0x08000000 */
    if (FAILED(IAudioClient_Initialize(g_ac, AUDCLNT_SHAREMODE_SHARED, 0x80000000u | 0x08000000u, 2000000, 0, &wf, NULL))) return -4;
    IAudioClient_GetBufferSize(g_ac, &g_buf_frames);
    if (FAILED(IAudioClient_GetService(g_ac, &IID_IAudioRenderClient_, (void **)&g_rc))) return -5;
    IAudioClient_Start(g_ac);
    g_stop = 0; g_th = CreateThread(NULL, 0, hilo_wasapi, NULL, 0, NULL);
    return 0;
}
void audio_salida_cerrar(void) {
    g_stop = 1; if (g_th) { WaitForSingleObject(g_th, 1000); CloseHandle(g_th); g_th = NULL; }
    if (g_ac) { IAudioClient_Stop(g_ac); IAudioClient_Release(g_ac); g_ac = NULL; }
}
#elif defined(AUDIO_BACKEND_SDL2)
#include <SDL.h>
static SDL_AudioDeviceID g_dev;
static void SDLCALL cb(void *u, Uint8 *s, int len) { (void)u; audio_leer48((int16_t *)s, len / 4); }
int audio_salida_iniciar(void) {
    if (SDL_InitSubSystem(SDL_INIT_AUDIO) < 0) return -1;
    SDL_AudioSpec w = {0}, o; w.freq = 48000; w.format = AUDIO_S16SYS; w.channels = 2; w.samples = 1024; w.callback = cb;
    g_dev = SDL_OpenAudioDevice(NULL, 0, &w, &o, 0);
    if (!g_dev) return -2;
    SDL_PauseAudioDevice(g_dev, 0); return 0;
}
void audio_salida_cerrar(void) { if (g_dev) SDL_CloseAudioDevice(g_dev); g_dev = 0; }
#else
int audio_salida_iniciar(void) { return 0; }       /* sin backend: la cola solo se llena y las pruebas la leen */
void audio_salida_cerrar(void) {}
#endif
