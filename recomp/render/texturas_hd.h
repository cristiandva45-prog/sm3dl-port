/* TEXTURAS DE REEMPLAZO / ALTA DEFINICION (9 oct 2026; contrato en agentes_tex\BRIEF_TEXTURAS.md).
 * La capa comun (raster_gl.c, textura_para) calcula la CLAVE de cada textura del juego y pregunta aqui si hay una version
 * en disco. Clave = FNV-1a de 32 bits (la misma fnv() de raster_gl.c, por palabras de 32 bits) sobre los bytes CRUDOS del
 * NIVEL 0 tal como estan en la memoria del 3DS (antes de decodificar), con el tamano y el formato PICA aparte en el nombre.
 * Archivo: <raiz>\texturas_hd\tex_<w>x<h>_f<fmt>_<CLAVE %08X>.png  (w,h = tamano ORIGINAL; el PNG puede ser k veces mayor).
 * Autor del modulo: agente T4. Ganchos en raster_gl.c: agente T2. Menu: agente T7. */
#ifndef TEXTURAS_HD_H
#define TEXTURAS_HD_H
#include <stdint.h>

/* 1 si el reemplazo esta encendido (SM3DL_TEX_HD=0 lo apaga; el menu lo cambia con texhd_fijar). */
int  texhd_activo(void);
void texhd_fijar(int encendido);

/* Busca el reemplazo de (clave, w, h, fmt). Si existe: devuelve 1 y deja en *W,*H el tamano del nivel 0 HD, en *niveles
   los mips generados (>= 1) y en *rgba los punteros RGBA8 de cada nivel (fila 0 = la misma convencion que el decodificador
   de texturas.c). Los datos son del modulo y valen hasta la proxima llamada a texhd_buscar. Si no existe: 0 (barato:
   el modulo recuerda las claves que no estan). */
int  texhd_buscar(uint32_t clave, int w, int h, int fmt, int *W, int *H, int *niveles, const uint8_t *const **rgba);

/* Modo volcado (SM3DL_TEX_VOLCAR=<carpeta>): guarda el ORIGINAL decodificado con su nombre de archivo de reemplazo, una
   vez por clave. Sirve para mapear y para que el dueno vea que texturas usa cada escena. */
int  texhd_volcando(void);
void texhd_volcar(uint32_t clave, int w, int h, int fmt, const uint8_t *rgba_nivel0);

/* Diagnostico: cuantas texturas se reemplazaron / se buscaron (para el log). */
void texhd_estadisticas(uint32_t *reemplazadas, uint32_t *buscadas);

#endif
