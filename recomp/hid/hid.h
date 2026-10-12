/* Memoria compartida de hid:USER (la que el juego recibe de GetIPCHandles) y su llenado desde la PC.
 * Layout (little-endian, como la ve el ARM11). Offsets verificados con _Static_assert en hid.c:
 *   0x000 pad   { s64 ticks_reinicio, s64 ticks_reinicio_prev, u32 indice, u32 _, f32 slider3d,
 *                 u32 estado_actual, u32 circle_crudo, u32 _, PadEntrada[8] (0x10 c/u) }       -> 0x0A8
 *   0x0A8 touch { s64, s64, u32 indice, u32 _, TouchEntrada cruda, TouchEntrada[8] (8 c/u) }   -> 0x108
 *   0x108 accel { s64, s64, u32 indice, u32 _, Xyz crudo + 2 pad, Xyz[8] (6 c/u) }             -> 0x158
 *   0x158 giro  { s64, s64, u32 indice, u32 _, Xyz crudo + 2 pad, Xyz[32] }                    -> 0x238
 * Ritmo en hardware: pad+touch 234 Hz (se señalan los eventos PadOrTouch1 y 2), accel 104 Hz, giro 101 Hz.
 * Referencia de lectura: Azahar src/core/hle/service/hid/hid.h (reescrito, no copiado). */
#ifndef SM3DL_HID_H
#define SM3DL_HID_H
#include <stdint.h>

enum {
    HID_A = 1u << 0, HID_B = 1u << 1, HID_SELECT = 1u << 2, HID_START = 1u << 3,
    HID_DERECHA = 1u << 4, HID_IZQUIERDA = 1u << 5, HID_ARRIBA = 1u << 6, HID_ABAJO = 1u << 7,
    HID_R = 1u << 8, HID_L = 1u << 9, HID_X = 1u << 10, HID_Y = 1u << 11,
    HID_CIRC_DERECHA = 1u << 28, HID_CIRC_IZQUIERDA = 1u << 29, HID_CIRC_ARRIBA = 1u << 30, HID_CIRC_ABAJO = 1u << 31,
};

#pragma pack(push, 1)
typedef struct { uint32_t actual, altas, bajas; int16_t cx, cy; } HidPadEntrada;          /* 0x10 */
typedef struct { uint16_t x, y; uint32_t valido; } HidTouchEntrada;                         /* 0x08 */
typedef struct { int16_t x, y, z; } HidXyz;                                                  /* 0x06 */
typedef struct {
    struct { int64_t ticks, ticks_prev; uint32_t indice, _p0; float slider3d; uint32_t actual, circle_crudo, _p1;
             HidPadEntrada e[8]; } pad;
    struct { int64_t ticks, ticks_prev; uint32_t indice, _p0; HidTouchEntrada crudo; HidTouchEntrada e[8]; } touch;
    struct { int64_t ticks, ticks_prev; uint32_t indice, _p0; HidXyz crudo; uint16_t _p1; HidXyz e[8]; } accel;
    struct { int64_t ticks, ticks_prev; uint32_t indice, _p0; HidXyz crudo; uint16_t _p1; HidXyz e[32]; } giro;
} HidShm;
#pragma pack(pop)

/* Estado de la PC ya normalizado: botones con los bits HID_*, stick en [-1, 1] (y hacia arriba positivo),
 * touch en [0, 1] sobre la pantalla inferior (320x240). */
typedef struct { uint32_t botones; float stick_x, stick_y; int tocando; float touch_x, touch_y; } HidEntradaPC;

typedef struct { uint32_t sig_pad, sig_touch; int16_t viejo_x[2], viejo_y[2]; } HidEstado;

void hid_iniciar(HidShm *m, HidEstado *s);
/* Una muestra (llamar a 234 Hz). ticks = reloj del 3DS (268.111.856 Hz). Devuelve 1 si hay que
 * señalar los eventos PadOrTouch1/2. */
int hid_muestrear(HidShm *m, HidEstado *s, const HidEntradaPC *e, int64_t ticks);
/* Lee el teclado (y XInput si hay mando) a un HidEntradaPC. Solo Windows. */
void hid_leer_pc(HidEntradaPC *e);

/* Entrada por guion (SM3DL_GUION, ver hid.c): suma al estado e lo que el guion pulse en este vblank.
 * Se carga solo la primera vez. Funciona sin foco de ventana. */
int hid_guion_cargar(const char *ruta);
void hid_guion_aplicar(HidEntradaPC *e, uint32_t vblank);
void hid_grabar(const HidEntradaPC *e, uint32_t vblank);   /* SM3DL_GRABAR=<archivo>: guion de lo que se juega */

#endif
