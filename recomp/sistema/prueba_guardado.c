/* Prueba del guardado (fs:USER archives 4/6/7/8), de los applets de APT:U y de cecd (agente S, 9 oct).
 * Secuencias de comandos como las que manda el juego (cabeceras del censo extraido\ipc_comandos.tsv) y los codigos de
 * error EXACTOS de Horizon (el juego decide "crear archivo nuevo" segun ellos).
 *   py -m ziglang cc -target x86_64-windows-gnu -O2 -Wall -Wextra -Irecomp\runtime recomp\sistema\sistema.c
 *      recomp\sistema\prueba_guardado.c -o recomp\build\prueba_guardado.exe
 *   recomp\build\prueba_guardado.exe
 * Sabotajes (la prueba debe FALLAR): -DSABOTAJE_GUARDADO_CODIGO (la SharedExtSaveData inexistente devuelve el codigo de
 * la ExtSaveData normal), -DSABOTAJE_APT_HANDLE (Glance/Receive dan siempre el mismo handle: el juego lo cierra y el
 * siguiente MapMemoryBlock cae, caso real de P), -DSABOTAJE_FS_OFFSET (lectura corrida 16 bytes). */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "sistema.h"

u8 *rt_pagina[1u << 20];
void rt_llamar(CPU *c, u32 addr) { (void)c; (void)addr; }

static int fallos, pruebas;
#define CHECK(c, ...) do { pruebas++; if (!(c)) { fallos++; printf("FALLA %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static CPU cpu;
static u32 *cmd;
#define BUF   0x08000000u
#define BUF_TAM 0x00100000u

static u32 svc(u32 num, u32 r0) { cpu.r[0] = r0; sis_svc_num(&cpu, num, 0x00100000u); return cpu.r[0]; }
static u32 enviar(u32 h) { return svc(0x32, h); }
static u32 cerrar(u32 h) { return svc(0x23, h); }

static u32 servicio(u32 srv, const char *nombre)
{
    memset(cmd, 0, 0x100);
    cmd[0] = 0x00050100u; memcpy(&cmd[1], nombre, strlen(nombre)); cmd[3] = (u32)strlen(nombre);
    enviar(srv);
    CHECK(cmd[1] == RES_OK, "GetServiceHandle(%s) 0x%08X", nombre, cmd[1]);
    return cmd[3];
}

static u32 ruta(u32 dir, const char *s) { sis_copiar_a_juego(dir, s, (u32)strlen(s) + 1); return (u32)strlen(s) + 1; }

#define RA 0x08000400u   /* ruta del archive */
#define RF 0x08000500u   /* ruta del archivo */

/* OpenArchive(id, ruta binaria {medio, bajo, alto}) o vacia (ext=0) -> resultado; handle en *h */
static u32 abrir_archive(u32 fs, u32 id, int binaria, u32 bajo, u32 alto, u64 *h)
{
    u32 b[3] = { 0, bajo, alto };
    sis_copiar_a_juego(RA, b, 12);
    cmd[0] = 0x080C00C2u; cmd[1] = id; cmd[2] = binaria ? 2 : 1; cmd[3] = binaria ? 12 : 1;
    cmd[4] = IPC_DESC_ESTATICO(binaria ? 12 : 1, 0); cmd[5] = RA;
    enviar(fs);
    CHECK(cmd[0] == 0x080C00C0u, "OpenArchive cabecera 0x%08X", cmd[0]);
    *h = (u64)cmd[2] | ((u64)cmd[3] << 32);
    return cmd[1];
}

static u32 abrir_archivo(u32 fs, u64 a, const char *r, u32 modo, u32 *h)
{
    u32 n = ruta(RF, r);
    cmd[0] = 0x080201C2u; cmd[1] = 0; cmd[2] = (u32)a; cmd[3] = (u32)(a >> 32); cmd[4] = 3; cmd[5] = n; cmd[6] = modo; cmd[7] = 0;
    cmd[8] = IPC_DESC_ESTATICO(n, 0); cmd[9] = RF;
    enviar(fs);
    CHECK(cmd[0] == 0x08020042u, "OpenFile cabecera 0x%08X", cmd[0]);
    *h = cmd[3];
    return cmd[1];
}

/* operacion de ruta sobre un archive: CreateFile(0x808, con tam) / CreateDirectory 0x809 / DeleteFile 0x804 / DeleteDirectory 0x806/0x807 */
static u32 op_ruta(u32 fs, u32 op, u64 a, const char *r, u64 tam)
{
    u32 n = ruta(RF, r), w;
    memset(cmd, 0, 0x100);
    cmd[1] = 0; cmd[2] = (u32)a; cmd[3] = (u32)(a >> 32); cmd[4] = 3; cmd[5] = n;
    if (op == 0x0808) { cmd[0] = 0x08080202u; cmd[6] = 0; cmd[7] = (u32)tam; cmd[8] = (u32)(tam >> 32); w = 9; }
    else if (op == 0x0809) { cmd[0] = 0x08090182u; cmd[6] = 0; w = 7; }
    else { cmd[0] = IPC_CAB(op, 5, 2); w = 6; }
    cmd[w] = IPC_DESC_ESTATICO(n, 0); cmd[w + 1] = RF;
    enviar(fs);
    return cmd[1];
}

static u32 escribir(u32 h, u64 off, const void *d, u32 n, u32 *hechos)
{
    sis_copiar_a_juego(BUF + 0x2000, d, n);
    cmd[0] = 0x08030102u; cmd[1] = (u32)off; cmd[2] = (u32)(off >> 32); cmd[3] = n; cmd[4] = 1;
    cmd[5] = IPC_DESC_MAPEADO(n, 1); cmd[6] = BUF + 0x2000;
    enviar(h);
    *hechos = cmd[2];
    return cmd[1];
}

static u32 leer(u32 h, u64 off, void *d, u32 n, u32 *hechos)
{
    cmd[0] = 0x080200C2u; cmd[1] = (u32)off; cmd[2] = (u32)(off >> 32); cmd[3] = n;
    cmd[4] = IPC_DESC_MAPEADO(n, 2); cmd[5] = BUF + 0x3000;
    enviar(h);
    *hechos = cmd[2];
    if (cmd[1] == RES_OK) sis_copiar_de_juego(d, BUF + 0x3000, cmd[2]);
    return cmd[1];
}

static void cerrar_archivo(u32 h) { cmd[0] = 0x08080000u; enviar(h); }

static void borrar_arbol(const char *dir)
{
    char p[MAX_PATH + 4], r[MAX_PATH * 2]; WIN32_FIND_DATAA w;
    snprintf(p, sizeof p, "%s\\*", dir);
    HANDLE fh = FindFirstFileA(p, &w);
    if (fh != INVALID_HANDLE_VALUE) {
        do {
            if (!strcmp(w.cFileName, ".") || !strcmp(w.cFileName, "..")) continue;
            snprintf(r, sizeof r, "%s\\%s", dir, w.cFileName);
            if (w.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) { borrar_arbol(r); RemoveDirectoryA(r); } else DeleteFileA(r);
        } while (FindNextFileA(fh, &w));
        FindClose(fh);
    }
}

/* APT: Glance/Receive -> resultado; remitente, senal, tam, handle */
static u32 apt_param(u32 apt, u32 cual, u32 *rem, u32 *senal, u32 *tam, u32 *h)
{
    W32(SIS_TLS + 0x180, IPC_DESC_ESTATICO(0x1000, 0)); W32(SIS_TLS + 0x184, BUF + 0x8000);
    cmd[0] = IPC_CAB(cual, 2, 0); cmd[1] = 0x300; cmd[2] = 0x1000;
    enviar(apt);
    *rem = cmd[2]; *senal = cmd[3]; *tam = cmd[4]; *h = cmd[6];
    return cmd[1];
}

static u32 apt_enviar_param(u32 apt, u32 org, u32 dst, u32 senal, const void *b, u32 n)
{
    sis_copiar_a_juego(BUF + 0x9000, b, n);
    cmd[0] = 0x000C0104u; cmd[1] = org; cmd[2] = dst; cmd[3] = senal; cmd[4] = n;
    cmd[5] = IPC_DESC_COPIA(1); cmd[6] = 0; cmd[7] = IPC_DESC_ESTATICO(n, 0); cmd[8] = BUF + 0x9000;
    enviar(apt);
    return cmd[1];
}

static u32 apt_simple(u32 apt, u32 id, u32 arg) { cmd[0] = IPC_CAB(id, 1, 0); cmd[1] = arg; enviar(apt); return cmd[1]; }

static u32 apt_start(u32 apt, u32 applet, const void *b, u32 n)
{
    sis_copiar_a_juego(BUF + 0x9000, b, n);
    cmd[0] = 0x001E0084u; cmd[1] = applet; cmd[2] = n; cmd[3] = IPC_DESC_COPIA(1); cmd[4] = 0;
    cmd[5] = IPC_DESC_ESTATICO(n, 0); cmd[6] = BUF + 0x9000;
    enviar(apt);
    return cmd[1];
}

/* Wrap(0x46)/Unwrap(0x47)(tam_out, tam_in, off_nonce, tam_nonce, in R, out W) */
static u32 apt_wrap(u32 apt, u32 id, u32 dir_in, u32 tin, u32 dir_out, u32 tout, u32 off, u32 tn)
{
    cmd[0] = IPC_CAB(id, 4, 4); cmd[1] = tout; cmd[2] = tin; cmd[3] = off; cmd[4] = tn;
    cmd[5] = IPC_DESC_MAPEADO(tin, 1); cmd[6] = dir_in; cmd[7] = IPC_DESC_MAPEADO(tout, 2); cmd[8] = dir_out;
    enviar(apt);
    return cmd[1];
}

int main(void)
{
    char guardado[MAX_PATH], r[MAX_PATH * 2];
    GetTempPathA(sizeof guardado, guardado);
    strcat(guardado, "sm3dl_prueba_guardado_S");
    CreateDirectoryA(guardado, NULL);
    borrar_arbol(guardado);

    sis_iniciar();
    fs_configurar(NULL, guardado);
    sis_mapear(BUF, BUF_TAM);
    cpu.tls = SIS_TLS;
    cmd = (u32 *)P(SIS_TLS + 0x80);

    sis_copiar_a_juego(BUF, "srv:", 5);
    cpu.r[1] = BUF;
    CHECK(svc(0x2D, 0) == RES_OK, "ConnectToPort(srv:)");
    u32 srv = cpu.r[1];
    u32 fs = servicio(srv, "fs:USER"), apt = servicio(srv, "APT:U"), cecd = servicio(srv, "cecd:u");
    for (const char **n = (const char *[]){ "ptm:u", "ac:u", "frd:u", "gsp::Lcd", "boss:U", "news:u", "cam:u", "y2r:u", "ir:USER", NULL }; *n; n++)
        servicio(srv, *n);
    u64 a, a7, a4;
    u32 h, n;

    /* ---------------- archives que no existen: el codigo decide si el juego crea/formatea */
    CHECK(abrir_archive(fs, 4, 0, 0, 0, &a) == 0xC8A04554u, "SaveData sin formatear: 0x%08X (esperado NotFormatted 0xC8A04554)", cmd[1]);
    cmd[0] = 0x084500C2u; cmd[1] = 4; cmd[2] = 1; cmd[3] = 1; cmd[4] = IPC_DESC_ESTATICO(1, 0); cmd[5] = RA; enviar(fs);
    CHECK(cmd[0] == 0x08450140u && cmd[1] == 0xC8A04554u, "GetFormatInfo sin formatear: 0x%08X", cmd[1]);
    CHECK(abrir_archive(fs, 7, 1, 0x12345678u, 0, &a) == 0xC8A04554u, "SharedExtSaveData inexistente: 0x%08X (esperado 0xC8A04554)", cmd[1]);
    CHECK(abrir_archive(fs, 6, 1, 0x00001234u, 0, &a) == 0xC8A04478u, "ExtSaveData inexistente: 0x%08X (esperado 0xC8A04478)", cmd[1]);
    CHECK(abrir_archive(fs, 8, 1, 0x00020000u, 0, &a) == 0xC8804478u, "SystemSaveData inexistente: 0x%08X (esperado 0xC8804478)", cmd[1]);
    CHECK(abrir_archive(fs, 0x1234, 0, 0, 0, &a) == 0xC8804478u, "archive desconocido: 0x%08X", cmd[1]);
    cmd[0] = 0x083F00C0u; cmd[1] = 0; cmd[2] = 0x1234; cmd[3] = 0; enviar(fs);
    CHECK(cmd[1] == 0xC8A04478u, "GetExtDataBlockSize de extdata inexistente: 0x%08X", cmd[1]);

    /* ---------------- SharedExtSaveData F000000B: existe (monedas de juego), tamano fijo */
    CHECK(abrir_archive(fs, 7, 1, 0xF000000Bu, 0, &a7) == RES_OK && a7, "Shared F000000B: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a7, "/gamecoin.dat", 1, &h) == RES_OK && h, "abrir gamecoin.dat: 0x%08X", cmd[1]);
    { u8 g[0x20] = {0}; leer(h, 0, g, 0x20, &n); u32 magia; memcpy(&magia, g, 4);
      CHECK(n == 0x14 && magia == 0x4F00, "gamecoin.dat: %u bytes, magia 0x%X", n, magia); }
    CHECK(escribir(h, 0x10, "12345678", 8, &n) == 0xE0E046C1u, "extdata: escribir mas alla del final: 0x%08X (esperado WriteBeyondEnd)", cmd[1]);
    CHECK(escribir(h, 0x4, "\x07\x00", 2, &n) == RES_OK && n == 2, "extdata: escribir dentro: 0x%08X", cmd[1]);
    cerrar_archivo(h);
    CHECK(abrir_archivo(fs, a7, "/nuevo.dat", 6, &h) == 0xE0C046F8u, "extdata: abrir con crear: 0x%08X (esperado UnsupportedOpenFlags)", cmd[1]);
    CHECK(op_ruta(fs, 0x0808, a7, "/vacio.dat", 0) == 0xE0C046F8u, "extdata: CreateFile de 0 bytes: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0808, a7, "/CFL_DB.dat", 0x100) == RES_OK, "extdata: CreateFile CFL_DB.dat: 0x%08X", cmd[1]);
    cmd[0] = 0x083F00C0u; cmd[1] = 0; cmd[2] = 0xF000000Bu; cmd[3] = 0; enviar(fs);
    CHECK(cmd[0] == 0x083F0180u && cmd[1] == RES_OK && cmd[6] == 0x1000, "GetExtDataBlockSize: 0x%08X bloque 0x%X", cmd[1], cmd[6]);

    /* ---------------- SaveData: formatear y la semantica de rutas/modos */
    cmd[0] = 0x084C0242u; cmd[1] = 4; cmd[2] = 1; cmd[3] = 1; cmd[4] = 0x200; cmd[5] = 0; cmd[6] = 1; cmd[7] = 1; cmd[8] = 1; cmd[9] = 1;
    cmd[10] = IPC_DESC_ESTATICO(1, 0); cmd[11] = RA; enviar(fs);
    CHECK(cmd[0] == 0x084C0040u && cmd[1] == RES_OK, "FormatSaveData: 0x%08X", cmd[1]);
    cmd[0] = 0x084C0242u; cmd[1] = 7; enviar(fs);
    CHECK(cmd[1] == 0xE0E046BEu, "FormatSaveData de otra archive: 0x%08X (esperado InvalidPath)", cmd[1]);
    cmd[0] = 0x084500C2u; cmd[1] = 4; cmd[2] = 1; cmd[3] = 1; cmd[4] = IPC_DESC_ESTATICO(1, 0); cmd[5] = RA; enviar(fs);
    CHECK(cmd[1] == RES_OK && cmd[2] == 0x40000 && cmd[3] == 0 && cmd[4] == 1 && cmd[5] == 1, "GetFormatInfo: %X %u %u %u", cmd[2], cmd[3], cmd[4], cmd[5]);
    CHECK(abrir_archive(fs, 4, 0, 0, 0, &a4) == RES_OK, "SaveData formateado: 0x%08X", cmd[1]);

    CHECK(abrir_archivo(fs, a4, "/GameData.bin", 1, &h) == 0xC8804470u, "archivo que no existe: 0x%08X (FileNotFound)", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/GameData.bin", 0, &h) == 0xE0C046F8u, "modo 0: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/GameData.bin", 4, &h) == 0xE0C046F8u, "crear sin escribir: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/dir/x.bin", 1, &h) == 0xC8804471u, "carpeta que no existe: 0x%08X (PathNotFound)", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/.formato.bin", 1, &h) == 0xE0E046BEu, "nombre reservado de la capa: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/a:b", 1, &h) == 0xE0E046BEu, "caracter prohibido: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/../x", 1, &h) == 0xE0E046BEu, "fuera de la raiz: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0809, a4, "/dir", 0) == RES_OK, "CreateDirectory /dir: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0809, a4, "/dir", 0) == 0xC82044B9u, "CreateDirectory repetido: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/dir", 1, &h) == 0xE0C04702u, "abrir una carpeta como archivo: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0808, a4, "/dir/x.bin", 0x40) == RES_OK, "CreateFile /dir/x.bin: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0808, a4, "/dir/x.bin", 0x40) == 0xC82044B4u, "CreateFile repetido: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/dir/x.bin/y", 1, &h) == 0xE0C04702u, "archivo en medio de la ruta: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/./dir//x.bin", 3, &h) == RES_OK, "ruta con . y //: 0x%08X", cmd[1]);
    cerrar_archivo(h);
    CHECK(abrir_archivo(fs, a4, "/nuevo.bin", 7, &h) == RES_OK, "abrir con crear: 0x%08X", cmd[1]);
    CHECK(escribir(h, 0x100, "X", 1, &n) == RES_OK && n == 1, "savedata crece al escribir lejos");
    cmd[0] = 0x08040000u; enviar(h); CHECK(cmd[2] == 0x101, "GetSize 0x%X", cmd[2]);
    cerrar_archivo(h);
    CHECK(abrir_archivo(fs, a4, "/nuevo.bin", 1, &h) == RES_OK, "abrir solo lectura");
    CHECK(escribir(h, 0, "Y", 1, &n) == 0xC92044E6u, "escribir en solo lectura: 0x%08X (InvalidOpenFlags)", cmd[1]);
    cerrar_archivo(h);

    /* listado: no se ven .formato.bin ni .extdata */
    {
        u32 l = ruta(RF, "/");
        cmd[0] = 0x080B0102u; cmd[1] = (u32)a4; cmd[2] = (u32)(a4 >> 32); cmd[3] = 3; cmd[4] = l; cmd[5] = IPC_DESC_ESTATICO(l, 0); cmd[6] = RF;
        enviar(fs);
        CHECK(cmd[1] == RES_OK && cmd[3], "OpenDirectory /: 0x%08X", cmd[1]);
        u32 hd = cmd[3];
        cmd[0] = 0x08010042u; cmd[1] = 8; cmd[2] = IPC_DESC_MAPEADO(8 * 0x228, 2); cmd[3] = BUF + 0x10000; enviar(hd);
        CHECK(cmd[1] == RES_OK && cmd[2] == 2, "DirRead: %u entradas (esperadas 2: dir y nuevo.bin)", cmd[2]);
        int vio_dir = 0, vio_nuevo = 0;
        for (u32 k = 0; k < cmd[2]; k++) {
            u8 e[0x228]; sis_copiar_de_juego(e, BUF + 0x10000 + k * 0x228, sizeof e);
            if (e[0] == 'd' && e[2] == 'i' && e[0x21C] == 1) vio_dir = 1;
            if (e[0] == 'n' && e[0x21C] == 0 && !memcmp(e + 0x20C, "NUEVO", 5) && !memcmp(e + 0x216, "BIN", 3)) vio_nuevo = 1;
        }
        CHECK(vio_dir && vio_nuevo, "DirRead: carpeta 'dir' y 'nuevo.bin' (8.3 NUEVO.BIN)");
        cmd[0] = 0x08020000u; enviar(hd);
        cmd[0] = 0x080B0102u; cmd[1] = (u32)a4; cmd[2] = (u32)(a4 >> 32); l = ruta(RF, "/nada"); cmd[3] = 3; cmd[4] = l; cmd[5] = IPC_DESC_ESTATICO(l, 0); cmd[6] = RF;
        enviar(fs);
        CHECK(cmd[1] == 0xC8804471u, "OpenDirectory inexistente: 0x%08X", cmd[1]);
    }
    CHECK(op_ruta(fs, 0x0806, a4, "/dir", 0) == 0xC92044F0u, "DeleteDirectory con contenido: 0x%08X (DirectoryNotEmpty)", cmd[1]);
    CHECK(op_ruta(fs, 0x0807, a4, "/dir", 0) == RES_OK, "DeleteDirectoryRecursively: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0804, a4, "/no.bin", 0) == 0xC8804470u, "DeleteFile inexistente: 0x%08X", cmd[1]);
    CHECK(op_ruta(fs, 0x0804, a4, "/nuevo.bin", 0) == RES_OK, "DeleteFile: 0x%08X", cmd[1]);

    /* ---------------- secuencia del juego (crear GameData.bin), commit y persistencia tras "reiniciar" */
    static u8 datos[18444];
    for (u32 i = 0; i < sizeof datos; i++) datos[i] = (u8)(i * 7 + 3);
    CHECK(op_ruta(fs, 0x0808, a4, "/GameData.bin", sizeof datos) == RES_OK, "CreateFile GameData.bin");
    CHECK(abrir_archivo(fs, a4, "/GameData.bin", 3, &h) == RES_OK, "OpenFile GameData.bin RW");
    for (u32 off = 0; off < sizeof datos; off += 0x1000) {
        u32 t = sizeof datos - off < 0x1000 ? sizeof datos - off : 0x1000;
        CHECK(escribir(h, off, datos + off, t, &n) == RES_OK && n == t, "Write %u", off);
    }
    cerrar_archivo(h);
    cmd[0] = 0x080D0144u; cmd[1] = (u32)a4; cmd[2] = (u32)(a4 >> 32); cmd[3] = 0; cmd[4] = 0; cmd[5] = 0;
    cmd[6] = IPC_DESC_MAPEADO(0, 1); cmd[7] = 0; cmd[8] = IPC_DESC_MAPEADO(0, 2); cmd[9] = 0; enviar(fs);
    CHECK(cmd[0] == 0x080D0040u && cmd[1] == RES_OK, "ControlArchive (commit): 0x%08X", cmd[1]);
    cmd[0] = 0x080E0080u; cmd[1] = (u32)a4; cmd[2] = (u32)(a4 >> 32); enviar(fs);
    CHECK(cmd[1] == RES_OK, "CloseArchive");
    cmd[0] = 0x080D0144u; cmd[1] = (u32)a4; cmd[2] = (u32)(a4 >> 32); enviar(fs);
    CHECK(cmd[1] == 0xC8804465u, "ControlArchive con archive cerrado: 0x%08X (ArchiveNotMounted)", cmd[1]);
    fs_configurar(NULL, guardado);                     /* "reinicio": se vuelve a montar desde el disco */
    CHECK(abrir_archive(fs, 4, 0, 0, 0, &a4) == RES_OK, "SaveData sigue formateado tras reiniciar: 0x%08X", cmd[1]);
    CHECK(abrir_archivo(fs, a4, "/GameData.bin", 1, &h) == RES_OK, "GameData.bin sigue ahi");
    {
        static u8 back[sizeof datos];
        u32 total = 0, k;
        for (u32 off = 0; off < sizeof datos; off += k) { leer(h, off, back + off, 0x1000, &k); if (!k) break; total += k; }
        CHECK(total == sizeof datos && memcmp(back, datos, sizeof datos) == 0, "GameData.bin: %u bytes, contenido %s", total, memcmp(back, datos, sizeof datos) ? "DISTINTO" : "igual");
        snprintf(r, sizeof r, "%s\\GameData.bin", guardado);
        FILE *f = fopen(r, "rb"); size_t t = 0;
        if (f) { t = fread(back, 1, sizeof back, f); fclose(f); }
        CHECK(t == sizeof datos && memcmp(back, datos, sizeof datos) == 0, "el archivo del anfitrion tiene los datos");
    }
    cerrar_archivo(h);

    /* ---------------- APT: parametro de HOME, applets de biblioteca */
    cmd[0] = 0x00020080u; cmd[1] = 0x300; cmd[2] = 0; enviar(apt);
    CHECK(cmd[1] == RES_OK, "APT Initialize");
    u32 rem, senal, tam, ha, hb;
    CHECK(apt_param(apt, 0xD, &rem, &senal, &tam, &ha) == 0xC8A0CFEFu, "Receive sin parametro: 0x%08X (NoData)", cmd[1]);
    apt_simple(apt, 0x3, 0);
    CHECK(apt_param(apt, 0xD, &rem, &senal, &tam, &ha) == RES_OK && rem == 0x101 && senal == 1, "Enable -> despertar de HOME (0x%X, %u)", rem, senal);
    CHECK(apt_simple(apt, 0x16, 0x402) == RES_OK, "PreloadLibraryApplet(0x402)");
    cmd[0] = 0x00090040u; cmd[1] = 0x402; enviar(apt);
    CHECK(cmd[2] == 1, "IsRegistered(0x402) tras Preload");
    u32 captura[8] = { 0x7800 };
    CHECK(apt_enviar_param(apt, 0x300, 0x402, 2, captura, 0x20) == RES_OK, "SendParameter Request al applet");
    CHECK(apt_enviar_param(apt, 0x300, 0x402, 2, captura, 0x20) == 0xC8A0CC02u, "SendParameter con uno pendiente: 0x%08X (ParameterPresent)", cmd[1]);
    CHECK(apt_param(apt, 0xE, &rem, &senal, &tam, &ha) == RES_OK && rem == 0x402 && senal == 3 && ha, "Glance: Response del applet con memoria (0x%X %u h=0x%X)", rem, senal, ha);
    CHECK(cerrar(ha) == RES_OK, "el juego cierra el handle movido del Glance");
    CHECK(apt_param(apt, 0xD, &rem, &senal, &tam, &hb) == RES_OK && hb && sis_obj_de_handle(hb), "Receive da un handle VALIDO tras cerrar el del Glance (0x%X)", hb);
    {   /* MapMemoryBlock del bloque recibido */
        cpu.r[0] = hb; cpu.r[1] = 0x10004000u; cpu.r[2] = 3; cpu.r[3] = 3;
        CHECK(sis_obj_de_handle(hb) != NULL, "el bloque de captura existe");
    }
    u8 cfg_mii[0x104] = {0};
    CHECK(apt_start(apt, 0x402, cfg_mii, sizeof cfg_mii) == RES_OK, "StartLibraryApplet(0x402)");
    CHECK(apt_param(apt, 0xD, &rem, &senal, &tam, &ha) == RES_OK && rem == 0x402 && senal == 0xA && tam == 0x84, "Mii: WakeupByExit con MiiResult (0x%X %u %u)", rem, senal, tam);
    {
        u8 m[0x84]; sis_copiar_de_juego(m, BUF + 0x8000, 0x84);
        u16 c = 0; for (u32 i = 0; i < 0x5E; i++) { c ^= (u16)(m[0x0C + i] << 8); for (int k = 0; k < 8; k++) c = (u16)((c & 0x8000) ? (c << 1) ^ 0x1021 : c << 1); }
        CHECK(m[3] == 0 && m[0x0C] == 3 && ((m[0x6A] << 8) | m[0x6B]) == c, "MiiResult: codigo %u, version %u, crc ok", m[3], m[0x0C]);
    }
    {   /* error/EULA con "Agree" (tipo 5) */
        static u8 eula[0xF80]; eula[0] = 5;
        apt_simple(apt, 0x18, 0x406);
        CHECK(apt_start(apt, 0x406, eula, sizeof eula) == RES_OK, "StartLibraryApplet(0x406)");
        CHECK(apt_param(apt, 0xD, &rem, &senal, &tam, &ha) == RES_OK && rem == 0x406 && senal == 0xA && tam == 0xF80, "EULA: WakeupByExit");
        u8 o[0xF80]; sis_copiar_de_juego(o, BUF + 0x8000, sizeof o);
        CHECK(o[0xF70] == 1 && o[0xF74] == 0x7F && o[0xF75] == 0x7F, "EULA aceptada (resultado %u, %u.%u)", o[0xF70], o[0xF75], o[0xF74]);
    }
    {   /* Wrap / Unwrap */
        u8 plano[0x40]; for (int i = 0; i < 0x40; i++) plano[i] = (u8)(0xA0 + i);
        sis_copiar_a_juego(BUF + 0xA000, plano, 0x40);
        CHECK(apt_wrap(apt, 0x46, BUF + 0xA000, 0x40, BUF + 0xB000, 0x50, 0x10, 12) == RES_OK, "Wrap");
        CHECK(apt_wrap(apt, 0x47, BUF + 0xB000, 0x50, BUF + 0xC000, 0x40, 0x10, 12) == RES_OK, "Unwrap");
        u8 vuelta[0x40]; sis_copiar_de_juego(vuelta, BUF + 0xC000, 0x40);
        CHECK(memcmp(vuelta, plano, 0x40) == 0, "Unwrap(Wrap(x)) == x");
        W8(BUF + 0xB000 + 20, R8(BUF + 0xB000 + 20) ^ 0xFF);
        CHECK(apt_wrap(apt, 0x47, BUF + 0xB000, 0x50, BUF + 0xC000, 0x40, 0x10, 12) == 0xC9010401u, "Unwrap de datos alterados: 0x%08X", cmd[1]);
    }

    /* ---------------- cecd: buzon de StreetPass */
    cmd[0] = 0x000E0000u; enviar(cecd);
    CHECK(cmd[1] == RES_OK && cmd[2] == 1, "GetCecdState = Idle (%u)", cmd[2]);
    cmd[0] = 0x000100C2u; cmd[1] = 0x00054000u; cmd[2] = 2; cmd[3] = 2; cmd[4] = 0x20; cmd[5] = 0; enviar(cecd);
    CHECK(cmd[1] == 0xC88103EFu, "Open MBoxInfo sin buzon: 0x%08X (NoData)", cmd[1]);
    cmd[0] = 0x000100C2u; cmd[1] = 0x00054000u; cmd[2] = 11; cmd[3] = 8 | 4; cmd[4] = 0x20; cmd[5] = 0; enviar(cecd);
    CHECK(cmd[1] == RES_OK, "Open MBoxDir con crear: 0x%08X", cmd[1]);
    cmd[0] = 0x000100C2u; cmd[1] = 0x00054000u; cmd[2] = 2; cmd[3] = 4 | 8; cmd[4] = 0x20; cmd[5] = 0; enviar(cecd);
    CHECK(cmd[1] == RES_OK && cmd[2] == 0, "Open MBoxInfo con buzon: 0x%08X", cmd[1]);
    sis_copiar_a_juego(BUF + 0xD000, "bb\0\0MBOX", 8);
    cmd[0] = 0x00050042u; cmd[1] = 8; cmd[2] = IPC_DESC_MAPEADO(8, 1); cmd[3] = BUF + 0xD000; enviar(cecd);
    CHECK(cmd[1] == RES_OK, "Write MBoxInfo");
    cmd[0] = 0x00020042u; cmd[1] = 0x20; cmd[2] = IPC_DESC_MAPEADO(0x20, 2); cmd[3] = BUF + 0xE000; enviar(cecd);
    CHECK(cmd[1] == RES_OK && cmd[2] == 8 && R8(BUF + 0xE004) == 'M', "Read MBoxInfo: %u bytes", cmd[2]);
    cmd[0] = 0x000A00C4u; cmd[1] = 2; cmd[2] = 1; cmd[3] = 0; cmd[4] = IPC_DESC_MAPEADO(0, 1); cmd[5] = 0; cmd[6] = IPC_DESC_MAPEADO(2, 2); cmd[7] = BUF + 0xE100; enviar(cecd);
    CHECK(cmd[1] == RES_OK && R8(BUF + 0xE100) == 0x7F, "ReadData version de EULA");

    printf("%s (%d pruebas, %d fallos)\n", fallos ? "FALLA" : "OK", pruebas, fallos);
    return fallos ? 1 : 0;
}
