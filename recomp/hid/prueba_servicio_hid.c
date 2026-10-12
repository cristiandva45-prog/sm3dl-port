/* Prueba del servicio hid:USER: comandos IPC y ritmo de hid_tick. */
#include "servicio_hid.h"
#include <stdio.h>
#include <string.h>

static int fallos;
#define EXIGE(c) do { if (!(c)) { printf("FALLA linea %d: %s\n", __LINE__, #c); fallos++; } } while (0)
static int veces[HIDEV_N];
static void senal(void *ctx, int ev) { (void)ctx; veces[ev]++; }

int main(void)
{
    static uint8_t mem[HID_SHM_TAM];
    static HidServicio h;
    hid_srv_iniciar(&h, mem, senal, 0);
    h.h_shm = 0x100; for (int i = 0; i < HIDEV_N; i++) h.h_ev[i] = 0x200 + i;
    uint32_t c[64];

    /* GetIPCHandles */
    memset(c, 0, sizeof c); c[0] = 0x000A0000u;
    EXIGE(hid_srv_comando(&h, c) == 1);
    EXIGE(c[0] == 0x000A0047u && c[1] == 0 && c[2] == 0x14000000u && c[3] == 0x100 && c[4] == 0x200 && c[8] == 0x204);

    /* coeficiente y calibracion */
    c[0] = 0x00150000u; EXIGE(hid_srv_comando(&h, c) == 1);
    float f; memcpy(&f, &c[2], 4); EXIGE(f == 14.375f && c[1] == 0);
    c[0] = 0x00160000u; EXIGE(hid_srv_comando(&h, c) == 1);
    int16_t p[9]; memcpy(p, &c[2], 18); EXIGE(p[1] == 6700 && p[2] == -6700 && p[7] == 6700 && c[0] == 0x00160180u);

    /* sin habilitar: 234 ticks = 234 muestras de pad, 0 de accel/giro */
    HidEntradaPC e; memset(&e, 0, sizeof e);
    for (int i = 0; i < 234; i++) hid_tick(&h, &e, 1000 + i);
    EXIGE(veces[HIDEV_PAD0] == 234 && veces[HIDEV_PAD1] == 234 && veces[HIDEV_ACCEL] == 0 && veces[HIDEV_GYRO] == 0);

    /* habilitar accel y giro: 1 s de ticks -> 104 y 101 eventos */
    c[0] = 0x00110000u; hid_srv_comando(&h, c);
    c[0] = 0x00130000u; hid_srv_comando(&h, c);
    EXIGE(h.cuenta_accel == 1 && h.cuenta_giro == 1);
    for (int i = 0; i < 234; i++) hid_tick(&h, &e, 5000 + i);
    EXIGE(veces[HIDEV_ACCEL] == 104 && veces[HIDEV_GYRO] == 101);
    EXIGE(h.shm->accel.crudo.z == -512 && h.shm->accel.crudo.x == 0 && h.shm->giro.crudo.x == 0);
    EXIGE(h.shm->accel.ticks != 0 && h.shm->giro.ticks != 0);

    /* deshabilitar: cuenta a 0 y se detienen */
    c[0] = 0x00120000u; hid_srv_comando(&h, c);
    c[0] = 0x00140000u; hid_srv_comando(&h, c);
    EXIGE(h.cuenta_accel == 0 && h.cuenta_giro == 0);
    int a = veces[HIDEV_ACCEL];
    for (int i = 0; i < 234; i++) hid_tick(&h, &e, 9000 + i);
    EXIGE(veces[HIDEV_ACCEL] == a);

    /* el mando llega al anillo que lee el juego */
    e.botones = HID_A; hid_tick(&h, &e, 20000);
    EXIGE(h.shm->pad.e[h.shm->pad.indice].actual == HID_A);

    /* comando desconocido */
    c[0] = 0x00990000u; EXIGE(hid_srv_comando(&h, c) == 0);
    if (fallos) printf("FALLOS: %d\n", fallos); else printf("OK servicio_hid\n");
    return fallos != 0;
}
