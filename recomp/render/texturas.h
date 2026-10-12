/* Decodificador de texturas PICA200 (14 formatos, mosaicos 8x8 en orden Morton) -> RGBA8 lineal.
   La salida va con la fila 0 ARRIBA (la PICA guarda la imagen invertida; aqui ya se endereza). */
#ifndef TEXTURAS_H
#define TEXTURAS_H
#include <stddef.h>
#include <stdint.h>

/* formatos: 0 RGBA8, 1 RGB8, 2 RGBA5551, 3 RGB565, 4 RGBA4, 5 LA8, 6 HILO8, 7 L8, 8 A8, 9 LA4, 10 L4, 11 A4,
   12 ETC1, 13 ETC1A4 */
size_t tex_tamano(int ancho, int alto, int fmt);  /* bytes de entrada del nivel 0; 0 si fmt no existe */
/* salida: ancho*alto*4 bytes (R,G,B,A). Devuelve 0 si ok, -1 si fmt invalido o faltan datos. */
int tex_decodificar(const uint8_t *datos, size_t largo, int ancho, int alto, int fmt, uint8_t *salida);
#endif
