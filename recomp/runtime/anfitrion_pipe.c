/* Anfitrion de pruebas: ejecutable que corre el codigo RECOMPILADO de forma nativa y habla con el
 * verificador de Python por stdin/stdout (Windows bloquea cargar DLLs propias con Smart App Control,
 * pero deja correr un .exe propio).
 *
 * Protocolo: mensajes {u32 op, u32 largo, datos}. Python -> exe:
 *   1 RESET            restaura code.bin y pone el monticulo de pruebas en cero
 *   2 WRITE addr+datos 3 READ addr,n (responde datos)   6 HASH addr,n (responde u64 FNV-1a)
 *   4 RUN func + CPU   ejecuta; durante la ejecucion el exe puede mandar EVENTO y esperar RESUME
 *   5 RESUME + CPU     (solo dentro de un evento)          7 SALIR
 * exe -> Python: 100+tipo EVENTO (addr + CPU; tipo 0 externo, 1 instruccion sin soporte, 2 svc),
 *                200 FIN (CPU), 201 DATOS, 202 HASH.
 */
#include "recomp.h"
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

void rt_mapear(u32 addr, u32 tam, u8 *host);
typedef void (*FnExterno)(CPU *c, u32 addr);
void rt_enganches(FnExterno externo, FnExterno desconocida, FnExterno svc);
void rt_ejecutar(CPU *c, u32 addr);

#define BASE 0x00100000u
#define FIN_JUEGO 0x00500000u
#define HEAP 0x08000000u
#define HEAP_T 0x00100000u

static u8 *g_juego, *g_juego0, *g_heap;
static u32 g_juego_t;

static void leer(void *p, size_t n)
{
    if (n && fread(p, 1, n, stdin) != n)
        exit(0); /* Python cerro la tuberia */
}
static void escribir(u32 op, const void *p, u32 n)
{
    fwrite(&op, 4, 1, stdout);
    fwrite(&n, 4, 1, stdout);
    if (n)
        fwrite(p, 1, n, stdout);
    fflush(stdout);
}

/* CRC32 (el mismo que zlib.crc32 de Python) para comparar memoria sin pasarla entera por la tuberia */
static u64 fnv(const u8 *p, u32 n)
{
    static u32 tabla[256];
    if (!tabla[1])
        for (u32 i = 0; i < 256; i++) {
            u32 c = i;
            for (int k = 0; k < 8; k++)
                c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            tabla[i] = c;
        }
    u32 crc = 0xFFFFFFFFu;
    for (u32 i = 0; i < n; i++)
        crc = tabla[(crc ^ p[i]) & 0xFF] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

static int atender(CPU *c); /* procesa comandos; devuelve 1 al recibir RESUME */

static void evento(CPU *c, u32 tipo, u32 addr)
{
    u8 buf[4 + sizeof(CPU)];
    memcpy(buf, &addr, 4);
    memcpy(buf + 4, c, sizeof(CPU));
    escribir(100 + tipo, buf, sizeof buf);
    atender(c);
}
static void ev_externo(CPU *c, u32 a) { evento(c, 0, a); }
static void ev_desconocida(CPU *c, u32 a) { evento(c, 1, a); }
static void ev_svc(CPU *c, u32 a) { evento(c, 2, a); }

static int atender(CPU *c)
{
    for (;;) {
        u32 op, n;
        leer(&op, 4);
        leer(&n, 4);
        u8 *d = n ? malloc(n) : NULL;
        leer(d, n);
        if (op == 1) {
            memcpy(g_juego, g_juego0, g_juego_t);
            memset(g_heap, 0, HEAP_T);
        } else if (op == 2) {
            u32 a;
            memcpy(&a, d, 4);
            for (u32 i = 0; i < n - 4; i++)
                *P(a + i) = d[4 + i];
        } else if (op == 3 || op == 6) {
            u32 a, k;
            memcpy(&a, d, 4);
            memcpy(&k, d + 4, 4);
            u8 *out = malloc(k ? k : 1);
            for (u32 i = 0; i < k; i++)
                out[i] = *P(a + i);
            if (op == 3) {
                escribir(201, out, k);
            } else {
                u64 h = fnv(out, k);
                escribir(202, &h, 8);
            }
            free(out);
        } else if (op == 4) {
            u32 f;
            CPU cpu;
            memcpy(&f, d, 4);
            memcpy(&cpu, d + 4, sizeof cpu);
            rt_ejecutar(&cpu, f);
            escribir(200, &cpu, sizeof cpu);
        } else if (op == 5) {
            memcpy(c, d, sizeof *c);
            free(d);
            return 1;
        } else if (op == 7) {
            exit(0);
        }
        free(d);
    }
}

int main(int argc, char **argv)
{
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    if (argc < 2) {
        fprintf(stderr, "uso: anfitrion code.bin\n");
        return 1;
    }
    g_juego_t = FIN_JUEGO - BASE;
    g_juego = calloc(1, g_juego_t);
    g_juego0 = calloc(1, g_juego_t);
    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "no abre %s\n", argv[1]);
        return 1;
    }
    fread(g_juego0, 1, g_juego_t, f);
    fclose(f);
    memcpy(g_juego, g_juego0, g_juego_t);
    g_heap = calloc(1, HEAP_T);
    rt_mapear(BASE, g_juego_t, g_juego);
    rt_mapear(HEAP, HEAP_T, g_heap);
    rt_mapear(0x0F000000u, 0x00100000u, calloc(1, 0x00100000u)); /* pila */
    rt_mapear(0x0E000000u, 0x1000u, calloc(1, 0x1000u));         /* espias */
    rt_mapear(0x0FFFF000u, 0x1000u, calloc(1, 0x1000u));         /* trampa */
    rt_enganches(ev_externo, ev_desconocida, ev_svc);
    CPU nada;
    atender(&nada);
    return 0;
}
