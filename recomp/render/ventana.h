/* Ventana del port (ver ventana.c). */
#ifndef VENTANA_H
#define VENTANA_H
#include "gsp.h"

/* callback de presentacion de gsp: copia la pantalla al lienzo y lo pinta tras la de abajo */
void ventana_presentar(const GspPresentacion *p);
/* 1 si la ventana del juego es la ventana activa (hid solo lee el teclado entonces) */
int ventana_con_foco(void);
/* gancho de hid (hid_toque_pc): toque de la pantalla de abajo por mouse o por "usar item" (tecla E / stick der.) */
int ventana_toque(int boton_item, float *x, float *y);
/* gancho de hid (hid_botones_pc): botones que agrega la ventana ("pulsa cualquier tecla" del titulo = A) */
uint32_t ventana_botones(void);
/* tic de 2 ms: en el modo de cuadros "monitor" presenta una vez por refresco del monitor */
void ventana_presentador(void);

#endif
