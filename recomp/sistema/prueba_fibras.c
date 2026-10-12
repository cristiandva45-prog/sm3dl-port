/* Prueba de la capa de sistema con hilos falsos (sin el juego): cambio de hilo en WaitSynchronizationN,
 * desalojo por prioridad al senalar, espera al fin de un hilo, timeout y address arbiter.
 * Cada "funcion del juego" es C escrito como lo emite el recompilador: trabaja sobre el CPU y hace svc.
 *
 * Compilar y correr (desde la raiz del port):
 *   py -m ziglang cc -target x86_64-windows-gnu -O2 -Irecomp\runtime recomp\sistema\sistema.c recomp\sistema\prueba_fibras.c -o recomp\build\prueba_fibras.exe
 *   recomp\build\prueba_fibras.exe
 */
#include <stdio.h>
#include <string.h>
#include "sistema.h"

u8 *rt_pagina[1u << 20];
void rt_externo(CPU *c, u32 addr) { (void)c; fprintf(stderr, "rt_externo 0x%08X\n", addr); }
void rt_desconocida(CPU *c, u32 addr) { (void)c; fprintf(stderr, "rt_desconocida 0x%08X\n", addr); }

static char g_log[256];
static void anota(const char *s) { strcat(g_log, s); strcat(g_log, " "); printf("  hilo %u: %s\n", sis_hilo_actual_id(), s); }

#define DATOS 0x00500000u   /* pagina de datos del juego falso */
#define VAR_EV  (DATOS + 0x00)
#define VAR_ARB (DATOS + 0x04)
#define VAR_CNT (DATOS + 0x08)
#define LISTA   (DATOS + 0x40)

static void svc(CPU *c, u32 n) { sis_svc_num(c, n, 0x00F00000u + n); }

static void espera_uno(CPU *c, u32 handle, s64 ns)
{
    W32(LISTA, handle);
    c->r[0] = (u32)ns; c->r[1] = LISTA; c->r[2] = 1; c->r[3] = 0; c->r[4] = (u32)((u64)ns >> 32);
    svc(c, 0x25);
}

/* hilo B (prio 0x31, menos urgente que el principal) */
static void f_hilo_b(CPU *c)
{
    anota("B1");
    c->r[0] = R32(VAR_EV); svc(c, 0x18);            /* SignalEvent: despierta al principal, que es mas urgente -> desaloja */
    anota("B2");
    /* vuelve: equivale a ExitThread */
}

/* hilo C: senala por el arbitro */
static void f_hilo_c(CPU *c)
{
    anota("C1");
    W32(VAR_CNT, 1);
    c->r[0] = R32(VAR_ARB); c->r[1] = VAR_CNT; c->r[2] = 0; c->r[3] = 1; svc(c, 0x22);  /* Signal a 1 hilo */
    anota("C2");
}

static int g_fallos;
static void exige(int ok, const char *que) { if (!ok) { printf("  FALLO: %s\n", que); g_fallos++; } }

/* hilo principal (prio 0x30) */
static void f_principal(CPU *c)
{
    anota("M1");
    c->r[1] = 0; svc(c, 0x17);                       /* CreateEvent oneshot */
    exige(c->r[0] == RES_OK, "CreateEvent");
    W32(VAR_EV, c->r[1]);
    c->r[0] = 0x31; c->r[1] = 0x00002000u; c->r[2] = 0; c->r[3] = 0x0FF00000u; c->r[4] = 0xFFFFFFFEu;
    svc(c, 0x08);                                    /* CreateThread B: menos urgente, no corre todavia */
    u32 hb = c->r[1];
    anota("M2");
    espera_uno(c, R32(VAR_EV), -1);                  /* bloquea -> corre B */
    exige(c->r[0] == RES_OK && c->r[1] == 0, "Wait del evento devuelve OK, indice 0");
    anota("M3");
    espera_uno(c, hb, -1);                           /* esperar a que B termine -> B sigue tras su SignalEvent */
    exige(c->r[0] == RES_OK, "Wait del hilo B");
    anota("M4");
    espera_uno(c, R32(VAR_EV), 2000000);             /* el evento oneshot ya se consumio: timeout de 2 ms */
    exige(c->r[0] == RES_TIMEOUT, "timeout devuelve 0x09401BFE");
    anota("M5");
    svc(c, 0x21);                                    /* CreateAddressArbiter */
    W32(VAR_ARB, c->r[1]);
    W32(VAR_CNT, 0);
    c->r[0] = 0x31; c->r[1] = 0x00003000u; c->r[2] = 0; c->r[3] = 0x0FE00000u; c->r[4] = 0xFFFFFFFEu;
    svc(c, 0x08);                                    /* CreateThread C */
    c->r[0] = R32(VAR_ARB); c->r[1] = VAR_CNT; c->r[2] = 1; c->r[3] = 1; svc(c, 0x22);  /* WaitIfLessThan(*cnt < 1) */
    exige(R32(VAR_CNT) == 1, "el arbitro desperto con el contador en 1");
    anota("M6");
    svc(c, 0x03);                                    /* ExitProcess (C nunca llega a C2) */
}

void rt_llamar(CPU *c, u32 addr)
{
    switch (addr) {
    case 0x00001000u: f_principal(c); return;
    case 0x00002000u: f_hilo_b(c); return;
    case 0x00003000u: f_hilo_c(c); return;
    default: rt_externo(c, addr); return;
    }
}

int main(void)
{
    sis_iniciar();
    sis_mapear(DATOS, 0x1000);
    sis_mapear(0x0FD00000u, 0x00300000u);            /* pilas */
    printf("prueba de fibras:\n");
    sis_correr(0x00001000u, 0x10000000u, 0x30);
    const char *esperado = "M1 M2 B1 M3 B2 M4 M5 C1 M6 ";
    exige(strcmp(g_log, esperado) == 0, "orden de ejecucion");
    printf("orden: %s\nesperado: %s\n%s (%d fallos)\n", g_log, esperado, g_fallos ? "MAL" : "OK", g_fallos);
    return g_fallos ? 1 : 0;
}
