/* Prueba del anillo de hid: escribe muestras y lee de vuelta como lo haria el juego. */
#include "hid.h"
#include <stdio.h>

static int fallos;
#define EXIGE(c) do { if (!(c)) { printf("FALLA linea %d: %s\n", __LINE__, #c); fallos++; } } while (0)

int main(void)
{
    static HidShm m;
    HidEstado s;
    hid_iniciar(&m, &s);
    HidEntradaPC e = {0};

    /* 1) pulsar A: alta en la entrada 0, ticks fijados al volver al indice 0 */
    e.botones = HID_A;
    hid_muestrear(&m, &s, &e, 1000);
    EXIGE(m.pad.indice == 0 && m.pad.e[0].actual == HID_A && m.pad.e[0].altas == HID_A && m.pad.e[0].bajas == 0);
    EXIGE(m.pad.ticks == 1000);

    /* 2) soltar A y pulsar B */
    e.botones = HID_B;
    hid_muestrear(&m, &s, &e, 2000);
    EXIGE(m.pad.indice == 1 && m.pad.e[1].altas == HID_B && m.pad.e[1].bajas == HID_A);

    /* 3) stick a fondo a la derecha: el promedio de 3 llega a 0x9A en la 3a muestra, y marca CIRC_DERECHA */
    e.botones = 0; e.stick_x = 1.0f;
    for (int k = 0; k < 3; k++) hid_muestrear(&m, &s, &e, 3000 + k);
    EXIGE(m.pad.e[m.pad.indice].cx == 0x9A && m.pad.e[m.pad.indice].cy == 0);
    EXIGE(m.pad.actual == HID_CIRC_DERECHA);

    /* 4) diagonal: dos direcciones */
    e.stick_x = 0.7f; e.stick_y = 0.7f;
    for (int k = 0; k < 3; k++) hid_muestrear(&m, &s, &e, 4000 + k);
    EXIGE(m.pad.actual == (HID_CIRC_DERECHA | HID_CIRC_ARRIBA));

    /* 5) el anillo da la vuelta (8 entradas) y reajusta ticks/ticks_prev */
    e.stick_x = e.stick_y = 0;
    int64_t antes = m.pad.ticks;
    for (int k = 0; k < 8; k++) hid_muestrear(&m, &s, &e, 9000 + k);
    EXIGE(m.pad.ticks_prev == antes && m.pad.ticks != antes && m.pad.indice < 8);

    /* 6) touch */
    e.tocando = 1; e.touch_x = 0.5f; e.touch_y = 0.25f;
    hid_muestrear(&m, &s, &e, 10000);
    EXIGE(m.touch.e[m.touch.indice].x == 160 && m.touch.e[m.touch.indice].y == 60 && m.touch.e[m.touch.indice].valido == 1);

    printf(fallos ? "prueba_hid: %d FALLAS\n" : "prueba_hid: OK\n", fallos);
    return fallos != 0;
}
