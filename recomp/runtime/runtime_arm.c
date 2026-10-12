/* Runtime para verificar la recompilacion DENTRO del emulador (compilada para ARM, memoria identica).
 * Los enganches son funciones vacias: el verificador pone un hook en su direccion y las atiende en Python.
 * Se usa mientras Windows (Smart App Control) no deje correr el anfitrion nativo. */
#include "recomp.h"

u8 *rt_pagina[1u << 20]; /* no se usa con RECOMP_IDENTIDAD, pero recomp.h la declara */

__attribute__((noinline)) void rt_externo(CPU *c, u32 addr) { __asm__ volatile("" ::"r"(c), "r"(addr) : "memory"); }
__attribute__((noinline)) void rt_desconocida(CPU *c, u32 addr) { __asm__ volatile("" ::"r"(c), "r"(addr) : "memory"); }
__attribute__((noinline)) void rt_svc(CPU *c, u32 num, u32 addr) { __asm__ volatile("" ::"r"(c), "r"(num), "r"(addr) : "memory"); }

/* punto de entrada: el verificador arranca aqui con r0 = CPU*, r1 = direccion original */
void rt_entrada(CPU *c, u32 addr) { rt_llamar(c, addr); }

void *memcpy(void *d, const void *s, size_t n)
{
    u8 *a = d;
    const u8 *b = s;
    while (n--)
        *a++ = *b++;
    return d;
}

void *memset(void *d, int v, size_t n)
{
    u8 *a = d;
    while (n--)
        *a++ = (u8)v;
    return d;
}
