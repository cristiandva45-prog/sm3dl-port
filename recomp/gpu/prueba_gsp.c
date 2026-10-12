/* Prueba del gsp::Gpu HLE. Memoria del juego falsa (tabla de paginas propia; el heap lineal en DOS bloques del
 * anfitrion NO contiguos para obligar a copiar por paginas). Las referencias son INDEPENDIENTES del codigo probado:
 * Morton sale de la tabla 8x8 dibujada (no del entrelazado de bits), los colores de valores calculados a mano.
 * Sale con codigo 1 si algo falla. probar_gsp.py la compila tambien con cada -DSABOTAJE=n y exige que falle. */
#include "gsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;

static int g_fallos, g_checks;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fallos++; printf("FALLA %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* ------------------------------------------------------------------ memoria falsa */
static u8 *g_pag[1u << 20];
static void mapear(u32 v, u32 tam) { u8 *h = calloc(1, tam); for (u32 o = 0; o < tam; o += 0x1000) g_pag[(v + o) >> 12] = h + o; }
static u8 *ptr(u32 v) { return g_pag[v >> 12] ? g_pag[v >> 12] + (v & 0xFFF) : NULL; }
static void poner32(u32 v, u32 x) { memcpy(ptr(v), &x, 4); }
static u32 leer32(u32 v) { u32 x; memcpy(&x, ptr(v), 4); return x; }

static u8 *g_shm;
static u32 crear_shm(u32 tam, u8 **host) { g_shm = calloc(1, tam); *host = g_shm; return 0x77; }
static u32 g_senales[0x10000];
static void senalar(u32 h) { g_senales[h & 0xFFFF]++; }
static GspPresentacion g_pres[2];
static u8 g_pres_img[2][400 * 240 * 4];
static int g_pres_n[2];
static void presentar(const GspPresentacion *p)
{
    g_pres[p->pantalla] = *p;
    g_pres_n[p->pantalla]++;
    if (p->rgba) memcpy(g_pres_img[p->pantalla], p->rgba, p->ancho * p->alto * 4);
}
static void silencio(const char *t) { (void)t; }
static u32 g_lista_dir, g_lista_tam, g_listas;
static void pica_falsa(u32 d, u32 t) { g_lista_dir = d; g_lista_tam = t; g_listas++; }

/* ------------------------------------------------------------------ Morton de referencia: la tabla dibujada */
static const u8 TABLA[8][8] = {   /* TABLA[y][x], y = 0 abajo */
    { 0,  1,  4,  5, 16, 17, 20, 21},
    { 2,  3,  6,  7, 18, 19, 22, 23},
    { 8,  9, 12, 13, 24, 25, 28, 29},
    {10, 11, 14, 15, 26, 27, 30, 31},
    {32, 33, 36, 37, 48, 49, 52, 53},
    {34, 35, 38, 39, 50, 51, 54, 55},
    {40, 41, 44, 45, 56, 57, 60, 61},
    {42, 43, 46, 47, 58, 59, 62, 63},
};
static u32 ref_morton(u32 x, u32 y, u32 ancho, u32 bpp)
{
    u32 mosaico = (y / 8) * (ancho / 8) + (x / 8);
    return (mosaico * 64 + TABLA[y % 8][x % 8]) * bpp;
}

/* ------------------------------------------------------------------ IPC */
static u32 g_cmd[0x80];
static void ipc(u32 sesion) { gsp_ipc(g_cmd, sesion); }

static void gx(u32 hilo, const u32 c[8])
{
    u8 *b = g_shm + 0x800 + hilo * 0x200;
    u32 pos = (b[0] + b[1]) % 15;
    memcpy(b + 0x20 + pos * 0x20, c, 32);
    b[1]++;
}
static void trigger(u32 sesion) { memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x000C0000; ipc(sesion); }
/* consume la cola de relevo del hilo como lo hace el juego; devuelve los ids en orden */
static int drenar(u32 hilo, u8 *ids)
{
    u8 *q = g_shm + hilo * 0x40;
    int n = 0;
    while (q[1]) { ids[n++] = q[0x0C + q[0]]; q[0] = (u8)((q[0] + 1) % 0x34); q[1]--; }
    return n;
}

int main(void)
{
    /* ============ 1. Morton contra la tabla dibujada */
    for (u32 y = 0; y < 16; y++)
        for (u32 x = 0; x < 24; x++)
            CHECK(gsp_offset_morton(x, y, 24, 3) == ref_morton(x, y, 24, 3), "morton (%u,%u)", x, y);

    /* ============ 2. pixeles (valores a mano) */
    {
        u8 c[4], p[4];
        const u8 rgba8[4] = {0x44, 0x33, 0x22, 0x11};
        gsp_decodificar_pixel(GSP_RGBA8, rgba8, c);
        CHECK(c[0] == 0x11 && c[1] == 0x22 && c[2] == 0x33 && c[3] == 0x44, "RGBA8 decod");
        u8 k1[4] = {0x80, 0x40, 0x20, 0xFF};
        gsp_codificar_pixel(GSP_RGB565, k1, p);
        CHECK((p[0] | p[1] << 8) == 0x8204, "RGB565 cod = 0x%04X", p[0] | p[1] << 8);
        u8 k2[4] = {255, 0, 255, 255};
        gsp_codificar_pixel(GSP_RGB5A1, k2, p);
        CHECK((p[0] | p[1] << 8) == 0xF83F, "RGB5A1 cod = 0x%04X", p[0] | p[1] << 8);
        u8 k3[4] = {0x12, 0x34, 0x56, 0x78};
        gsp_codificar_pixel(GSP_RGBA4, k3, p);
        CHECK((p[0] | p[1] << 8) == 0x1357, "RGBA4 cod = 0x%04X", p[0] | p[1] << 8);
        const u8 h[2] = {0x1F, 0xF8};   /* 0xF81F = magenta */
        gsp_decodificar_pixel(GSP_RGB565, h, c);
        CHECK(c[0] == 255 && c[1] == 0 && c[2] == 255 && c[3] == 255, "RGB565 decod");
        gsp_codificar_pixel(GSP_RGB8, k3, p);
        CHECK(p[0] == 0x56 && p[1] == 0x34 && p[2] == 0x12, "RGB8 cod (BGR)");
    }

    /* ============ 3. DisplayTransfer puro: mosaico RGBA8 16x16 -> lineal RGB8, con y sin volteo */
    {
        static u8 ent[16 * 16 * 4], sal[16 * 16 * 3];
        for (u32 y = 0; y < 16; y++)
            for (u32 x = 0; x < 16; x++) {
                u8 *q = ent + ref_morton(x, y, 16, 4);
                q[0] = 0xFF; q[1] = 0x5A; q[2] = (u8)y; q[3] = (u8)x;      /* A B G R */
            }
        for (int volteo = 0; volteo < 2; volteo++) {
            GspTransfer t = {16, 16, 16, 16, (u32)volteo | (GSP_RGBA8 << 8) | (GSP_RGB8 << 12)};
            memset(sal, 0, sizeof sal);
            CHECK(gsp_display_transfer(ent, sal, &t) == 0, "DT rgba8->rgb8");
            int malos = 0;
            for (u32 y = 0; y < 16; y++)
                for (u32 x = 0; x < 16; x++) {
                    u32 oy = volteo ? 15 - y : y;
                    u8 *q = sal + (x + oy * 16) * 3;
                    if (q[0] != 0x5A || q[1] != y || q[2] != x) malos++;
                }
            CHECK(malos == 0, "DT mosaico->lineal volteo=%d: %d pixeles mal", volteo, malos);
        }
        /* lineal -> mosaico RGB565 */
        static u8 lin[16 * 8 * 4], mos[16 * 8 * 2];
        for (u32 y = 0; y < 8; y++)
            for (u32 x = 0; x < 16; x++) {
                u8 *q = lin + (x + y * 16) * 4;
                q[0] = 0xFF; q[1] = 0; q[2] = (u8)(y * 32); q[3] = (u8)(x * 16);
            }
        GspTransfer t2 = {16, 8, 16, 8, 2u | (GSP_RGBA8 << 8) | (GSP_RGB565 << 12)};
        CHECK(gsp_display_transfer(lin, mos, &t2) == 0, "DT lineal->mosaico");
        int malos = 0;
        for (u32 y = 0; y < 8; y++)
            for (u32 x = 0; x < 16; x++) {
                u8 *q = mos + ref_morton(x, y, 16, 2);
                u32 h = q[0] | q[1] << 8, esp = ((u32)(x * 16) >> 3) << 11 | ((u32)(y * 32) >> 2) << 5;
                if (h != esp) malos++;
            }
        CHECK(malos == 0, "DT lineal->mosaico RGB565: %d mal", malos);
        /* escala X: promedio de dos vecinos horizontales */
        static u8 s2[8 * 8 * 4];
        GspTransfer t3 = {16, 8, 16, 8, (1u << 24) | (GSP_RGBA8 << 8) | (GSP_RGBA8 << 12)};
        static u8 e3[16 * 8 * 4];
        for (u32 y = 0; y < 8; y++)
            for (u32 x = 0; x < 16; x++) { u8 *q = e3 + ref_morton(x, y, 16, 4); q[0] = 255; q[1] = 0; q[2] = 0; q[3] = (u8)(x * 10); }
        CHECK(gsp_display_transfer(e3, s2, &t3) == 0, "DT escala X");
        CHECK(s2[(3 + 2 * 8) * 4 + 3] == (60 + 70) / 2, "DT escala X: R = %u", s2[(3 + 2 * 8) * 4 + 3]);
    }

    /* ============ 4. TextureCopy puro con huecos y MemoryFill puro */
    {
        u8 e[4 * 48], s[128];
        for (u32 i = 0; i < sizeof e; i++) e[i] = (u8)i;
        memset(s, 0, sizeof s);
        gsp_texture_copy(e, s, 128, (1u << 16) | 2u, 0);
        int malos = 0;
        for (u32 i = 0; i < 128; i++) if (s[i] != (u8)((i / 32) * 48 + i % 32)) malos++;
        CHECK(malos == 0, "TextureCopy con hueco de entrada: %d mal", malos);
        u32 te, ts;
        gsp_texture_copy_tam(128, (1u << 16) | 2u, 0, &te, &ts);
        CHECK(te == 176 && ts == 128, "TextureCopy tamanos %u %u", te, ts);
        u8 f[12];
        memset(f, 0, sizeof f);
        gsp_memory_fill(f, f + 12, 0x00CCBBAA, 1u << 8);
        CHECK(f[0] == 0xAA && f[1] == 0xBB && f[2] == 0xCC && f[9] == 0xAA && f[11] == 0xCC, "fill 24");
        gsp_memory_fill(f, f + 12, 0x11223344, 0);
        CHECK(f[0] == 0x44 && f[1] == 0x33 && f[10] == 0x44, "fill 16");
    }

    /* ============ 5. servicio completo por IPC + cola GX en la shm */
    mapear(0x14000000, 0x200000);   /* heap lineal: dos bloques del anfitrion separados */
    mapear(0x14200000, 0x200000);
    mapear(0x14400000, 0x80000);    /* framebuffer de prueba */
    mapear(0x1F000000, 0x600000);   /* VRAM */
    mapear(0x00100000, 0x10000);    /* memoria "normal" del juego (buffers estaticos del IPC) */
    GspAnfitrion an = {ptr, crear_shm, senalar, presentar, silencio};
    gsp_iniciar(&an);
    gsp_pica = pica_falsa;
    CHECK(gsp_virtual_a_fisica(0x14000010) == 0x20000010 && gsp_virtual_a_fisica(0x1F000020) == 0x18000020, "virt->fis");
    CHECK(gsp_fisica_a_virtual(0x20123450) == 0x14123450, "fis->virt");
    CHECK(gsp_fisica_a_host(0x201FF000, 0x2000) == NULL && gsp_fisica_a_host(0x20000000, 0x2000) == ptr(0x14000000),
          "contiguidad");

    const u32 S0 = 0x1001, S1 = 0x1002;
    memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00160042; g_cmd[1] = 0; g_cmd[3] = 0xFFFF8001; ipc(S0);
    CHECK(g_cmd[0] == 0x00160040 && g_cmd[1] == 0, "AcquireRight");
    memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00130042; g_cmd[1] = 1; g_cmd[3] = 0x5555; ipc(S0);
    CHECK(g_cmd[0] == 0x00130082 && g_cmd[1] == 0x2A07 && g_cmd[2] == 0 && g_cmd[4] == 0x77, "Register 1: %08X %08X %08X %08X",
          g_cmd[0], g_cmd[1], g_cmd[2], g_cmd[4]);
    memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00130042; g_cmd[1] = 1; g_cmd[3] = 0x6666; ipc(S1);
    CHECK(g_cmd[1] == 0 && g_cmd[2] == 1, "Register 2 (hilo 1)");

    /* MemoryFill 32 bits que cruza de un bloque del anfitrion al otro */
    {
        u32 c[8] = {2, 0x141FFF00, 0xAABBCCDD, 0x14200100, 0, 0, 0, (1u | (1u << 9))};
        gx(0, c);
        trigger(S0);
        CHECK(leer32(0x141FFF00) == 0xAABBCCDD && leer32(0x142000FC) == 0xAABBCCDD && leer32(0x14200100) == 0,
              "MemoryFill por GX");
        u8 ids[64];
        int n = drenar(0, ids);
        CHECK(n == 1 && ids[0] == GSP_INT_PSC0 && g_senales[0x5555] == 1 && g_senales[0x6666] == 0, "PSC0 al hilo con derechos");
    }
    /* ProcessCommandList: direccion FISICA al interprete y P3D */
    {
        u32 c[8] = {1, 0x14010000, 0x100, 0, 0, 0, 0, 0};
        gx(0, c);
        trigger(S0);
        CHECK(g_listas == 1 && g_lista_dir == 0x20010000 && g_lista_tam == 0x100, "lista PICA 0x%08X %u", g_lista_dir, g_lista_tam);
        u8 ids[64];
        CHECK(drenar(0, ids) == 1 && ids[0] == GSP_INT_P3D, "P3D");
    }
    /* DisplayTransfer + TextureCopy en el mismo disparo */
    {
        for (u32 y = 0; y < 16; y++)
            for (u32 x = 0; x < 16; x++) {
                u8 *q = ptr(0x1F000000 + ref_morton(x, y, 16, 4));
                q[0] = 0xFF; q[1] = 0x77; q[2] = (u8)y; q[3] = (u8)x;
            }
        u32 c1[8] = {3, 0x1F000000, 0x14300000, (16u << 16) | 16, (16u << 16) | 16, 1u | (GSP_RGB8 << 12), 0, 0};
        for (u32 i = 0; i < 64; i++) ptr(0x14310000)[i] = (u8)(i + 1);
        u32 c2[8] = {4, 0x14310000, 0x14320000, 64, 0, 0, 1u << 3, 0};
        gx(0, c1); gx(0, c2);
        trigger(S0);
        int malos = 0;
        for (u32 y = 0; y < 16; y++)
            for (u32 x = 0; x < 16; x++) {
                u8 *q = ptr(0x14300000 + (x + (15 - y) * 16) * 3);
                if (q[0] != 0x77 || q[1] != y || q[2] != x) malos++;
            }
        CHECK(malos == 0, "DisplayTransfer por GX: %d mal", malos);
        CHECK(memcmp(ptr(0x14310000), ptr(0x14320000), 64) == 0 && ptr(0x14320000)[64] == 0, "TextureCopy por GX");
        u8 ids[64];
        int n = drenar(0, ids);
        CHECK(n == 2 && ids[0] == GSP_INT_PPF && ids[1] == GSP_INT_PPF, "2 x PPF");
        u8 *b = g_shm + 0x800;
        CHECK(b[1] == 0 && b[0] == 4, "cabecera de la cola: indice %u cuenta %u", b[0], b[1]);
    }
    /* la cola GX da la vuelta (15 entradas) */
    {
        u32 base = g_listas;
        for (int r = 0; r < 3; r++) {
            for (int k = 0; k < 7; k++) { u32 c[8] = {1, 0x14010000 + (u32)k * 0x100, 0x80, 0, 0, 0, 0, 0}; gx(0, c); }
            trigger(S0);
        }
        CHECK(g_listas == base + 21, "vuelta de la cola GX: %u listas", g_listas - base);
        u8 ids[64]; drenar(0, ids);
    }

    /* WriteHWRegs / WithMask / ReadHWRegs (framebuffer de arriba) */
    {
        poner32(0x00100000, 0x18100000); poner32(0x00100004, 0x18200000);
        memset(g_cmd, 0, sizeof g_cmd);
        g_cmd[0] = 0x00010082; g_cmd[1] = 0x400468; g_cmd[2] = 8; g_cmd[3] = (8u << 14) | 2; g_cmd[4] = 0x00100000; ipc(S0);
        CHECK(g_cmd[0] == 0x00010040 && g_cmd[1] == 0, "WriteHWRegs");
        CHECK(gsp_leer_reg(0x1EF00468) == 0x18100000 && gsp_leer_reg(0x1EF0046C) == 0x18200000, "regs fb");
        poner32(0x00100010, 0x00000042);
        g_cmd[0] = 0x00010082; g_cmd[1] = 0x400470; g_cmd[2] = 4; g_cmd[4] = 0x00100010; ipc(S0);
        poner32(0x00100020, 0x12345678); poner32(0x00100030, 0x0000FF00);
        memset(g_cmd, 0, sizeof g_cmd);
        g_cmd[0] = 0x00020084; g_cmd[1] = 0x400470; g_cmd[2] = 4; g_cmd[4] = 0x00100020; g_cmd[6] = 0x00100030; ipc(S0);
        CHECK(gsp_leer_reg(0x1EF00470) == 0x00005642, "WithMask = 0x%08X", gsp_leer_reg(0x1EF00470));
        memset(g_cmd, 0, sizeof g_cmd);
        g_cmd[0] = 0x00040080; g_cmd[1] = 0x400468; g_cmd[2] = 12; g_cmd[0x40] = (0x80u << 14) | 2; g_cmd[0x41] = 0x00100100; ipc(S0);
        CHECK(g_cmd[0] == 0x00040042 && g_cmd[1] == 0 && g_cmd[3] == 0x00100100 && leer32(0x00100100) == 0x18100000 &&
              leer32(0x00100108) == 0x00005642, "ReadHWRegs");
        memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00010082; g_cmd[1] = 0x420000; g_cmd[2] = 4; g_cmd[4] = 0x00100000; ipc(S0);
        CHECK(g_cmd[1] == 0xE0E02A01, "WriteHWRegs fuera de rango");
        memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00010082; g_cmd[1] = 0x400468; g_cmd[2] = 0x84; g_cmd[4] = 0x00100000; ipc(S0);
        CHECK(g_cmd[1] == 0xE0E02BEC, "WriteHWRegs tamano");
        memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00080082; g_cmd[1] = 0x14000000; g_cmd[2] = 0x100; ipc(S0);
        CHECK(g_cmd[0] == 0x00080040 && g_cmd[1] == 0, "FlushDataCache");
    }

    /* VBlank: sin dirty no se toca el framebuffer; con dirty se aplica, se limpia la marca y se presenta */
    {
        u8 *u = g_shm + 0x200 + (2 * 0 + 0) * 0x40;   /* hilo 0, pantalla de arriba */
        u32 info[7] = {1, 0x14400000, 0x14400000, 240 * 3, GSP_RGB8, 1, 0};
        memcpy(u + 4 + 0x1C, info, sizeof info);
        u[0] = 1; u[1] = 0;
        gsp_vblank();
        CHECK(gsp_leer_reg(0x1EF0046C) == 0x18200000, "VBlank sin dirty no cambia el fb (0x%08X)", gsp_leer_reg(0x1EF0046C));
        u8 ids[64];
        int n = drenar(0, ids);
        CHECK(n == 2 && ids[0] == GSP_INT_PDC0 && ids[1] == GSP_INT_PDC1, "PDC0+PDC1 hilo 0");
        CHECK(g_shm[0x40 + 1] == 2, "PDC tambien al hilo 1 (sin derechos)");
        /* framebuffer: columna x=10, fila de pantalla y=20 en rojo */
        u8 *px = ptr(0x14400000 + 10 * 720 + (239 - 20) * 3);
        px[0] = 0; px[1] = 0; px[2] = 0xFF;
        u[1] = 1;
        gsp_vblank();
        CHECK(gsp_leer_reg(0x1EF0046C) == 0x20400000 && gsp_leer_reg(0x1EF00478) == 1 && gsp_leer_reg(0x1EF00490) == 720 &&
              gsp_leer_reg(0x1EF00470) == GSP_RGB8, "VBlank con dirty aplica el fb");
        CHECK(u[1] == 0, "dirty limpiado");
        CHECK(g_pres_n[0] == 2 && g_pres[0].dir_fisica == 0x20400000 && g_pres[0].ancho == 400 && g_pres[0].rgba, "presentacion");
        u8 *o = g_pres_img[0] + (20 * 400 + 10) * 4;
        u8 *o2 = g_pres_img[0] + (219 * 400 + 10) * 4;
        CHECK(o[0] == 0xFF && o[1] == 0 && o[2] == 0 && o2[0] == 0, "pixel enderezado (rojo en 10,20)");
        drenar(0, ids);
        /* forzar negro */
        memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x000B0040; g_cmd[1] = 1; ipc(S0);
        gsp_vblank();
        CHECK(g_pres[0].negro && g_pres_img[0][(20 * 400 + 10) * 4] == 0, "SetLcdForceBlack");
        g_cmd[0] = 0x000B0040; g_cmd[1] = 0; ipc(S0);
        gsp_vblank();
        CHECK(!g_pres[0].negro && g_pres_img[0][(20 * 400 + 10) * 4] == 0xFF, "SetLcdForceBlack off");
        drenar(0, ids);
    }
    /* el hilo 1 nunca drena: a partir de 0x20 se cuentan PDC perdidos */
    {
        for (int i = 0; i < 20; i++) gsp_vblank();
        u8 *q = g_shm + 0x40;
        u32 perdidos0, perdidos1;
        memcpy(&perdidos0, q + 4, 4); memcpy(&perdidos1, q + 8, 4);
        CHECK(q[1] == 0x20 && perdidos0 > 0 && perdidos1 > 0, "umbral PDC: cuenta %u, perdidos %u/%u", q[1], perdidos0, perdidos1);
        u8 ids[64]; drenar(0, ids);
    }
    /* la cola de relevo da la vuelta en 0x34 */
    {
        u8 *q = g_shm;
        q[0] = 0x31; q[1] = 0;
        for (int i = 0; i < 5; i++) gsp_interrupcion(GSP_INT_PSC1);
        CHECK(q[0x0C + 0x33] == GSP_INT_PSC1 && q[0x0C + 0] == GSP_INT_PSC1 && q[0x0C + 1] == GSP_INT_PSC1 && q[1] == 5,
              "vuelta de la cola de relevo");
        u8 ids[64]; drenar(0, ids);
        q[0] = 0; q[1] = 0x34;
        gsp_interrupcion(GSP_INT_PSC0);
        CHECK(q[2] == 1 && q[1] == 0x34, "cola llena -> error");
        q[1] = 0; q[2] = 0;
    }
    /* ReleaseRight: las interrupciones que no son PDC ya no llegan */
    {
        memset(g_cmd, 0, sizeof g_cmd); g_cmd[0] = 0x00170000; ipc(S0);
        CHECK(gsp_estadistica()->hilo_con_derechos == 0xFFFFFFFFu, "ReleaseRight");
        gsp_interrupcion(GSP_INT_PPF);
        CHECK(g_shm[1] == 0, "sin derechos no hay PPF");
    }

    printf("prueba_gsp: %d/%d comprobaciones OK%s\n", g_checks - g_fallos, g_checks, g_fallos ? " -- HAY FALLAS" : "");
    return g_fallos ? 1 : 0;
}
