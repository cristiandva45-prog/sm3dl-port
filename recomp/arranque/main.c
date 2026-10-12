/* Primer arranque del port nativo: carga code.bin en la memoria del juego, prepara el hilo principal como lo deja
 * Horizon y corre la entrada recompilada (0x00100000) sobre la capa de sistema (recomp\sistema).
 * Registro: cada svc e IPC a stderr (sis_traza = 1). Bitacora en recomp\arranque\BITACORA.md.
 *
 * Paginas sin mapear: en vez de NULL apuntan a un ESPEJO de 4 GB reservado (sin memoria detras). Un acceso fuera de
 * mapa revienta en espejo + direccion_3DS, asi el manejador de excepciones dice la direccion exacta del juego. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <xmmintrin.h>
#include <dbghelp.h>
#include "sistema.h"

void rt_enganches(void (*externo)(CPU *, u32), void (*desconocida)(CPU *, u32), void (*svc)(CPU *, u32));

/* GPU dedicada en portatiles hibridos (Optimus / AMD): el driver busca estas exportaciones al cargar el exe.
 * compilar.py --gpu-integrada las quita -> exe de "PC minimo" que se queda en la Intel. */
#ifndef SM3DL_GPU_INTEGRADA
__declspec(dllexport) unsigned long NvOptimusEnablement = 1;
__declspec(dllexport) int AmdPowerXpressRequestHighPerformance = 1;
#endif

#define CODE_BASE  0x00100000u
#define BSS_INI    0x003F39D4u
#define BSS_TAM    0x0003D684u
#define PILA_TOPE  0x10000000u
#define PILA_TAM   0x00020000u   /* exheader */
#define PRIO_MAIN  0x30u         /* exheader */

static u8 *g_espejo;

static void externo(CPU *c, u32 addr)
{
    fprintf(stderr, "[arranque] rt_externo: salto a 0x%08X sin traducir (lr=0x%08X sp=0x%08X hilo %u)\n",
            addr, c->r[14], c->r[13], sis_hilo_actual_id());
    fflush(stderr);
    ExitProcess(2);
}

static void desconocida(CPU *c, u32 addr)
{
    fprintf(stderr, "[arranque] instruccion sin soporte en 0x%08X (lr=0x%08X hilo %u)\n", addr, c->r[14], sis_hilo_actual_id());
    fflush(stderr);
    ExitProcess(3);
}

static LONG WINAPI excepcion(EXCEPTION_POINTERS *e)
{
    DWORD cod = e->ExceptionRecord->ExceptionCode;
    if (cod != EXCEPTION_ACCESS_VIOLATION && cod != EXCEPTION_STACK_OVERFLOW && cod != EXCEPTION_INT_DIVIDE_BY_ZERO &&
        cod != EXCEPTION_ILLEGAL_INSTRUCTION)
        return EXCEPTION_CONTINUE_SEARCH;
    void *pc_host = e->ExceptionRecord->ExceptionAddress;
    HMODULE m = GetModuleHandleA(NULL);
    fprintf(stderr, "[arranque] EXCEPCION 0x%08lX en el anfitrion: rip = exe+0x%llX (hilo %u)\n", cod,
            (unsigned long long)((u8 *)pc_host - (u8 *)m), sis_hilo_actual_id());
    {   /* nombre de la funcion recompilada (f_XXXXXXXX = direccion del juego) desde el PDB */
        static char buf[sizeof(SYMBOL_INFO) + 256];
        SYMBOL_INFO *s = (SYMBOL_INFO *)buf;
        DWORD64 desp = 0;
        s->SizeOfStruct = sizeof(SYMBOL_INFO);
        s->MaxNameLen = 255;
        SymInitialize(GetCurrentProcess(), NULL, TRUE);
        if (SymFromAddr(GetCurrentProcess(), (DWORD64)(ULONG_PTR)pc_host, &desp, s))
            fprintf(stderr, "[arranque]   en %s+0x%llX\n", s->Name, (unsigned long long)desp);
    }
    if (cod == EXCEPTION_ACCESS_VIOLATION) {
        ULONG_PTR tipo = e->ExceptionRecord->ExceptionInformation[0];
        u8 *a = (u8 *)e->ExceptionRecord->ExceptionInformation[1];
        if (a >= g_espejo && a < g_espejo + 0x100000000ull)
            fprintf(stderr, "[arranque]   %s en direccion del 3DS SIN MAPEAR 0x%08llX\n", tipo ? "escritura" : "lectura",
                    (unsigned long long)(a - g_espejo));
        else
            fprintf(stderr, "[arranque]   %s en direccion del anfitrion %p\n", tipo ? "escritura" : "lectura", (void *)a);
    }
    {   /* registros del juego y posibles direcciones de vuelta en la pila (cadena de llamadas aproximada) */
        CPU *gc = sis_hilo_actual_cpu();
        if (gc) {
            fprintf(stderr, "[arranque]   juego:");
            for (int k = 0; k < 16; k++) fprintf(stderr, " r%d=%08X", k, gc->r[k]);
            fprintf(stderr, "\n[arranque]   pila (palabras en .text):");
            for (u32 k = 0, n = 0; k < 256 && n < 16; k++) {
                u32 a = gc->r[13] + 4 * k;
                u8 *pg = rt_pagina[a >> 12];
                if (!pg || IsBadReadPtr(pg + (a & 0xFFF), 4)) break;   /* fin de la pila mapeada */
                u32 v = *(u32 *)(pg + (a & 0xFFF));
                if (v >= 0x00100000u && v < 0x003A2000u) { fprintf(stderr, " [sp+%X]=%08X", 4 * k, v); n++; }
            }
            fprintf(stderr, "\n");
        }
    }
    {   /* pila del ANFITRION: cada 'bl' del juego es una llamada C, asi que es la cadena de llamadas del juego.
           Resolver offline: py simbolo.py sm3dl.exe <offsets> (linea de parte_NN.c -> f_XXXXXXXX) */
        void *fr[48];
        USHORT n = RtlCaptureStackBackTrace(0, 48, fr, NULL);
        fprintf(stderr, "[arranque]   pila anfitrion (exe+):");
        for (USHORT k = 0; k < n; k++) {
            unsigned long long o = (unsigned long long)((u8 *)fr[k] - (u8 *)m);
            if (o < 0x10000000ull) fprintf(stderr, " %llX", o);
        }
        fprintf(stderr, "\n");
    }
    fflush(stderr);
    ExitProcess(4);
    return EXCEPTION_CONTINUE_SEARCH;
}

static u8 *leer_archivo(const char *ruta, u32 *tam)
{
    FILE *f = fopen(ruta, "rb");
    if (!f) { fprintf(stderr, "[arranque] no abre %s\n", ruta); exit(1); }
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    u8 *b = malloc((size_t)n);
    if (fread(b, 1, (size_t)n, f) != (size_t)n) { fprintf(stderr, "[arranque] lectura corta\n"); exit(1); }
    fclose(f);
    *tam = (u32)n;
    return b;
}

/* SM3DL_SEGUNDOS=N: sale limpio a los N s vaciando stderr (con _IOLBF el CRT de Windows guarda todo en el
   bufer y matar el proceso perdia el log; 8 oct) */
static DWORD WINAPI cronometro(LPVOID p)
{
    Sleep((DWORD)(uintptr_t)p * 1000u);
    fprintf(stderr, "[arranque] fin por SM3DL_SEGUNDOS\n");
    fflush(stderr);
    fflush(stdout);
    ExitProcess(0);
}

int main(int argc, char **argv)
{
    const char *ruta_code = argc > 1 ? argv[1] : "extraido\\code.bin";
    setvbuf(stderr, NULL, _IOLBF, 1 << 16);
    { const char *s = getenv("SM3DL_SEGUNDOS");
      if (s && atoi(s) > 0) CreateThread(NULL, 0, cronometro, (LPVOID)(uintptr_t)atoi(s), 0, NULL); }
    AddVectoredExceptionHandler(1, excepcion);
    {   /* 8 oct: sin EcoQoS. Windows 11 manda a los nucleos de eficiencia y a reloj bajo a los procesos sin ventana
           visible o en segundo plano (ventana oculta de las mediciones, juego sin foco): el intermedio costaba ~2x */
        PROCESS_POWER_THROTTLING_STATE pt = { PROCESS_POWER_THROTTLING_CURRENT_VERSION,
                                              PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0 };
        if (!getenv("SM3DL_CON_ECOQOS"))
            SetProcessInformation(GetCurrentProcess(), ProcessPowerThrottling, &pt, sizeof pt);
    }

    /* espejo de 4 GB: toda pagina sin mapear cae aqui y revienta con su direccion */
    g_espejo = VirtualAlloc(NULL, 0x100000000ull, MEM_RESERVE, PAGE_NOACCESS);
    if (!g_espejo) { fprintf(stderr, "[arranque] no se pudo reservar el espejo\n"); return 1; }
    for (u32 i = 0; i < (1u << 20); i++) rt_pagina[i] = g_espejo + ((u64)i << 12);

    /* code.bin: .text .rodata .data contiguos desde 0x00100000 (escribible: el juego lee literales de .text) */
    u32 tam;
    u8 *code = leer_archivo(ruta_code, &tam);
    u32 fin = BSS_INI + BSS_TAM;
    u8 *img = sis_mapear(CODE_BASE, fin - CODE_BASE);   /* en cero: el .bss queda limpio */
    memcpy(img, code, tam < fin - CODE_BASE ? tam : fin - CODE_BASE);
    fprintf(stderr, "[arranque] code.bin %u bytes en 0x%08X..0x%08X (.bss en cero hasta 0x%08X)\n", tam, CODE_BASE,
            CODE_BASE + tam, fin);

    sis_iniciar();
    sis_mapear(PILA_TOPE - PILA_TAM, PILA_TAM);
    rt_enganches(externo, desconocida, sis_svc);
    sis_traza = getenv("SM3DL_SIN_TRAZA") ? 0 : 1;

    /* VFP del 3DS = FTZ + DAZ, redondeo al mas cercano. Las fibras comparten el MXCSR de este hilo. */
    _mm_setcsr((_mm_getcsr() & ~0x6000u) | 0x8040u);

    fprintf(stderr, "[arranque] entrada 0x%08X, pila 0x%08X, prio 0x%X\n", CODE_BASE, PILA_TOPE, PRIO_MAIN);
    sis_correr(CODE_BASE, PILA_TOPE, PRIO_MAIN);
    fprintf(stderr, "[arranque] sis_correr volvio\n");
    for (int s = 0; s < SRV_CUENTA; s++)
        if (sis_comandos_vistos[s]) fprintf(stderr, "[arranque]   %s: %u comandos\n", sis_nombre_servicio(s), sis_comandos_vistos[s]);
    return 0;
}
