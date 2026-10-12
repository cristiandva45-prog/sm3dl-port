/* Tanda 2 de decompilacion a mano: funciones de tamano medio (el 66% del codigo esta en 30-300 instrucciones). */
#include "sm3dl.h"

/* --- originales que se llaman --- */
s32 isSensorPlayer(void *sensor);
s32 isSensorEnemyAttack(void *sensor);
s32 isSensorEnemy(void *sensor);
s32 isSensorMapObj(void *sensor);
s32 isNerve(void *actor, const void *nerve);
void setNerve(void *actor, const void *nerve);
s32 sendMsgPush(void *receptor, void *emisor);
s32 sendMsgEnemyAttack(void *receptor, void *emisor);
void sendMsgPushAndKillVelocityToTarget(void *actor, void *mio, void *otro);
extern const u8 NrvKuribo_Attack[], NrvKuribo_PopOut[], NrvKuribo_PressDown[], NrvKuribo_BlowDown[];

void FUN_00273064(Vec3 *out, const Vec3 *a, const Vec3 *b);
s32 isNearZeroVec3(Vec3 *v);
s32 FUN_001721f0(const Vec3 *v, const Vec3 *frente);
s32 FUN_0026f714(const Vec3 *v, f32 eps);
Objeto *FUN_0026e1d4(void); /* tabla global de parametros del jugador */

typedef f32 (*MetodoF)(Objeto *self);

static inline s32 bits(f32 f)
{
    union { f32 f; s32 i; } u;
    u.f = f;
    return u.i;
}

static inline f32 largo(const Vec3 *v)
{
    f32 s = v->x * v->x;
    s = s + v->y * v->y;
    s = s + v->z * v->z;
    return __builtin_sqrtf(s);
}

/* 0x0030820C: el Goomba choca con algo.
 * - contra Mario con su sensor de ataque: lo empuja y le hace dano; si el dano entra, pasa a "atacar"
 *   (salvo que ya este aplastado, volando o atacando).
 * - contra otro enemigo: empujon que le quita la velocidad (salvo que este saliendo disparado).
 * - contra un objeto del mapa: empujon. */
void Kuribo_attackSensor(void *self, void *mio, void *otro)
{
    if (isSensorPlayer(otro) && isSensorEnemyAttack(mio)) {
        if (isNerve(self, NrvKuribo_PressDown) || isNerve(self, NrvKuribo_BlowDown))
            return;
        sendMsgPush(otro, mio);
        if (!sendMsgEnemyAttack(otro, mio))
            return;
        if (isNerve(self, NrvKuribo_Attack))
            return;
        setNerve(self, NrvKuribo_Attack);
        return;
    }
    if (isSensorEnemy(otro)) {
        if (isNerve(self, NrvKuribo_PopOut))
            return;
        sendMsgPushAndKillVelocityToTarget(self, mio, otro);
        return;
    }
    if (isSensorMapObj(otro))
        sendMsgPush(otro, mio);
}

/* 0x002D3D58: condicion "Frenar" (stick contrario a la velocidad).
 * this: +4 fisica, +8 control, +0xC condicion extra, +0x10 contador de frames que quedan.
 * Todas las comparaciones de floats son de BITS como entero con signo, igual que el original. */
s32 PlayerActionCondBrake_evaluate(u8 *self)
{
    u8 *fis = CAMPO(u8 *, self, 4);
    Objeto *ctrl = CAMPO(Objeto *, self, 8);

    f32 fuerza = largo((const Vec3 *)VLLAMAR_I(ctrl, 3));   /* |stick| */
    Vec3 stick = *(const Vec3 *)VLLAMAR_I(ctrl, 3);
    FUN_00273064(&stick, &CAMPO(Vec3, fis, 0x18), &stick);
    isNearZeroVec3(&stick);
    s32 casi_frente = FUN_001721f0(&stick, &CAMPO(Vec3, fis, 0xC));

    if (bits(fuerza) > 0x3F666666 /* 0.9 */ && casi_frente == 0 && FUN_0026f714(&stick, 0.001f) == 0) {
        Vec3 vel;
        FUN_00273064(&vel, &CAMPO(Vec3, fis, 0x18), &CAMPO(Vec3, fis, 0x24));
        Vec3 dir = vel;
        isNearZeroVec3(&dir);
        const Vec3 *frente = &CAMPO(Vec3, fis, 0xC);
        f32 rapidez = largo(&vel);
        Objeto *param = FUN_0026e1d4();
        f32 minimo = ((MetodoF)param->vt[0x2C8 / 4])(param);
        s32 opuesto = 0;
        if (!(rapidez < minimo)) {
            f32 d1 = vel.x * stick.x;
            d1 = d1 + vel.y * stick.y;
            d1 = d1 + vel.z * stick.z;
            if (bits(d1) >= 0x3F3504F3 /* cos 45 */) {
                f32 d2 = frente->x * stick.x;
                d2 = d2 + frente->y * stick.y;
                d2 = d2 + frente->z * stick.z;
                opuesto = bits(d2) >= 0x3F3504F3;
            }
        }
        if (opuesto) {
            Objeto *p2 = FUN_0026e1d4();
            CAMPO(s32, self, 0x10) = VLLAMAR_I(p2, 0x2C4 / 4);
        } else {
            CAMPO(s32, self, 0x10) = 0;
        }
    }

    if (VLLAMAR_I(CAMPO(Objeto *, self, 0xC), 0) == 0)
        CAMPO(s32, self, 0x10) = 0;

    s32 cont = CAMPO(s32, self, 0x10);
    /* original: cmp 0.3, fuerza ; cmple casi_frente, #0 ; beq -> solo si fuerza >= 0.3 Y casi_frente == 0 */
    if (bits(fuerza) >= 0x3E99999A /* 0.3 */ && casi_frente == 0) {
        if (cont != 0)
            CAMPO(s32, self, 0x10) = cont - 1;
        return 0;
    }
    return cont != 0;
}
