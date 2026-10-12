/* Servicios provisionales: APT:U, cfg:u, dsp::DSP, ndm:u, mic:u, cecd:u/s y los hid:USER / gsp::Gpu de
 * arranque (los reales los enchufan otros archivos con ipc_registrar). Cada comando conocido responde con la forma
 * correcta (cuantas palabras, que handles); lo que no se conoce pasa por ipc_no_implementado (se registra).
 * Numeros de comando y forma de las respuestas: documentacion de Horizon (Azahar solo como referencia).
 * Se compila dentro de sistema.c. */
#ifdef SIS_IPC_SEPARADO
#include <stdio.h>
#include <string.h>
#include "sistema.h"
#endif

void fs_user_atender(IpcPeticion *p);            /* fs.c */
/* de fs.c (misma unidad de compilacion: sistema.c incluye stubs.c y luego fs.c) */
static const char *fs_guardado(void);
static int fs_es_dir(const char *r);
static void fs_mkdir_p(const char *r);
static void fs_vaciar(const char *dir, int saltar_punto);

/* respuesta "todo bien" con n palabras normales (en cero salvo el resultado) */
static void st_ok(IpcPeticion *p, u32 n) { ipc_respuesta(p, n, 0, RES_OK); }

/* devuelve en la respuesta, tras las palabras normales, los buffers mapeados de la peticion (como hace el kernel) */
static void st_eco_mapeados(IpcPeticion *p, u32 normales)
{
    u32 w = 1 + normales, t = 0;
    IpcDesc *d;
    for (u32 i = 0; (d = ipc_desc(p, IPC_D_MAPEADO, i)) != NULL; i++, t += 2) {
        p->cmd[w + t] = IPC_DESC_MAPEADO(d->tam, d->extra);
        p->cmd[w + t + 1] = d->dir;
    }
    p->cmd[0] = IPC_CAB(p->id, normales, t);
}

/* un handle nuevo de un objeto en cmd[w] con su descriptor de copia en cmd[w-1] */
static void st_handle(IpcPeticion *p, u32 w, SisObj *o) { p->cmd[w - 1] = IPC_DESC_COPIA(1); p->cmd[w] = sis_handle_nuevo(o); }

/* ============================================================ APT:U
 * Un solo "parametro" en vuelo, como el gestor de applets de Horizon (agente S, 9 oct; semantica leida en
 * applet_manager.cpp de Azahar, reimplementada). Enable deja "despertar" de HOME para la aplicacion. Los applets de
 * biblioteca (teclado 0x401, Mii 0x402, error/EULA 0x406...) se "ejecutan" al instante sin pantalla:
 *   Preload/PrepareToStart -> OK; SendParameter(Request) al applet -> el applet responde Response con un bloque de
 *   memoria del tamano pedido (CaptureBufferInfo); StartLibraryApplet(buffer) -> el applet cierra enseguida y la
 *   aplicacion recibe WakeupByExit con el buffer de vuelta (EULA aceptada / Mii cancelado / el resto, eco). */
#define APT_HOME_MENU   0x101u
#define APT_APLICACION  0x300u
#define APT_SENAL_DESPERTAR   0x1u
#define APT_SENAL_PEDIDO      0x2u
#define APT_SENAL_RESPUESTA   0x3u
#define APT_SENAL_FIN_APPLET  0xAu    /* WakeupByExit */
#define APT_RES_SIN_DATOS     0xC8A0CFEFu   /* NoData(1007), Applet(51), InvalidState, Status */
#define APT_RES_NO_ES_PARA_TI 0xC880CFFAu   /* NotFound(1018), Applet, NotFound, Status */
#define APT_RES_PARAM_PENDIENTE 0xC8A0CC02u /* ParameterPresent(2), Applet, InvalidState, Status */
#define APT_RES_YA_EXISTE     0xC8A0CFFCu   /* AlreadyExists(1020), Applet, InvalidState, Status */
#define APT_BUF 0x1000u

static struct {
    SisObj *notif, *param, *lock;
    int hay_param;
    u32 remitente, destino, senal, tam;
    SisObj *obj;                       /* handle que viaja con el parametro (o NULL) */
    u8 buf[APT_BUF];
    u32 applet;                        /* applet de biblioteca preparado (0: ninguno) */
    u32 captura_tam;
} apt;

static void apt_poner(u32 rem, u32 dst, u32 senal, const void *b, u32 n, SisObj *obj)
{
    apt.hay_param = 1; apt.remitente = rem; apt.destino = dst; apt.senal = senal; apt.obj = obj;
    apt.tam = n > APT_BUF ? APT_BUF : n;
    if (apt.tam && b) memcpy(apt.buf, b, apt.tam);
    if (apt.param) sis_senalar(apt.param);
}

/* (Mii de P, agentes_noche\P\parche_apt_applets.py) */
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
/* el applet termina: devuelve a la aplicacion su buffer (ya "contestado") */
static void apt_applet_cierra(u32 applet, u8 *b, u32 n)
{
    switch (applet) {
    case 0x406: case 0x206:                            /* error / EULA: "Agree" (tipo 5) -> aceptada 127.127 */
        if (n >= 0xF78 && b[0] == 5) { u32 uno = 1; memcpy(b + 0xF70, &uno, 4); b[0xF74] = 0x7F; b[0xF75] = 0x7F; }
        break;
    case 0x402: case 0x202:                            /* selector de Mii: devuelve el Mii estandar (MiiResult 0x84) */
        if (getenv("SM3DL_MII_CANCELAR")) { memset(b, 0, 0x84); b[3] = 1; n = 0x84; }   /* "cancelar": el juego vuelve a preguntar */
        else n = apt_mii_resultado(b);
        break;
    default: break;                                    /* teclado y demas: eco (el juego vera lo que mando) */
    }
    fprintf(stderr, "[apt] applet 0x%03X cerrado sin pantalla (%u bytes de vuelta)\n", applet, n);
    apt_poner(applet, APT_APLICACION, APT_SENAL_FIN_APPLET, b, n, NULL);
    apt.applet = 0;
}

static void apt_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001:                                       /* GetLockHandle(flags) -> attr, estado, mutex */
    {
        u32 attr = cmd[1];
        if (!apt.lock) apt.lock = sis_mutex_nuevo();
        ipc_respuesta(p, 3, 2, RES_OK);
        cmd[2] = attr; cmd[3] = 0;
    }
        st_handle(p, 5, apt.lock);
        return;
    case 0x0002:                                       /* Initialize(appid, attr) -> evento de notificacion y de parametro */
        if (!apt.notif) { apt.notif = sis_evento_nuevo(0); apt.param = sis_evento_nuevo(0); }
        ipc_respuesta(p, 1, 3, RES_OK);
        cmd[2] = IPC_DESC_COPIA(2); cmd[3] = sis_handle_nuevo(apt.notif); cmd[4] = sis_handle_nuevo(apt.param);
        return;
    case 0x0003:                                       /* Enable(attr): el menu HOME le manda "despertar" a la aplicacion */
        apt_poner(APT_HOME_MENU, APT_APLICACION, APT_SENAL_DESPERTAR, NULL, 0, NULL);
        st_ok(p, 1);
        return;
    case 0x0005:                                       /* GetAppletManInfo(pos) -> pos, pedido, home, activo */
        ipc_respuesta(p, 5, 0, RES_OK);
        cmd[2] = 0; cmd[3] = APT_APLICACION; cmd[4] = APT_HOME_MENU; cmd[5] = APT_APLICACION;
        return;
    case 0x0006:                                       /* GetAppletInfo(appid) -> titulo, medio, registrado, cargado, attr */
        ipc_respuesta(p, 7, 0, RES_OK);
        cmd[2] = 0x00054000u; cmd[3] = 0x00040000u; cmd[4] = 2; cmd[5] = 1; cmd[6] = 1;
        return;
    case 0x0009:                                       /* IsRegistered(appid) -> 1 (HOME, la aplicacion y el applet preparado) */
        { u32 id = cmd[1]; ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = (id == APT_HOME_MENU || id == APT_APLICACION || (apt.applet && id == apt.applet)) ? 1 : 0; }
        return;
    case 0x000B:                                       /* InquireNotification -> 0 (ninguna: no hay HOME ni reposo) */
        st_ok(p, 2);
        return;
    case 0x000C: {                                     /* SendParameter(origen, destino, senal, tam, handle, buffer estatico) */
        u32 org = cmd[1], dst = cmd[2], senal = cmd[3], tam = cmd[4];
        IpcDesc *ds = ipc_desc(p, IPC_D_ESTATICO, 0);
        u8 b[APT_BUF]; u32 n = 0;
        memset(b, 0, sizeof b);
        if (ds) { n = tam < ds->tam ? tam : ds->tam; if (n > APT_BUF) n = APT_BUF; sis_copiar_de_juego(b, ds->dir, n); }
        if (apt.hay_param) { ipc_respuesta(p, 1, 0, APT_RES_PARAM_PENDIENTE); return; }
        st_ok(p, 1);
        if (apt.applet && dst == apt.applet) {
            if (senal == APT_SENAL_PEDIDO) {           /* CaptureBufferInfo: el applet contesta con su memoria */
                u32 tam_cap = 0; memcpy(&tam_cap, b, 4);
                if (!tam_cap || tam_cap > 0x400000) tam_cap = 0x1000;
                apt.captura_tam = tam_cap;
                apt_poner(dst, org, APT_SENAL_RESPUESTA, NULL, 0, sis_bloque_nuevo(tam_cap, NULL));
            } else if (senal == APT_SENAL_DESPERTAR) {
                apt_applet_cierra(dst, b, n);
            }
        } else {
            fprintf(stderr, "[apt] SendParameter 0x%03X -> 0x%03X senal %u (%u bytes): nadie lo atiende\n", org, dst, senal, n);
        }
        return;
    }
    case 0x000D: case 0x000E: {                        /* ReceiveParameter / GlanceParameter(appid, tam) */
        u32 quien = cmd[1], max = cmd[2];
        if (!apt.hay_param) { ipc_respuesta(p, 1, 0, APT_RES_SIN_DATOS); return; }
        if (apt.destino != quien) { ipc_respuesta(p, 1, 0, APT_RES_NO_ES_PARA_TI); return; }
        u32 n = apt.tam < max ? apt.tam : max;
        ipc_respuesta(p, 4, 4, RES_OK);
        cmd[2] = apt.remitente; cmd[3] = apt.senal; cmd[4] = n;
#ifdef SABOTAJE_APT_HANDLE
        { static u32 h_fijo; if (apt.obj && !h_fijo) h_fijo = sis_handle_nuevo(apt.obj);   /* el mismo handle siempre (bug visto por P) */
          cmd[5] = IPC_DESC_MOVER(1); cmd[6] = apt.obj ? h_fijo : 0; }
#else
        cmd[5] = IPC_DESC_MOVER(1); cmd[6] = apt.obj ? sis_handle_nuevo(apt.obj) : 0;
#endif
        ipc_salida_estatica(p, 7, 0, n ? apt.buf : NULL, n);
        if (p->id == 0x000D) { apt.hay_param = 0; apt.obj = NULL; }
        return;
    }
    case 0x000F: {                                     /* CancelParameter(revisar_org, org, revisar_dst, dst) -> cancelado */
        int ok = apt.hay_param && (!cmd[1] || apt.remitente == cmd[2]) && (!cmd[3] || apt.destino == cmd[4]);
        if (ok) { apt.hay_param = 0; apt.obj = NULL; }
        ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = ok;
        return;
    }
    case 0x0016: case 0x0018:                          /* PreloadLibraryApplet / PrepareToStartLibraryApplet(appid) */
        if (p->id == 0x0018 && apt.hay_param) { ipc_respuesta(p, 1, 0, APT_RES_PARAM_PENDIENTE); return; }
        if (apt.applet && apt.applet != cmd[1]) { ipc_respuesta(p, 1, 0, APT_RES_YA_EXISTE); return; }
        apt.applet = cmd[1];
        fprintf(stderr, "[apt] %s applet 0x%03X\n", p->id == 0x0016 ? "Preload" : "PrepareToStart", cmd[1]);
        st_ok(p, 1);
        return;
    case 0x001E: {                                     /* StartLibraryApplet(appid, tam, handle, buffer estatico) */
        u32 id = cmd[1], tam = cmd[2];
        IpcDesc *ds = ipc_desc(p, IPC_D_ESTATICO, 0);
        u8 b[APT_BUF]; u32 n = 0;
        memset(b, 0, sizeof b);
        if (ds) { n = tam < ds->tam ? tam : ds->tam; if (n > APT_BUF) n = APT_BUF; sis_copiar_de_juego(b, ds->dir, n); }
        if (apt.hay_param) { ipc_respuesta(p, 1, 0, APT_RES_PARAM_PENDIENTE); return; }
        st_ok(p, 1);
        apt_applet_cierra(id, b, n);
        return;
    }
    case 0x003B:                                       /* CancelLibraryApplet(saliendo): el applet cierra devolviendo nada */
        if (apt.hay_param) { ipc_respuesta(p, 1, 0, APT_RES_PARAM_PENDIENTE); return; }
        if (apt.applet) { u8 nada[4] = {0}; apt_applet_cierra(apt.applet, nada, 0); }
        st_ok(p, 1);
        return;
    case 0x0019: case 0x001F:                          /* PrepareToStart / StartSystemApplet: no hay applets de sistema */
    case 0x0022: case 0x0027:                          /* PrepareToCloseApplication / CloseApplication */
    case 0x002B: case 0x002C:                          /* PrepareToJumpToHomeMenu / JumpToHomeMenu */
        fprintf(stderr, "[apt] cmd 0x%04X (applet de sistema / cerrar / HOME): sin efecto\n", p->id);
        st_ok(p, 1);
        return;
    case 0x003E: case 0x003F: case 0x0042: case 0x0043:/* ReplySleepQuery, ReplySleepNotificationComplete, SleepSystem, NotifyToWait */
        st_ok(p, 1);
        return;
    case 0x0040: {                                     /* SendCaptureBufferInfo(tam, buffer estatico) */
        apt.captura_tam = cmd[1];
        st_ok(p, 1);
        return;
    }
    case 0x0046: case 0x0047: {                        /* Wrap / Unwrap (AES-CCM del APT; aqui sin cifrado, con MAC propio) */
        u32 tam_out = cmd[1], tam_in = cmd[2], off_n = cmd[3], tam_n = cmd[4];
        IpcDesc *di = ipc_desc(p, IPC_D_MAPEADO, 0), *dout = ipc_desc(p, IPC_D_MAPEADO, 1);
        u32 res = RES_OK;
        tam_n = (tam_n & ~3u) < 12 ? (tam_n & ~3u) : 12;
        if (di && dout && tam_in <= 0x100000 && tam_out <= 0x100000) {
            u8 *in = calloc(1, tam_in + 32), *out = calloc(1, tam_out + 32);
            sis_copiar_de_juego(in, di->dir, tam_in);
            if (p->id == 0x0046 && tam_out >= tam_in + 16 && off_n + tam_n <= tam_in) {
                /* salida = nonce | datos sin el nonce | MAC (FNV-1a de los datos, 16 bytes) */
                u32 nd = tam_in - tam_n;
                memcpy(out, in + off_n, tam_n);
                memcpy(out + tam_n, in, off_n);
                memcpy(out + tam_n + off_n, in + off_n + tam_n, nd - off_n);
                u32 h = 2166136261u;
                for (u32 i = 0; i < nd; i++) h = (h ^ out[tam_n + i]) * 16777619u;
                for (int i = 0; i < 4; i++) memcpy(out + tam_n + nd + 4 * i, &h, 4);
                sis_copiar_a_juego(dout->dir, out, tam_in + 16);
            } else if (p->id == 0x0047 && tam_in >= tam_n + 16 && tam_out + tam_n + 16 >= tam_in && off_n <= tam_in - tam_n - 16) {
                u32 nd = tam_in - tam_n - 16, h = 2166136261u, mac;
                for (u32 i = 0; i < nd; i++) h = (h ^ in[tam_n + i]) * 16777619u;
                memcpy(&mac, in + tam_n + nd, 4);
                if (mac != h) res = 0xC9010401u;   /* como Horizon al fallar el descifrado: desc 1, PS(65), WrongArgument, Status */
                memcpy(out, in + tam_n, off_n);
                memcpy(out + off_n, in, tam_n);
                memcpy(out + off_n + tam_n, in + tam_n + off_n, nd - off_n);
                if (res == RES_OK) sis_copiar_a_juego(dout->dir, out, nd + tam_n);
            } else {
                res = 0xE0E0CFE9u;   /* tamanos imposibles */
            }
            free(in); free(out);
        }
        ipc_respuesta(p, 1, 0, res);
        st_eco_mapeados(p, 1);
        return;
    }
    case 0x004B: {                                     /* AppletUtility(util, tam_in, tam_out) -> resultado del applet */
        static const u8 ceros[0x100];
        u32 n = cmd[3] < sizeof ceros ? cmd[3] : sizeof ceros;
        ipc_respuesta(p, 2, 2, RES_OK);
        ipc_salida_estatica(p, 3, 0, ceros, n);
        return;
    }
    default:
        ipc_no_implementado(p, 1);
        return;
    }
}

/* ============================================================ cfg:u */
static u32 cfg_bloque(u32 id, u8 *dst, u32 tam)
{
    static const float camara[8] = { 62.0f, 289.0f, 76.80000305f, 46.08000183f, 10.0f, 5.0f, 55.58000183f, 21.56999969f };
    memset(dst, 0, tam);
    switch (id) {
    case 0x00050005: memcpy(dst, camara, tam < sizeof camara ? tam : sizeof camara); return 1;   /* camara estereo */
    case 0x00070001: if (tam) dst[0] = 1; return 1;                                                /* sonido: estereo */
    case 0x000A0000: { const char *n = "SM3DL"; for (u32 i = 0; n[i] && 2 * i + 1 < tam; i++) dst[2 * i] = (u8)n[i]; return 1; } /* usuario */
    case 0x000A0001: if (tam >= 2) { dst[0] = 1; dst[1] = 1; } return 1;                           /* cumpleanos */
    case 0x000A0002: if (tam) dst[0] = 1; return 1;                                                /* idioma: ingles */
    case 0x000B0000: if (tam >= 4) { dst[2] = 2; dst[3] = 49; } return 1;                          /* pais: EE. UU. */
    case 0x000D0000: if (tam >= 2) { dst[0] = 0x7F; dst[1] = 0x7F; } return 1;                     /* EULA aceptada 127.127 */
    case 0x000C0000: case 0x000C0001: case 0x00130000: return 1;                                     /* control parental, COPPACS, modo depuracion: en cero */
    default: return 0;
    }
}

static void cfg_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001: {                                     /* GetConfigInfoBlk2(tam, bloque, buffer mapeado de salida) */
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        u32 tam = cmd[1], bloque = cmd[2];
        if (d) {
            u8 tmp[0x400];
            u32 n = tam < sizeof tmp ? tam : sizeof tmp;
            if (!cfg_bloque(bloque, tmp, n))
                fprintf(stderr, "[ipc] cfg:u bloque 0x%08X desconocido (%u bytes): ceros\n", bloque, tam);
            sis_copiar_a_juego(d->dir, tmp, n);
        }
        ipc_respuesta(p, 1, 0, RES_OK);
        st_eco_mapeados(p, 1);
        return;
    }
    case 0x0002:                                       /* SecureInfoGetRegion -> 1 (EE. UU.) */
        ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 1;
        return;
    case 0x0003:                                       /* GenHashConsoleUnique(sal) -> 64 bits */
        ipc_respuesta(p, 3, 0, RES_OK); cmd[2] = 0x4B5A3344u; cmd[3] = 0x00000001u;
        return;
    default:
        ipc_no_implementado(p, 1);
        return;
    }
}

/* ============================================================ dsp::DSP (silencio: el audio real es de otro paso) */
static SisObj *dsp_semaforo, *dsp_evento_interrupcion;

static void dsp_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001: case 0x0002:                          /* RecvData(reg) -> 1 (DSP listo) / RecvDataIsReady -> 1 */
        ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 1;
        return;
    case 0x0007: case 0x0012: case 0x0013: case 0x0014: case 0x0017:
        st_ok(p, 1);                                   /* SetSemaphore, Unload, Flush/Invalidate cache, SetSemaphoreMask */
        return;
    case 0x000C:                                       /* ConvertProcessAddressFromDspDram(dir) */
        { u32 a = cmd[1]; ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = (a << 1) + 0x1FF40000u; }
        return;
    case 0x000D:                                       /* WriteProcessPipe(canal, tam, buffer estatico) */
        ipc_no_implementado(p, 1);
        return;
    case 0x0010: {                                     /* ReadPipeIfPossible(canal, par, tam) -> 0 bytes */
        ipc_no_implementado(p, 1);
        ipc_respuesta(p, 2, 2, RES_OK);
        ipc_salida_estatica(p, 3, 0, NULL, 0);
        return;
    }
    case 0x0011:                                       /* LoadComponent(tam, mascaras, buffer mapeado) -> cargado */
        ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 1;
        st_eco_mapeados(p, 2);
        return;
    case 0x0015: {                                     /* RegisterInterruptEvents(interrupcion, canal, evento) */
        IpcDesc *d = ipc_desc(p, IPC_D_COPIA, 0);
        if (d) dsp_evento_interrupcion = d->objs[0];
        st_ok(p, 1);
        return;
    }
    case 0x0016:                                       /* GetSemaphoreEventHandle */
        if (!dsp_semaforo) dsp_semaforo = sis_evento_nuevo(0);
        ipc_respuesta(p, 1, 2, RES_OK); st_handle(p, 3, dsp_semaforo);
        return;
    case 0x001F:                                       /* GetHeadphoneStatus -> 0 */
        st_ok(p, 2);
        return;
    default:
        ipc_no_implementado(p, 1);
        return;
    }
}

/* ============================================================ ndm:u, mic:u */
static void ndm_atender(IpcPeticion *p)
{
    switch (p->id) {
    case 0x0006: case 0x0007: case 0x0008: case 0x0009: case 0x0014: st_ok(p, 1); return;  /* Suspend/Resume, Override */
    default: ipc_no_implementado(p, 1); return;
    }
}

static void mic_atender(IpcPeticion *p)
{
    switch (p->id) {
    case 0x0006: case 0x0009: st_ok(p, 2); return;                                /* IsSampling, GetGain */
    case 0x0001: case 0x0002: case 0x0003: case 0x0005: case 0x0008: case 0x000A: case 0x000C: case 0x000D: st_ok(p, 1); return;   /* Map/Unmap, StartSampling (silencio), ... */
    default: ipc_no_implementado(p, 1); return;
    }
}

/* ============================================================ cecd:u / cecd:s (StreetPass)
 * Buzon guardado en <guardado>\.cecd\ con la misma forma de rutas del modulo CECD (/CEC/<id>/MBoxInfo____...).
 * Open/Read/Write/Delete de verdad (archivo por sesion), mensajes por id en base16, ReadData = EULA aceptada y sin
 * control parental, estado "inactivo" (no hay radio: nunca llegan pases). Semantica leida en cecd.cpp de Azahar.
 * (agente S, 9 oct) */
#define CECD_RES_NO_HAY   0xC88103EFu   /* NoData(1007), CEC(66), NotFound, Status */
#define CECD_RES_NO_AUT   0xC88103EAu   /* NotAuthorized(1002), CEC, NotFound, Status: Read/Write sin Open */

typedef struct { char ruta[MAX_PATH]; int abierto, es_dir; } CecdSes;

static void cecd_ruta(u32 prog, u32 tipo, const u8 *msg, u32 msg_tam, char *dst, u32 max)
{
    char b[MAX_PATH], m[64] = "";
    for (u32 i = 0; i < msg_tam && i < 24; i++) snprintf(m + 2 * i, sizeof m - 2 * i, "%02X", msg[i]);
    snprintf(b, sizeof b, "%s\\.cecd\\CEC", fs_guardado());
    switch (tipo) {
    case 1:  snprintf(dst, max, "%s\\MBoxList____", b); return;
    case 2:  snprintf(dst, max, "%s\\%08x\\MBoxInfo____", b, prog); return;
    case 3:  snprintf(dst, max, "%s\\%08x\\InBox___\\BoxInfo_____", b, prog); return;
    case 4:  snprintf(dst, max, "%s\\%08x\\OutBox__\\BoxInfo_____", b, prog); return;
    case 5:  snprintf(dst, max, "%s\\%08x\\OutBox__\\OBIndex_____", b, prog); return;
    case 6:  snprintf(dst, max, "%s\\%08x\\InBox___\\_%s", b, prog, m); return;
    case 7:  snprintf(dst, max, "%s\\%08x\\OutBox__\\_%s", b, prog, m); return;
    case 10: snprintf(dst, max, "%s", b); return;
    case 11: snprintf(dst, max, "%s\\%08x", b, prog); return;
    case 12: snprintf(dst, max, "%s\\%08x\\InBox___", b, prog); return;
    case 13: snprintf(dst, max, "%s\\%08x\\OutBox__", b, prog); return;
    default: snprintf(dst, max, "%s\\%08x\\MBoxData.%03u", b, prog, tipo >= 100 ? tipo - 100 : tipo); return;
    }
}

static u32 cecd_contar(const char *dir)
{
    char patron[MAX_PATH + 4]; WIN32_FIND_DATAA w; u32 n = 0;
    snprintf(patron, sizeof patron, "%s\\*", dir);
    HANDLE fh = FindFirstFileA(patron, &w);
    if (fh == INVALID_HANDLE_VALUE) return 0;
    do { if (strcmp(w.cFileName, ".") && strcmp(w.cFileName, "..")) n++; } while (FindNextFileA(fh, &w));
    FindClose(fh);
    return n;
}

static long cecd_tam(const char *r) { FILE *f = fopen(r, "rb"); long t = -1; if (f) { fseek(f, 0, SEEK_END); t = ftell(f); fclose(f); } return t; }

/* escribe un archivo entero creando las carpetas de arriba */
static int cecd_escribir(const char *r, const u8 *b, u32 n)
{
    char dir[MAX_PATH];
    snprintf(dir, sizeof dir, "%s", r);
    char *c = strrchr(dir, '\\'); if (c) { *c = 0; fs_mkdir_p(dir); }
    FILE *f = fopen(r, "wb");
    if (!f) return -1;
    fwrite(b, 1, n, f); fclose(f);
    return 0;
}

static SisObj *cecd_evento;
static void cecd_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    if (!p->ses->datos) p->ses->datos = calloc(1, sizeof(CecdSes));
    CecdSes *s = p->ses->datos;
    switch (p->id) {
    case 0x0001: {                                     /* Open(prog, tipo, modo, pid) -> tam / entradas */
        u32 prog = cmd[1], tipo = cmd[2], modo = cmd[3];
        cecd_ruta(prog, tipo, NULL, 0, s->ruta, sizeof s->ruta);
        s->es_dir = tipo >= 10 && tipo <= 13;
        ipc_respuesta(p, 2, 0, RES_OK);
        if (s->es_dir) {
            if (!fs_es_dir(s->ruta)) {
                if (modo & 8) { fs_mkdir_p(s->ruta); cmd[2] = 0; }          /* bit 3 = crear (CecOpenMode) */
                else { cmd[1] = CECD_RES_NO_HAY; cmd[2] = 0; }
            } else cmd[2] = cecd_contar(s->ruta);
            s->abierto = cmd[1] == RES_OK;
        } else {
            long t = cecd_tam(s->ruta);
            if (t < 0) {   /* Horizon abre los archivos con "crear": falla solo si no existe la carpeta del buzon */
                char arriba[MAX_PATH]; snprintf(arriba, sizeof arriba, "%s", s->ruta);
                char *c = strrchr(arriba, 0x5C); if (c) *c = 0;   /* barra invertida */
                if (!fs_es_dir(arriba)) { cmd[1] = CECD_RES_NO_HAY; cmd[2] = 0; s->abierto = 0; }
                else { cecd_escribir(s->ruta, NULL, 0); t = 0; }
            }
            if (t >= 0) { cmd[2] = (u32)t; s->abierto = 1; }
        }
        if (sis_traza) fprintf(stderr, "[cecd] Open %08X tipo %u modo 0x%X -> 0x%08X (%u)\n", prog, tipo, modo, cmd[1], cmd[2]);
        return;
    }
    case 0x0002: {                                     /* Read(tam, mapeado W) -> leidos */
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        u32 n = 0, pedido = cmd[1];   /* antes de ipc_respuesta, que pone en cero las palabras */
        ipc_respuesta(p, 2, 0, RES_OK);
        if (!s->abierto || s->es_dir || !d) cmd[1] = CECD_RES_NO_AUT;
        else {
            FILE *f = fopen(s->ruta, "rb");
            u32 max = pedido < d->tam ? pedido : d->tam;
            if (f) { u8 *b = malloc(max ? max : 1); n = (u32)fread(b, 1, max, f); fclose(f); sis_copiar_a_juego(d->dir, b, n); free(b); }
        }
        cmd[2] = n;
        st_eco_mapeados(p, 2);
        return;
    }
    case 0x0003: {                                     /* ReadMessage(prog, outbox, tam_id, tam, id R, buffer W) -> leidos */
        IpcDesc *di = ipc_desc(p, IPC_D_MAPEADO, 0), *db = ipc_desc(p, IPC_D_MAPEADO, 1);
        u8 id[32] = {0}; u32 nid = cmd[3] < 32 ? cmd[3] : 32, n = 0;
        char r[MAX_PATH];
        if (di) sis_copiar_de_juego(id, di->dir, nid);
        cecd_ruta(cmd[1], cmd[2] ? 7 : 6, id, nid, r, sizeof r);
        ipc_respuesta(p, 2, 0, RES_OK);
        FILE *f = fopen(r, "rb");
        if (!f || !db) cmd[1] = CECD_RES_NO_HAY;
        else { u32 max = cmd[4] < db->tam ? cmd[4] : db->tam; u8 *b = malloc(max ? max : 1); n = (u32)fread(b, 1, max, f); sis_copiar_a_juego(db->dir, b, n); free(b); }
        if (f) fclose(f);
        cmd[2] = n;
        st_eco_mapeados(p, 2);
        return;
    }
    case 0x0005: {                                     /* Write(tam, mapeado R) */
        IpcDesc *d = ipc_desc(p, IPC_D_MAPEADO, 0);
        u32 res = RES_OK;
        if (!s->abierto || s->es_dir || !d) res = CECD_RES_NO_AUT;
        else {
            u32 n = cmd[1] < d->tam ? cmd[1] : d->tam;
            u8 *b = malloc(n ? n : 1); sis_copiar_de_juego(b, d->dir, n);
            if (cecd_escribir(s->ruta, b, n)) res = CECD_RES_NO_AUT;
            free(b);
        }
        ipc_respuesta(p, 1, 0, res);
        st_eco_mapeados(p, 1);
        return;
    }
    case 0x0007: {                                     /* WriteMessageWithHMAC(prog, outbox, tam_id, tam, buf R, hmac R, id RW) */
        IpcDesc *db = ipc_desc(p, IPC_D_MAPEADO, 0), *di = ipc_desc(p, IPC_D_MAPEADO, 2);
        u8 id[32] = {0}; u32 nid = cmd[3] < 32 ? cmd[3] : 32;
        char r[MAX_PATH];
        if (di) sis_copiar_de_juego(id, di->dir, nid);
        cecd_ruta(cmd[1], cmd[2] ? 7 : 6, id, nid, r, sizeof r);
        u32 res = RES_OK;
        if (db) {
            u32 n = cmd[4] < db->tam ? cmd[4] : db->tam;
            u8 *b = malloc(n ? n : 1); sis_copiar_de_juego(b, db->dir, n);
            if (cecd_escribir(r, b, n)) res = CECD_RES_NO_AUT;
            free(b);
        }
        ipc_respuesta(p, 1, 0, res);
        st_eco_mapeados(p, 1);
        return;
    }
    case 0x0008: {                                     /* Delete(prog, tipo, outbox, tam_id, id R) */
        IpcDesc *di = ipc_desc(p, IPC_D_MAPEADO, 0);
        u8 id[32] = {0}; u32 nid = cmd[4] < 32 ? cmd[4] : 32;
        char r[MAX_PATH];
        if (di) sis_copiar_de_juego(id, di->dir, nid);
        cecd_ruta(cmd[1], cmd[2], id, nid, r, sizeof r);
        if (fs_es_dir(r)) { fs_vaciar(r, 0); RemoveDirectoryA(r); } else DeleteFileA(r);
        ipc_respuesta(p, 1, 0, RES_OK);
        st_eco_mapeados(p, 1);
        return;
    }
    case 0x0009:                                       /* SetData(prog, tam, opcion, mapeado R): sin efecto */
        ipc_respuesta(p, 1, 0, RES_OK);
        st_eco_mapeados(p, 1);
        return;
    case 0x000A: {                                     /* ReadData(tam, tipo, tam_param, param R, destino W) */
        IpcDesc *dd = ipc_desc(p, IPC_D_MAPEADO, 1);
        u8 b[2] = {0, 0}; u32 n = 0;
        if (cmd[2] == 1) { b[0] = 0x7F; b[1] = 0x7F; n = 2; }   /* version de EULA */
        else if (cmd[2] == 2) { b[0] = 1; n = 1; }               /* EULA aceptada */
        else if (cmd[2] == 3) { b[0] = 0; n = 1; }               /* sin control parental */
        if (dd && n) sis_copiar_a_juego(dd->dir, b, n < cmd[1] ? n : cmd[1]);
        ipc_respuesta(p, 1, 0, RES_OK);
        st_eco_mapeados(p, 1);
        return;
    }
    case 0x000B: case 0x000C: st_ok(p, 1); return;    /* Start / Stop(comando) */
    case 0x000E:                                       /* GetCecdState -> 1 (NdmStatusIdle) */
        ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 1;
        return;
    case 0x0010:                                       /* GetChangeStateEventHandle */
        if (!cecd_evento) cecd_evento = sis_evento_nuevo(0);
        ipc_respuesta(p, 1, 2, RES_OK); st_handle(p, 3, cecd_evento);
        return;
    default: ipc_no_implementado(p, 1); return;
    }
}

/* ============================================================ servicios del exheader que el juego aun no abre
 * (ptm:u, frd:u, ac:u, boss:U, news:u, cam:u, y2r:u, ir:USER, gsp::Lcd): respuestas de Azahar para los comandos
 * comunes; lo demas pasa por ipc_no_implementado (se ve en el log). */
static void ptm_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0005: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetAdapterState: sin cargador */
    case 0x0006: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 1; return;   /* GetShellState: tapa abierta */
    case 0x0007: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 5; return;   /* GetBatteryLevel: llena (0-5) */
    case 0x0008: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetBatteryChargeState */
    case 0x0009: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetPedometerState */
    case 0x000B: ipc_respuesta(p, 1, 0, RES_OK); return;               /* GetStepHistory */
    case 0x000C: ipc_respuesta(p, 3, 0, RES_OK); cmd[2] = 0; cmd[3] = 0; return;   /* GetTotalStepCount */
    default: ipc_no_implementado(p, 1); return;
    }
}

static void ac_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001: { static const u8 ceros[0x200]; ipc_respuesta(p, 1, 2, RES_OK); ipc_salida_estatica(p, 2, 0, ceros, 0x200); return; } /* CreateDefaultConfig */
    case 0x000C: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetStatus: desconectado (Azahar dice internet) */
    case 0x000D: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* GetWifiStatus: sin red */
    case 0x003E: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* IsConnected: no */
    case 0x0004: case 0x0008: case 0x0030: case 0x0040: st_ok(p, 1); return;   /* Connect/Close/RegisterDisconnectEvent/SetClientVersion */
    default: ipc_no_implementado(p, 1); return;
    }
}

static void frd_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001: case 0x0002: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;   /* HasLoggedIn / IsOnline: no */
    case 0x0006: ipc_respuesta(p, 4, 0, RES_OK); return;                          /* GetMyPreference: privado, nada a la vista */
    case 0x0011: ipc_respuesta(p, 2, 0, RES_OK); cmd[2] = 0; return;               /* GetFriendKeyList: 0 amigos */
    case 0x0032: st_ok(p, 1); return;                                              /* SetClientSdkVersion */
    default: ipc_no_implementado(p, 1); return;
    }
}

static void lcd_atender(IpcPeticion *p)
{
    switch (p->id) {
    case 0x000A: case 0x0011: case 0x0012: st_ok(p, 1); return;   /* SetBrightnessRaw, PowerOn/OffBacklight */
    case 0x0014: ipc_respuesta(p, 2, 0, RES_OK); p->cmd[2] = 0; return;   /* GetVendor */
    default: ipc_no_implementado(p, 1); return;
    }
}

static void generico_atender(IpcPeticion *p) { ipc_no_implementado(p, 1); }

/* ============================================================ gsp::Gpu y hid:USER provisionales (los reemplazan E y D) */
static SisObj *gsp_prov_shm, *gsp_prov_evento;

static void gsp_provisional(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0013: {                                     /* RegisterInterruptRelayQueue(flags, evento) -> indice, shm */
        IpcDesc *d = ipc_desc(p, IPC_D_COPIA, 0);
        if (d) gsp_prov_evento = d->objs[0];
        if (!gsp_prov_shm) gsp_prov_shm = sis_bloque_nuevo(0x1000, NULL);
        ipc_respuesta(p, 2, 2, 0x2A07u);               /* "primera inicializacion", como el GSP real */
        cmd[2] = 0;
        st_handle(p, 4, gsp_prov_shm);
        return;
    }
    case 0x0004: {                                     /* ReadHWRegs(reg, tam) -> ceros */
        static const u8 ceros[0x80];
        u32 n = cmd[2] < sizeof ceros ? cmd[2] : sizeof ceros;
        ipc_respuesta(p, 1, 2, RES_OK);
        ipc_salida_estatica(p, 2, 0, ceros, n);
        return;
    }
    case 0x0018: st_ok(p, 9); return;                  /* ImportDisplayCaptureInfo */
    default: ipc_no_implementado(p, 1); return;
    }
}

static SisObj *hid_prov_shm, *hid_prov_ev[5];

static void hid_provisional(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x000A:                                       /* GetIPCHandles -> shm + 5 eventos */
        if (!hid_prov_shm) {
            hid_prov_shm = sis_bloque_nuevo(0x2B0, NULL);
            for (int i = 0; i < 5; i++) hid_prov_ev[i] = sis_evento_nuevo(0);
        }
        ipc_respuesta(p, 1, 7, RES_OK);
        cmd[2] = IPC_DESC_COPIA(6); cmd[3] = sis_handle_nuevo(hid_prov_shm);
        for (int i = 0; i < 5; i++) cmd[4 + i] = sis_handle_nuevo(hid_prov_ev[i]);
        return;
    case 0x0011: case 0x0012: case 0x0013: case 0x0014: st_ok(p, 1); return;   /* acelerometro / giroscopio on-off */
    case 0x0015: { float k = 14.375f; ipc_respuesta(p, 2, 0, RES_OK); memcpy(&cmd[2], &k, 4); return; }
    case 0x0016: st_ok(p, 6); return;                  /* GetGyroscopeCalibrateParam: 0x14 bytes en cero */
    default: ipc_no_implementado(p, 1); return;
    }
}

/* ============================================================ registro de base */
void ipc_registrar_base(void)
{
    ipc_registrar("srv:", srv_atender);
    ipc_registrar("err:f", errf_atender);
    ipc_registrar("fs:USER", fs_user_atender);
    ipc_registrar("APT:U", apt_atender);
    ipc_registrar("cfg:u", cfg_atender);
    ipc_registrar("dsp::DSP", dsp_atender);
    ipc_registrar("ndm:u", ndm_atender);
    ipc_registrar("mic:u", mic_atender);
    ipc_registrar("cecd:u", cecd_atender);
    ipc_registrar("cecd:s", cecd_atender);   /* segunda sesion de StreetPass */
    ipc_registrar("gsp::Gpu", gsp_provisional);
    ipc_registrar("hid:USER", hid_provisional);
    /* del exheader (agente S): el juego no los abre hoy, pero si lo hace no cae en "servicio sin implementar" */
    ipc_registrar("ptm:u", ptm_atender);
    ipc_registrar("ac:u", ac_atender);
    ipc_registrar("frd:u", frd_atender);
    ipc_registrar("gsp::Lcd", lcd_atender);
    ipc_registrar("boss:U", generico_atender);
    ipc_registrar("news:u", generico_atender);
    ipc_registrar("cam:u", generico_atender);
    ipc_registrar("y2r:u", generico_atender);
    ipc_registrar("ir:USER", generico_atender);
    ipc_registrar("nwm::UDS", generico_atender);
}

/* ============================================================ enganche del hid real (agente D) */
static SisObj *hid_d_ev[5];

void sis_hid_preparar(u8 **pagina, u32 *h_shm, u32 h_ev[5])
{
    *h_shm = sis_handle_nuevo(sis_bloque_nuevo(0x1000, pagina));
    for (int i = 0; i < 5; i++) { hid_d_ev[i] = sis_evento_nuevo(0); h_ev[i] = sis_handle_nuevo(hid_d_ev[i]); }
}

void sis_senal_hid(void *ctx, int evento)
{
    (void)ctx;
    if (evento >= 0 && evento < 5) sis_senalar(hid_d_ev[evento]);
}
