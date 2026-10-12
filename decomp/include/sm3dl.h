/* Tipos y ayudas comunes de la decompilacion de Super Mario 3D Land.
 *
 * Decompilacion FUNCIONAL: cada funcion de src/ hace lo mismo que la original (lo comprueba
 * decomp/verificar.py corriendo ambas en Unicorn con las mismas entradas), pero no tiene por
 * que generar los mismos bytes: no tenemos el compilador de Nintendo (ARMCC).
 *
 * Las funciones originales se llaman por su nombre de extraido/simbolos.txt (o FUN_xxxxxxxx):
 * build.py las enlaza a su direccion real dentro de code.bin.
 */
#ifndef SM3DL_H
#define SM3DL_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef int s32;
typedef float f32;

/* Campo de un struct que todavia no tiene tipo: acceso por desplazamiento en bytes. */
#define CAMPO(tipo, p, off) (*(tipo *)((u8 *)(p) + (off)))

/* Objeto con vtable. En este binario el metodo k vive en vptr[k] (vptr = primera palabra). */
typedef struct Objeto {
    void **vt;
} Objeto;

typedef s32 (*MetodoI)(Objeto *self);
#define VLLAMAR_I(obj, k) (((MetodoI)((Objeto *)(obj))->vt[(k)])((Objeto *)(obj)))

/* Condicion del grafo de Mario: evaluar() es el metodo 2 (vptr+8). */
#define EVALUAR(cond) VLLAMAR_I((cond), 2)

typedef struct Vec3 {
    f32 x, y, z;
} Vec3;

#endif
