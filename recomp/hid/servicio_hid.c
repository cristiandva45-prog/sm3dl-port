#include "servicio_hid.h"
#include <string.h>

#define ACCEL_1G 512          /* 1 g = 512 cuentas */
#define GIRO_COEF 14.375f     /* cuentas por grado/s (valor de la consola real) */

void hid_srv_iniciar(HidServicio *h, void *shm_host, HidSenal senal, void *ctx)
{
    memset(h, 0, sizeof *h);
    memset(shm_host, 0, HID_SHM_TAM);
    h->shm = (HidShm *)shm_host;
    h->senal = senal; h->ctx = ctx;
    h->volumen = 0x3F;
    hid_iniciar(h->shm, &h->est);
}

static void senalar(HidServicio *h, int ev) { if (h->senal) h->senal(h->ctx, ev); }

int hid_srv_comando(HidServicio *h, uint32_t *c)
{
    uint32_t id = c[0] >> 16;
    if (id < 0x20) h->comandos[id]++;
    switch (id) {
    case 0x0A: /* GetIPCHandles: 1 normal + 7 de traduccion (descriptor de 6 handles copiados + 6 handles) */
        c[0] = 0x000A0047u; c[1] = 0;
        c[2] = (5u << 26);                       /* descriptor "copiar 6 handles" */
        c[3] = h->h_shm;
        for (int i = 0; i < HIDEV_N; i++) c[4 + i] = h->h_ev[i];
        return 1;
    case 0x11: case 0x13:
        if (id == 0x11) h->cuenta_accel++; else h->cuenta_giro++;
        c[0] = (id << 16) | 0x40u; c[1] = 0;
        return 1;
    case 0x12: case 0x14:
        if (id == 0x12) h->cuenta_accel--; else h->cuenta_giro--;
        c[0] = (id << 16) | 0x40u; c[1] = 0;
        return 1;
    case 0x15: { /* coeficiente raw -> grados/s */
        float f = GIRO_COEF;
        c[0] = 0x00150080u; c[1] = 0; memcpy(&c[2], &f, 4);
        return 1; }
    case 0x16: { /* calibracion: {cero, +unidad, -unidad} x3 ejes, s16; unidad = 6700 (valor aproximado del hardware) */
        int16_t p[9] = { 0, 6700, -6700, 0, 6700, -6700, 0, 6700, -6700 };
        c[0] = 0x00160180u; c[1] = 0;
        memset(&c[2], 0, 5 * 4);
        memcpy(&c[2], p, sizeof p);              /* 18 bytes */
        return 1; }
    case 0x17:
        c[0] = 0x00170080u; c[1] = 0; c[2] = h->volumen;
        return 1;
    default:
        return 0;
    }
}

static void muestra_accel(HidServicio *h, int64_t ticks)
{
    HidShm *m = h->shm;
    m->accel.indice = h->sig_accel;
    h->sig_accel = (h->sig_accel + 1) % 8;
    HidXyz *x = &m->accel.e[m->accel.indice];
    x->x = 0; x->y = 0; x->z = -ACCEL_1G;       /* en reposo, plana: la gravedad en Z */
    m->accel.crudo = *x;
    if (m->accel.indice == 0) { m->accel.ticks_prev = m->accel.ticks; m->accel.ticks = ticks; }
}

static void muestra_giro(HidServicio *h, int64_t ticks)
{
    HidShm *m = h->shm;
    m->giro.indice = h->sig_giro;
    h->sig_giro = (h->sig_giro + 1) % 32;
    HidXyz *x = &m->giro.e[m->giro.indice];
    x->x = 0; x->y = 0; x->z = 0;               /* giro 0 */
    m->giro.crudo = *x;
    if (m->giro.indice == 0) { m->giro.ticks_prev = m->giro.ticks; m->giro.ticks = ticks; }
}

void hid_tick(HidServicio *h, const HidEntradaPC *e, int64_t ticks)
{
    if (hid_muestrear(h->shm, &h->est, e, ticks)) { senalar(h, HIDEV_PAD0); senalar(h, HIDEV_PAD1); }
    if (h->cuenta_accel > 0) {
        h->acu_accel += HID_HZ_ACCEL;
        if (h->acu_accel >= HID_HZ_PAD) { h->acu_accel -= HID_HZ_PAD; muestra_accel(h, ticks); senalar(h, HIDEV_ACCEL); }
    }
    if (h->cuenta_giro > 0) {
        h->acu_giro += HID_HZ_GIRO;
        if (h->acu_giro >= HID_HZ_PAD) { h->acu_giro -= HID_HZ_PAD; muestra_giro(h, ticks); senalar(h, HIDEV_GYRO); }
    }
}
