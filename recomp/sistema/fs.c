/* fs:USER real para el port.
 * - Archive 3 (SelfNCCH): el RomFS. El SDK del juego abre la IMAGEN del nivel 3 del RomFS (ruta binaria de 12 bytes,
 *   tipo 0) y la parsea el mismo, asi que aqui se sirve la imagen cruda tal cual esta en la ROM descifrada
 *   (NCCH: offset del RomFS + 0x1000, que es donde empieza el nivel 3). extraido\romfs no sirve para esto: solo se
 *   usa en la prueba para comparar.
 * - Archive 4 (SaveData): una carpeta local (SM3DL_GUARDADO). Sin ".formato.bin" el archive no esta formateado (como
 *   una tarjeta nueva) y el juego llama FormatSaveData.
 * - Archives 6/7 (ExtSaveData / SharedExtSaveData) y 8 (SystemSaveData): subcarpetas .extdata / .sistema (ver abajo).
 * - Archive 9 (SDMC): no hay tarjeta SD.
 * Numeros de comando y forma de las respuestas: documentacion de Horizon (Azahar solo como referencia).
 * Se compila dentro de sistema.c. */
#ifdef SIS_IPC_SEPARADO
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sistema.h"
#endif
#include <io.h>
#include <direct.h>
#include <sys/stat.h>
#include <ctype.h>

/* resultados del modulo FS (nivel | resumen | modulo 17 | descripcion) */
#define FS_RES(desc, resumen, nivel) (((u32)(nivel) << 27) | ((u32)(resumen) << 21) | (17u << 10) | (u32)(desc))
#define FS_NO_FORMATEADO   FS_RES(340, 5, 25)   /* 0xC8A04554 */
#define FS_NO_ENCONTRADO   FS_RES(120, 4, 25)   /* 0xC8804478 */
#define FS_ARCHIVO_NO_HAY  FS_RES(112, 4, 25)   /* 0xC8804470 */
#define FS_RUTA_NO_HAY     FS_RES(113, 4, 25)   /* 0xC8804471 */
#define FS_YA_EXISTE       FS_RES(180, 1, 25)   /* 0xC82044B4 */
#define FS_RUTA_MALA       FS_RES(702, 7, 28)   /* 0xE0E046BE */
#define FS_ARCHIVE_MALO    FS_RES(101, 4, 25)
#define FS_SIN_PERMISO     FS_RES(630, 6, 28)
#define FS_SIN_ROMFS       FS_RES(100, 4, 25)

/* (agente S, 9 oct; codigos verificados contra file_sys/errors.h de Azahar, ver svcs.md) */
#define FS_NO_ENC_ESTADO   FS_RES(120, 5, 25)   /* 0xC8A04478 ExtSaveData que no existe */
#define FS_FLAGS_MALOS     FS_RES(760, 6, 28)   /* 0xE0C046F8 UnsupportedOpenFlags */
#define FS_FLAGS_INVALIDOS FS_RES(230, 9, 25)   /* 0xC92044E6 InvalidOpenFlags (escribir sin permiso) */
#define FS_INESPERADO      FS_RES(770, 6, 28)   /* 0xE0C04702 UnexpectedFileOrDirectory */
#define FS_DIR_YA_EXISTE   FS_RES(185, 1, 25)   /* 0xC82044B9 */
#define FS_DIR_NO_VACIO    FS_RES(240, 9, 25)   /* 0xC92044F0 */
#define FS_MAS_ALLA_FIN    FS_RES(705, 7, 28)   /* 0xE0E046C1 WriteBeyondEnd (extdata de tamano fijo) */

#define FS_ARCH_SELFNCCH 3u
#define FS_ARCH_SAVEDATA 4u
#define FS_ARCH_EXTSAVE  6u
#define FS_ARCH_EXTSAVE_COMP 7u
#define FS_ARCH_SISTEMA  8u
#define FS_ARCH_SDMC     9u

static char fs_ruta_rom[MAX_PATH] = "";
static char fs_ruta_guardado[MAX_PATH] = "";
static FILE *fs_rom;
static u64 fs_lv3_off, fs_lv3_tam;

void fs_configurar(const char *rom, const char *carpeta_guardado)
{
    if (rom) { snprintf(fs_ruta_rom, sizeof fs_ruta_rom, "%s", rom); if (fs_rom) { fclose(fs_rom); fs_rom = NULL; } }
    if (carpeta_guardado) snprintf(fs_ruta_guardado, sizeof fs_ruta_guardado, "%s", carpeta_guardado);
}

static const char *fs_guardado(void)
{
    if (!fs_ruta_guardado[0]) {
        const char *e = getenv("SM3DL_GUARDADO");
        snprintf(fs_ruta_guardado, sizeof fs_ruta_guardado, "%s",
                 e ? e : "C:\\Users\\usuario\\Desktop\\Decopilar\\sm3dl-port\\guardado");
    }
    return fs_ruta_guardado;
}

/* abre la ROM y ubica el nivel 3 del RomFS de la particion 0 (el juego) */
static int fs_abrir_rom(void)
{
    if (fs_rom) return 0;
    if (!fs_ruta_rom[0]) {
        const char *e = getenv("SM3DL_ROM");
        snprintf(fs_ruta_rom, sizeof fs_ruta_rom, "%s",
                 e ? e : "C:\\Users\\usuario\\Desktop\\Decopilar\\Super Mario 3D Land USA.3ds");
    }
    FILE *f = fopen(fs_ruta_rom, "rb");
    if (!f) { fprintf(stderr, "[fs] no se pudo abrir la ROM \"%s\" (variable SM3DL_ROM)\n", fs_ruta_rom); return -1; }
    u8 ncsd[0x200], ncch[0x200];
    u32 p0, rom_off, rom_tam;
    if (fread(ncsd, 1, sizeof ncsd, f) != sizeof ncsd || memcmp(ncsd + 0x100, "NCSD", 4) != 0) goto mala;
    memcpy(&p0, ncsd + 0x120, 4);
    if (_fseeki64(f, (s64)p0 * 0x200, SEEK_SET) || fread(ncch, 1, sizeof ncch, f) != sizeof ncch || memcmp(ncch + 0x100, "NCCH", 4) != 0) goto mala;
    memcpy(&rom_off, ncch + 0x1B0, 4);
    memcpy(&rom_tam, ncch + 0x1B4, 4);
    if (!rom_off || rom_tam * 0x200ull <= 0x1000) goto mala;
    fs_lv3_off = (u64)p0 * 0x200 + (u64)rom_off * 0x200 + 0x1000;
    fs_lv3_tam = (u64)rom_tam * 0x200 - 0x1000;
    {   /* el RomFS debe empezar con la cabecera IVFC */
        char ivfc[4];
        if (_fseeki64(f, fs_lv3_off - 0x1000, SEEK_SET) || fread(ivfc, 1, 4, f) != 4 || memcmp(ivfc, "IVFC", 4) != 0) goto mala;
    }
    fs_rom = f;
    fprintf(stderr, "[fs] RomFS nivel 3 en 0x%llX (+0x%llX) de \"%s\"\n",
            (unsigned long long)fs_lv3_off, (unsigned long long)fs_lv3_tam, fs_ruta_rom);
    return 0;
mala:
    fprintf(stderr, "[fs] \"%s\" no es una ROM descifrada (NCSD/NCCH/IVFC)\n", fs_ruta_rom);
    fclose(f);
    return -1;
}

/* SelfNCCH tipo 2: un archivo del ExeFS de la particion 0 (el juego lo pide al activar StreetPass: P, 10 oct) */
static int fs_exefs_buscar(const u8 *nombre8, u64 *off, u64 *tam)
{
    u8 ncsd[0x200], ncch[0x200], cab[0xA0];
    u32 p0, ex_off;
    if (fs_abrir_rom()) return -1;
    if (_fseeki64(fs_rom, 0, SEEK_SET) || fread(ncsd, 1, sizeof ncsd, fs_rom) != sizeof ncsd) return -1;
    memcpy(&p0, ncsd + 0x120, 4);
    if (_fseeki64(fs_rom, (s64)p0 * 0x200, SEEK_SET) || fread(ncch, 1, sizeof ncch, fs_rom) != sizeof ncch) return -1;
    memcpy(&ex_off, ncch + 0x1A0, 4);
    if (!ex_off) return -1;
    u64 base = (u64)p0 * 0x200 + (u64)ex_off * 0x200;
    if (_fseeki64(fs_rom, (s64)base, SEEK_SET) || fread(cab, 1, sizeof cab, fs_rom) != sizeof cab) return -1;
    for (int k = 0; k < 10; k++) {
        u8 *e = cab + 16 * k;
        if (!e[0] || strncmp((const char *)e, (const char *)nombre8, 8)) continue;
        u32 o, n;
        memcpy(&o, e + 8, 4); memcpy(&n, e + 12, 4);
        *off = base + 0x200 + o; *tam = n;
        return 0;
    }
    return -1;
}

/* ---------------------------------------------------------------- archives abiertos
 * Cada archive abierto guarda su carpeta del anfitrion (raiz). Disposicion bajo la carpeta de guardado (agente S, 9 oct):
 *   <guardado>\                      SaveData (0x4) del juego; ".formato.bin" = formateado (FormatSaveData)
 *   <guardado>\.extdata\HHHHHHHH_LLLLLLLL\   ExtSaveData (0x6) y SharedExtSaveData (0x7) por id de 64 bits
 *   <guardado>\.sistema\HHHHHHHH_LLLLLLLL\   SystemSaveData (0x8)
 * Los nombres que empiezan con "." en la raiz del SaveData son de la capa: no se listan ni se pueden abrir. */
typedef struct { u64 handle; u32 id; int ext; char raiz[MAX_PATH]; } FsArchive;
static FsArchive fs_archives[32];
static u64 fs_sig_archive = 1;

static FsArchive *fs_archive_de(u64 h)
{
    for (int i = 0; i < 32; i++) if (fs_archives[i].handle == h && h) return &fs_archives[i];
    return NULL;
}

static int fs_formateado(void)
{
    char r[MAX_PATH];
    snprintf(r, sizeof r, "%s\\.formato.bin", fs_guardado());
    return _access(r, 0) == 0;
}

static int fs_es_dir(const char *r) { DWORD a = GetFileAttributesA(r); return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY); }

/* crea la carpeta y sus padres */
static void fs_mkdir_p(const char *r)
{
    char t[MAX_PATH];
    snprintf(t, sizeof t, "%s", r);
    for (char *c = t + 3; *c; c++) if (*c == '\\') { *c = 0; _mkdir(t); *c = '\\'; }
    _mkdir(t);
}

/* borra el contenido de una carpeta (recursivo); si saltar_punto, deja las entradas que empiezan con "." */
static void fs_vaciar(const char *dir, int saltar_punto)
{
    char patron[MAX_PATH + 4], r[MAX_PATH * 2];
    WIN32_FIND_DATAA w;
    snprintf(patron, sizeof patron, "%s\\*", dir);
    HANDLE fh = FindFirstFileA(patron, &w);
    if (fh == INVALID_HANDLE_VALUE) return;
    do {
        if (!strcmp(w.cFileName, ".") || !strcmp(w.cFileName, "..")) continue;
        if (saltar_punto && w.cFileName[0] == '.') continue;
        snprintf(r, sizeof r, "%s\\%s", dir, w.cFileName);
        if (w.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) { fs_vaciar(r, 0); RemoveDirectoryA(r); }
        else DeleteFileA(r);
    } while (FindNextFileA(fh, &w));
    FindClose(fh);
}

/* ---------------------------------------------------------------- rutas (LowPath) */
typedef struct { u32 tipo; u8 datos[0x200]; u32 tam; } FsRuta;   /* 1 vacia, 2 binaria, 3 ASCII, 4 UTF-16 */

static int fs_leer_ruta(IpcPeticion *p, u32 indice_estatico, u32 tipo, u32 tam, FsRuta *r)
{
    IpcDesc *d = ipc_desc(p, IPC_D_ESTATICO, indice_estatico);
    r->tipo = tipo;
    r->tam = tam < sizeof r->datos ? tam : sizeof r->datos;
    memset(r->datos, 0, sizeof r->datos);
    if (r->tam && d) sis_copiar_de_juego(r->datos, d->dir, r->tam < d->tam || !d->tam ? r->tam : d->tam);
    return 0;
}

/* Estado de una ruta dentro de un archive (la semantica del PathParser de Horizon: se valida la ruta, luego cada
   componente intermedio tiene que ser carpeta, luego el ultimo). */
enum { FS_HS_INVALIDA = -1, FS_HS_RUTA_NO, FS_HS_ARCHIVO_EN_RUTA, FS_HS_DIR, FS_HS_NO_HAY, FS_HS_ARCHIVO };

static int fs_resolver(const FsArchive *ar, const FsRuta *r, char *host, u32 max)
{
    char txt[0x200], comp[32][0x100];
    u32 n = 0, nc = 0;
    if (r->tipo == 3) {
        for (u32 i = 0; i < r->tam && r->datos[i] && n + 1 < sizeof txt; i++) txt[n++] = (char)r->datos[i];
    } else if (r->tipo == 4) {
        for (u32 i = 0; i + 1 < r->tam && n + 1 < sizeof txt; i += 2) {
            u16 ch = (u16)(r->datos[i] | (r->datos[i + 1] << 8));
            if (!ch) break;
            if (ch > 0x7E) return FS_HS_INVALIDA;   /* el juego solo usa nombres ASCII */
            txt[n++] = (char)ch;
        }
    } else {
        return FS_HS_INVALIDA;
    }
    txt[n] = 0;
    if (txt[0] != '/' || strpbrk(txt, "<>\\|:\"*?")) return FS_HS_INVALIDA;
    for (char *s = txt; *s;) {
        while (*s == '/') s++;
        if (!*s) break;
        char *e = strchr(s, '/');
        size_t L = e ? (size_t)(e - s) : strlen(s);
        if (L >= sizeof comp[0]) return FS_HS_INVALIDA;
        if (L == 1 && s[0] == '.') { /* nada */ }
        else if (L == 2 && s[0] == '.' && s[1] == '.') { if (!nc) return FS_HS_INVALIDA; nc--; }
        else { if (nc == 32) return FS_HS_INVALIDA; memcpy(comp[nc], s, L); comp[nc][L] = 0; nc++; }
        s += L;
    }
    if (ar->id == FS_ARCH_SAVEDATA && nc && comp[0][0] == '.') return FS_HS_INVALIDA;   /* reservado de la capa */
    size_t L = (size_t)snprintf(host, max, "%s", ar->raiz);
    if (!nc) return FS_HS_DIR;
    for (u32 i = 0; i < nc; i++) {
        L += (size_t)snprintf(host + L, max - L, "\\%s", comp[i]);
        if (L >= max) return FS_HS_INVALIDA;
        DWORD a = GetFileAttributesA(host);
        if (i + 1 < nc) {
            if (a == INVALID_FILE_ATTRIBUTES) return FS_HS_RUTA_NO;
            if (!(a & FILE_ATTRIBUTE_DIRECTORY)) return FS_HS_ARCHIVO_EN_RUTA;
        } else {
            if (a == INVALID_FILE_ATTRIBUTES) return FS_HS_NO_HAY;
            return (a & FILE_ATTRIBUTE_DIRECTORY) ? FS_HS_DIR : FS_HS_ARCHIVO;
        }
    }
    return FS_HS_INVALIDA;
}

/* ---------------------------------------------------------------- sesion de archivo */
typedef struct { int romfs; FILE *f; u64 base, tam; int escribir, fijo; char ruta[MAX_PATH]; } FsArchivo;

static u64 fs_tam_archivo(FsArchivo *a)
{
    if (a->romfs) return a->tam;
    fflush(a->f);
    return (u64)_filelengthi64(_fileno(a->f));
}

static void fs_archivo_atender(IpcPeticion *p)
{
    FsArchivo *a = p->ses->datos;
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0802: {                                     /* Read(offset64, tam, buffer mapeado W) -> leidos */
        u64 off = (u64)cmd[1] | ((u64)cmd[2] << 32);
        u32 tam = cmd[3];
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        if (!d || !a->f) { ipc_respuesta(p, 2, 0, FS_SIN_PERMISO); return; }
        if (tam > d->tam) tam = d->tam;
        u64 total = fs_tam_archivo(a);
        u32 n = off >= total ? 0 : (u32)((total - off) < tam ? (total - off) : tam);
#ifdef SABOTAJE_FS_OFFSET
        off += 0x10;   /* lee 16 bytes corrido: la prueba tiene que verlo */
#endif
        u32 hechos = 0;
        if (n) {
            u8 *buf = malloc(n);
            if (_fseeki64(a->f, (s64)(a->base + off), SEEK_SET) == 0) hechos = (u32)fread(buf, 1, n, a->f);
            sis_copiar_a_juego(d->dir, buf, hechos);
            free(buf);
        }
        ipc_respuesta(p, 2, 2, RES_OK);
        cmd[2] = hechos;
        cmd[3] = IPC_DESC_MAPEADO(d->tam, d->extra); cmd[4] = d->dir;
        return;
    }
    case 0x0803: {                                     /* Write(offset64, tam, flush, buffer mapeado R) -> escritos */
        u64 off = (u64)cmd[1] | ((u64)cmd[2] << 32);
        u32 tam = cmd[3];
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        if (!d || a->romfs) { ipc_respuesta(p, 2, 0, FS_SIN_PERMISO); return; }
        if (!a->escribir) { ipc_respuesta(p, 2, 0, FS_FLAGS_INVALIDOS); return; }
        if (tam > d->tam) tam = d->tam;
        if (a->fijo && off + tam > fs_tam_archivo(a)) { ipc_respuesta(p, 2, 0, FS_MAS_ALLA_FIN); return; }   /* extdata: tamano fijo */
        u8 *buf = malloc(tam ? tam : 1);
        sis_copiar_de_juego(buf, d->dir, tam);
        u32 hechos = 0;
        if (_fseeki64(a->f, (s64)off, SEEK_SET) == 0) hechos = (u32)fwrite(buf, 1, tam, a->f);
        fflush(a->f);
        free(buf);
        ipc_respuesta(p, 2, 2, RES_OK);
        cmd[2] = hechos;
        cmd[3] = IPC_DESC_MAPEADO(d->tam, d->extra); cmd[4] = d->dir;
        return;
    }
    case 0x0804: {                                     /* GetSize -> u64 */
        u64 t = a->f ? fs_tam_archivo(a) : 0;
        ipc_respuesta(p, 3, 0, RES_OK);
        cmd[2] = (u32)t; cmd[3] = (u32)(t >> 32);
        return;
    }
    case 0x0805: {                                     /* SetSize(u64) */
        u64 t = (u64)cmd[1] | ((u64)cmd[2] << 32);
        if (a->romfs || !a->escribir || a->fijo) { ipc_respuesta(p, 1, 0, FS_SIN_PERMISO); return; }
        fflush(a->f);
        ipc_respuesta(p, 1, 0, _chsize_s(_fileno(a->f), (s64)t) == 0 ? RES_OK : FS_SIN_PERMISO);
        return;
    }
    case 0x0808:                                       /* Close */
        if (a->f && !a->romfs) fclose(a->f);
        a->f = NULL;
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    case 0x0809:                                       /* Flush */
        if (a->f && !a->romfs) fflush(a->f);
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    case 0x080A: ipc_respuesta(p, 1, 0, RES_OK); return;            /* SetPriority */
    case 0x080B: ipc_respuesta(p, 2, 0, RES_OK); return;            /* GetPriority -> 0 */
    default: ipc_no_implementado(p, 1); return;
    }
}

/* ---------------------------------------------------------------- sesion de directorio */
typedef struct { WIN32_FIND_DATAA *ent; u32 n, sig; } FsDir;

/* nombre corto 8.3 en mayusculas, como lo arma el FS ('nombrelargo.dat' -> 'NOMBRE~1' + 'DAT') */
static void fs_83(const char *nombre, int es_dir, u8 *corto, u8 *ext)
{
    const char *punto = es_dir ? NULL : strrchr(nombre, '.');
    size_t base = punto ? (size_t)(punto - nombre) : strlen(nombre);
    memset(corto, 0, 9); memset(ext, 0, 4);
    for (size_t i = 0; i < 8 && i < base; i++) corto[i] = (u8)toupper((unsigned char)nombre[i]);
    if (base > 8) { corto[6] = '~'; corto[7] = '1'; }
    int fin = !punto;
    for (int i = 0; i < 3; i++) {
        if (!fin && !punto[1 + i]) fin = 1;
        ext[i] = fin ? ' ' : (u8)toupper((unsigned char)punto[1 + i]);
    }
}

static void fs_dir_atender(IpcPeticion *p)
{
    FsDir *dd = p->ses->datos;
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0801: {                                     /* Read(cuantas, buffer mapeado) -> leidas; entradas de 0x228 */
        u32 cuantas = cmd[1], k = 0;
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        if (d) {
            if (cuantas > d->tam / 0x228) cuantas = d->tam / 0x228;
            for (; k < cuantas && dd->sig < dd->n; k++, dd->sig++) {
                WIN32_FIND_DATAA *w = &dd->ent[dd->sig];
                u8 e[0x228];
                int es_dir = (w->dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
                memset(e, 0, sizeof e);
                for (u32 i = 0; w->cFileName[i] && i < 0x105; i++) e[2 * i] = (u8)w->cFileName[i];
                fs_83(w->cFileName, es_dir, e + 0x20C, e + 0x216);
                e[0x21C] = es_dir ? 1 : 0;                     /* carpeta */
                e[0x21D] = w->cFileName[0] == '.';             /* oculto */
                e[0x21E] = es_dir ? 0 : 1;                     /* archivo */
                u64 t = es_dir ? 0 : (((u64)w->nFileSizeHigh << 32) | w->nFileSizeLow);
                memcpy(e + 0x220, &t, 8);
                sis_copiar_a_juego(d->dir + k * 0x228, e, sizeof e);
            }
        }
        ipc_respuesta(p, 2, d ? 2 : 0, RES_OK);
        cmd[2] = k;
        if (d) { cmd[3] = IPC_DESC_MAPEADO(d->tam, d->extra); cmd[4] = d->dir; }
        return;
    }
    case 0x0802: ipc_respuesta(p, 1, 0, RES_OK); return;            /* Close */
    default: ipc_no_implementado(p, 1); return;
    }
}

/* ---------------------------------------------------------------- montar un archive */

/* ExtSaveData / SharedExtSaveData: ruta binaria {medio, id bajo, id alto}. Carpeta .extdata\ALTO_BAJO */
static int fs_ruta_ext(const FsRuta *ra, char *dst, u32 max, u32 *bajo, u32 *alto)
{
    if (ra->tipo != 2 || ra->tam < 12) return -1;
    memcpy(bajo, ra->datos + 4, 4);
    memcpy(alto, ra->datos + 8, 4);
    snprintf(dst, max, "%s\\.extdata\\%08X_%08X", fs_guardado(), *alto, *bajo);
    return 0;
}

/* SharedExtSaveData 0xF000000B (monedas de juego): en la consola siempre existe; el modulo PTM la crea con un
   gamecoin.dat por defecto (0x14 bytes: magia 0x4F00, monedas, monedas del dia, pasos, pasos del ultimo dia, fecha). */
static void fs_provisionar_monedas(const char *dir)
{
    char r[MAX_PATH + 16];
    if (fs_es_dir(dir)) return;
    fs_mkdir_p(dir);
    snprintf(r, sizeof r, "%s\\gamecoin.dat", dir);
    FILE *f = fopen(r, "wb");
    if (!f) return;
    u8 g[0x14] = {0};
    u32 magia = 0x4F00; u16 monedas = 10, anio = 2026;
    memcpy(g, &magia, 4); memcpy(g + 4, &monedas, 2); memcpy(g + 0x10, &anio, 2); g[0x12] = 10; g[0x13] = 9;
    fwrite(g, 1, sizeof g, f);
    fclose(f);
    fprintf(stderr, "[fs] SharedExtSaveData F000000B creada con gamecoin.dat (como el PTM de la consola)\n");
}

static void fs_log_ruta(const char *que, const FsRuta *r);

/* llena raiz/ext del archive id con la ruta ra; devuelve el resultado de Horizon */
static u32 fs_montar(u32 id, const FsRuta *ra, FsArchive *ar)
{
    u32 bajo, alto;
    ar->id = id; ar->ext = 0; ar->raiz[0] = 0;
    switch (id) {
    case FS_ARCH_SELFNCCH:
        return fs_abrir_rom() ? FS_SIN_ROMFS : RES_OK;
    case FS_ARCH_SAVEDATA:
        snprintf(ar->raiz, sizeof ar->raiz, "%s", fs_guardado());
        return fs_formateado() ? RES_OK : FS_NO_FORMATEADO;
    case FS_ARCH_EXTSAVE: case FS_ARCH_EXTSAVE_COMP:
        if (fs_ruta_ext(ra, ar->raiz, sizeof ar->raiz, &bajo, &alto)) return FS_RUTA_MALA;
        ar->ext = 1;
        if (id == FS_ARCH_EXTSAVE_COMP && bajo == 0xF000000Bu) fs_provisionar_monedas(ar->raiz);
        if (!fs_es_dir(ar->raiz)) {
            /* ExtSaveData inexistente: NotFound con resumen InvalidState; la compartida: NotFormatted */
            fprintf(stderr, "[fs] %s %08X_%08X no existe\n", id == FS_ARCH_EXTSAVE ? "ExtSaveData" : "SharedExtSaveData", alto, bajo);
#ifdef SABOTAJE_GUARDADO_CODIGO
            return FS_NO_ENC_ESTADO;   /* la compartida con el codigo de la normal: prueba_guardado tiene que verlo */
#endif
            return id == FS_ARCH_EXTSAVE ? FS_NO_ENC_ESTADO : FS_NO_FORMATEADO;
        }
        return RES_OK;
    case FS_ARCH_SISTEMA:
        if (ra->tipo != 2 || ra->tam < 8) return FS_RUTA_MALA;
        memcpy(&bajo, ra->datos, 4); memcpy(&alto, ra->datos + 4, 4);
        snprintf(ar->raiz, sizeof ar->raiz, "%s\\.sistema\\%08X_%08X", fs_guardado(), alto, bajo);
        if (!fs_es_dir(ar->raiz)) { fprintf(stderr, "[fs] SystemSaveData %08X_%08X no existe\n", alto, bajo); return FS_NO_ENCONTRADO; }
        return RES_OK;
    default:
        fprintf(stderr, "[fs] archive 0x%08X sin soporte\n", id);
        fs_log_ruta("  archive", ra);
        return FS_NO_ENCONTRADO;
    }
}

/* ---------------------------------------------------------------- abrir */

static u32 fs_abrir_en(const FsArchive *ar, const FsRuta *ruta, u32 modo, FsArchivo **salida)
{
    *salida = NULL;
    if (ar->id == FS_ARCH_SELFNCCH) {
        u32 tipo = 0;
        if (ruta->tipo != 2 || ruta->tam < 4) return FS_RUTA_MALA;
        memcpy(&tipo, ruta->datos, 4);
        if (tipo == 2 && ruta->tam >= 12) {   /* ExeFS: icon, banner, logo */
            u64 o, n;
            char nom[9] = {0};
            memcpy(nom, ruta->datos + 4, 8);
            if (modo & 6) return FS_SIN_PERMISO;
            if (fs_exefs_buscar(ruta->datos + 4, &o, &n)) { fprintf(stderr, "[fs] SelfNCCH ExeFS \"%s\" no esta\n", nom); return FS_NO_ENCONTRADO; }
            fprintf(stderr, "[fs] SelfNCCH ExeFS \"%s\": %llu bytes\n", nom, (unsigned long long)n);
            FsArchivo *a = calloc(1, sizeof *a);
            a->romfs = 1; a->f = fs_rom; a->base = o; a->tam = n;
            *salida = a;
            return RES_OK;
        }
        if (tipo != 0 && tipo != 5) { fprintf(stderr, "[fs] SelfNCCH tipo %u sin soporte (solo RomFS)\n", tipo); return FS_NO_ENCONTRADO; }
        if (modo & 6) return FS_SIN_PERMISO;
        if (fs_abrir_rom()) return FS_SIN_ROMFS;
        FsArchivo *a = calloc(1, sizeof *a);
        a->romfs = 1; a->f = fs_rom; a->base = fs_lv3_off; a->tam = fs_lv3_tam;
        *salida = a;
        return RES_OK;
    }
    char r[MAX_PATH];
    int hs = fs_resolver(ar, ruta, r, sizeof r);
    if (hs == FS_HS_INVALIDA) return FS_RUTA_MALA;
    if (modo == 0) return FS_FLAGS_MALOS;
    if ((modo & 4) && (ar->ext || !(modo & 2))) return FS_FLAGS_MALOS;   /* crear sin escribir; extdata no crea al abrir */
    switch (hs) {
    case FS_HS_RUTA_NO: return FS_RUTA_NO_HAY;
    case FS_HS_ARCHIVO_EN_RUTA: case FS_HS_DIR: return FS_INESPERADO;
    case FS_HS_NO_HAY: {
        if (!(modo & 4)) return FS_ARCHIVO_NO_HAY;
        FILE *c = fopen(r, "wb");
        if (!c) return FS_ARCHIVO_NO_HAY;
        fclose(c);
        break;
    }
    default: break;
    }
    FILE *f = fopen(r, "r+b");
    if (!f) return FS_ARCHIVO_NO_HAY;
    FsArchivo *a = calloc(1, sizeof *a);
    a->f = f; a->escribir = ar->ext || (modo & 2) != 0; a->fijo = ar->ext;
    snprintf(a->ruta, sizeof a->ruta, "%s", r);
    *salida = a;
    return RES_OK;
}

/* archive NCCH (0x2345678A) de un titulo de SISTEMA: ruta binaria {low, high, medio, 0}. Se sirven los reemplazos de
   codigo abierto que trae Azahar (externals\open_source_archives), extraidos a extraido\sistema\<HIGH>_<LOW>_*.romfs:
   como Azahar, la imagen va cruda (el juego parsea el RomFS nivel 3 el mismo). El juego abre los datos de Mii
   (0x0004009B/0x00010202) al cargar y, si fallan, parsea un buffer vacio y cae (lectura en 0x02F37100, 8 oct). */
#define FS_ARCH_NCCH 0x2345678Au
static u32 fs_abrir_ncch(const FsRuta *ra, const FsRuta *rf, FsArchivo **salida)
{
    u32 low, high;
    *salida = NULL;
    if (ra->tipo != 2 || ra->tam < 8 || rf->tipo != 2 || rf->tam < 4) return FS_RUTA_MALA;
    memcpy(&low, ra->datos, 4);
    memcpy(&high, ra->datos + 4, 4);
    u32 tipo_f;
    memcpy(&tipo_f, rf->datos, 4);
    if (tipo_f != 0) { fprintf(stderr, "[fs] NCCH %08X_%08X: tipo de archivo %u sin soporte\n", high, low, tipo_f); return FS_NO_ENCONTRADO; }
    WIN32_FIND_DATAA fd;
    char patron[MAX_PATH], r[MAX_PATH];
    snprintf(patron, sizeof patron, "extraido\\sistema\\%08X_%08X_*.romfs", high, low);
    HANDLE h = FindFirstFileA(patron, &fd);
    if (h == INVALID_HANDLE_VALUE) { fprintf(stderr, "[fs] titulo de sistema %08X_%08X sin reemplazo\n", high, low); return FS_NO_ENCONTRADO; }
    FindClose(h);
    snprintf(r, sizeof r, "extraido\\sistema\\%s", fd.cFileName);
    FILE *f = fopen(r, "rb");
    if (!f) return FS_NO_ENCONTRADO;
    FsArchivo *a = calloc(1, sizeof *a);
    a->romfs = 1; a->f = f; a->base = 0;
    a->tam = ((u64)fd.nFileSizeHigh << 32) | fd.nFileSizeLow;
    if (sis_traza) fprintf(stderr, "[fs] titulo de sistema %08X_%08X -> %s (%llu bytes)\n", high, low, r, (unsigned long long)a->tam);
    *salida = a;
    return RES_OK;
}

static void fs_responder_archivo(IpcPeticion *p, u32 res, FsArchivo *a)
{
    ipc_respuesta(p, 1, 2, res);
    p->cmd[2] = IPC_DESC_MOVER(1);
    p->cmd[3] = 0;
    if (res == RES_OK) {
        IpcSesion *s = ipc_sesion_nueva(a->romfs ? "fs:USER/romfs" : "fs:USER/archivo", fs_archivo_atender, a, SRV_FS);
        p->cmd[3] = sis_handle_nuevo(ipc_obj_sesion(s));
    }
}

static void fs_log_ruta(const char *que, const FsRuta *r)
{
    if (!sis_traza) return;
    fprintf(stderr, "[fs] %s ruta tipo %u (%u bytes):", que, r->tipo, r->tam);
    if (r->tipo == 3 || r->tipo == 4) { fputc(' ', stderr); for (u32 i = 0; i < r->tam; i += (r->tipo == 4 ? 2 : 1)) if (r->datos[i]) fputc(r->datos[i], stderr); }
    else for (u32 i = 0; i < r->tam && i < 16; i++) fprintf(stderr, " %02X", r->datos[i]);
    fputc('\n', stderr);
}

/* archive del juego por handle u64 en cmd[w], cmd[w+1] (NULL si no esta abierto) */
static FsArchive *fs_ar_de(u32 *cmd, u32 w) { return fs_archive_de((u64)cmd[w] | ((u64)cmd[w + 1] << 32)); }

/* info de formato guardada (5 palabras: tam, dirs, archivos, reservado, duplicado) */
static int fs_leer_formato(const char *raiz, u32 info[5])
{
    char r[MAX_PATH + 16];
    snprintf(r, sizeof r, "%s\\.formato.bin", raiz);
    FILE *f = fopen(r, "rb");
    memset(info, 0, 5 * sizeof(u32));
    if (!f) return -1;
    size_t n = fread(info, 4, 5, f); (void)n;
    fclose(f);
    return 0;
}

void fs_user_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0801:                                       /* Initialize(pid) */
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    case 0x0802: {                                     /* OpenFile(trans, archive64, tipo, tam, modo, attr, ruta) */
        FsRuta r; FsArchivo *a = NULL;
        FsArchive *ar = fs_ar_de(cmd, 2);
        fs_leer_ruta(p, 0, cmd[4], cmd[5], &r);
        fs_log_ruta("OpenFile", &r);
        u32 res = ar ? fs_abrir_en(ar, &r, cmd[6], &a) : FS_ARCHIVE_MALO;
        if (res != RES_OK && sis_traza) fprintf(stderr, "[fs] OpenFile -> 0x%08X\n", res);
        fs_responder_archivo(p, res, a);
        return;
    }
    case 0x0803: {                                     /* OpenFileDirectly(trans, id, tipoA, tamA, tipoF, tamF, modo, attr, rutaA, rutaF) */
        FsRuta ra, rf; FsArchivo *a = NULL; FsArchive ar;
        u32 id = cmd[2], modo = cmd[7], res;
        fs_leer_ruta(p, 0, cmd[3], cmd[4], &ra);
        fs_leer_ruta(p, 1, cmd[5], cmd[6], &rf);
        fs_log_ruta("OpenFileDirectly archive", &ra);
        fs_log_ruta("OpenFileDirectly", &rf);
        if (id == FS_ARCH_NCCH) res = fs_abrir_ncch(&ra, &rf, &a);
        else if ((res = fs_montar(id, &ra, &ar)) == RES_OK) res = fs_abrir_en(&ar, &rf, modo, &a);
        fs_responder_archivo(p, res, a);
        return;
    }
    case 0x0804: {                                     /* DeleteFile(trans, archive64, tipo, tam, ruta) */
        FsRuta r; char h[MAX_PATH];
        FsArchive *ar = fs_ar_de(cmd, 2);
        fs_leer_ruta(p, 0, cmd[4], cmd[5], &r);
        if (!ar) { ipc_respuesta(p, 1, 0, FS_ARCHIVE_MALO); return; }
        if (ar->id == FS_ARCH_SELFNCCH) { ipc_respuesta(p, 1, 0, FS_SIN_PERMISO); return; }
        int hs = fs_resolver(ar, &r, h, sizeof h);
        u32 res = hs == FS_HS_INVALIDA ? FS_RUTA_MALA : hs == FS_HS_RUTA_NO ? FS_RUTA_NO_HAY
                : hs != FS_HS_ARCHIVO ? FS_ARCHIVO_NO_HAY : DeleteFileA(h) ? RES_OK : FS_ARCHIVO_NO_HAY;
        ipc_respuesta(p, 1, 0, res);
        return;
    }
    case 0x0806: case 0x0807: {                        /* DeleteDirectory(+Recursively)(trans, archive64, tipo, tam, ruta) */
        FsRuta r; char h[MAX_PATH];
        FsArchive *ar = fs_ar_de(cmd, 2);
        fs_leer_ruta(p, 0, cmd[4], cmd[5], &r);
        if (!ar) { ipc_respuesta(p, 1, 0, FS_ARCHIVE_MALO); return; }
        if (ar->id == FS_ARCH_SELFNCCH) { ipc_respuesta(p, 1, 0, FS_SIN_PERMISO); return; }
        int hs = fs_resolver(ar, &r, h, sizeof h);
        u32 res;
        if (hs == FS_HS_INVALIDA) res = FS_RUTA_MALA;
        else if (hs == FS_HS_DIR && !strcmp(h, ar->raiz)) res = FS_DIR_NO_VACIO;   /* la raiz no se borra */
        else if (hs == FS_HS_RUTA_NO || hs == FS_HS_NO_HAY) res = FS_RUTA_NO_HAY;
        else if (hs != FS_HS_DIR) res = FS_INESPERADO;
        else {
            if (p->id == 0x0807) fs_vaciar(h, 0);
            res = RemoveDirectoryA(h) ? RES_OK : FS_DIR_NO_VACIO;
        }
        ipc_respuesta(p, 1, 0, res);
        return;
    }
    case 0x0808: {                                     /* CreateFile(trans, archive64, tipo, tam, attr, tam64, ruta) */
        FsRuta r; char h[MAX_PATH];
        FsArchive *ar = fs_ar_de(cmd, 2);
        u64 t = (u64)cmd[7] | ((u64)cmd[8] << 32);
        fs_leer_ruta(p, 0, cmd[4], cmd[5], &r);
        fs_log_ruta("CreateFile", &r);
        if (!ar) { ipc_respuesta(p, 1, 0, FS_ARCHIVE_MALO); return; }
        if (ar->id == FS_ARCH_SELFNCCH) { ipc_respuesta(p, 1, 0, FS_SIN_PERMISO); return; }
        int hs = fs_resolver(ar, &r, h, sizeof h);
        u32 res;
        if (hs == FS_HS_INVALIDA) res = FS_RUTA_MALA;
        else if (hs == FS_HS_RUTA_NO) res = FS_RUTA_NO_HAY;
        else if (hs == FS_HS_ARCHIVO_EN_RUTA) res = FS_INESPERADO;
        else if (hs == FS_HS_DIR || hs == FS_HS_ARCHIVO) res = FS_YA_EXISTE;
        else if (t == 0 && ar->ext) res = FS_FLAGS_MALOS;   /* extdata: no se crean archivos vacios */
        else {
            FILE *f = fopen(h, "wb");
            if (!f) res = FS_RUTA_NO_HAY;
            else { _chsize_s(_fileno(f), (s64)t); fclose(f); res = RES_OK; }   /* el archivo nuevo queda en ceros */
        }
        if (res != RES_OK && sis_traza) fprintf(stderr, "[fs] CreateFile -> 0x%08X\n", res);
        ipc_respuesta(p, 1, 0, res);
        return;
    }
    case 0x0809: {                                     /* CreateDirectory(trans, archive64, tipo, tam, attr, ruta) */
        FsRuta r; char h[MAX_PATH];
        FsArchive *ar = fs_ar_de(cmd, 2);
        fs_leer_ruta(p, 0, cmd[4], cmd[5], &r);
        if (!ar) { ipc_respuesta(p, 1, 0, FS_ARCHIVE_MALO); return; }
        if (ar->id == FS_ARCH_SELFNCCH) { ipc_respuesta(p, 1, 0, FS_SIN_PERMISO); return; }
        int hs = fs_resolver(ar, &r, h, sizeof h);
        u32 res = hs == FS_HS_INVALIDA ? FS_RUTA_MALA : hs == FS_HS_RUTA_NO ? FS_RUTA_NO_HAY
                : hs == FS_HS_ARCHIVO_EN_RUTA ? FS_INESPERADO : hs != FS_HS_NO_HAY ? FS_DIR_YA_EXISTE
                : CreateDirectoryA(h, NULL) ? RES_OK : FS_RUTA_NO_HAY;
        ipc_respuesta(p, 1, 0, res);
        return;
    }
    case 0x080B: {                                     /* OpenDirectory(archive64, tipo, tam, ruta) */
        FsRuta r; char h[MAX_PATH], patron[MAX_PATH + 4];
        FsArchive *ar = fs_ar_de(cmd, 1);
        fs_leer_ruta(p, 0, cmd[3], cmd[4], &r);
        ipc_respuesta(p, 1, 2, RES_OK);
        cmd[2] = IPC_DESC_MOVER(1); cmd[3] = 0;
        if (!ar) { cmd[1] = FS_ARCHIVE_MALO; return; }
        if (ar->id == FS_ARCH_SELFNCCH) { cmd[1] = FS_SIN_PERMISO; return; }
        int hs = fs_resolver(ar, &r, h, sizeof h);
        if (hs == FS_HS_INVALIDA) { cmd[1] = FS_RUTA_MALA; return; }
        if (hs == FS_HS_RUTA_NO || hs == FS_HS_NO_HAY) { cmd[1] = FS_RUTA_NO_HAY; return; }
        if (hs != FS_HS_DIR) { cmd[1] = FS_INESPERADO; return; }
        int es_raiz_guardado = ar->id == FS_ARCH_SAVEDATA && !strcmp(h, ar->raiz);
        snprintf(patron, sizeof patron, "%s\\*", h);
        FsDir *dd = calloc(1, sizeof *dd);
        WIN32_FIND_DATAA w;
        HANDLE fh = FindFirstFileA(patron, &w);
        if (fh != INVALID_HANDLE_VALUE) {
            do {
                if (!strcmp(w.cFileName, ".") || !strcmp(w.cFileName, "..")) continue;
                if ((es_raiz_guardado || ar->ext) && w.cFileName[0] == '.') continue;   /* cosas de la capa */
                dd->ent = realloc(dd->ent, (dd->n + 1) * sizeof *dd->ent);
                dd->ent[dd->n++] = w;
            } while (FindNextFileA(fh, &w));
            FindClose(fh);
        }
        cmd[3] = sis_handle_nuevo(ipc_obj_sesion(ipc_sesion_nueva("fs:USER/dir", fs_dir_atender, dd, SRV_FS)));
        return;
    }
    case 0x080C: {                                     /* OpenArchive(id, tipo, tam, ruta) -> handle64 */
        FsRuta ra; FsArchive tmp;
        u32 id = cmd[1];
        fs_leer_ruta(p, 0, cmd[2], cmd[3], &ra);
        if (id != FS_ARCH_SELFNCCH) fs_log_ruta("OpenArchive", &ra);
        u32 res = fs_montar(id, &ra, &tmp);
        if (sis_traza && id != FS_ARCH_SELFNCCH) fprintf(stderr, "[fs] OpenArchive 0x%X -> 0x%08X\n", id, res);
        ipc_respuesta(p, 3, 0, res);
        if (res != RES_OK) return;
        for (int i = 0; i < 32; i++)
            if (!fs_archives[i].handle) {
                fs_archives[i] = tmp;
                fs_archives[i].handle = fs_sig_archive++;
                cmd[2] = (u32)fs_archives[i].handle; cmd[3] = (u32)(fs_archives[i].handle >> 32);
                return;
            }
        cmd[1] = FS_SIN_PERMISO;
        return;
    }
    case 0x080D:                                       /* ControlArchive(archive64, accion, tam_in, tam_out, 2 mapeados): commit */
        /* las escrituras ya van al disco (fflush); el "commit" del guardado no tiene nada pendiente */
        ipc_respuesta(p, 1, 0, fs_ar_de(cmd, 1) ? RES_OK : FS_ARCHIVE_MALO);
        return;
    case 0x080E: {                                     /* CloseArchive(archive64) */
        FsArchive *a = fs_ar_de(cmd, 1);
        if (a) a->handle = 0;
        ipc_respuesta(p, 1, 0, a ? RES_OK : FS_ARCHIVE_MALO);
        return;
    }
    case 0x0817: case 0x0818:                          /* IsSdmcDetected / IsSdmcWritable -> 0 */
        ipc_respuesta(p, 2, 0, RES_OK);
        return;
    case 0x083F: {                                     /* GetExtDataBlockSize(medio, id64) -> bloques totales64, libres64, tam de bloque */
        FsRuta ra; char dir[MAX_PATH]; u32 b, a;
        ra.tipo = 2; ra.tam = 12; memcpy(ra.datos, &cmd[1], 12);
        if (fs_ruta_ext(&ra, dir, sizeof dir, &b, &a) || !fs_es_dir(dir)) { ipc_respuesta(p, 6, 0, FS_NO_ENC_ESTADO); return; }
        ipc_respuesta(p, 6, 0, RES_OK);
        cmd[2] = 0x400; cmd[3] = 0; cmd[4] = 0x3F0; cmd[5] = 0; cmd[6] = 0x1000;   /* 4 MB en bloques de 4 KB */
        return;
    }
    case 0x0845: {                                     /* GetFormatInfo(id, tipo, tam, ruta) -> tam, dirs, archivos, duplicado */
        FsRuta ra; u32 info[5]; char dir[MAX_PATH]; u32 b, a;
        fs_leer_ruta(p, 0, cmd[2], cmd[3], &ra);
        int ok = -1;
        if (cmd[1] == FS_ARCH_SAVEDATA) ok = fs_leer_formato(fs_guardado(), info);
        else if ((cmd[1] == FS_ARCH_EXTSAVE || cmd[1] == FS_ARCH_EXTSAVE_COMP) && !fs_ruta_ext(&ra, dir, sizeof dir, &b, &a) && fs_es_dir(dir)) {
            ok = 0; fs_leer_formato(dir, info);
        }
        if (ok) { ipc_respuesta(p, 5, 0, FS_NO_FORMATEADO); return; }
        ipc_respuesta(p, 5, 0, RES_OK);
        cmd[2] = info[0]; cmd[3] = info[1]; cmd[4] = info[2]; cmd[5] = info[4] ? 1 : 0;
        return;
    }
    case 0x0849:                                       /* GetArchiveResource(medio) -> sector, cluster, capacidad, libre */
        ipc_respuesta(p, 5, 0, RES_OK);
        cmd[2] = 0x200; cmd[3] = 0x4000; cmd[4] = 0x80000; cmd[5] = 0x80000;
        return;
    case 0x084C: {                                     /* FormatSaveData(id, tipo, tam, bloques, dirs, archivos, cubos, cubos, duplicado) */
        if (cmd[1] != FS_ARCH_SAVEDATA) { ipc_respuesta(p, 1, 0, FS_RUTA_MALA); return; }
        u32 info[5] = { cmd[4] * 0x200u, cmd[5], cmd[6], 0, cmd[9] & 0xFF };   /* tam = bloques * 512 */
        char r[MAX_PATH];
        fs_mkdir_p(fs_guardado());
        fs_vaciar(fs_guardado(), 1);                   /* formatear = vaciar (deja .extdata, .sistema) */
        snprintf(r, sizeof r, "%s\\.formato.bin", fs_guardado());
        FILE *f = fopen(r, "wb");
        if (!f) { ipc_respuesta(p, 1, 0, FS_SIN_PERMISO); return; }
        fwrite(info, 4, 5, f);
        fclose(f);
        fprintf(stderr, "[fs] FormatSaveData: %u bytes, %u carpetas, %u archivos, duplicado %u\n", info[0], info[1], info[2], info[4]);
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    }
    default:
        ipc_no_implementado(p, 1);
        return;
    }
}
