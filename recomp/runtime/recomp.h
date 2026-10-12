/* Runtime de la recompilacion estatica ARM11 -> C de Super Mario 3D Land.
 *
 * El codigo generado (gen/juego.c) trabaja sobre un "procesador virtual" (CPU) y sobre la memoria del
 * juego vista por paginas de 4 KB (rt_pagina). Las direcciones son las del 3DS: el codigo traducido
 * lee y escribe exactamente donde lo hacia el original.
 *
 * Punto flotante: el SDK del 3DS deja el VFP en modo RunFast (FZ: desnormales a cero; DN: todo NaN
 * resultante es 0x7FC00000). En x86 se imita con FTZ/DAZ del MXCSR (rt_ejecutar) + canonizar NaN (FB()).
 */
#ifndef RECOMP_H
#define RECOMP_H

#include <stdint.h>
#ifdef RECOMP_IDENTIDAD
#include <stddef.h>
void *memcpy(void *d, const void *s, size_t n);
void *memset(void *d, int v, size_t n);
#else
#include <string.h>
#endif

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t s8;
typedef int16_t s16;
typedef int32_t s32;
typedef int64_t s64;

typedef struct CPU {
    u32 r[16];       /* r13 = sp, r14 = lr, r15 = pc (solo informativo) */
    u32 n, z, c, v;  /* banderas del CPSR */
    u32 s[32];       /* registros VFP de simple precision, como bits */
    u32 fn, fz, fc, fv; /* banderas del FPSCR (las copia vmrs APSR_nzcv) */
    u32 tls;            /* CP15 c13,c0,3 (TPIDRURO): puntero de hilo que pone el sistema */
    u32 tls_rw;         /* CP15 c13,c0,2 (TPIDRURW) */
    u32 excl, excl_addr; /* monitor exclusivo de ldrex/strex */
    u32 fpscr;          /* lo que escribio vmsr (el juego pone 0x03000000 una vez) */
} CPU;

extern u8 *rt_pagina[1u << 20];
void rt_externo(CPU *c, u32 addr);       /* llamada a algo no recompilado (lo atiende el anfitrion) */
void rt_llamar(CPU *c, u32 addr);         /* salto indirecto: tabla de funciones recompiladas */
void rt_desconocida(CPU *c, u32 addr);   /* instruccion que el recompilador aun no soporta */
void rt_svc(CPU *c, u32 num, u32 addr);  /* llamada al sistema del 3DS */

#ifdef RECOMP_IDENTIDAD
/* compilado para ARM y corriendo dentro del emulador: la memoria del 3DS ES la memoria del proceso */
static inline u8 *P(u32 a) { return (u8 *)(uintptr_t)a; }
#else
static inline u8 *P(u32 a) { return rt_pagina[a >> 12] + (a & 0xFFF); }
#endif
static inline u32 R32(u32 a) { u32 v; memcpy(&v, P(a), 4); return v; }
static inline u32 R16(u32 a) { u16 v; memcpy(&v, P(a), 2); return v; }
static inline u32 R8(u32 a) { return *P(a); }
static inline void W32(u32 a, u32 v) { memcpy(P(a), &v, 4); }
static inline void W16(u32 a, u32 v) { u16 x = (u16)v; memcpy(P(a), &x, 2); }
static inline void W8(u32 a, u32 v) { *P(a) = (u8)v; }

/* --- flotantes --- */
static inline float F(u32 b) { float f; memcpy(&f, &b, 4); return f; }
static inline u32 FB(float f)
{
    u32 b;
    memcpy(&b, &f, 4);
    if ((b & 0x7F800000u) == 0x7F800000u && (b & 0x007FFFFFu))
        return 0x7FC00000u; /* DN: NaN por defecto */
    return b;
}
static inline float sqrt_f(float x) { return __builtin_sqrtf(x); }

/* vcmp: N Z C V como el ARM (menor 1000, igual 0110, mayor 0010, sin orden 0011) */
static inline void vcmp(CPU *c, float a, float b)
{
    if (a != a || b != b) { c->fn = 0; c->fz = 0; c->fc = 1; c->fv = 1; }
    else if (a < b) { c->fn = 1; c->fz = 0; c->fc = 0; c->fv = 0; }
    else if (a == b) { c->fn = 0; c->fz = 1; c->fc = 1; c->fv = 0; }
    else { c->fn = 0; c->fz = 0; c->fc = 1; c->fv = 0; }
}

/* vcvt.s32.f32 (hacia cero, saturando, NaN -> 0) */
static inline u32 f2s(float f)
{
    if (f != f) return 0;
    if (f >= 2147483648.0f) return 0x7FFFFFFFu;
    if (f <= -2147483648.0f) return 0x80000000u;
    return (u32)(s32)f;
}
static inline u32 f2u(float f)
{
    if (f != f || f <= 0.0f) return 0;
    if (f >= 4294967296.0f) return 0xFFFFFFFFu;
    return (u32)f;
}

/* --- desplazador de ARM: valor y acarreo de salida (co) --- */
static inline u32 lsl_i(u32 v, u32 n, u32 cin, u32 *co)
{
    if (n == 0) { *co = cin; return v; }
    *co = (v >> (32 - n)) & 1; return v << n;
}
static inline u32 lsr_i(u32 v, u32 n, u32 *co) /* n en 1..32 */
{
    if (n == 32) { *co = v >> 31; return 0; }
    *co = (v >> (n - 1)) & 1; return v >> n;
}
static inline u32 asr_i(u32 v, u32 n, u32 *co) /* n en 1..32 */
{
    if (n >= 32) { *co = v >> 31; return (u32)((s32)v >> 31); }
    *co = (v >> (n - 1)) & 1; return (u32)((s32)v >> n);
}
static inline u32 ror_i(u32 v, u32 n, u32 *co) /* n en 1..31 */
{
    u32 r = (v >> n) | (v << (32 - n));
    *co = r >> 31; return r;
}
static inline u32 rrx(u32 v, u32 cin, u32 *co) { *co = v & 1; return (v >> 1) | (cin << 31); }
/* por registro: se usa el byte bajo */
static inline u32 lsl_r(u32 v, u32 s, u32 cin, u32 *co)
{
    s &= 0xFF;
    if (s == 0) { *co = cin; return v; }
    if (s < 32) { *co = (v >> (32 - s)) & 1; return v << s; }
    *co = (s == 32) ? (v & 1) : 0; return 0;
}
static inline u32 lsr_r(u32 v, u32 s, u32 cin, u32 *co)
{
    s &= 0xFF;
    if (s == 0) { *co = cin; return v; }
    if (s < 32) { *co = (v >> (s - 1)) & 1; return v >> s; }
    *co = (s == 32) ? (v >> 31) : 0; return 0;
}
static inline u32 asr_r(u32 v, u32 s, u32 cin, u32 *co)
{
    s &= 0xFF;
    if (s == 0) { *co = cin; return v; }
    if (s < 32) { *co = (v >> (s - 1)) & 1; return (u32)((s32)v >> s); }
    *co = v >> 31; return (u32)((s32)v >> 31);
}
static inline u32 ror_r(u32 v, u32 s, u32 cin, u32 *co)
{
    s &= 0xFF;
    if (s == 0) { *co = cin; return v; }
    s &= 31;
    if (s == 0) { *co = v >> 31; return v; }
    u32 r = (v >> s) | (v << (32 - s));
    *co = r >> 31; return r;
}

/* --- aritmetica con banderas --- */
static inline u32 add_f(CPU *c, u32 a, u32 b, u32 cin)
{
    u64 r = (u64)a + b + cin;
    u32 res = (u32)r;
    c->n = res >> 31; c->z = res == 0; c->c = (u32)(r >> 32);
    c->v = ((~(a ^ b) & (a ^ res)) >> 31) & 1;
    return res;
}
static inline u32 sub_f(CPU *c, u32 a, u32 b, u32 cin) /* a - b - !cin */
{
    return add_f(c, a, ~b, cin);
}
static inline void nz(CPU *c, u32 r) { c->n = r >> 31; c->z = r == 0; }

static inline u32 clz32(u32 v) { return v ? (u32)__builtin_clz(v) : 32; }

/* --- doble precision: d[k] = s[2k] (bajo) + s[2k+1] (alto), como en VFPv2 --- */
static inline double DF(u32 lo, u32 hi)
{
    u64 b = ((u64)hi << 32) | lo;
    double d;
    memcpy(&d, &b, 8);
    return d;
}
static inline u64 DB(double d)
{
    u64 b;
    memcpy(&b, &d, 8);
    if (((b >> 52) & 0x7FF) == 0x7FF && (b & 0xFFFFFFFFFFFFFull))
        return 0x7FF8000000000000ull; /* DN */
    return b;
}
#define GD(k) DF(c->s[2 * (k)], c->s[2 * (k) + 1])
#define SD(k, bits) do { u64 b_ = (bits); c->s[2 * (k)] = (u32)b_; c->s[2 * (k) + 1] = (u32)(b_ >> 32); } while (0)
static inline void vcmpd(CPU *c, double a, double b)
{
    if (a != a || b != b) { c->fn = 0; c->fz = 0; c->fc = 1; c->fv = 1; }
    else if (a < b) { c->fn = 1; c->fz = 0; c->fc = 0; c->fv = 0; }
    else if (a == b) { c->fn = 0; c->fz = 1; c->fc = 1; c->fv = 0; }
    else { c->fn = 0; c->fz = 0; c->fc = 1; c->fv = 0; }
}
static inline u32 d2s(double f)
{
    if (f != f) return 0;
    if (f >= 2147483648.0) return 0x7FFFFFFFu;
    if (f <= -2147483649.0) return 0x80000000u;
    return (u32)(s32)f;
}
static inline u32 d2u(double f)
{
    if (f != f || f <= -1.0) return 0;
    if (f >= 4294967296.0) return 0xFFFFFFFFu;
    return (u32)f;
}

/* --- saturacion y medias palabras --- */
static inline u32 usat_n(s32 v, u32 n)
{
    s64 tope = ((s64)1 << n) - 1;
    return v < 0 ? 0 : ((s64)v > tope ? (u32)tope : (u32)v);
}
static inline u32 ssat_n(s32 v, u32 n)
{
    s64 lo = -((s64)1 << (n - 1)), hi = ((s64)1 << (n - 1)) - 1;
    return (u32)(s32)(v < lo ? lo : (v > hi ? hi : v));
}
static inline u32 sat16(s32 v) { return (u32)(u16)(s16)(v < -32768 ? -32768 : (v > 32767 ? 32767 : v)); }
static inline s32 lo16(u32 v) { return (s16)(v & 0xFFFF); }
static inline s32 hi16(u32 v) { return (s16)(v >> 16); }
static inline u32 par16(u32 lo, u32 hi) { return (lo & 0xFFFF) | (hi << 16); }
/* rotacion sin acarreo (indices 'ror #n' y la rotacion de las extensiones) */
static inline u32 ror32(u32 v, u32 n) { n &= 31; return n ? (v >> n) | (v << (32 - n)) : v; }
/* extension de los bytes 0 y 2 a dos medias palabras */
static inline u32 uxtb16(u32 v) { return v & 0x00FF00FFu; }
static inline u32 sxtb16(u32 v) { return par16((u32)(s32)(s8)v, (u32)(s32)(s8)(v >> 16)); }
static inline u32 uxtab16(u32 a, u32 v) { return par16((a & 0xFFFF) + (v & 0xFF), (a >> 16) + ((v >> 16) & 0xFF)); }
static inline u32 sxtab16(u32 a, u32 v) { return par16((a & 0xFFFF) + (u32)(s32)(s8)v, (a >> 16) + (u32)(s32)(s8)(v >> 16)); }
/* SIMD de 8 bits a la mitad: (a+b)>>1 y (a-b)>>1 por byte, sin perder el bit 9 */
static inline u32 uhadd8(u32 a, u32 b) { return (a & b) + (((a ^ b) >> 1) & 0x7F7F7F7Fu); }
static inline u32 uhsub8(u32 a, u32 b)
{
    u32 r = 0;
    for (int k = 0; k < 32; k += 8) r |= ((u32)(((s32)((a >> k) & 0xFF) - (s32)((b >> k) & 0xFF)) >> 1) & 0xFF) << k;
    return r;
}

#endif
