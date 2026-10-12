/* Lote piloto de decompilacion a mano (7 oct 2026).
 * Cada funcion lleva su direccion original; decomp/verificar.py la compara contra esa direccion.
 */
#include "sm3dl.h"

/* --- funciones originales que se llaman (build.py las enlaza a code.bin) --- */
void FUN_0026dd60(void *iter, void *colisionador); /* iniciar iterador de contactos */
s32 FUN_0026dd4c(void *iter);                     /* iterador terminado? */
s32 FUN_0026dcf0(void *iter);                     /* contacto actual valido? */
void FUN_0026dc94(void *iter, void *info);        /* copiar info del contacto */
void FUN_0026dc84(void *iter);                    /* avanzar */
void FUN_00273064(Vec3 *out, const Vec3 *a, const Vec3 *b); /* resta de vectores */

/* 0x0026EBE0: *p |= 1 << bit. El desplazamiento de ARM usa el byte bajo y da 0 desde 32. */
void setFlagBit(u32 *p, u32 bit)
{
    u32 n = bit & 0xFF;
    *p = *p | (n >= 32 ? 0u : 1u << n);
}

/* 0x0027DB90: el mensaje mas consultado del juego (significado abierto). */
s32 isMsg17(s32 msg) { return msg == 0x11; }

/* 0x0027DBA0 */
s32 isMsgPlayerTailAttack(s32 msg) { return msg == 0x12; }

/* 0x00277D5C */
s32 isMsgPlayerKick(s32 msg) { return msg == 0x13; }

/* 0x00225458: velocidad (+0x24) en la direccion "arriba" del actor (+0x18) > 0.
 * Mismo orden de operaciones que el original: ((x*x') + (y*y')) + (z*z'). */
s32 isActorRising(const u8 *actor)
{
    const Vec3 *arriba = &CAMPO(Vec3, actor, 0x18);
    const Vec3 *vel = &CAMPO(Vec3, actor, 0x24);
    f32 d = arriba->x * vel->x;
    d = d + arriba->y * vel->y;
    d = d + arriba->z * vel->z;
    return d > 0.0f;
}

/* 0x001A9520: NOT. El original hace resultado ^ 1 sobre el entero entero, no un '!'. */
s32 PlayerActionCondNot_evaluate(u8 *self)
{
    return EVALUAR(CAMPO(Objeto *, self, 4)) ^ 1;
}

/* Lista intrusiva de condiciones (AND/OR): primer enlace en +0x8, centinela en +0x4,
 * desplazamiento del enlace dentro del elemento en +0x10; elemento[0] = condicion,
 * siguiente enlace en enlace+4. */

/* 0x001B8B74: AND que evalua TODAS (sin cortocircuito). */
s32 PlayerActionCondAnd_evaluate(u8 *self)
{
    s32 r = 1;
    u32 off = CAMPO(u32, self, 0x10);
    u8 *enlace = CAMPO(u8 *, self, 0x8);
    for (;;) {
        u8 *elem = enlace - off;
        if (elem == self + 4 - CAMPO(u32, self, 0x10))
            return r;
        r = (EVALUAR(CAMPO(Objeto *, elem, 0)) & r) != 0;
        enlace = CAMPO(u8 *, enlace, 4);
    }
}

/* 0x001A7288: OR que evalua TODAS. */
s32 PlayerActionCondOr_evaluate(u8 *self)
{
    s32 r = 0;
    u32 off = CAMPO(u32, self, 0x10);
    u8 *enlace = CAMPO(u8 *, self, 0x8);
    for (;;) {
        u8 *elem = enlace - off;
        if (elem == self + 4 - CAMPO(u32, self, 0x10))
            return r;
        r = (EVALUAR(CAMPO(Objeto *, elem, 0)) | r) != 0;
        enlace = CAMPO(u8 *, enlace, 4);
    }
}

/* 0x0018144C: elige el siguiente estado. Recorre las aristas del nodo actual en orden de
 * registro; la primera cuya condicion da true gana. El nodo se relee en cada vuelta porque
 * evaluar() podria cambiarlo (el original lo hace asi). */
void PlayerActionExecutor_selectNext(u8 *self)
{
    CAMPO(u32, self, 4) = 0;
    u8 *it = CAMPO(u8 *, CAMPO(u8 *, self, 0), 0xC);
    while (it != CAMPO(u8 *, self, 0) + 8) {
        u8 *arista = CAMPO(u8 *, it, 8);
        if (EVALUAR(CAMPO(Objeto *, arista, 0x10)) != 0) {
            CAMPO(u32, self, 4) = CAMPO(u32, CAMPO(u8 *, it, 8), 0x14);
            return;
        }
        it = CAMPO(u8 *, it, 4);
    }
}

/* Info de un contacto de colision (lo que llena FUN_0026dc94). */
typedef struct InfoContacto {
    f32 normal[3]; /* +0x0 */
    s32 codigo;    /* +0xC (cuadra con Floor_code) */
    s32 otro[3];   /* +0x10.. */
} InfoContacto;

/* 0x00225498: algun contacto activo tiene codigo == N? */
s32 PlayerCollider_isTouchCode(void *colisionador, s32 codigo)
{
    InfoContacto info = {{0.0f, 0.0f, 0.0f}, 0, {0, 0, 0}};
    u32 iter[2];
    FUN_0026dd60(iter, colisionador);
    while (!FUN_0026dd4c(iter)) {
        if (FUN_0026dcf0(iter)) {
            FUN_0026dc94(iter, &info);
            if (info.codigo == codigo)
                return 1;
        }
        FUN_0026dc84(iter);
    }
    return 0;
}

/* 0x002D2C6C: "pulso A/B (<=5f) Y en suelo Y NO subiendo".
 * this+0xC = colisionador (vf9 = en suelo), this+0x8 = fisica, this+0x4 = control (vf9 = salto). */
s32 PlayerActionCondJumpOnGround_evaluate(u8 *self)
{
    if (VLLAMAR_I(CAMPO(Objeto *, self, 0xC), 9) == 0)
        return 0;
    if (isActorRising(CAMPO(u8 *, self, 0x8)) != 0)
        return 0;
    return VLLAMAR_I(CAMPO(Objeto *, self, 0x4), 9) != 0;
}

/* 0x002D3B34: "velocidad ~ 0": |FUN_00273064(+0x6C, +0x24)| <= 0.1.
 * El original compara los BITS del float como entero con signo (vale igual para floats >= 0). */
s32 PlayerActionCondStopped_evaluate(u8 *self)
{
    u8 *fis = CAMPO(u8 *, self, 4);
    Vec3 v;
    FUN_00273064(&v, &CAMPO(Vec3, fis, 0x6C), &CAMPO(Vec3, fis, 0x24));
    f32 s = v.x * v.x;
    s = s + v.y * v.y;
    s = s + v.z * v.z;
    union { f32 f; s32 i; } largo;
    largo.f = __builtin_sqrtf(s);
    return largo.i <= 0x3DCCCCCD;
}

/* 0x00326C54: frames desde que pulso A/B < 5 (buffer de salto). */
s32 PlayerInput_isJumpTriggerBuffered(const u8 *in) { return CAMPO(u32, in, 0x34) < 5; }

/* 0x00326C78 */
s32 PlayerInput_isJumpHold(const u8 *in) { return CAMPO(s8, in, 0x30); }

/* 0x00326C44 */
const Vec3 *PlayerInput_getStickDir3D(const u8 *in) { return &CAMPO(Vec3, in, 0x10); }
