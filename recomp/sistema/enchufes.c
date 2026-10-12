/* Enchufes de los servicios reales que viven fuera de recomp\sistema (cada uno compila aparte, sin sistema.h):
 *   -DSIS_CON_HID  : recomp\hid\servicio_hid.c + hid.c    (agente D; enlazar -lxinput1_4)
 *   -DSIS_CON_GSP  : recomp\gpu\gsp.c                      (agente E)
 *   -DSIS_CON_PICA : recomp\render\pica.c + pica_dibujar.c (agente F; requiere SIS_CON_GSP)
 *   -DSIS_CON_DSP  : recomp\audio\dsp.c + audio_salida.c   (agente H; -ffp-contract=off, -DAUDIO_BACKEND_WASAPI, -lole32)
 * Sin la bandera queda el provisional de stubs.c. Los eventos periodicos (VBlank, muestreo de HID, tick del DSP)
 * corren en el planificador (sis_periodico), en el hilo del sistema operativo de las fibras: sin hilos del anfitrion
 * que toquen objetos del kernel. Se compila dentro de sistema.c. */
#ifdef SIS_IPC_SEPARADO
#include <stdio.h>
#include <string.h>
#include "sistema.h"
#endif

/* ------------------------------------------------------------------ memoria fisica -> anfitrion */
/* FCRAM 0x20000000 <-> heap lineal 0x14000000; VRAM 0x18000000 <-> 0x1F000000; RAM del DSP 0x1FF00000 (identidad) */
u32 sis_fisica_a_virtual(u32 f)
{
    if (f >= 0x20000000u && f < 0x28000000u) return f - 0x20000000u + SIS_LINEAL;
    if (f >= 0x18000000u && f < 0x18600000u) return f - 0x18000000u + SIS_VRAM;
    if (f >= 0x1FF00000u && f < 0x1FF80000u) return f;
    return 0;
}

u8 *sis_fisica_a_host(u32 f, u32 n)
{
    u32 v = sis_fisica_a_virtual(f);
    if (!v || !rt_pagina[v >> 12]) return NULL;
    /* contiguo en el anfitrion pagina por pagina */
    for (u32 pg = (v >> 12) + 1; pg <= ((v + (n ? n - 1 : 0)) >> 12); pg++)
        if (rt_pagina[pg] != rt_pagina[pg - 1] + 0x1000) return NULL;
    return P(v);
}

/* ------------------------------------------------------------------ hid:USER (agente D) */
#ifdef SIS_CON_HID
#include "../hid/servicio_hid.h"
static HidServicio g_hid;
static int hid_crudo(void *ctx, u32 *cmd, u32 sesion) { (void)sesion; return hid_srv_comando((HidServicio *)ctx, cmd); }
#ifdef SIS_CON_GSP
#include "../gpu/gsp.h"
#endif
/* vblank actual para el guion (SM3DL_GUION): el contador de gsp si esta; si no, por reloj (4.481.136 ticks) */
static uint32_t vblank_actual(void)
{
#ifdef SIS_CON_GSP
    return gsp_estadistica()->vblanks;
#else
    return (uint32_t)(sis_ticks() / 4481136ull);
#endif
}
static void hid_periodico(void)
{
    HidEntradaPC e;
    /* SM3DL_HASTA_VBLANK=N: salir limpio al llegar al vblank N (con SM3DL_TURBO el tiempo real no sirve de corte) */
    static long hasta = -2;
    if (hasta == -2) { const char *s = getenv("SM3DL_HASTA_VBLANK"); hasta = s && atol(s) > 0 ? atol(s) : -1; }
    if (hasta > 0 && vblank_actual() >= (uint32_t)hasta) {
        fprintf(stderr, "[arranque] fin por SM3DL_HASTA_VBLANK (%ld)\n", hasta);
        fflush(stderr); fflush(stdout);
        ExitProcess(0);
    }
#ifdef SIS_CON_RASTER
    { void raster_vblank(unsigned); raster_vblank(vblank_actual()); }
#endif
    hid_leer_pc(&e);
    hid_grabar(&e, vblank_actual());   /* antes del guion: graba solo lo que juega una persona */
    hid_guion_aplicar(&e, vblank_actual());   /* agente P: entrada por guion, suma al teclado/mando */
    hid_tick(&g_hid, &e, (int64_t)sis_ticks());
}
static void enchufar_hid(void)
{
    u8 *pagina;
    sis_hid_preparar(&pagina, &g_hid.h_shm, g_hid.h_ev);   /* antes de iniciar: hid_srv_iniciar no debe pisar los handles */
    u32 shm = g_hid.h_shm, ev[5];
    memcpy(ev, g_hid.h_ev, sizeof ev);
    hid_srv_iniciar(&g_hid, pagina, sis_senal_hid, NULL);
    g_hid.h_shm = shm; memcpy(g_hid.h_ev, ev, sizeof ev);
    ipc_registrar_crudo("hid:USER", hid_crudo, &g_hid);
    sis_periodico(hid_periodico, 1000000000ull / HID_HZ_PAD);
}
#endif

/* ------------------------------------------------------------------ gsp::Gpu (agente E) + PICA (agente F) */
#ifdef SIS_CON_GSP
#include "../gpu/gsp.h"
#ifdef SIS_CON_PICA
#include "../render/pica.h"
#endif
#ifdef SIS_CON_RASTER
#include "../render/raster_gl.h"
#endif
static uint8_t *gsp_puntero(uint32_t v) { return rt_pagina[v >> 12] ? P(v) : NULL; }
static uint32_t gsp_crear_shm(uint32_t tam, uint8_t **host) { return sis_handle_nuevo(sis_bloque_nuevo(tam, host)); }
static void gsp_log(const char *t) { fprintf(stderr, "[gsp] %s\n", t); }
static int gsp_crudo(void *ctx, u32 *cmd, u32 sesion) { (void)ctx; gsp_ipc(cmd, sesion); return 1; }
/* cada 2 s: si el juego dibuja de verdad, listas y swaps suben al ritmo de los vblanks (8 oct) */
static void gsp_reporte(void)
{
    const GspEstadistica *e = gsp_estadistica();
    fprintf(stderr, "[gsp-est] vblanks=%u listas=%u fills=%u transfers=%u texcopies=%u dmas=%u swaps=%u presentaciones=%u\n",
            e->vblanks, e->listas, e->fills, e->transfers, e->texcopies, e->dmas, e->swaps, e->presentaciones);
}
/* Capturas (8 oct; agente P 10 oct):
 *   - por defecto: cada 300 presentaciones por pantalla, un PPM en recomp\arranque\capturas\ (como antes).
 *   - SM3DL_CAPTURAS=<carpeta>: PNG con las DOS pantallas (400x480, como la ventana) cada SM3DL_CAPTURA_CADA
 *     presentaciones de la pantalla de abajo (por defecto 300), nombre v<vblank>.png: el vblank sirve para el guion. */
static uint32_t png_crc_tabla[256];
static uint32_t png_crc(uint32_t c, const uint8_t *b, size_t n)
{
    if (!png_crc_tabla[1])
        for (uint32_t k = 0; k < 256; k++) {
            uint32_t v = k;
            for (int j = 0; j < 8; j++) v = (v & 1) ? 0xEDB88320u ^ (v >> 1) : v >> 1;
            png_crc_tabla[k] = v;
        }
    c = ~c;
    while (n--) c = png_crc_tabla[(c ^ *b++) & 0xFF] ^ (c >> 8);
    return ~c;
}
static void png_be32(uint8_t *d, uint32_t v) { d[0] = (uint8_t)(v >> 24); d[1] = (uint8_t)(v >> 16); d[2] = (uint8_t)(v >> 8); d[3] = (uint8_t)v; }
static void png_trozo(FILE *f, const char *tipo, const uint8_t *d, uint32_t n)
{
    uint8_t c[8];
    png_be32(c, n); memcpy(c + 4, tipo, 4);
    fwrite(c, 1, 8, f);
    if (n) fwrite(d, 1, n, f);
    uint32_t crc = png_crc(png_crc(0, (const uint8_t *)tipo, 4), d, n);
    png_be32(c, crc);
    fwrite(c, 1, 4, f);
}
/* PNG RGB sin comprimir (deflate con bloques "stored"): sin zlib, ~600 KB por captura */
static int png_guardar(const char *ruta, const uint8_t *rgb, uint32_t w, uint32_t h)
{
    size_t crudo = (size_t)(w * 3 + 1) * h, nb = (crudo + 65534) / 65535;
    uint8_t *z = malloc(2 + crudo + 5 * nb + 4), *o = z;
    uint8_t *fila = malloc(crudo);
    if (!z || !fila) { free(z); free(fila); return -1; }
    for (uint32_t y = 0; y < h; y++) { fila[(size_t)y * (w * 3 + 1)] = 0; memcpy(fila + (size_t)y * (w * 3 + 1) + 1, rgb + (size_t)y * w * 3, (size_t)w * 3); }
    *o++ = 0x78; *o++ = 0x01;
    uint32_t a = 1, b = 0;
    for (size_t k = 0; k < crudo; k++) { a = (a + fila[k]) % 65521; b = (b + a) % 65521; }
    for (size_t p = 0; p < crudo; p += 65535) {
        uint32_t n = (uint32_t)(crudo - p < 65535 ? crudo - p : 65535);
        *o++ = p + n == crudo; *o++ = (uint8_t)n; *o++ = (uint8_t)(n >> 8); *o++ = (uint8_t)~n; *o++ = (uint8_t)(~n >> 8);
        memcpy(o, fila + p, n); o += n;
    }
    png_be32(o, (b << 16) | a); o += 4;
    FILE *f = fopen(ruta, "wb");
    if (f) {
        static const uint8_t firma[8] = { 0x89, 'P', 'N', 'G', 13, 10, 26, 10 };
        uint8_t ih[13];
        fwrite(firma, 1, 8, f);
        png_be32(ih, w); png_be32(ih + 4, h); ih[8] = 8; ih[9] = 2; ih[10] = ih[11] = ih[12] = 0;
        png_trozo(f, "IHDR", ih, 13);
        png_trozo(f, "IDAT", z, (uint32_t)(o - z));
        png_trozo(f, "IEND", NULL, 0);
        fclose(f);
    }
    free(z); free(fila);
    return f ? 0 : -1;
}
static void gsp_capturar(const GspPresentacion *p)
{
    static unsigned n[2];
    static int modo = -1;            /* -1 sin leer, 0 PPM de siempre, 1 PNG en carpeta */
    static char carpeta[260];
    static unsigned cada = 300;
    static uint8_t lienzo[400 * 480 * 3];
    if (modo < 0) {
        const char *c = getenv("SM3DL_CAPTURAS"), *k = getenv("SM3DL_CAPTURA_CADA");
        modo = c && *c ? 1 : 0;
        if (modo) { snprintf(carpeta, sizeof carpeta, "%s", c); CreateDirectoryA(carpeta, NULL); }
        if (k && atoi(k) > 0) cada = (unsigned)atoi(k);
        memset(lienzo, 0x20, sizeof lienzo);
    }
    if (!p->rgba || p->pantalla < 0 || p->pantalla > 1) return;
    if (modo == 1) {
        uint32_t x0 = p->pantalla ? 40 : 0, y0 = p->pantalla ? 240 : 0, w = p->pantalla ? 320 : 400;
        if (p->ancho == w && p->alto == 240)
            for (uint32_t y = 0; y < 240; y++)
                for (uint32_t x = 0; x < w; x++) {
                    uint8_t *d = lienzo + ((size_t)(y0 + y) * 400 + x0 + x) * 3;
                    const uint8_t *o = p->rgba + ((size_t)y * w + x) * 4;
                    if (p->negro) d[0] = d[1] = d[2] = 0; else { d[0] = o[0]; d[1] = o[1]; d[2] = o[2]; }
                }
        if (p->pantalla != 1 || n[1]++ % cada != cada - 1) return;
        char r[400];
        uint32_t vb = gsp_estadistica()->vblanks;
        snprintf(r, sizeof r, "%s\\v%06u.png", carpeta, vb);
        png_guardar(r, lienzo, 400, 480);
        fprintf(stderr, "[captura] %s\n", r);
        return;
    }
    if (n[p->pantalla]++ % cada != cada - 1) return;
    fprintf(stderr, "[captura] pantalla %d: negro=%d formato=0x%X stride=%u fb=0x%08X rgba0=%02X%02X%02X%02X\n",
            p->pantalla, p->negro, p->formato, p->stride, p->dir_fisica, p->rgba[0], p->rgba[1], p->rgba[2], p->rgba[3]);
    char r[128];
    CreateDirectoryA("recomp\\arranque\\capturas", NULL);
    snprintf(r, sizeof r, "recomp\\arranque\\capturas\\%s_%04u.ppm", p->pantalla ? "abajo" : "arriba", n[p->pantalla]);
    FILE *f = fopen(r, "wb");
    if (!f) return;
    fprintf(f, "P6\n%u %u\n255\n", p->ancho, p->alto);
    for (uint32_t k = 0; k < p->ancho * p->alto; k++) fwrite(p->rgba + 4 * k, 1, 3, f);
    fclose(f);
}
#ifdef SIS_CON_RASTER
/* con rasterizador: ventana visible + las capturas de siempre; el teclado solo cuenta con la ventana activa */
#include "../render/ventana.h"
extern int (*hid_teclado_activo)(void);
static void gsp_mostrar(const GspPresentacion *p)
{
    gsp_capturar(p);
    ventana_presentar(p);
}
#endif
static void enchufar_gsp(void)
{
    static GspAnfitrion a;
    a.puntero = gsp_puntero; a.crear_shm = gsp_crear_shm; a.senalar_evento = sis_senalar_handle;
    a.presentar = gsp_capturar; a.log = gsp_log;
#ifdef SIS_CON_RASTER
    a.presentar = gsp_mostrar;
#ifdef SIS_CON_HID
    hid_teclado_activo = ventana_con_foco;
    { extern int (*hid_toque_pc)(int, float *, float *); hid_toque_pc = ventana_toque; }
    { extern uint32_t (*hid_botones_pc)(void); hid_botones_pc = ventana_botones; }
#endif
#endif
    gsp_iniciar(&a);
#ifdef SIS_CON_PICA
    gsp_pica = pica_ejecutar;
    pica_memoria = gsp_fisica_a_host;
#endif
#ifdef SIS_CON_RASTER
    raster_iniciar();
#endif
    ipc_registrar_crudo("gsp::Gpu", gsp_crudo, NULL);
    sis_periodico(gsp_vblank, 16713800ull);                /* 59,83 Hz = 4.481.136 ticks */
    sis_periodico(gsp_reporte, 2000000000ull);
#ifdef SIS_CON_RASTER
    sis_periodico(ventana_presentador, 2000000ull);       /* modo de cuadros "monitor" (>60 FPS) */
#endif
}
#endif

/* ------------------------------------------------------------------ dsp::DSP (agente H) */
#ifdef SIS_CON_DSP
#include "../audio/dsp.h"
static const uint8_t *dsp_fis(void *ud, uint32_t f, uint32_t n) { (void)ud; return sis_fisica_a_host(f, n); }
static void dsp_senal(void *ud, uint32_t h) { (void)ud; sis_senalar_handle(h); }
static void dsp_periodico(void) { dsp_tick(); }
#define DSP_RES(r) ((r) == 0 ? RES_OK : 0xC8A0D7FCu)  /* error generico del DSP */

static void dsp_real(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001: { u16 v = dsp_RecvData(cmd[1]); ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = v; return; }
    case 0x0002: { int v = dsp_RecvDataIsReady(cmd[1]); ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = (u32)v; return; }
    case 0x0007: { int r = dsp_SetSemaphore((u16)cmd[1]); ipc_respuesta(p, 1, 0, DSP_RES(r)); return; }
    case 0x000C: { u32 v = dsp_ConvertProcessAddressFromDspDram(cmd[1]); ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = v; return; }
    case 0x000D: {                                     /* WriteProcessPipe(canal, tam, estatico) */
        IpcDesc *d = ipc_desc(p, IPC_D_ESTATICO, 0);
        u32 canal = cmd[1], tam = cmd[2];
        u8 buf[0x400];
        if (!d || tam > sizeof buf) { ipc_respuesta(p, 1, 0, IPC_RES_CAB_MALA); return; }
        sis_copiar_de_juego(buf, d->dir, tam);
        int r = dsp_WriteProcessPipe(canal, buf, tam);
        ipc_respuesta(p, 1, 0, DSP_RES(r));
        return;
    }
    case 0x0010: {                                     /* ReadPipeIfPossible(canal, par, tam) -> leidos, estatico 0 */
        u8 buf[0x400]; u32 leidos = 0, tam = cmd[3] & 0xFFFF;
        if (tam > sizeof buf) tam = sizeof buf;
        int r = dsp_ReadPipeIfPossible(cmd[1], cmd[2], buf, tam, &leidos);
        ipc_respuesta(p, 2, 2, DSP_RES(r));
        cmd[2] = leidos;
        ipc_salida_estatica(p, 3, 0, buf, leidos);
        return;
    }
    case 0x0011: {                                     /* LoadComponent(tam, pm, dm, mapeado) -> cargado */
        u8 cargado = 0;
        int r = dsp_LoadComponent(cmd[1], cmd[2], cmd[3], &cargado);
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        ipc_respuesta(p, 2, d ? 2 : 0, DSP_RES(r));
        cmd[2] = cargado;
        if (d) { cmd[3] = IPC_DESC_MAPEADO(d->tam, d->extra); cmd[4] = d->dir; }
        return;
    }
    case 0x0012: { int r = dsp_UnloadComponent(); ipc_respuesta(p, 1, 0, DSP_RES(r)); return; }
    case 0x0013: case 0x0014: {                        /* Flush/InvalidateDataCache(va, tam, handle de proceso) */
        int r = p->id == 0x13 ? dsp_FlushDataCache(cmd[1], cmd[2]) : dsp_InvalidateDataCache(cmd[1], cmd[2]);
        ipc_respuesta(p, 1, 0, DSP_RES(r));
        return;
    }
    case 0x0015: {                                     /* RegisterInterruptEvents(tipo, canal, evento) */
        u32 tipo = cmd[1], canal = cmd[2], h = cmd[4];   /* cmd[3] = descriptor de copia */
        int r = dsp_RegisterInterruptEvents(h, tipo, canal);
        ipc_respuesta(p, 1, 0, DSP_RES(r));
        return;
    }
    case 0x0016: {                                     /* GetSemaphoreEventHandle */
        static u32 h_sem;
        if (!h_sem) { h_sem = sis_handle_nuevo(sis_evento_nuevo(0)); dsp_poner_evento_semaforo(h_sem); }
        ipc_respuesta(p, 1, 2, RES_OK);
        cmd[2] = IPC_DESC_COPIA(1); cmd[3] = dsp_GetSemaphoreEventHandle();
        return;
    }
    case 0x0017: { int r = dsp_SetSemaphoreMask((u16)cmd[1]); ipc_respuesta(p, 1, 0, DSP_RES(r)); return; }
    case 0x001F: { u32 v = dsp_GetHeadphoneStatus(); ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = v; return; }
    default: ipc_no_implementado(p, 1); return;
    }
}

static void enchufar_dsp(void)
{
    static dsp_host_t h;
    h.fis = dsp_fis; h.senal = dsp_senal; h.salida = NULL; h.ud = NULL;
    dsp_iniciar(&h);
    sis_mapear_host(DSP_RAM_BASE, DSP_RAM_TAM, dsp_ram());
    ipc_registrar("dsp::DSP", dsp_real);
    sis_periodico(dsp_periodico, 4888600ull);              /* 160 muestras a 32.728 Hz */
}
#endif

void sis_enchufar_externos(void)
{
#ifdef SIS_CON_HID
    enchufar_hid();
#endif
#ifdef SIS_CON_GSP
    enchufar_gsp();
#endif
#ifdef SIS_CON_DSP
    enchufar_dsp();
#endif
}
