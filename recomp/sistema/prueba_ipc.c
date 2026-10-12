/* Prueba de la capa IPC HLE (ipc.c, srv.c, stubs.c, fs.c) sin el juego: arma los buffers de comando en TLS+0x80
 * como lo hacen los wrappers del juego y llama SendSyncRequest (svc 0x32) por sis_svc_num.
 * Lo fuerte: lee por IPC la imagen del RomFS (nivel 3) de la ROM, la parsea como lo haria nn::fs, busca
 * EffectData.szs y lo compara byte a byte con extraido\romfs (sacado por otra via: tools\listar_romfs.py).
 *
 *   py -m ziglang cc -target x86_64-windows-gnu -O2 -Wall -Wextra -Irecomp\runtime recomp\sistema\sistema.c
 *      recomp\sistema\prueba_ipc.c recomp\runtime\runtime.c -o recomp\build\prueba_ipc.exe
 *   recomp\build\prueba_ipc.exe [raiz del proyecto]
 * Sabotajes (la prueba debe FALLAR): -DSABOTAJE_FS_OFFSET (fs.c lee corrido 16 bytes),
 *   -DSABOTAJE_DESC_MAPEADO (ipc.c decodifica mal el tamano de un buffer mapeado), -DSABOTAJE_PID (no escribe el pid). */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sistema.h"

/* lo que en el arranque pone runtime.c (esta prueba no corre codigo recompilado) */
u8 *rt_pagina[1u << 20];
void rt_llamar(CPU *c, u32 addr) { (void)c; (void)addr; }

static int fallos, pruebas;
#define CHECK(c, ...) do { pruebas++; if (!(c)) { fallos++; printf("FALLA %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static CPU cpu;
static u32 *cmd;                       /* TLS+0x80 */
#define BUF   0x08000000u              /* memoria de trabajo del "juego" */
#define BUF_TAM 0x00100000u

static u32 svc(u32 num, u32 r0) { cpu.r[0] = r0; sis_svc_num(&cpu, num, 0x00100000u); return cpu.r[0]; }
static u32 enviar(u32 h) { return svc(0x32, h); }

static u32 conectar(const char *puerto)
{
    sis_copiar_a_juego(BUF, puerto, (u32)strlen(puerto) + 1);
    cpu.r[1] = BUF;
    CHECK(svc(0x2D, 0) == RES_OK, "ConnectToPort(%s)", puerto);
    return cpu.r[1];
}

static u32 obtener_servicio(u32 srv, const char *nombre, u32 *res)
{
    memset(cmd, 0, 0x100);
    cmd[0] = 0x00050100u;
    memcpy(&cmd[1], nombre, strlen(nombre) < 8 ? strlen(nombre) : 8);
    cmd[3] = (u32)strlen(nombre); cmd[4] = 0;
    CHECK(enviar(srv) == RES_OK, "SendSyncRequest srv:");
    *res = cmd[1];
    return cmd[3];
}

/* fs: Read(off, tam) en el buffer del juego `dst`; devuelve los bytes leidos */
static u32 fs_leer(u32 h, u64 off, u32 tam, u32 dst, u32 *res)
{
    cmd[0] = 0x080200C2u; cmd[1] = (u32)off; cmd[2] = (u32)(off >> 32); cmd[3] = tam;
    cmd[4] = IPC_DESC_MAPEADO(tam, 2); cmd[5] = dst;
    enviar(h);
    *res = cmd[1];
    if (cmd[1] == RES_OK) CHECK(cmd[0] == 0x08020082u && cmd[3] == IPC_DESC_MAPEADO(tam, 2) && cmd[4] == dst, "Read: respuesta 0x%08X / eco del buffer", cmd[0]);
    return cmd[2];
}

static u32 ruta_ascii(u32 dir, const char *s) { sis_copiar_a_juego(dir, s, (u32)strlen(s) + 1); return (u32)strlen(s) + 1; }

static void prueba_eco(IpcPeticion *p);
static IpcPeticion ultima;             /* lo que vio el servicio de prueba */
static void prueba_eco(IpcPeticion *p) { ultima = *p; ipc_respuesta(p, 1, 0, RES_OK); }

int main(int argc, char **argv)
{
    const char *raiz = argc > 1 ? argv[1] : ".";
    char guardado[MAX_PATH], r[MAX_PATH * 2];
    GetTempPathA(sizeof guardado, guardado);
    strcat(guardado, "sm3dl_prueba_guardado");
    CreateDirectoryA(guardado, NULL);
    snprintf(r, sizeof r, "%s\\*", guardado);
    {   WIN32_FIND_DATAA w; HANDLE fh = FindFirstFileA(r, &w);
        if (fh != INVALID_HANDLE_VALUE) { do { char x[MAX_PATH * 2]; snprintf(x, sizeof x, "%s\\%s", guardado, w.cFileName); DeleteFileA(x); } while (FindNextFileA(fh, &w)); FindClose(fh); } }

    sis_iniciar();
    fs_configurar(NULL, guardado);
    sis_mapear(BUF, BUF_TAM);
    cpu.tls = SIS_TLS;
    cmd = (u32 *)P(SIS_TLS + 0x80);

    /* ---------------- srv: */
    u32 srv = conectar("srv:");
    memset(cmd, 0, 0x100);
    cmd[0] = 0x00010002u; cmd[1] = 0x20; cmd[2] = 0xDEAD;          /* RegisterClient(CallingPid) */
    enviar(srv);
    CHECK(cmd[0] == 0x00010040u && cmd[1] == RES_OK, "RegisterClient: 0x%08X 0x%08X", cmd[0], cmd[1]);
    CHECK(cmd[2] == ipc_pid, "el kernel debe escribir el pid del cliente (hay 0x%X)", cmd[2]);

    const char *servicios[] = { "APT:U", "fs:USER", "hid:USER", "gsp::Gpu", "dsp::DSP", "cfg:u", "cecd:s", "ndm:u", "mic:u", "cecd:u" };
    u32 hs[10], res;
    for (int i = 0; i < 10; i++) {
        hs[i] = obtener_servicio(srv, servicios[i], &res);
        CHECK(res == RES_OK && cmd[0] == 0x00050042u && cmd[2] == IPC_DESC_MOVER(1) && sis_obj_de_handle(hs[i]),
              "GetServiceHandle(%s): res 0x%08X cab 0x%08X desc 0x%08X", servicios[i], res, cmd[0], cmd[2]);
    }
    u32 h_apt = hs[0], h_fs = hs[1], h_dsp = hs[4], h_cfg = hs[5], h_ndm = hs[7];
    obtener_servicio(srv, "nada:u", &res);
    CHECK(res == RES_NO_HAY, "servicio desconocido debe fallar (0x%08X)", res);
    /* el largo esta en cmd[3]: "fs:USERx" con largo 7 debe dar fs:USER */
    {
        memset(cmd, 0, 0x100);
        cmd[0] = 0x00050100u; memcpy(&cmd[1], "fs:USERx", 8); cmd[3] = 7;
        enviar(srv);
        CHECK(cmd[1] == RES_OK, "GetServiceHandle respeta el largo de cmd[3]");
    }

    /* ---------------- traduccion de descriptores: servicio de prueba enchufado por nombre */
    CHECK(ipc_registrar("prueba:e", prueba_eco) == 0, "registrar");
    u32 h_eco = obtener_servicio(srv, "prueba:e", &res);
    CHECK(res == RES_OK, "GetServiceHandle(prueba:e)");
    {
        SisObj *ev = sis_evento_nuevo(0);
        u32 h1 = sis_handle_nuevo(ev), h2 = sis_handle_nuevo(ev);
        cmd[0] = IPC_CAB(0x0042, 1, 10);
        cmd[1] = 0x1234;
        cmd[2] = IPC_DESC_COPIA(1); cmd[3] = h1;
        cmd[4] = IPC_DESC_MOVER(1); cmd[5] = h2;
        cmd[6] = IPC_DESC_ESTATICO(0x30, 3); cmd[7] = BUF + 0x100;
        cmd[8] = IPC_DESC_MAPEADO(0x5000, 1); cmd[9] = BUF + 0x2000;
        cmd[10] = 0x20; cmd[11] = 0;
        enviar(h_eco);
        CHECK(ultima.n_desc == 5, "5 descriptores (hay %u)", ultima.n_desc);
        CHECK(ultima.desc[0].tipo == IPC_D_COPIA && ultima.desc[0].objs[0] == ev, "copia -> objeto");
        CHECK(ultima.desc[1].tipo == IPC_D_MOVER && ultima.desc[1].objs[0] == ev, "mover -> objeto");
        CHECK(sis_obj_de_handle(h1) == ev, "copiar no cierra el handle del cliente");
        CHECK(sis_obj_de_handle(h2) == NULL, "mover cierra el handle del cliente");
        CHECK(ultima.desc[2].tipo == IPC_D_ESTATICO && ultima.desc[2].tam == 0x30 && ultima.desc[2].extra == 3 && ultima.desc[2].dir == BUF + 0x100, "estatico");
        CHECK(ultima.desc[3].tipo == IPC_D_MAPEADO && ultima.desc[3].tam == 0x5000 && ultima.desc[3].extra == 1 && ultima.desc[3].dir == BUF + 0x2000,
              "mapeado tam 0x%X perm %u", ultima.desc[3].tam, ultima.desc[3].extra);
        CHECK(ultima.desc[4].tipo == IPC_D_PID, "pid");
        /* cabecera imposible */
        cmd[0] = IPC_CAB(0x0001, 60, 10);
        enviar(h_eco);
        CHECK(cmd[1] == IPC_RES_CAB_MALA, "cabecera de mas de 64 palabras debe rechazarse");
        /* descriptor que se sale de la cabecera */
        cmd[0] = IPC_CAB(0x0001, 0, 1); cmd[1] = IPC_DESC_MAPEADO(4, 1);
        enviar(h_eco);
        CHECK(cmd[1] == IPC_RES_CAB_MALA, "descriptor truncado debe rechazarse");
    }

    /* ---------------- fs:USER: RomFS */
    cmd[0] = 0x08010002u; cmd[1] = 0x20; cmd[2] = 0;
    enviar(h_fs);
    CHECK(cmd[0] == 0x08010040u && cmd[1] == RES_OK, "FS Initialize");

    u32 ruta_rom = BUF + 0x400;
    { u32 z[3] = {0, 0, 0}; sis_copiar_a_juego(ruta_rom, z, 12); W8(BUF + 0x440, 0); }
    cmd[0] = 0x08030204u; cmd[1] = 0; cmd[2] = 3; cmd[3] = 1; cmd[4] = 1; cmd[5] = 2; cmd[6] = 12; cmd[7] = 1; cmd[8] = 0;
    cmd[9] = IPC_DESC_ESTATICO(1, 0); cmd[10] = BUF + 0x440;
    cmd[11] = IPC_DESC_ESTATICO(12, 1); cmd[12] = ruta_rom;
    enviar(h_fs);
    CHECK(cmd[0] == 0x08030042u && cmd[1] == RES_OK && cmd[2] == IPC_DESC_MOVER(1), "OpenFileDirectly(RomFS): 0x%08X 0x%08X", cmd[0], cmd[1]);
    u32 h_rom = cmd[3];

    cmd[0] = 0x08040000u; enviar(h_rom);
    u64 tam_rom = (u64)cmd[2] | ((u64)cmd[3] << 32);
    CHECK(cmd[0] == 0x080400C0u && cmd[1] == RES_OK && tam_rom > 0x10000000ull, "GetSize RomFS = 0x%llX", (unsigned long long)tam_rom);

    /* cabecera del nivel 3 */
    u32 cab[10];
    CHECK(fs_leer(h_rom, 0, 0x28, BUF, &res) == 0x28 && res == RES_OK, "leer cabecera nivel 3");
    sis_copiar_de_juego(cab, BUF, 0x28);
    CHECK(cab[0] == 0x28, "cabecera del nivel 3: tamano 0x%X (esperado 0x28)", cab[0]);
    u32 fmeta_off = cab[7], fmeta_tam = cab[8], datos_off = cab[9];
    CHECK(fmeta_tam < BUF_TAM / 2, "metadatos de archivos 0x%X", fmeta_tam);

    /* buscar EffectData.szs en la tabla de archivos (como nn::fs) y compararlo con extraido\romfs */
    int encontrado = 0;
    if (cab[0] == 0x28 && fmeta_tam < BUF_TAM / 2) {
        u32 n = fs_leer(h_rom, fmeta_off, fmeta_tam, BUF, &res);
        CHECK(n == fmeta_tam, "leer metadatos (%u de %u)", n, fmeta_tam);
        u8 *meta = malloc(fmeta_tam);
        sis_copiar_de_juego(meta, BUF, fmeta_tam);
        for (u32 o = 0; o + 0x20 <= fmeta_tam; ) {
            u32 largo; u64 doff, dtam;
            memcpy(&doff, meta + o + 8, 8); memcpy(&dtam, meta + o + 16, 8); memcpy(&largo, meta + o + 28, 4);
            char nombre[128] = {0};
            for (u32 i = 0; i < largo / 2 && i < 127; i++) nombre[i] = (char)meta[o + 32 + 2 * i];
            if (strcmp(nombre, "EffectData.szs") == 0) {
                encontrado = 1;
                snprintf(r, sizeof r, "%s\\extraido\\romfs\\EffectData\\EffectData.szs", raiz);
                FILE *f = fopen(r, "rb");
                CHECK(f != NULL, "no se pudo abrir %s", r);
                if (f) {
                    u8 *ref = malloc((size_t)dtam + 1);
                    size_t lr = fread(ref, 1, (size_t)dtam + 1, f);
                    fclose(f);
                    CHECK(lr == dtam, "tamano: RomFS %llu, extraido %zu", (unsigned long long)dtam, lr);
                    u32 leidos = fs_leer(h_rom, (u64)datos_off + doff, (u32)dtam, BUF + 0x80000, &res);
                    CHECK(leidos == dtam && res == RES_OK, "leer EffectData.szs (%u)", leidos);
                    u8 *got = malloc((size_t)dtam);
                    sis_copiar_de_juego(got, BUF + 0x80000, (u32)dtam);
                    u32 dif = 0, primera = 0xFFFFFFFFu;
                    for (u32 i = 0; i < dtam && i < lr; i++) if (got[i] != ref[i]) { if (!dif++) primera = i; }
                    CHECK(dif == 0, "EffectData.szs difiere en %u bytes (primera en 0x%X)", dif, primera);
                    printf("EffectData.szs: %llu bytes leidos por IPC, %u diferencias con extraido\\romfs\n", (unsigned long long)dtam, dif);
                    free(ref); free(got);
                }
                break;
            }
            o += 32 + ((largo + 3) & ~3u);
        }
        free(meta);
    }
    CHECK(encontrado, "EffectData.szs no esta en la tabla del RomFS");

    /* leer pasado el final: solo lo que hay */
    CHECK(fs_leer(h_rom, tam_rom - 10, 100, BUF, &res) == 10, "lectura al final debe cortar en 10");
    /* escribir en el RomFS: error */
    cmd[0] = 0x08030102u; cmd[1] = 0; cmd[2] = 0; cmd[3] = 4; cmd[4] = 0; cmd[5] = IPC_DESC_MAPEADO(4, 1); cmd[6] = BUF;
    enviar(h_rom);
    CHECK(cmd[1] != RES_OK, "escribir en el RomFS debe fallar");
    cmd[0] = 0x08080000u; enviar(h_rom);
    CHECK(cmd[0] == 0x08080040u && cmd[1] == RES_OK, "Close RomFS");

    /* RomFS por OpenArchive(3) + OpenFile */
    cmd[0] = 0x080C00C2u; cmd[1] = 3; cmd[2] = 1; cmd[3] = 1; cmd[4] = IPC_DESC_ESTATICO(1, 0); cmd[5] = BUF + 0x440;
    enviar(h_fs);
    CHECK(cmd[0] == 0x080C00C0u && cmd[1] == RES_OK, "OpenArchive(3)");
    u32 a3lo = cmd[2], a3hi = cmd[3];
    cmd[0] = 0x080201C2u; cmd[1] = 0; cmd[2] = a3lo; cmd[3] = a3hi; cmd[4] = 2; cmd[5] = 12; cmd[6] = 1; cmd[7] = 0;
    cmd[8] = IPC_DESC_ESTATICO(12, 0); cmd[9] = ruta_rom;
    enviar(h_fs);
    CHECK(cmd[1] == RES_OK && cmd[3], "OpenFile(archive 3, RomFS)");
    { u32 h2 = cmd[3]; u32 c0; fs_leer(h2, 0, 4, BUF, &res); sis_copiar_de_juego(&c0, BUF, 4); CHECK(c0 == 0x28, "OpenFile(RomFS) lee la misma imagen"); }

    /* ---------------- fs:USER: guardado */
    #define OPEN_ARCHIVE_4() do { cmd[0] = 0x080C00C2u; cmd[1] = 4; cmd[2] = 1; cmd[3] = 1; cmd[4] = IPC_DESC_ESTATICO(1, 0); cmd[5] = BUF + 0x440; enviar(h_fs); } while (0)
    OPEN_ARCHIVE_4();
    CHECK(cmd[1] == 0xC8A04554u, "guardado sin formatear: 0x%08X (esperado 0xC8A04554)", cmd[1]);
    cmd[0] = 0x084C0242u; cmd[1] = 4; cmd[2] = 1; cmd[3] = 1; cmd[4] = 0x40; cmd[5] = 10; cmd[6] = 10; cmd[7] = 10; cmd[8] = 10; cmd[9] = 0;
    cmd[10] = IPC_DESC_ESTATICO(1, 0); cmd[11] = BUF + 0x440;
    enviar(h_fs);
    CHECK(cmd[0] == 0x084C0040u && cmd[1] == RES_OK, "FormatSaveData");
    cmd[0] = 0x084500C2u; cmd[1] = 4; cmd[2] = 1; cmd[3] = 1; cmd[4] = IPC_DESC_ESTATICO(1, 0); cmd[5] = BUF + 0x440;
    enviar(h_fs);
    CHECK(cmd[1] == RES_OK && cmd[2] == 0x40 * 0x200 && cmd[3] == 10 && cmd[4] == 10, "GetFormatInfo: %u %u %u", cmd[2], cmd[3], cmd[4]);
    OPEN_ARCHIVE_4();
    CHECK(cmd[1] == RES_OK, "OpenArchive(4) formateado");
    u32 a4lo = cmd[2], a4hi = cmd[3];

    u32 rs = BUF + 0x500, ls = ruta_ascii(rs, "/save.bin");
    #define CREATE_FILE() do { cmd[0] = 0x08080202u; cmd[1] = 0; cmd[2] = a4lo; cmd[3] = a4hi; cmd[4] = 3; cmd[5] = ls; cmd[6] = 0; cmd[7] = 0x100; cmd[8] = 0; \
        cmd[9] = IPC_DESC_ESTATICO(ls, 0); cmd[10] = rs; enviar(h_fs); } while (0)
    CREATE_FILE();
    CHECK(cmd[0] == 0x08080040u && cmd[1] == RES_OK, "CreateFile /save.bin: 0x%08X", cmd[1]);
    CREATE_FILE();
    CHECK(cmd[1] == 0xC82044B4u, "CreateFile repetido: 0x%08X", cmd[1]);

    #define OPEN_FILE(dir, largo, tipo, modo) do { cmd[0] = 0x080201C2u; cmd[1] = 0; cmd[2] = a4lo; cmd[3] = a4hi; cmd[4] = (tipo); cmd[5] = (largo); cmd[6] = (modo); cmd[7] = 0; \
        cmd[8] = IPC_DESC_ESTATICO((largo), 0); cmd[9] = (dir); enviar(h_fs); } while (0)
    OPEN_FILE(rs, ls, 3, 3);
    CHECK(cmd[1] == RES_OK && cmd[3], "OpenFile /save.bin RW");
    u32 h_sav = cmd[3];
    const char msg[16] = "HOLA MARIO 3DL!";
    sis_copiar_a_juego(BUF + 0x600, msg, 16);
    cmd[0] = 0x08030102u; cmd[1] = 0x20; cmd[2] = 0; cmd[3] = 16; cmd[4] = 1; cmd[5] = IPC_DESC_MAPEADO(16, 1); cmd[6] = BUF + 0x600;
    enviar(h_sav);
    CHECK(cmd[0] == 0x08030082u && cmd[1] == RES_OK && cmd[2] == 16, "Write: 0x%08X %u", cmd[1], cmd[2]);
    cmd[0] = 0x08040000u; enviar(h_sav);
    CHECK(cmd[2] == 0x100 && cmd[3] == 0, "GetSize guardado = 0x%X", cmd[2]);
    CHECK(fs_leer(h_sav, 0x20, 16, BUF + 0x700, &res) == 16, "leer lo escrito");
    { char back[16]; sis_copiar_de_juego(back, BUF + 0x700, 16); CHECK(memcmp(back, msg, 16) == 0, "lo leido no es lo escrito"); }
    cmd[0] = 0x08080000u; enviar(h_sav);
    {   /* el archivo del anfitrion tiene el dato en 0x20 */
        snprintf(r, sizeof r, "%s\\save.bin", guardado);
        FILE *f = fopen(r, "rb"); char x[16] = {0};
        CHECK(f != NULL, "no existe %s", r);
        if (f) { fseek(f, 0x20, SEEK_SET); size_t k = fread(x, 1, 16, f); fclose(f); CHECK(k == 16 && memcmp(x, msg, 16) == 0, "el archivo del anfitrion no tiene el dato"); }
    }
    /* UTF-16, solo lectura */
    {
        const char *s = "/save.bin"; u32 ru = BUF + 0x800, n = (u32)strlen(s);
        for (u32 i = 0; i <= n; i++) W16(ru + 2 * i, (u8)s[i]);
        OPEN_FILE(ru, 2 * (n + 1), 4, 1);
        CHECK(cmd[1] == RES_OK, "OpenFile UTF-16");
        u32 h = cmd[3];
        cmd[0] = 0x08030102u; cmd[1] = 0; cmd[2] = 0; cmd[3] = 4; cmd[4] = 0; cmd[5] = IPC_DESC_MAPEADO(4, 1); cmd[6] = BUF;
        enviar(h);
        CHECK(cmd[1] != RES_OK, "escribir en un archivo abierto solo lectura debe fallar");
    }
    { u32 l = ruta_ascii(BUF + 0x900, "/no.bin"); OPEN_FILE(BUF + 0x900, l, 3, 1); CHECK(cmd[1] == 0xC8804470u, "archivo inexistente: 0x%08X", cmd[1]); }
    { u32 l = ruta_ascii(BUF + 0x900, "/../fuera.bin"); OPEN_FILE(BUF + 0x900, l, 3, 7); CHECK(cmd[1] == 0xE0E046BEu, "ruta con ..: 0x%08X", cmd[1]); }
    /* directorio */
    {
        u32 l = ruta_ascii(BUF + 0x900, "/");
        cmd[0] = 0x080B0102u; cmd[1] = a4lo; cmd[2] = a4hi; cmd[3] = 3; cmd[4] = l; cmd[5] = IPC_DESC_ESTATICO(l, 0); cmd[6] = BUF + 0x900;
        enviar(h_fs);
        CHECK(cmd[1] == RES_OK && cmd[3], "OpenDirectory /");
        u32 hd = cmd[3];
        cmd[0] = 0x08010042u; cmd[1] = 4; cmd[2] = IPC_DESC_MAPEADO(4 * 0x228, 2); cmd[3] = BUF + 0x1000;
        enviar(hd);
        u8 e[0x228]; sis_copiar_de_juego(e, BUF + 0x1000, sizeof e);
        u64 t; memcpy(&t, e + 0x220, 8);
        CHECK(cmd[1] == RES_OK && cmd[2] == 1 && e[0] == 's' && e[2] == 'a' && t == 0x100, "DirRead: %u entradas, '%c', tam %llu", cmd[2], e[0], (unsigned long long)t);
    }

    /* ---------------- APT:U */
    cmd[0] = 0x00020080u; cmd[1] = 0x300; cmd[2] = 0;
    enviar(h_apt);
    CHECK(cmd[0] == 0x00020043u, "APT Initialize cab 0x%08X", cmd[0]);
    CHECK(cmd[1] == RES_OK && cmd[2] == IPC_DESC_COPIA(2) && sis_es_evento(sis_obj_de_handle(cmd[3])) && sis_es_evento(sis_obj_de_handle(cmd[4])), "APT Initialize: 2 eventos");
    cmd[0] = 0x00030040u; cmd[1] = 0; enviar(h_apt);
    CHECK(cmd[1] == RES_OK, "APT Enable");
    W32(SIS_TLS + 0x180, IPC_DESC_ESTATICO(0x100, 0)); W32(SIS_TLS + 0x184, BUF + 0x3000);
    cmd[0] = 0x000E0080u; cmd[1] = 0x300; cmd[2] = 0x100; enviar(h_apt);
    CHECK(cmd[0] == IPC_CAB(0xE, 4, 4) && cmd[1] == RES_OK && cmd[2] == 0x101 && cmd[3] == 1 && cmd[5] == IPC_DESC_MOVER(1) && cmd[8] == BUF + 0x3000,
          "GlanceParameter: despertar desde HOME (0x%X 0x%X)", cmd[2], cmd[3]);
    cmd[0] = 0x000D0080u; cmd[1] = 0x300; cmd[2] = 0x100; enviar(h_apt);
    CHECK(cmd[1] == RES_OK && cmd[3] == 1, "ReceiveParameter");
    cmd[0] = 0x000D0080u; cmd[1] = 0x300; cmd[2] = 0x100; enviar(h_apt);
    CHECK(cmd[1] != RES_OK, "ReceiveParameter sin parametro pendiente debe fallar");

    /* ---------------- cfg:u, dsp, ndm (no implementado) */
    W8(BUF + 0x50, 0xEE);
    cmd[0] = 0x00010082u; cmd[1] = 1; cmd[2] = 0x000A0002u; cmd[3] = IPC_DESC_MAPEADO(1, 2); cmd[4] = BUF + 0x50;
    enviar(h_cfg);
    CHECK(cmd[0] == 0x00010042u && cmd[1] == RES_OK && R8(BUF + 0x50) == 1 && cmd[4] == BUF + 0x50, "cfg idioma = %u", R8(BUF + 0x50));
    cmd[0] = 0x00160000u; enviar(h_dsp);
    CHECK(cmd[0] == 0x00160042u && sis_es_evento(sis_obj_de_handle(cmd[3])), "DSP GetSemaphoreEventHandle");
    cmd[0] = 0x000C0040u; cmd[1] = 0x1000; enviar(h_dsp);
    CHECK(cmd[2] == 0x1FF42000u, "DSP ConvertProcessAddressFromDspDram 0x%08X", cmd[2]);
    u32 antes = ipc_sin_implementar;
    cmd[0] = 0x00770000u; enviar(h_ndm);
    CHECK(cmd[0] == 0x00770040u && cmd[1] == RES_OK && ipc_sin_implementar == antes + 1, "comando desconocido: registrado y \"todo bien\"");
    cmd[0] = 0x00770000u; enviar(h_ndm);
    CHECK(ipc_sin_implementar == antes + 1, "se registra una sola vez");

    /* ---------------- servicios reales enchufados (enchufes.c), si se compilaron */
    {
        u32 h_gsp = hs[3], h_hid0 = hs[2];
        cmd[0] = 0x000A0000u; enviar(h_hid0);
        CHECK(cmd[0] == 0x000A0047u && cmd[1] == RES_OK && cmd[2] == IPC_DESC_COPIA(6) && sis_obj_de_handle(cmd[3]) && sis_es_evento(sis_obj_de_handle(cmd[8])),
              "hid GetIPCHandles: 0x%08X", cmd[0]);
        SisObj *ev = sis_evento_nuevo(0);
        u32 he = sis_handle_nuevo(ev);
        cmd[0] = 0x00130042u; cmd[1] = 1; cmd[2] = IPC_DESC_COPIA(1); cmd[3] = he; enviar(h_gsp);
        CHECK(cmd[0] == 0x00130082u && cmd[1] == 0x2A07u && sis_obj_de_handle(cmd[4]), "gsp RegisterInterruptRelayQueue: 0x%08X 0x%08X", cmd[0], cmd[1]);
#ifdef SIS_CON_DSP
        cmd[0] = 0x00010040u; cmd[1] = 0; enviar(h_dsp);
        CHECK(cmd[0] == 0x00010080u && cmd[1] == RES_OK, "dsp real RecvData");
        CHECK(sis_fisica_a_host(0x1FF00000u, 0x80000u) == P(0x1FF00000u), "RAM del DSP mapeada en 0x1FF00000");
#endif
#if defined(SIS_CON_HID) || defined(SIS_CON_GSP) || defined(SIS_CON_DSP)
        printf("servicios reales enchufados:%s%s%s\n",
#ifdef SIS_CON_HID
               " hid",
#else
               "",
#endif
#ifdef SIS_CON_GSP
               " gsp",
#else
               "",
#endif
#ifdef SIS_CON_DSP
               " dsp"
#else
               ""
#endif
        );
#endif
    }

    /* ---------------- enchufe: reemplazar hid:USER */
    ipc_registrar("hid:USER", prueba_eco);
    u32 h_hid = obtener_servicio(srv, "hid:USER", &res);
    cmd[0] = 0x000A0000u; enviar(h_hid);
    CHECK(ultima.ses && ultima.id == 0x000A && strcmp(ultima.ses->nombre, "hid:USER") == 0, "hid:USER reemplazado por ipc_registrar");

    printf("%s (%d pruebas, %d fallos)\n", fallos ? "FALLA" : "OK", pruebas, fallos);
    return fallos ? 1 : 0;
}
