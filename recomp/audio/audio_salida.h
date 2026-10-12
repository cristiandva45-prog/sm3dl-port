/* Salida de audio del port (agente H). El DSP HLE entrega frames de 160 muestras estereo s16 a 32.728 Hz
 * por audio_salida(); aqui se encolan, se re-muestrean a 48 kHz y se sirven a un backend:
 *   -DAUDIO_BACKEND_WASAPI  (shared mode, solo Windows, sin dependencias)
 *   -DAUDIO_BACKEND_SDL2    (necesita SDL2)
 *   ninguno                 (solo cola; las pruebas leen con audio_leer48) */
#ifndef AUDIO_SALIDA_H
#define AUDIO_SALIDA_H
#include <stdint.h>
void audio_salida(const int16_t *estereo, int n);          /* n = muestras (pares L,R) a 32.728 Hz */
int  audio_salida_iniciar(void);                           /* abre el backend; 0 = ok */
void audio_salida_cerrar(void);
void audio_leer48(int16_t *estereo, int n);                /* n pares a 48 kHz; rellena con silencio si falta */
uint32_t audio_cola_vacia(void);                           /* veces que el backend se quedo sin datos */
uint32_t audio_cola_descartes(void);                       /* muestras tiradas por cola llena */
/* agente AU (9 oct): salida con colchon + control de ritmo; SM3DL_AUDIO_VIEJO=1 = comportamiento anterior */
int      audio_modo_viejo(void);
uint32_t audio_cuadros_a_llenar(uint32_t pad, uint32_t tam_bufer);  /* cuanto escribir en el backend (WASAPI y pruebas) */
void     audio_reiniciar_estado(void);                     /* solo pruebas: estado de arranque, relee el entorno */
uint64_t audio_huecos48(void);                             /* muestras de 48 kHz sostenidas (todas, no solo la 1a) */
double   audio_cola_ms(void);                              /* nivel filtrado de la cola */
double   audio_ajuste(void);                               /* correccion relativa del paso de remuestreo */
uint32_t audio_saltos(void);
#endif
