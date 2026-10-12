r"""PEDIDO DE INTEGRACION para S (fs.c): SelfNCCH tipo 2 = archivo del ExeFS (icon/banner/logo).
Aplica el parche al fs.c que se le pase (por defecto la copia de diagnostico de P). Para integrarlo en el real:
    py -I agentes_noche\P\parche_fs_exefs.py recomp\sistema\fs.c
Ruta binaria de SelfNCCH (12 bytes): u32 tipo + char nombre[8] (para tipo 2, nombre del ExeFS: "icon", "banner"...).
ExeFS del NCCH: cabecera en ncch+0x1A0 (offset, unidades de 0x200) / 0x1A4 (tamano); 10 entradas {char nombre[8];
u32 off; u32 tam} y los datos desde +0x200. En una ROM descifrada el ExeFS esta en claro (".code" va comprimido,
pero aqui se pide "icon")."""
import os, sys
r = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sis_diag", "fs.c")
t = open(r, encoding="utf-8").read()
if "fs_exefs_buscar" in t:
    sys.exit("ya aplicado")
ancla = "/* ---------------------------------------------------------------- archives abiertos\n"
nuevo = r'''/* SelfNCCH tipo 2: un archivo del ExeFS de la particion 0 (el juego lo pide al activar StreetPass: P, 10 oct) */
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

'''
assert t.count(ancla) == 1
t = t.replace(ancla, nuevo + ancla)
old = '''        if (tipo != 0 && tipo != 5) { fprintf(stderr, "[fs] SelfNCCH tipo %u sin soporte (solo RomFS)\\n", tipo); return FS_NO_ENCONTRADO; }'''
new = '''        if (tipo == 2 && ruta->tam >= 12) {   /* ExeFS: icon, banner, logo */
            u64 o, n;
            char nom[9] = {0};
            memcpy(nom, ruta->datos + 4, 8);
            if (modo & 6) return FS_SIN_PERMISO;
            if (fs_exefs_buscar(ruta->datos + 4, &o, &n)) { fprintf(stderr, "[fs] SelfNCCH ExeFS \\"%s\\" no esta\\n", nom); return FS_NO_ENCONTRADO; }
            fprintf(stderr, "[fs] SelfNCCH ExeFS \\"%s\\": %llu bytes\\n", nom, (unsigned long long)n);
            FsArchivo *a = calloc(1, sizeof *a);
            a->romfs = 1; a->f = fs_rom; a->base = o; a->tam = n;
            *salida = a;
            return RES_OK;
        }
''' + old
assert t.count(old) == 1, "no encuentro la linea del tipo sin soporte"
t = t.replace(old, new)
open(r + ".tmp", "w", encoding="utf-8").write(t)
os.replace(r + ".tmp", r)
print("parche ExeFS aplicado a", r)
