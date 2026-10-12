import os, re
raiz = r"C:\Users\usuario\Desktop\Decopilar\sm3dl-port"
p = os.path.join(raiz, r"recomp\sistema\fs.c")
s = open(p, encoding="utf-8").read()
cab = s[:s.index("/* ---------------------------------------------------------------- archives abiertos")]
cola = open(os.path.join(raiz, r"agentes_noche\S\fs_cola.c"), encoding="utf-8").read()
# fs_83 simple
i = cola.index("static void fs_83("); j = cola.index("static void fs_dir_atender")
cola = cola[:i] + '''static void fs_83(const char *nombre, int es_dir, u8 *corto, u8 *ext)
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

''' + cola[j:]
viejo_def = '''#define FS_ARCH_SELFNCCH 3u
#define FS_ARCH_SAVEDATA 4u
#define FS_ARCH_SDMC     9u'''
nuevo_def = '''/* (agente S, 9 oct; codigos verificados contra file_sys/errors.h de Azahar, ver svcs.md) */
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
#define FS_ARCH_SDMC     9u'''
assert cab.count(viejo_def) == 1
cab = cab.replace(viejo_def, nuevo_def)
cab = cab.replace("#include <sys/stat.h>\n", "#include <sys/stat.h>\n#include <ctype.h>\n", 1)
cab = cab.replace(''' * - Archive 4 (SaveData): una carpeta local. Sin "formato.bin" el archive no esta formateado (como una tarjeta nueva)
 *   y el juego llama FormatSaveData.''', ''' * - Archive 4 (SaveData): una carpeta local (SM3DL_GUARDADO). Sin ".formato.bin" el archive no esta formateado (como
 *   una tarjeta nueva) y el juego llama FormatSaveData.
 * - Archives 6/7 (ExtSaveData / SharedExtSaveData) y 8 (SystemSaveData): subcarpetas .extdata / .sistema (ver abajo).''')
open(p + ".tmp", "w", encoding="utf-8").write(cab + cola)
os.replace(p + ".tmp", p)
print("ok", len(cab + cola))
