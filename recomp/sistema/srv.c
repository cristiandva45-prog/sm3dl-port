/* srv: (gestor de servicios) y err:f. Numeros de comando segun la documentacion de Horizon (Azahar solo como
 * referencia, reimplementado). Se compila dentro de sistema.c. */
#ifdef SIS_IPC_SEPARADO
#include <stdio.h>
#include <string.h>
#include "sistema.h"
#endif

static SisObj *srv_semaforo;   /* EnableNotification: nunca se senala (no hay notificaciones de sistema) */

static void srv_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    switch (p->id) {
    case 0x0001:                                  /* RegisterClient(pid) */
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    case 0x0002:                                  /* EnableNotification -> semaforo */
        if (!srv_semaforo) srv_semaforo = sis_evento_nuevo(1);
        ipc_respuesta(p, 1, 2, RES_OK);
        cmd[2] = IPC_DESC_COPIA(1); cmd[3] = sis_handle_nuevo(srv_semaforo);
        return;
    case 0x0005: {                                /* GetServiceHandle(nombre[8], largo, flags) -> sesion */
        char nombre[9] = {0};
        memcpy(nombre, &cmd[1], 8);
        nombre[cmd[3] < 8 ? cmd[3] : 8] = 0;   /* cmd[1..2] nombre, cmd[3] largo, cmd[4] flags */
        Servicio sv = sis_servicio_por_nombre(nombre);
        if (sv == SRV_NINGUNO && strcmp(nombre, "cecd:s") == 0) sv = SRV_CECD;
        IpcSesion *s = ipc_abrir(nombre, sv);
        if (!s) {
            fprintf(stderr, "[ipc] srv: servicio sin implementar \"%s\"\n", nombre);
            ipc_respuesta(p, 1, 0, RES_NO_HAY);
            return;
        }
        ipc_respuesta(p, 1, 2, RES_OK);
        cmd[2] = IPC_DESC_MOVER(1); cmd[3] = sis_handle_nuevo(ipc_obj_sesion(s));
        return;
    }
    case 0x0009: case 0x000A:                     /* Subscribe / Unsubscribe(id) */
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    case 0x000B:                                  /* ReceiveNotification -> id (0: ninguna) */
        ipc_respuesta(p, 2, 0, RES_OK);
        return;
    default:
        ipc_no_implementado(p, 1);
        return;
    }
}

static void errf_atender(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    if (p->id == 0x0001) {                        /* ThrowFatalError(ErrInfo de 0x80 bytes en cmd[1..]) */
        fprintf(stderr, "[ipc] err:f ThrowFatalError: tipo %u, resultado 0x%08X, pc 0x%08X\n", cmd[1] & 0xFF, cmd[2], cmd[3]);
        sis_detener("err:f ThrowFatalError");
        ipc_respuesta(p, 1, 0, RES_OK);
        return;
    }
    ipc_no_implementado(p, 1);
}
