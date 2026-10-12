/* Capa de sistema del port nativo: hace de kernel (Horizon) y de servicios del 3DS para el codigo recompilado.
 *
 * - Cada hilo del juego es una FIBRA de Windows con su propio CPU virtual: el codigo recompilado se anida en la pila
 *   nativa de la fibra, asi que cambiar de hilo a mitad de una funcion es un SwitchToFiber.
 * - Planificador cooperativo por prioridad (como el nucleo de la app en Horizon, que no reparte tiempo entre
 *   hilos de igual prioridad): solo se cambia de hilo dentro de una svc.
 * - Los servicios (IPC) se atienden en el momento, dentro de SendSyncRequest (HLE).
 * Diseno completo: recomp\sistema\DISENO.md. Lista de svc: recomp\sistema\svcs.md.
 */
#ifndef SISTEMA_H
#define SISTEMA_H

#include "recomp.h"

/* --- mapa de memoria del 3DS (vista de la aplicacion) --- */
#define SIS_HEAP          0x08000000u  /* ControlMemory COMMIT */
#define SIS_SHM           0x10000000u  /* bloques compartidos que el juego mapea sin direccion; la pila principal termina aqui */
#define SIS_LINEAL        0x14000000u  /* ControlMemory LINEAR (FCRAM contigua: la que lee la GPU) */
#define SIS_VRAM          0x1F000000u
#define SIS_CONFIG        0x1FF80000u  /* config memory (version del kernel, memoria de la app) */
#define SIS_PAGINA_COMP   0x1FF81000u  /* shared page (hora, estado de la bateria, 3D) */
#define SIS_TLS           0x1FF82000u  /* TLS: 0x200 por hilo; comando IPC en TLS+0x80 */
#define SIS_TLS_TAM       0x200u
#define SIS_TICKS_SEG     268111856ull /* reloj del ARM11 */

/* resultados de Horizon que el juego compara */
#define RES_OK            0x00000000u
#define RES_TIMEOUT       0x09401BFEu
#define RES_HANDLE_MALO   0xD8E007F7u
#define RES_NO_HAY        0xD8E0080Au   /* no se encontro (servicio desconocido) */

#define HANDLE_HILO_ACTUAL    0xFFFF8000u
#define HANDLE_PROCESO_ACTUAL 0xFFFF8001u

/* --- memoria del juego --- */
u8 *sis_mapear(u32 addr, u32 tam);                     /* reserva memoria del anfitrion (en cero) y la ve en addr */
void sis_mapear_host(u32 addr, u32 tam, u8 *host);     /* ve memoria ya existente en addr (p. ej. code.bin) */
int sis_mapeada(u32 addr);

/* --- arranque --- */
typedef void (*SisLog)(const char *texto);
void sis_iniciar(void);                                         /* config memory, pagina compartida, objetos base */
void sis_correr(u32 entrada, u32 pila_tope, u32 prioridad);     /* crea el hilo principal y planifica hasta ExitProcess o bloqueo total */

/* enganche de las svc: compatible con rt_enganches() de runtime.c (el numero llega en c->r[15]) */
void sis_svc(CPU *c, u32 addr);
/* lo mismo con el numero explicito */
void sis_svc_num(CPU *c, u32 num, u32 addr);

/* --- servicios (HLE) --- */
typedef enum {
    SRV_NINGUNO = 0, SRV_SRV, SRV_ERRF, SRV_GSP, SRV_HID, SRV_FS, SRV_DSP, SRV_APT, SRV_CFG, SRV_NDM, SRV_MIC, SRV_CECD,
    SRV_DESCONOCIDO_3E3190, SRV_CUENTA
} Servicio;
const char *sis_nombre_servicio(Servicio s);
Servicio sis_servicio_por_nombre(const char *nombre);   /* SRV_NINGUNO si no es uno de los conocidos */
/* contador de comandos recibidos por servicio (para el registro del primer arranque) */
extern u32 sis_comandos_vistos[SRV_CUENTA];

/* ===================================================================================================================
 * PUNTO DE ENCHUFE DE SERVICIOS (IPC HLE). Implementacion: ipc.c (despachador), srv.c (srv:, err:f),
 * stubs.c (APT, cfg, dsp, ndm, mic, cecd:u/s y los hid/gsp provisionales), fs.c (fs:USER real).
 *
 * Un servicio = un nombre + un manejador. Para enchufar uno nuevo (o reemplazar el provisional):
 *
 *     static void hid_atender(IpcPeticion *p) { switch (p->id) { ... } }
 *     ...
 *     sis_iniciar();                          // registra los de base
 *     ipc_registrar("hid:USER", hid_atender); // el ultimo registro con el mismo nombre gana
 *
 * El manejador lee el comando en p->cmd (vista del anfitrion de TLS+0x80; los descriptores de la peticion ya vienen
 * traducidos en p->desc[]), escribe la respuesta en el mismo p->cmd y vuelve. Se ejecuta DENTRO de
 * SendSyncRequest, en la fibra del hilo que llamo: no puede bloquear (si necesita esperar, que senale un evento).
 * Lo que no implemente: ipc_no_implementado(p, normales) (registra una vez y responde "todo bien").
 * =================================================================================================================== */
typedef struct Obj SisObj;          /* objeto del kernel (evento, mutex, bloque, sesion...) */
typedef struct IpcSesion IpcSesion;

/* objetos del kernel para los servicios. Guardar el SisObj*, no el handle: el juego puede cerrar su handle. */
SisObj *sis_evento_nuevo(int reinicio);           /* 0 oneshot, 1 sticky, 2 pulse */
SisObj *sis_mutex_nuevo(void);
SisObj *sis_bloque_nuevo(u32 tam, u8 **host);     /* memoria compartida (en cero); *host = vista del anfitrion */
SisObj *sis_obj_de_handle(u32 handle);            /* NULL si no existe */
u32  sis_handle_nuevo(SisObj *o);                 /* un handle NUEVO del juego hacia o (como una copia) */
void sis_handle_cerrar(u32 handle);
void sis_senalar(SisObj *evento);                 /* senala y despierta (sin ceder: el cambio de hilo llega en la proxima svc) */
void sis_limpiar(SisObj *evento);
int  sis_es_evento(SisObj *o);
void sis_detener(const char *motivo);
void sis_senalar_handle(u32 handle);              /* lo mismo por handle (gsp: el evento que paso el juego) */

/* eventos periodicos del anfitrion (VBlank de GSP a 59,83 Hz, muestreo de HID a 234 Hz...): el planificador llama f
 * cada periodo_ns (entre cambios de hilo y mientras todos duermen) y despues despierta a quien espere lo senalado.
 * Con alguno registrado, "nadie listo" ya no es bloqueo total: se duerme hasta el proximo. */
int sis_periodico(void (*f)(void), u64 periodo_ns);

/* --- enganche del hid real (agente D, reportes/hid.md seccion 5) ---
 * sis_hid_preparar crea la pagina compartida (0x1000; el juego la mapea con MapMemoryBlock) y 5 eventos oneshot
 * (PAD0, PAD1, accel, gyro, debugpad) y da sus handles para g_hid.h_shm / g_hid.h_ev[]. Luego:
 *     hid_srv_iniciar(&g_hid, pagina, sis_senal_hid, NULL);
 * sis_senal_hid(ctx, evento) senala el evento `evento` (0..4) creado aqui (ctx se ignora).
 * Los adaptadores ya escritos estan en enchufes.c (se activan con -DSIS_CON_HID / -DSIS_CON_GSP). */
void sis_hid_preparar(u8 **pagina, u32 *h_shm, u32 h_ev[5]);
void sis_senal_hid(void *ctx, int evento);
void sis_enchufar_externos(void);
u64 sis_ticks(void);                              /* reloj del 3DS (268.111.856 Hz), el mismo de GetSystemTick */
/* direccion fisica (FCRAM 0x20000000, VRAM 0x18000000, RAM del DSP 0x1FF00000) -> virtual del juego (0 si no hay) */
u32 sis_fisica_a_virtual(u32 fisica);
u8 *sis_fisica_a_host(u32 fisica, u32 n);         /* NULL si no esta mapeada o no es contigua en el anfitrion */                /* enchufes.c: registra hid/gsp reales si se compilaron */             /* fin ordenado (err:f, fallo): el planificador sale tras la svc actual */

/* --- peticion IPC ya decodificada --- */
#define IPC_MAX_DESC 8
typedef enum { IPC_D_COPIA, IPC_D_MOVER, IPC_D_PID, IPC_D_ESTATICO, IPC_D_PXI, IPC_D_MAPEADO } IpcTipoDesc;
typedef struct {
    IpcTipoDesc tipo;
    u32 palabra;        /* indice en cmd[] del descriptor */
    u32 n;              /* handles: cuantos */
    SisObj *objs[8];    /* handles: objetos ya resueltos (NULL si el handle era 0 o malo) */
    u32 dir, tam;       /* buffers: direccion del juego y tamano */
    u32 extra;          /* estatico: id del buffer; mapeado: permisos (1 R, 2 W, 3 RW) */
} IpcDesc;

struct IpcPeticion;
typedef void (*IpcManejador)(struct IpcPeticion *p);

struct IpcSesion {
    const char *nombre;     /* "fs:USER", "fs:USER/archivo", ... (para el registro) */
    IpcManejador atender;
    void *datos;            /* estado propio de la sesion (p. ej. el archivo abierto) */
    Servicio srv;           /* para las estadisticas */
    SisObj *obj;            /* su objeto de kernel (lo crea ipc_obj_sesion) */
    u32 serie;              /* id estable de la sesion (1, 2, ...) */
};

typedef struct IpcPeticion {
    CPU *c;
    u32 *cmd;               /* TLS+0x80 del hilo que llama (64 palabras) */
    u32 tls;                /* TLS del juego (para los buffers estaticos de recepcion en TLS+0x180) */
    u32 cab, id, normales, traducidos;
    u32 n_desc;
    IpcDesc desc[IPC_MAX_DESC];
    IpcSesion *ses;
} IpcPeticion;

int  ipc_registrar(const char *nombre, IpcManejador m);       /* 0 ok; reemplaza si ya existe */
/* Variante "cruda" para modulos que no incluyen este encabezado (recomp/hid, recomp/gpu): f(ctx, cmd, sesion) recibe
 * el buffer de comando (TLS+0x80; los buffers estaticos de recepcion estan en cmd+0x40), un id estable de la sesion
 * (su numero de serie) y devuelve 1 si respondio; 0 = no lo conoce (se registra y responde "todo bien"). */
typedef int (*IpcCrudo)(void *ctx, u32 *cmd, u32 sesion);
int  ipc_registrar_crudo(const char *nombre, IpcCrudo f, void *ctx);
IpcManejador ipc_buscar(const char *nombre);
IpcSesion *ipc_abrir(const char *nombre, Servicio srv);      /* sesion nueva al servicio registrado; NULL si no hay */
IpcSesion *ipc_sesion_nueva(const char *nombre, IpcManejador m, void *datos, Servicio srv);
SisObj *ipc_obj_sesion(IpcSesion *s);                        /* objeto de kernel de la sesion (dar handle con sis_handle_nuevo) */
void ipc_despachar(CPU *c, IpcSesion *s);                    /* lo llama SendSyncRequest */
void ipc_registrar_base(void);                               /* srv:, err:f, fs:USER y los provisionales */

/* armar la respuesta */
#define IPC_CAB(id, normales, traducidos) (((u32)(id) << 16) | ((u32)(normales) << 6) | (u32)(traducidos))
#define IPC_DESC_COPIA(n)   ((((u32)(n) - 1) << 26) | 0x00u)
#define IPC_DESC_MOVER(n)   ((((u32)(n) - 1) << 26) | 0x10u)
#define IPC_DESC_ESTATICO(tam, id) (((u32)(tam) << 14) | (((u32)(id) & 0xF) << 10) | 0x2u)
#define IPC_DESC_MAPEADO(tam, perm) (((u32)(tam) << 4) | 0x8u | (((u32)(perm) & 3) << 1))
void ipc_respuesta(IpcPeticion *p, u32 normales, u32 traducidos, u32 resultado);   /* cabecera + resultado; normales en 0 */
IpcDesc *ipc_desc(IpcPeticion *p, IpcTipoDesc tipo, u32 indice);                   /* el indice-esimo de ese tipo, o NULL */
/* copia datos al buffer estatico de recepcion `id` del cliente (TLS+0x180) y escribe desc+dir en cmd[w], cmd[w+1]; devuelve lo copiado */
u32 ipc_salida_estatica(IpcPeticion *p, u32 w, u32 id, const void *datos, u32 tam);
void ipc_no_implementado(IpcPeticion *p, u32 normales);
extern u32 ipc_pid;
extern u32 ipc_sin_implementar;   /* cuantos (servicio, comando) distintos cayeron en ipc_no_implementado */
#define IPC_RES_CAB_MALA 0xD9001830u   /* cabecera o descriptor imposible */

/* fs:USER (fs.c): ROM descifrada (.3ds) de la que se sirve el RomFS y carpeta del guardado.
 * NULL = no cambiar. Por defecto: variables SM3DL_ROM y SM3DL_GUARDADO, o las rutas del proyecto. */
void fs_configurar(const char *rom, const char *carpeta_guardado);

/* copiar entre el anfitrion y la memoria del juego (cruza paginas) */
void sis_copiar_a_juego(u32 dir, const void *src, u32 n);
void sis_copiar_de_juego(void *dst, u32 dir, u32 n);          /* lo que el kernel escribe para un descriptor CallingPid */

/* --- informacion para pruebas y depuracion --- */
u32 sis_hilo_actual_id(void);
CPU *sis_hilo_actual_cpu(void);   /* registros del juego del hilo que corre (diagnostico) */
extern int sis_traza;   /* 1: imprime cada svc */

#endif
