/* Capa de sistema del port nativo (kernel Horizon + servicios, HLE). Ver sistema.h y DISENO.md.
 * Escrito desde cero; Azahar se uso solo como referencia de la semantica de cada svc. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sistema.h"

int sis_traza = 0;
u32 sis_comandos_vistos[SRV_CUENTA];

/* ======================================================================= memoria */

u8 *sis_mapear(u32 addr, u32 tam)
{
    u32 ini = addr & ~0xFFFu, fin = (addr + tam + 0xFFFu) & ~0xFFFu;
    u8 *host = VirtualAlloc(NULL, fin - ini, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!host) { fprintf(stderr, "[sis] sin memoria para 0x%08X (+0x%X)\n", addr, tam); abort(); }
    sis_mapear_host(ini, fin - ini, host);
    return host + (addr - ini);
}

void sis_mapear_host(u32 addr, u32 tam, u8 *host)
{
    for (u32 o = 0; o < tam; o += 0x1000)
        rt_pagina[(addr + o) >> 12] = host + o;
}

int sis_mapeada(u32 addr) { return rt_pagina[addr >> 12] != NULL; }

/* asignadores "de tope" de cada region: el juego nunca devuelve el heap (no hay FREE que importe) */
static u32 g_heap_sig = SIS_HEAP, g_lineal_sig = SIS_LINEAL, g_shm_sig = SIS_SHM + 0x01000000u;

/* ======================================================================= objetos y handles */

typedef enum { OB_HILO = 1, OB_EVENTO, OB_MUTEX, OB_ARBITRO, OB_SESION, OB_BLOQUE, OB_LIMITE } TipoObj;

typedef struct Hilo Hilo;
typedef struct Obj {
    TipoObj tipo;
    int refs;
    /* evento */
    int senal, reinicio;      /* reinicio: 0 oneshot, 1 sticky, 2 pulse */
    /* mutex */
    Hilo *dueno; u32 cuenta;
    /* sesion IPC */
    IpcSesion *ses;
    /* bloque de memoria compartida: paginas del anfitrion */
    u8 *host; u32 tam;
    /* hilo */
    Hilo *hilo;
} Obj;

#define MAX_HANDLES 4096
static Obj *g_handles[MAX_HANDLES];
#define HANDLE_BASE 0x00010000u

static u32 nuevo_handle(Obj *o)
{
    for (u32 i = 1; i < MAX_HANDLES; i++)
        if (!g_handles[i]) { g_handles[i] = o; o->refs++; return HANDLE_BASE + i; }
    fprintf(stderr, "[sis] tabla de handles llena\n");
    abort();
}

static Obj *nuevo_obj(TipoObj t)
{
    Obj *o = calloc(1, sizeof *o);
    o->tipo = t;
    return o;
}

/* ======================================================================= hilos y planificador */

typedef enum { H_LISTO, H_CORRIENDO, H_ESPERA, H_MUERTO } EstadoHilo;
typedef enum { E_NADA, E_SYNC, E_ARBITRO, E_DORMIR } TipoEspera;

struct Hilo {
    CPU cpu;
    void *fibra;
    u32 id, prio, entrada, slot_tls;
    u64 orden;                 /* FIFO entre hilos de igual prioridad */
    EstadoHilo estado;
    Obj *obj;                  /* el objeto "hilo" (se senala al morir) */
    /* espera */
    TipoEspera espera;
    Obj *esperando[64]; u32 n_esperando; int esperar_todos;
    u32 arb_addr;
    u64 limite_ns;             /* UINT64_MAX = sin limite */
    Hilo *sig;
};

static Hilo *g_hilos;          /* todos (lista enlazada) */
static Hilo *g_actual;
static void *g_fibra_plan;
static u64 g_orden;
static u32 g_sig_id = 1;
static int g_salir;
static u32 g_slots_tls;

u32 sis_hilo_actual_id(void) { return g_actual ? g_actual->id : 0; }
CPU *sis_hilo_actual_cpu(void) { return g_actual ? &g_actual->cpu : 0; }

/* SM3DL_TURBO=1 (7 oct): reloj VIRTUAL para pruebas. Cuando ningun hilo puede correr, en vez de dormir hasta el
 * proximo evento (vblank, DSP, mando, limite de espera) el reloj salta hasta el: el juego corre tan rapido como
 * da el PC y ve el mismo tiempo que en tiempo real (vblanks, ticks y DSP salen del mismo reloj). Audio acelerado. */
static u64 g_desfase_ns;
static int g_turbo = -1;
static u64 ahora_ns(void)
{
    static LARGE_INTEGER f;
    LARGE_INTEGER t;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t);
    return (u64)((double)t.QuadPart * 1e9 / (double)f.QuadPart) + g_desfase_ns;
}

static void poner_listo(Hilo *h)
{
    h->estado = H_LISTO;
    h->espera = E_NADA;
    h->orden = g_orden++;
}

/* vuelve al planificador; regresa cuando este hilo vuelve a correr */
static void ceder(void)
{
    SwitchToFiber(g_fibra_plan);
}

/* tras despertar a alguien: si hay un hilo listo MAS urgente que el actual, el actual le cede (como Horizon) */
static void quiza_ceder(void)
{
#ifdef SABOTAJE_SIN_DESALOJO
    return;
#endif
    for (Hilo *h = g_hilos; h; h = h->sig)
        if (h->estado == H_LISTO && h->prio < g_actual->prio) {
            poner_listo(g_actual);
            ceder();
            return;
        }
}

static int puede_tomar(Obj *o, Hilo *h)
{
    switch (o->tipo) {
    case OB_EVENTO: return o->senal;
    case OB_MUTEX: return o->dueno == NULL || o->dueno == h;
    case OB_HILO: return o->hilo->estado == H_MUERTO;
    default: return 0;
    }
}

static void tomar(Obj *o, Hilo *h)
{
    if (o->tipo == OB_EVENTO && o->reinicio == 0) o->senal = 0;
    if (o->tipo == OB_MUTEX) { o->dueno = h; o->cuenta++; }
}

/* intenta completar la espera de h; devuelve 1 si quedo listo */
static int resolver_sync(Hilo *h)
{
    if (h->esperar_todos) {
        for (u32 i = 0; i < h->n_esperando; i++)
            if (!puede_tomar(h->esperando[i], h)) return 0;
        for (u32 i = 0; i < h->n_esperando; i++) tomar(h->esperando[i], h);
        h->cpu.r[1] = 0;
    } else {
        u32 i;
        for (i = 0; i < h->n_esperando; i++)
            if (puede_tomar(h->esperando[i], h)) break;
        if (i == h->n_esperando) return 0;
        tomar(h->esperando[i], h);
        h->cpu.r[1] = i;
    }
    h->cpu.r[0] = RES_OK;
    poner_listo(h);
    return 1;
}

/* algo se senalo: revisar a todos los que esperan objetos */
static void despertar_esperas(void)
{
    for (Hilo *h = g_hilos; h; h = h->sig)
        if (h->estado == H_ESPERA && h->espera == E_SYNC) resolver_sync(h);
    /* los eventos "pulse" solo despiertan a quien ya esperaba */
    for (u32 i = 1; i < MAX_HANDLES; i++)
        if (g_handles[i] && g_handles[i]->tipo == OB_EVENTO && g_handles[i]->reinicio == 2) g_handles[i]->senal = 0;
}

static void revisar_limites(u64 t)
{
    for (Hilo *h = g_hilos; h; h = h->sig)
        if (h->estado == H_ESPERA && h->limite_ns <= t) {
            h->cpu.r[0] = h->espera == E_DORMIR ? RES_OK : RES_TIMEOUT;
#ifdef SABOTAJE_TIMEOUT
            h->cpu.r[0] = RES_OK;
#endif
            if (h->espera == E_SYNC) h->cpu.r[1] = 0xFFFFFFFFu;
            poner_listo(h);
        }
}

static void esperar(TipoEspera tipo, s64 ns)
{
    g_actual->estado = H_ESPERA;
    g_actual->espera = tipo;
    g_actual->limite_ns = ns < 0 ? UINT64_MAX : ahora_ns() + (u64)ns;
    ceder();
}

static void WINAPI fibra_de_hilo(void *p);

static Hilo *crear_hilo(u32 entrada, u32 arg, u32 pila, u32 prio)
{
    Hilo *h = calloc(1, sizeof *h);
    h->id = g_sig_id++;
    h->prio = prio;
    h->entrada = entrada;
    h->slot_tls = g_slots_tls++;
    h->cpu.r[0] = arg;
    h->cpu.r[13] = pila;
    h->cpu.r[14] = 0;                       /* volver de la entrada = ExitThread */
    h->cpu.tls = SIS_TLS + h->slot_tls * SIS_TLS_TAM;
    h->cpu.fpscr = 0x03000000u;             /* lo que el juego pone en 0x105208; se fija por si un hilo corre antes */
    h->limite_ns = UINT64_MAX;
    h->obj = nuevo_obj(OB_HILO);
    h->obj->hilo = h;
    /* 16 MB reservados: el codigo recompilado anida llamadas nativas y algunas funciones tienen marcos grandes */
    h->fibra = CreateFiberEx(64 * 1024, 16u * 1024 * 1024, 0, fibra_de_hilo, h);
    if (!h->fibra) { fprintf(stderr, "[sis] CreateFiberEx fallo (%lu)\n", GetLastError()); abort(); }
    h->sig = g_hilos;
    g_hilos = h;
    poner_listo(h);
    return h;
}

static void terminar_hilo_actual(void)
{
    g_actual->estado = H_MUERTO;
    despertar_esperas();
    for (;;) ceder();                       /* el planificador borra la fibra; esto no vuelve */
}

static void WINAPI fibra_de_hilo(void *p)
{
    Hilo *h = p;
    rt_llamar(&h->cpu, h->entrada);
    terminar_hilo_actual();
}

static Hilo *elegir(void)
{
    Hilo *mejor = NULL;
    for (Hilo *h = g_hilos; h; h = h->sig)
        if (h->estado == H_LISTO && (!mejor || h->prio < mejor->prio || (h->prio == mejor->prio && h->orden < mejor->orden)))
            mejor = h;
    return mejor;
}

static void listar_bloqueados(void)
{
    for (Hilo *h = g_hilos; h; h = h->sig)
        if (h->estado == H_ESPERA)
            fprintf(stderr, "[sis]   hilo %u (prio 0x%X) espera tipo %d, %u objetos, arb 0x%08X\n",
                    h->id, h->prio, h->espera, h->n_esperando, h->arb_addr);
}

/* eventos periodicos del anfitrion */
static struct { void (*f)(void); u64 periodo, prox; } g_per[8];
static int g_n_per;

int sis_periodico(void (*f)(void), u64 periodo_ns)
{
    if (g_n_per == 8 || !f || !periodo_ns) return -1;
    g_per[g_n_per].f = f; g_per[g_n_per].periodo = periodo_ns; g_per[g_n_per].prox = 0;
    g_n_per++;
    return 0;
}

/* corre los que tocan; devuelve el proximo instante (UINT64_MAX si no hay) */
static u64 correr_periodicos(u64 t)
{
    u64 prox = UINT64_MAX;
    int alguno = 0;
    for (int i = 0; i < g_n_per; i++) {
        if (!g_per[i].prox) g_per[i].prox = t + g_per[i].periodo;
        /* atrasado: recuperar hasta 8 periodos (el DSP de 4,9 ms pierde ticks si el sueno se pasa); mas atras que
           eso, resincronizar en vez de soltar una rafaga (agente S, 9 oct) */
        for (int k = 0; t >= g_per[i].prox && k < 8; k++) {
            g_per[i].f();
            alguno = 1;
            g_per[i].prox += g_per[i].periodo;
        }
        if (g_per[i].prox <= t) g_per[i].prox = t + g_per[i].periodo;
        if (g_per[i].prox < prox) prox = g_per[i].prox;
    }
    if (alguno) despertar_esperas();
    return prox;
}

/* Sleep(4) dura ~15,6 ms en Windows sin timeBeginPeriod: temporizador de alta resolucion (Windows 10 1803+), sin winmm */
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
static HANDLE g_temporizador;
static void dormir_ns(u64 ns)
{
    if (!g_temporizador) {
        g_temporizador = CreateWaitableTimerExW(NULL, NULL, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
        if (!g_temporizador) g_temporizador = INVALID_HANDLE_VALUE;
    }
#ifndef SABOTAJE_SUENO_GRUESO
    if (g_temporizador != INVALID_HANDLE_VALUE) {
        LARGE_INTEGER v; v.QuadPart = -(LONGLONG)(ns / 100u);   /* relativo, en unidades de 100 ns */
        if (v.QuadPart == 0) v.QuadPart = -1;
        if (SetWaitableTimer(g_temporizador, &v, 0, NULL, NULL, FALSE)) { WaitForSingleObject(g_temporizador, INFINITE); return; }
    }
#endif
    Sleep((DWORD)(ns / 1000000u));
}

void sis_correr(u32 entrada, u32 pila_tope, u32 prioridad)
{
    g_fibra_plan = ConvertThreadToFiber(NULL);
    if (!g_fibra_plan) g_fibra_plan = GetCurrentFiber();
    crear_hilo(entrada, 0, pila_tope, prioridad);
    while (!g_salir) {
        Hilo *h = elegir();
        if (!h) {
            u64 prox = correr_periodicos(ahora_ns());
            if (elegir()) continue;
            for (Hilo *x = g_hilos; x; x = x->sig)
                if (x->estado == H_ESPERA && x->limite_ns < prox) prox = x->limite_ns;
            if (prox == UINT64_MAX) {
                /* sin limites ni eventos periodicos del anfitrion (sis_periodico): nadie va a despertar */
                fprintf(stderr, "[sis] bloqueo total: ningun hilo listo ni con limite de tiempo\n");
                listar_bloqueados();
                break;
            }
            u64 t = ahora_ns();
            static u64 t0_real;
            if (g_turbo < 0) {
                /* SM3DL_TURBO=1: sin limite. SM3DL_TURBO=N (N>=2): como mucho N veces el tiempo real, para no
                   calentar el PC del duenno mientras trabaja (pidio cuidarlo el 7 oct). */
                const char *s = getenv("SM3DL_TURBO");
                g_turbo = s && *s && *s != '0' ? atoi(s) : 0;
                if (g_turbo < 0) g_turbo = 1;
                t0_real = ahora_ns();
                if (g_turbo) fprintf(stderr, "[sis] TURBO: reloj virtual, limite %s\n", g_turbo >= 2 ? s : "ninguno");
            }
            if (prox > t) {
                if (g_turbo) {
                    g_desfase_ns += prox - t;
                    if (g_turbo >= 2) {   /* virtual transcurrido <= N * real transcurrido */
                        u64 virt = prox - t0_real, real = prox - g_desfase_ns - t0_real;
                        u64 tope = real * (u64)g_turbo;
                        if (virt > tope) dormir_ns((virt - tope) / (u64)g_turbo);
                    }
                } else dormir_ns(prox - t);
            }
            revisar_limites(ahora_ns());
            continue;
        }
        g_actual = h;
        h->estado = H_CORRIENDO;
        SwitchToFiber(h->fibra);
        /* volvio: borrar los hilos muertos (nunca la fibra en la que se esta) */
        for (Hilo **pp = &g_hilos; *pp;) {
            Hilo *x = *pp;
            if (x->estado == H_MUERTO && x->fibra) { DeleteFiber(x->fibra); x->fibra = NULL; }
            pp = &x->sig;
        }
        revisar_limites(ahora_ns());
        correr_periodicos(ahora_ns());
    }
    g_actual = NULL;
}

/* ======================================================================= servicios (IPC): nombres y objetos para ipc.c */

static const char *NOMBRES_SRV[SRV_CUENTA] = {
    "?", "srv:", "err:f", "gsp::Gpu", "hid:USER", "fs:USER", "dsp::DSP", "APT:U", "cfg:u", "ndm:u", "mic:u", "cecd:u",
    "desconocido(0x3E3190)"
};

const char *sis_nombre_servicio(Servicio s) { return s < SRV_CUENTA ? NOMBRES_SRV[s] : "?"; }

Servicio sis_servicio_por_nombre(const char *n)
{
    for (int s = SRV_SRV; s < SRV_DESCONOCIDO_3E3190; s++)
        if (strcmp(n, NOMBRES_SRV[s]) == 0) return (Servicio)s;
    return SRV_NINGUNO;
}

static void despertar_esperas(void);
static Obj *obj_de(u32 h);

SisObj *sis_evento_nuevo(int reinicio) { Obj *o = nuevo_obj(OB_EVENTO); o->reinicio = reinicio; return o; }
SisObj *sis_mutex_nuevo(void) { return nuevo_obj(OB_MUTEX); }
SisObj *sis_bloque_nuevo(u32 tam, u8 **host)
{
    Obj *o = nuevo_obj(OB_BLOQUE);
    o->tam = (tam + 0xFFFu) & ~0xFFFu;
    o->host = VirtualAlloc(NULL, o->tam, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (host) *host = o->host;
    return o;
}
u32 sis_handle_nuevo(SisObj *o) { return nuevo_handle(o); }
void sis_handle_cerrar(u32 h)
{
    if (h >= HANDLE_BASE && h < HANDLE_BASE + MAX_HANDLES && g_handles[h - HANDLE_BASE]) {
        g_handles[h - HANDLE_BASE]->refs--;
        g_handles[h - HANDLE_BASE] = NULL;
    }
}
void sis_senalar(SisObj *o) { if (o && o->tipo == OB_EVENTO) { o->senal = 1; if (g_hilos) despertar_esperas(); } }
void sis_limpiar(SisObj *o) { if (o && o->tipo == OB_EVENTO) o->senal = 0; }
int sis_es_evento(SisObj *o) { return o && o->tipo == OB_EVENTO; }
static u64 ahora_ns(void);
u64 sis_ticks(void)
{
    u64 t = ahora_ns();
    return (t / 1000000000ull) * SIS_TICKS_SEG + (t % 1000000000ull) * SIS_TICKS_SEG / 1000000000ull;
}
void sis_senalar_handle(u32 h) { Obj *o = obj_de(h); if (o) sis_senalar(o); }
void sis_detener(const char *motivo) { fprintf(stderr, "[sis] detener: %s\n", motivo); g_salir = 1; }

SisObj *ipc_obj_sesion(IpcSesion *s)
{
    if (!s->obj) { Obj *o = nuevo_obj(OB_SESION); o->ses = s; s->obj = o; }
    return s->obj;
}

/* ======================================================================= svc */

static Obj *obj_de(u32 h)
{
    if (h == HANDLE_HILO_ACTUAL) return g_actual->obj;
    if (h < HANDLE_BASE || h >= HANDLE_BASE + MAX_HANDLES) return NULL;
    return g_handles[h - HANDLE_BASE];
}

SisObj *sis_obj_de_handle(u32 h) { return (g_actual || h != HANDLE_HILO_ACTUAL) ? obj_de(h) : NULL; }

static void leer_cadena(u32 addr, char *dst, u32 max)
{
    u32 i = 0;
    for (; i + 1 < max; i++) { dst[i] = (char)R8(addr + i); if (!dst[i]) break; }
    dst[i] = 0;
}

void sis_svc(CPU *c, u32 addr) { sis_svc_num(c, c->r[15], addr); }

void sis_svc_num(CPU *c, u32 num, u32 addr)
{
    u32 *r = c->r;
    if (sis_traza) {
        /* cada (svc, direccion) se registra a lo sumo 20 veces: un bucle de espera lleno 95 M de lineas en 60 s */
        static u32 vistos_dir[4096]; static u16 vistos_n[4096];
        u32 h = ((addr >> 2) ^ (num * 2654435761u)) & 4095;
        if (vistos_dir[h] != (addr ^ (num << 24))) { vistos_dir[h] = addr ^ (num << 24); vistos_n[h] = 0; }
        if (vistos_n[h] < 20)
            fprintf(stderr, "[svc] hilo %u 0x%02X en 0x%08X (r0=%08X r1=%08X r2=%08X r3=%08X)%s\n",
                    sis_hilo_actual_id(), num, addr, r[0], r[1], r[2], r[3],
                    vistos_n[h] == 19 ? " (se callan las repeticiones)" : "");
        if (vistos_n[h] < 0xFFFF) vistos_n[h]++;
    }
    switch (num) {
    case 0x01: {                              /* ControlMemory(op r0, addr0 r1, addr1 r2, size r3, perm r4) -> r1 */
        u32 op = r[0] & 0xFF, tam = (r[3] + 0xFFFu) & ~0xFFFu, a = r[1];
        if (op == 3) {                        /* COMMIT */
            if (r[0] & 0x10000u) { a = g_lineal_sig; g_lineal_sig += tam; }
            else if (!a) { a = g_heap_sig; }
            if (a == g_heap_sig) g_heap_sig += tam;
            sis_mapear(a, tam);
        }
        /* FREE (1) y los demas: se deja mapeado */
        r[0] = RES_OK; r[1] = a;
        return;
    }
    case 0x03:                                /* ExitProcess */
        g_salir = 1;
        for (;;) ceder();
    case 0x08: {                              /* CreateThread(prio r0, entry r1, arg r2, stack_top r3, core r4) -> r1 */
        Hilo *h = crear_hilo(r[1], r[2], r[3], r[0]);
        r[0] = RES_OK; r[1] = nuevo_handle(h->obj);
        quiza_ceder();
        return;
    }
    case 0x09:                                /* ExitThread */
        terminar_hilo_actual();
        return;
    case 0x0A: {                              /* SleepThread(ns r0:r1) */
        s64 ns = (s64)((u64)r[0] | ((u64)r[1] << 32));
        if (ns <= 0) { poner_listo(g_actual); ceder(); return; }
        esperar(E_DORMIR, ns);
        return;
    }
    case 0x0B: {                              /* GetThreadPriority(handle r1) -> r1 */
        Obj *o = obj_de(r[1]);
        if (!o || o->tipo != OB_HILO) { r[0] = RES_HANDLE_MALO; return; }
        r[0] = RES_OK; r[1] = o->hilo->prio;
        return;
    }
    case 0x0C: {                              /* SetThreadPriority(handle r0, prio r1) */
        Obj *o = obj_de(r[0]);
        if (!o || o->tipo != OB_HILO) { r[0] = RES_HANDLE_MALO; return; }
        o->hilo->prio = r[1];
        r[0] = RES_OK;
        quiza_ceder();
        return;
    }
    case 0x13: {                              /* CreateMutex(initial r1) -> r1 */
        Obj *o = nuevo_obj(OB_MUTEX);
        if (r[1]) { o->dueno = g_actual; o->cuenta = 1; }
        r[0] = RES_OK; r[1] = nuevo_handle(o);
        return;
    }
    case 0x14: {                              /* ReleaseMutex(handle r0) */
        Obj *o = obj_de(r[0]);
        if (!o || o->tipo != OB_MUTEX || o->dueno != g_actual) { r[0] = RES_HANDLE_MALO; return; }
        if (--o->cuenta == 0) { o->dueno = NULL; despertar_esperas(); }
        r[0] = RES_OK;
        quiza_ceder();
        return;
    }
    case 0x17: {                              /* CreateEvent(reset r1) -> r1 */
        Obj *o = nuevo_obj(OB_EVENTO);
        o->reinicio = (int)r[1];
        r[0] = RES_OK; r[1] = nuevo_handle(o);
        return;
    }
    case 0x18: case 0x19: {                   /* SignalEvent / ClearEvent (handle r0) */
        Obj *o = obj_de(r[0]);
        if (!o || o->tipo != OB_EVENTO) { r[0] = RES_HANDLE_MALO; return; }
        r[0] = RES_OK;
        if (num == 0x19) { o->senal = 0; return; }
        o->senal = 1;
        despertar_esperas();
        quiza_ceder();
        return;
    }
    case 0x1E: {                              /* CreateMemoryBlock(other r0, addr r1, size r2, my r3) -> r1 */
        Obj *o = nuevo_obj(OB_BLOQUE);
        o->tam = (r[2] + 0xFFFu) & ~0xFFFu;
        if (r[1]) o->host = P(r[1]);         /* memoria ya mapeada del juego: se comparte la misma */
        else o->host = VirtualAlloc(NULL, o->tam, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        r[0] = RES_OK; r[1] = nuevo_handle(o);
        return;
    }
    case 0x1F: {                              /* MapMemoryBlock(handle r0, addr r1, perm r2, other r3) */
        Obj *o = obj_de(r[0]);
        if (!o || o->tipo != OB_BLOQUE) { r[0] = RES_HANDLE_MALO; return; }
        u32 a = r[1];
        if (!a) { a = g_shm_sig; g_shm_sig += o->tam; }
        sis_mapear_host(a, o->tam, o->host);
        r[0] = RES_OK;
        return;
    }
    case 0x20: {                              /* UnmapMemoryBlock(handle r0, addr r1) */
        Obj *o = obj_de(r[0]);
        if (o && o->tipo == OB_BLOQUE)
            for (u32 k = 0; k < o->tam; k += 0x1000) rt_pagina[(r[1] + k) >> 12] = NULL;
        r[0] = RES_OK;
        return;
    }
    case 0x21: {                              /* CreateAddressArbiter -> r1 */
        r[0] = RES_OK; r[1] = nuevo_handle(nuevo_obj(OB_ARBITRO));
        return;
    }
    case 0x22: {                              /* ArbitrateAddress(h r0, addr r1, tipo r2, valor r3, ns r4:r5) */
        u32 a = r[1], tipo = r[2];
        s32 valor = (s32)r[3];
        s64 ns = (s64)((u64)r[4] | ((u64)r[5] << 32));
        r[0] = RES_OK;
        if (tipo == 0) {                      /* Signal: despierta a 'valor' hilos (los mas urgentes primero); <0 = todos */
            for (s32 k = 0; valor < 0 || k < valor; k++) {
                Hilo *m = NULL;
                for (Hilo *h = g_hilos; h; h = h->sig)
                    if (h->estado == H_ESPERA && h->espera == E_ARBITRO && h->arb_addr == a && (!m || h->prio < m->prio))
                        m = h;
                if (!m) break;
                m->cpu.r[0] = RES_OK;
                poner_listo(m);
            }
            quiza_ceder();
            return;
        }
        s32 actual = (s32)R32(a);
        if (actual >= valor) return;          /* no hay que esperar */
        if (tipo == 2 || tipo == 4) W32(a, (u32)(actual - 1));
        g_actual->arb_addr = a;
        esperar(E_ARBITRO, (tipo == 3 || tipo == 4) ? ns : -1);
        return;
    }
    case 0x23: {                              /* CloseHandle(r0) */
        if (r[0] >= HANDLE_BASE && r[0] < HANDLE_BASE + MAX_HANDLES) {
            Obj *o = g_handles[r[0] - HANDLE_BASE];
            g_handles[r[0] - HANDLE_BASE] = NULL;
            if (o) o->refs--;                 /* los objetos no se liberan: un hilo puede seguir esperandolos */
        }
        r[0] = RES_OK;
        return;
    }
    case 0x25: {                              /* WaitSynchronizationN(ns_lo r0, handles r1, n r2, todos r3, ns_hi r4) -> r1 */
        s64 ns = (s64)((u64)r[0] | ((u64)r[4] << 32));
        u32 n = r[2];
        if (n > 64) n = 64;
        g_actual->n_esperando = n;
        g_actual->esperar_todos = (int)(r[3] & 0xFF);
        for (u32 i = 0; i < n; i++) {
            Obj *o = obj_de(R32(r[1] + 4 * i));
            if (!o) { r[0] = RES_HANDLE_MALO; return; }
            g_actual->esperando[i] = o;
        }
        if (resolver_sync(g_actual)) { g_actual->estado = H_CORRIENDO; return; }
        if (ns == 0) { r[0] = RES_TIMEOUT; r[1] = 0xFFFFFFFFu; return; }
        esperar(E_SYNC, ns);                  /* resolver_sync / revisar_limites dejan r0, r1 */
        return;
    }
    case 0x27: {                              /* DuplicateHandle(r1) -> r1 */
        Obj *o = obj_de(r[1]);
        if (!o) { r[0] = RES_HANDLE_MALO; return; }
        r[0] = RES_OK; r[1] = nuevo_handle(o);
        return;
    }
    case 0x28: {                              /* GetSystemTick -> r0:r1 */
        u64 t = ahora_ns();
        u64 ticks = (t / 1000000000ull) * SIS_TICKS_SEG + (t % 1000000000ull) * SIS_TICKS_SEG / 1000000000ull;
        r[0] = (u32)ticks; r[1] = (u32)(ticks >> 32);
        return;
    }
    case 0x2D: {                              /* ConnectToPort(nombre r1) -> r1 */
        char nombre[16];
        leer_cadena(r[1], nombre, sizeof nombre);
        IpcSesion *s = (strcmp(nombre, "srv:") == 0 || strcmp(nombre, "err:f") == 0) ? ipc_abrir(nombre, sis_servicio_por_nombre(nombre)) : NULL;
        if (!s) { fprintf(stderr, "[svc] puerto desconocido \"%s\"\n", nombre); r[0] = RES_NO_HAY; return; }
        r[0] = RES_OK; r[1] = nuevo_handle(ipc_obj_sesion(s));
        return;
    }
    case 0x32: {                              /* SendSyncRequest(handle r0): comando en TLS+0x80 (ipc.c) */
        Obj *o = obj_de(r[0]);
        if (!o || o->tipo != OB_SESION) { r[0] = RES_HANDLE_MALO; return; }
        ipc_despachar(c, o->ses);
        r[0] = RES_OK;
        if (g_salir) for (;;) ceder();
        return;
    }
    case 0x35: r[0] = RES_OK; r[1] = 0x28; return;                       /* GetProcessId */
    case 0x37: {                                                          /* GetThreadId(handle r1) */
        Obj *o = obj_de(r[1]);
        r[0] = RES_OK; r[1] = (o && o->tipo == OB_HILO) ? o->hilo->id : 0;
        return;
    }
    case 0x38: r[0] = RES_OK; r[1] = nuevo_handle(nuevo_obj(OB_LIMITE)); return;  /* GetResourceLimit */
    case 0x3A:                                                            /* GetResourceLimitCurrentValues */
        for (u32 i = 0; i < r[3]; i++) { W32(r[0] + 8 * i, 0); W32(r[0] + 8 * i + 4, 0); }
        r[0] = RES_OK;
        return;
    case 0x3C:                                                            /* Break */
        fprintf(stderr, "[svc] Break(%u) en 0x%08X, hilo %u\n", r[0], addr, sis_hilo_actual_id());
        g_salir = 1;
        for (;;) ceder();
    default:
        fprintf(stderr, "[svc] 0x%02X sin implementar en 0x%08X\n", num, addr);
        r[0] = 0xF8C007F4u;
        return;
    }
}

/* ======================================================================= arranque */

void sis_iniciar(void)
{
    /* config memory: version del kernel y memoria de la aplicacion (lo lee el SDK al arrancar) */
    u8 *cfg = sis_mapear(SIS_CONFIG, 0x1000);
    cfg[0x02] = 0x22; cfg[0x03] = 2;                          /* KERNEL_VERSION 2.34 (firmware de 2011) */
    *(u32 *)(cfg + 0x40) = 64u * 1024 * 1024;                 /* APPMEMALLOC: 64 MB (3DS viejo) */
    /* pagina compartida: hora, 3D, bateria (se llenara cuando el juego la lea) */
    sis_mapear(SIS_PAGINA_COMP, 0x1000);
    /* TLS: 32 hilos de sobra */
    sis_mapear(SIS_TLS, 32 * SIS_TLS_TAM);
    sis_mapear(SIS_VRAM, 0x00600000u);
    /* servicios de base (srv:, err:f, fs:USER y los provisionales); hid/gsp reales se enchufan despues con ipc_registrar */
    ipc_registrar_base();
    sis_enchufar_externos();
}

/* La capa IPC vive en sus propios archivos. recomp/arranque/compilar.py solo enlaza sistema.c, asi que por defecto
 * entran aqui como una unidad unica. Si el enlazador los recibe por separado: compilar con -DSIS_IPC_SEPARADO. */
#ifndef SIS_IPC_SEPARADO
#include "ipc.c"
#include "srv.c"
#include "stubs.c"
#include "fs.c"
#include "enchufes.c"
#endif
