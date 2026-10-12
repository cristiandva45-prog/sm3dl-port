/* Servicio hid:USER en HLE (reimplementado desde el comportamiento observado; Azahar solo como referencia).
 * Independiente de recomp/sistema: el sistema le da (1) la memoria compartida (HID_SHM_TAM bytes del anfitrion que mapea en la
 * direccion que pida el juego), (2) una funcion para senalar eventos, (3) los valores de los handles. Ver "pedido de integracion"
 * en reportes/hid.md.
 * Comandos atendidos (cabecera IPC >> 16): 0x0A GetIPCHandles, 0x11/0x12 Enable/DisableAccelerometer,
 * 0x13/0x14 Enable/DisableGyroscopeLow, 0x15 GetGyroscopeLowRawToDpsCoefficient, 0x16 GetGyroscopeLowCalibrateParam,
 * 0x17 GetSoundVolume. Cualquier otro: devuelve 0 (no atendido) y el sistema decide. */
#ifndef SM3DL_SERVICIO_HID_H
#define SM3DL_SERVICIO_HID_H
#include "hid.h"

enum { HIDEV_PAD0, HIDEV_PAD1, HIDEV_ACCEL, HIDEV_GYRO, HIDEV_DEBUGPAD, HIDEV_N };

#define HID_SHM_TAM 0x1000u
#define HID_HZ_PAD   234
#define HID_HZ_ACCEL 104
#define HID_HZ_GIRO  101

typedef void (*HidSenal)(void *ctx, int evento);   /* evento = HIDEV_* ; el sistema hace SignalEvent del handle correspondiente */

typedef struct {
    HidShm *shm;                 /* apunta a HID_SHM_TAM bytes del anfitrion (los que ve el juego) */
    HidSenal senal; void *ctx;
    uint32_t h_shm, h_ev[HIDEV_N];   /* handles que devuelve GetIPCHandles (los rellena el sistema) */
    HidEstado est;
    int cuenta_accel, cuenta_giro;   /* Enable/Disable llevan cuenta, como el servicio real */
    int acu_accel, acu_giro;         /* acumuladores de Bresenham 104/234 y 101/234 */
    uint32_t sig_accel, sig_giro;
    uint32_t volumen;                /* 0..0x3F */
    uint32_t comandos[0x20];         /* contador por numero de comando (diagnostico) */
} HidServicio;

void hid_srv_iniciar(HidServicio *h, void *shm_host, HidSenal senal, void *ctx);
/* Atiende un comando IPC. cmd = palabras del buffer de comando (TLS+0x80); se lee la peticion y se escribe la respuesta
 * en el mismo buffer. Devuelve 1 si lo atendio. */
int hid_srv_comando(HidServicio *h, uint32_t *cmd);
/* Llamar a 234 Hz. e = estado de la PC; ticks = reloj del 3DS. Actualiza pad+touch (siempre), acelerometro y giroscopio
 * (solo si estan habilitados; en reposo) y senala los eventos que toquen. */
void hid_tick(HidServicio *h, const HidEntradaPC *e, int64_t ticks);

#endif
