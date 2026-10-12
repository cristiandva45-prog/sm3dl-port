/* dsp::DSP HLE para el port de SM3DL (agente H, 8 oct 2026).
 * Servicio enchufable: no ejecuta el firmware DSP1; emula el contrato de memoria compartida
 * (24 fuentes, 2 regiones) y el tick de 160 muestras a 32.728 Hz. Semantica reimplementada a partir
 * del comportamiento observado en azahar-src/src/audio_core/hle (no es copia literal).
 * Uso desde la capa de sistema: ver "pedido de integracion" en agentes_8oct/H.md. */
#ifndef DSP_H
#define DSP_H
#include <stdint.h>

#define DSP_RAM_BASE    0x1FF00000u   /* donde el juego ve la RAM del DSP (512 KB) */
#define DSP_RAM_TAM     0x80000u
#define DSP_REGION0     0x50000u
#define DSP_REGION1     0x70000u
#define DSP_FUENTES     24
#define DSP_MUESTRAS    160           /* por tick */
#define DSP_FS          32728

/* Tipos de interrupcion de RegisterInterruptEvents */
enum { DSP_INT_CERO = 0, DSP_INT_UNO = 1, DSP_INT_PIPE = 2 };
/* Pipes */
enum { DSP_PIPE_DEBUG = 0, DSP_PIPE_DMA = 1, DSP_PIPE_AUDIO = 2, DSP_PIPE_BINARY = 3 };

typedef struct dsp_host {
    /* puntero del anfitrion a memoria FISICA del guest (>= nbytes validos) o NULL */
    const uint8_t *(*fis)(void *ud, uint32_t paddr, uint32_t nbytes);
    /* SignalEvent del handle registrado (puede ser NULL en pruebas) */
    void (*senal)(void *ud, uint32_t handle);
    /* destino de cada frame de 160 muestras estereo (NULL = audio_salida) */
    void (*salida)(void *ud, const int16_t *estereo, int n);
    void *ud;
} dsp_host_t;

void     dsp_iniciar(const dsp_host_t *h);
uint8_t *dsp_ram(void);                 /* 512 KB: mapear en DSP_RAM_BASE del guest */

/* ---- servicio dsp::DSP (los nombres son los del SDK) ---- */
int      dsp_LoadComponent(uint32_t size, uint32_t prog_mask, uint32_t data_mask, uint8_t *cargado);
int      dsp_UnloadComponent(void);
uint32_t dsp_GetSemaphoreEventHandle(void);          /* handle puesto con dsp_poner_evento_semaforo */
void     dsp_poner_evento_semaforo(uint32_t handle);
int      dsp_RegisterInterruptEvents(uint32_t handle, uint32_t interrupt, uint32_t canal); /* handle 0 = desregistrar */
int      dsp_WriteProcessPipe(uint32_t canal, const uint8_t *buf, uint32_t len);
int      dsp_ReadPipeIfPossible(uint32_t canal, uint32_t peer, uint8_t *buf, uint32_t len, uint32_t *leidos);
uint32_t dsp_ConvertProcessAddressFromDspDram(uint32_t dir_dsp);
int      dsp_FlushDataCache(uint32_t va, uint32_t tam);
int      dsp_InvalidateDataCache(uint32_t va, uint32_t tam);
int      dsp_SetSemaphore(uint16_t v);
int      dsp_SetSemaphoreMask(uint16_t m);
uint16_t dsp_RecvData(uint32_t reg);
int      dsp_RecvDataIsReady(uint32_t reg);
uint32_t dsp_GetHeadphoneStatus(void);

/* ---- reloj ---- */
int      dsp_tick(void);                /* genera UN frame (160 muestras). 1 si el DSP esta On */
#ifdef DSP_HILO_WIN32
void     dsp_hilo_iniciar(void);        /* hilo del anfitrion: un tick cada 4,8886 ms */
void     dsp_hilo_parar(void);
#endif

/* diagnostico */
uint32_t dsp_frames_generados(void);
uint32_t dsp_cola_desbordes(void);
#endif
