/* Runtime: memoria por paginas, puntos de enganche con el anfitrion y ejecucion con el FPU como el 3DS. */
#include "recomp.h"
#include <xmmintrin.h>
#include <pmmintrin.h>

#if defined(_WIN32) && defined(RECOMP_DLL)
#define EXPORTA __declspec(dllexport)
#else
#define EXPORTA __attribute__((visibility("default")))
#endif

u8 *rt_pagina[1u << 20];

typedef void (*FnExterno)(CPU *c, u32 addr);
static FnExterno g_externo;
static FnExterno g_desconocida;
static FnExterno g_svc;

EXPORTA void rt_mapear(u32 addr, u32 tam, u8 *host)
{
    for (u32 o = 0; o < tam; o += 0x1000)
        rt_pagina[(addr + o) >> 12] = host + o;
}

EXPORTA void rt_enganches(FnExterno externo, FnExterno desconocida, FnExterno svc)
{
    g_externo = externo;
    g_desconocida = desconocida;
    g_svc = svc;
}

void rt_externo(CPU *c, u32 addr) { g_externo(c, addr); }
void rt_desconocida(CPU *c, u32 addr) { g_desconocida(c, addr); }
void rt_svc(CPU *c, u32 num, u32 addr) { c->r[15] = num; g_svc(c, addr); }

/* Ejecuta la funcion recompilada de 'addr' con FTZ+DAZ (= RunFast del VFP del 3DS). */
EXPORTA void rt_ejecutar(CPU *c, u32 addr)
{
    unsigned int antes = _mm_getcsr();
    _mm_setcsr((antes & ~0x6000u) | 0x8040u); /* FTZ, DAZ, redondeo al mas cercano */
    rt_llamar(c, addr);
    _mm_setcsr(antes);
}
