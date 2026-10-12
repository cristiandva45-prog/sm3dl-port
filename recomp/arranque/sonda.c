/* Sonda de POSICION DE MARIO (7 oct) para armar guiones con coordenadas en vez de a ciegas.
 * Gancho rt_sonda_llamar (lo emite partir.py al inicio de rt_llamar; lld COFF no tiene --wrap): con SM3DL_POS
 * cada salto indirecto pasa por aqui (una comparacion); sin SM3DL_POS el puntero queda en NULL. Cuando el
 * juego llama a PlayerActor_movement (0x00132A58, por vtable, una vez por cuadro) r0 = el jugador; su posicion
 * es getTrans (0x00280284): *(actor+0x14) + 4 -> 3 floats (HIPOTESIS de simbolos.txt, a confirmar viendo que
 * cambie al caminar/saltar).
 * SM3DL_POS=N: una linea "[pos] v<vblank> actor x y z" cada N vblanks (por defecto apagado). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sistema.h"
#include "gsp.h"

extern void (*rt_sonda_llamar)(CPU *c, u32 addr);

static int g_cada = -1;
static u32 g_ultimo_vb;

static const u8 *host(u32 a)
{
    u8 *p = rt_pagina[a >> 12];
    return p ? p + (a & 0xFFFu) : NULL;
}

static void sondear(u32 actor)
{
    u32 vb = gsp_estadistica()->vblanks;
    if (vb - g_ultimo_vb < (u32)g_cada) return;
    g_ultimo_vb = vb;
    const u8 *pk = host(actor + 0x14);
    if (!pk) return;
    u32 pose;
    memcpy(&pose, pk, 4);
    const u8 *t = pose ? host(pose + 4) : NULL;
    if (!t) return;
    float xyz[3];
    memcpy(xyz, t, sizeof xyz);
    fprintf(stderr, "[pos] v%u actor 0x%08X  %.1f %.1f %.1f\n", vb, actor, xyz[0], xyz[1], xyz[2]);
}

static void sonda(CPU *c, u32 addr)
{
    if (addr == 0x00132A58u) sondear(c->r[0]);
}

__attribute__((constructor)) static void sonda_iniciar(void)
{
    const char *s = getenv("SM3DL_POS");
    g_cada = s ? atoi(s) : 0;
    if (g_cada > 0) rt_sonda_llamar = sonda;
}
