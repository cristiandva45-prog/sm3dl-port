r"""PEDIDO DE INTEGRACION para S (stubs.c, APT:U): applets de biblioteca en HLE minimo (P, 10 oct).
El juego, al confirmar "se te dara un Mii premade" en la seleccion de archivo, lanza el selector de Mii (0x402) y,
si algo falla al activar StreetPass, el applet de error (0x406). Protocolo (Horizon; Azahar applet_manager.cpp y
applets\mii_selector.cpp solo como lectura):
  1. app -> SendParameter(src 0x300, dst 0x4xx, senal 2 Request, buffer CaptureBufferInfo 0x20)
     applet -> app: senal 3 Response + handle de memoria compartida (tam = primer u32 del buffer)
  2. app -> StartLibraryApplet(appid, tam, handle, buffer de configuracion)
     applet -> app (al terminar): senal 0xA WakeupByExit + buffer de resultado
       0x402 (Mii): MiiResult 0x84 = {u32be codigo 0, u32be es_invitado 0, u32be idx_invitado 0xFFFFFFFF,
                    MiiData 0x5C + u16 pad + u16be crc16 (CCITT 0x1021, init 0), u16 nombre_invitado[12]}
       resto (0x406 error, ...): se devuelve el mismo buffer de configuracion (como erreula).
ReceiveParameter/GlanceParameter devuelven remitente, senal, tamano, handle (descriptor mover) y el buffer.
Uso: py -I agentes_noche\P\parche_apt_applets.py [ruta\stubs.c]   (por defecto la copia de diagnostico de P)"""
import os, sys
r = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sis_diag", "stubs.c")
t = open(r, encoding="utf-8").read()
if "apt_mii_resultado" in t:
    sys.exit("ya aplicado")

def cambiar(old, new):
    global t
    assert t.count(old) == 1, old[:80]
    t = t.replace(old, new)

cambiar("""    int hay_param;
    u32 remitente, senal;
} apt;
""", """    int hay_param;
    u32 remitente, senal;
    SisObj *obj;            /* objeto que viaja con el parametro (NULL = ninguno): handle NUEVO en cada entrega */
    u32 nbuf;
    u8 buf[0x400];
} apt;

/* Mii "premade" para el selector de Mii (valores de un Mii estandar publicados en 3dbrew/Azahar; datos, no codigo) */
static u16 apt_crc16(const u8 *d, u32 n)
{
    u16 c = 0;
    for (u32 i = 0; i < n; i++) {
        c ^= (u16)(d[i] << 8);
        for (int k = 0; k < 8; k++) c = (u16)((c & 0x8000) ? (c << 1) ^ 0x1021 : c << 1);
    }
    return c;
}
static u32 apt_mii_resultado(u8 *o)
{
    static const u8 mii[0x5C] = {
        0x03, 0x00, 0x10, 0x30, 0xD2, 0x85, 0xB6, 0xB3, 0x00, 0xC8, 0x85, 0x0A,   /* version..system_id (BE) */
        0x98, 0x39, 0x1E, 0xE4, 0x40, 0xF4, 0x07, 0xB7, 0x37, 0x10, 0x00, 0x00,   /* mii_id (BE), mac, pad */
        0xA6, 0x00, 'C', 0, 'i', 0, 't', 0, 'r', 0, 'a', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,   /* detalles (BE), nombre */
        0x40, 0x40, 0x00, 0x00, 0x21, 0x01,                                       /* alto, ancho, cara, pelo */
        0x02, 0x68, 0x44, 0x18, 0x26, 0x34, 0x46, 0x14, 0x81, 0x12, 0x17, 0x68,   /* ojos, cejas, nariz, boca (BE) */
        0x0D, 0x00, 0x00, 0x29, 0x00, 0x52, 0x48, 0x50,                           /* bigote, barba, gafas, lunar (BE) */
        'f', 0, 'l', 0, 'T', 0, 'o', 0, 'b', 0, 'i', 0, 0, 0, 0, 0, 0, 0, 0, 0,   /* autor */
    };
    memset(o, 0, 0x84);
    o[8] = o[9] = o[10] = o[11] = 0xFF;          /* indice de invitado = ninguno */
    memcpy(o + 0x0C, mii, sizeof mii);
    u16 c = apt_crc16(o + 0x0C, 0x5E);
    o[0x0C + 0x5E] = (u8)(c >> 8); o[0x0C + 0x5F] = (u8)c;
    return 0x84;
}
static void apt_poner_param(u32 remitente, u32 senal, SisObj *o, const u8 *b, u32 n)
{
    apt.hay_param = 1; apt.remitente = remitente; apt.senal = senal; apt.obj = o;
    apt.nbuf = n < sizeof apt.buf ? n : sizeof apt.buf;
    if (b && apt.nbuf) memcpy(apt.buf, b, apt.nbuf);
    if (apt.param) sis_senalar(apt.param);
    fprintf(stderr, "[apt] parametro para la app: de 0x%X senal 0x%X %s %u bytes\\n", remitente, senal, o ? "con objeto" : "sin objeto", apt.nbuf);
}
""")
cambiar("""        apt.hay_param = 1; apt.remitente = APT_HOME_MENU; apt.senal = APT_SENAL_DESPERTAR;
        if (apt.param) sis_senalar(apt.param);
        st_ok(p, 1);""", """        apt_poner_param(APT_HOME_MENU, APT_SENAL_DESPERTAR, NULL, NULL, 0);
        st_ok(p, 1);""")
cambiar("""        ipc_respuesta(p, 4, 4, RES_OK);
        cmd[2] = apt.remitente; cmd[3] = apt.senal; cmd[4] = 0;
        cmd[5] = IPC_DESC_MOVER(1); cmd[6] = 0;
        ipc_salida_estatica(p, 7, 0, NULL, 0);
        if (p->id == 0x000D) apt.hay_param = 0;""", """        u32 n = apt.nbuf < cmd[2] ? apt.nbuf : cmd[2];
        ipc_respuesta(p, 4, 4, RES_OK);
        cmd[2] = apt.remitente; cmd[3] = apt.senal; cmd[4] = n;
        /* Glance (hilo de eventos de APT) y Receive reciben cada uno SU handle: el juego cierra el del Glance */
        cmd[5] = IPC_DESC_MOVER(1); cmd[6] = apt.obj ? sis_handle_nuevo(apt.obj) : 0;
        ipc_salida_estatica(p, 7, 0, apt.buf, n);
        if (p->id == 0x000D) { apt.hay_param = 0; apt.obj = NULL; }""")
cambiar("""    case 0x000C: case 0x0016: case 0x0018:""", """    case 0x000C: {                                     /* SendParameter(src, dst, senal, tam, handle, buffer) */
        u32 dst = cmd[2], senal = cmd[3], tam = cmd[4];
        IpcDesc *d = ipc_desc(p, IPC_D_ESTATICO, 0);
        u8 b[0x400];
        u32 n = d && tam <= sizeof b ? tam : 0;
        if (n) sis_copiar_de_juego(b, d->dir, n);
        fprintf(stderr, "[apt] SendParameter a 0x%X senal 0x%X (%u bytes)\\n", dst, senal, tam);
        if ((dst & 0xF00) >= 0x200 && dst != APT_APLICACION && senal == 2) {   /* applet: Request -> Response + memoria */
            u32 tm = n >= 4 ? (b[0] | b[1] << 8 | b[2] << 16 | (u32)b[3] << 24) : 0x1000;
            if (tm < 0x1000 || tm > 0x400000) tm = 0x1000;
            apt_poner_param(dst, 3, sis_bloque_nuevo((tm + 0xFFF) & ~0xFFFu, NULL), NULL, 0);
        }
        st_ok(p, 1);
        return;
    }
    case 0x001E: {                                     /* StartLibraryApplet(appid, tam, handle, buffer): termina al instante */
        u32 id = cmd[1], tam = cmd[2];
        IpcDesc *d = ipc_desc(p, IPC_D_ESTATICO, 0);
        static u8 b[0x400];
        u32 n = d && tam <= sizeof b ? tam : 0;
        if (n) sis_copiar_de_juego(b, d->dir, n);
        fprintf(stderr, "[apt] StartLibraryApplet 0x%X (%u bytes de configuracion): sale enseguida\\n", id, tam);
        if ((id & 0xFF) == 0x02) { static u8 r[0x84]; apt_poner_param(id, 0xA, NULL, r, apt_mii_resultado(r)); }
        else apt_poner_param(id, 0xA, NULL, b, n);
        st_ok(p, 1);
        return;
    }
    case 0x0016: case 0x0018:""")
cambiar("case 0x0019: case 0x001E: case 0x001F:", "case 0x0019: case 0x001F:")
open(r + ".tmp", "w", encoding="utf-8").write(t)
os.replace(r + ".tmp", r)
print("parche applets APT aplicado a", r)
