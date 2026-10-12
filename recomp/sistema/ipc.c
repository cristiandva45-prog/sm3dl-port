/* Capa IPC HLE: registro de servicios por nombre y despachador de SendSyncRequest.
 * El comando vive en TLS+0x80 del hilo que llama: cabecera (id<<16 | normales<<6 | traducidos), luego las palabras
 * normales y luego las traducidas (descriptor + datos). Este archivo decodifica y traduce los descriptores como lo
 * haria el kernel y le pasa la peticion al manejador del servicio, que responde en el mismo buffer.
 * Semantica de la cabecera y los descriptores tomada de la documentacion de Horizon (Azahar hle/ipc.h solo como
 * referencia); escrito desde cero. Se compila dentro de sistema.c (ver el final de ese archivo). */
#ifdef SIS_IPC_SEPARADO
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sistema.h"
#endif

u32 ipc_pid = 0x28;
u32 ipc_sin_implementar;

/* ---------------------------------------------------------------- copia anfitrion <-> juego */

void sis_copiar_a_juego(u32 dir, const void *src, u32 n)
{
    const u8 *s = src;
    while (n) {
        u32 k = 0x1000u - (dir & 0xFFFu);
        if (k > n) k = n;
        memcpy(P(dir), s, k);
        dir += k; s += k; n -= k;
    }
}

void sis_copiar_de_juego(void *dst, u32 dir, u32 n)
{
    u8 *d = dst;
    while (n) {
        u32 k = 0x1000u - (dir & 0xFFFu);
        if (k > n) k = n;
        memcpy(d, P(dir), k);
        dir += k; d += k; n -= k;
    }
}

/* ---------------------------------------------------------------- registro nombre -> manejador */

#define IPC_MAX_SERVICIOS 48
typedef struct { char nombre[16]; IpcManejador m; IpcCrudo crudo; void *ctx; } IpcEntrada;
static IpcEntrada ipc_tabla[IPC_MAX_SERVICIOS];
static int ipc_n_tabla;

static IpcEntrada *ipc_entrada(const char *nombre, int crear)
{
    for (int i = 0; i < ipc_n_tabla; i++)
        if (strcmp(ipc_tabla[i].nombre, nombre) == 0) return &ipc_tabla[i];
    if (!crear || ipc_n_tabla == IPC_MAX_SERVICIOS || strlen(nombre) >= sizeof ipc_tabla[0].nombre) return NULL;
    strcpy(ipc_tabla[ipc_n_tabla].nombre, nombre);
    return &ipc_tabla[ipc_n_tabla++];
}

int ipc_registrar(const char *nombre, IpcManejador m)
{
    IpcEntrada *e = ipc_entrada(nombre, 1);
    if (!e || !m) return -1;
    e->m = m; e->crudo = NULL; e->ctx = NULL;
    return 0;
}

/* sesiones de un servicio crudo: datos = su entrada en la tabla */
static void ipc_trampolin_crudo(IpcPeticion *p)
{
    IpcEntrada *e = p->ses->datos;
    if (!e->crudo(e->ctx, p->cmd, p->ses->serie)) ipc_no_implementado(p, 1);
}

int ipc_registrar_crudo(const char *nombre, IpcCrudo f, void *ctx)
{
    IpcEntrada *e = ipc_entrada(nombre, 1);
    if (!e || !f) return -1;
    e->m = ipc_trampolin_crudo; e->crudo = f; e->ctx = ctx;
    return 0;
}

IpcManejador ipc_buscar(const char *nombre)
{
    IpcEntrada *e = ipc_entrada(nombre, 0);
    return e ? e->m : NULL;
}

IpcSesion *ipc_abrir(const char *nombre, Servicio srv)
{
    IpcEntrada *e = ipc_entrada(nombre, 0);
    if (!e || !e->m) return NULL;
    /* el nombre apunta a la tabla (vive siempre); los crudos reciben su entrada como datos */
    return ipc_sesion_nueva(e->nombre, e->m, e->crudo ? (void *)e : NULL, srv);
}

IpcSesion *ipc_sesion_nueva(const char *nombre, IpcManejador m, void *datos, Servicio srv)
{
    IpcSesion *s = calloc(1, sizeof *s);
    static u32 serie;
    s->nombre = nombre; s->atender = m; s->datos = datos; s->srv = srv; s->serie = ++serie;
    return s;
}

/* ---------------------------------------------------------------- ayudas para armar respuestas */

void ipc_respuesta(IpcPeticion *p, u32 normales, u32 traducidos, u32 resultado)
{
    p->cmd[0] = IPC_CAB(p->id, normales, traducidos);
    for (u32 i = 1; i <= normales; i++) p->cmd[i] = 0;
    if (normales) p->cmd[1] = resultado;
}

IpcDesc *ipc_desc(IpcPeticion *p, IpcTipoDesc tipo, u32 indice)
{
    for (u32 i = 0; i < p->n_desc; i++)
        if (p->desc[i].tipo == tipo && indice-- == 0) return &p->desc[i];
    return NULL;
}

u32 ipc_salida_estatica(IpcPeticion *p, u32 w, u32 id, const void *datos, u32 tam)
{
    u32 rb = p->tls + 0x180u + 8u * (id & 0xFu);   /* buffers estaticos de RECEPCION que declaro el cliente */
    u32 desc = R32(rb), dir = R32(rb + 4);
    u32 cap = ((desc & 0xFu) == 0x2u) ? desc >> 14 : 0;
    u32 n = tam < cap ? tam : cap;
    if (tam > cap)
        fprintf(stderr, "[ipc] %s cmd 0x%04X: salida estatica %u de %u bytes (buffer %u del cliente: 0x%08X)\n",
                p->ses->nombre, p->id, n, tam, id, desc);
    if (n) sis_copiar_a_juego(dir, datos, n);
    p->cmd[w] = IPC_DESC_ESTATICO(n, id);
    p->cmd[w + 1] = dir;
    return n;
}

static struct { const char *nombre; u32 id; } ipc_vistos_ni[512];

void ipc_no_implementado(IpcPeticion *p, u32 normales)
{
    u32 i;
    for (i = 0; i < ipc_sin_implementar && i < 512; i++)
        if (ipc_vistos_ni[i].id == p->id && strcmp(ipc_vistos_ni[i].nombre, p->ses->nombre) == 0) break;
    if (i == ipc_sin_implementar) {
        if (i < 512) { ipc_vistos_ni[i].nombre = p->ses->nombre; ipc_vistos_ni[i].id = p->id; }
        ipc_sin_implementar++;
        fprintf(stderr, "[ipc] SIN IMPLEMENTAR %s cmd 0x%04X (cabecera 0x%08X, hilo %u): responde \"todo bien\"\n",
                p->ses->nombre, p->id, p->cab, sis_hilo_actual_id());
    }
    ipc_respuesta(p, normales ? normales : 1, 0, RES_OK);
}

/* ---------------------------------------------------------------- traduccion de la peticion */

/* devuelve 0 si la peticion es valida */
static int ipc_decodificar(IpcPeticion *p)
{
    u32 *cmd = p->cmd;
    if (1 + p->normales + p->traducidos > 64) return -1;
    u32 i = 1 + p->normales, fin = i + p->traducidos;
    while (i < fin) {
        u32 d = cmd[i];
        if (p->n_desc == IPC_MAX_DESC) return -2;
        IpcDesc *x = &p->desc[p->n_desc++];
        memset(x, 0, sizeof *x);
        x->palabra = i;
        if ((d & 0xFu) == 0x0u) {                     /* handles: copia, mover o pid */
            u32 n = (d >> 26) + 1, t = (d >> 4) & 3;
            if (t == 2) {                             /* CallingPid: el kernel escribe el pid del cliente */
                x->tipo = IPC_D_PID; x->n = 1;
                if (i + 1 >= fin) return -3;
#ifndef SABOTAJE_PID
                cmd[i + 1] = ipc_pid;
#endif
                i += 2;
                continue;
            }
            if (t == 3 || n > 8 || i + n >= fin) return -4;
            x->tipo = t == 1 ? IPC_D_MOVER : IPC_D_COPIA;
            x->n = n;
            for (u32 k = 0; k < n; k++) {
                u32 h = cmd[i + 1 + k];
                x->objs[k] = h ? sis_obj_de_handle(h) : NULL;
                if (h && !x->objs[k] && h < 0xFFFF8000u)   /* 0xFFFF8000/8001 = hilo/proceso actual: validos */
                    fprintf(stderr, "[ipc] %s cmd 0x%04X: handle malo 0x%08X en la peticion\n", p->ses->nombre, p->id, h);
                if (t == 1 && h && h < 0xFFFF8000u) sis_handle_cerrar(h);   /* mover: el cliente lo pierde */
            }
            i += 1 + n;
        } else if ((d & 0xFu) == 0x2u) {              /* buffer estatico (el cliente envia dir + tamano) */
            if (i + 1 >= fin) return -5;
            x->tipo = IPC_D_ESTATICO; x->tam = d >> 14; x->extra = (d >> 10) & 0xF; x->dir = cmd[i + 1];
            i += 2;
        } else if ((d & 0xEu) == 0x4u) {              /* PXI */
            if (i + 1 >= fin) return -6;
            x->tipo = IPC_D_PXI; x->tam = d >> 8; x->extra = (d >> 4) & 0xF; x->dir = cmd[i + 1];
            i += 2;
        } else if (d & 0x8u) {                        /* buffer mapeado: misma memoria, se pasa la direccion */
            if (i + 1 >= fin) return -7;
            x->tipo = IPC_D_MAPEADO; x->tam = d >> 4;
#ifdef SABOTAJE_DESC_MAPEADO
            x->tam = d >> 5;
#endif
            x->extra = (d >> 1) & 3; x->dir = cmd[i + 1];
            i += 2;
        } else {
            return -8;
        }
    }
    return 0;
}

void ipc_despachar(CPU *c, IpcSesion *s)
{
    IpcPeticion p;
    memset(&p, 0, sizeof p);
    p.c = c; p.tls = c->tls; p.cmd = (u32 *)P(c->tls + 0x80); p.ses = s;
    p.cab = p.cmd[0]; p.id = p.cab >> 16; p.normales = (p.cab >> 6) & 0x3F; p.traducidos = p.cab & 0x3F;
    if (s->srv < SRV_CUENTA) sis_comandos_vistos[s->srv]++;
    if (sis_traza || (s->srv < SRV_CUENTA && sis_comandos_vistos[s->srv] <= 64))
        fprintf(stderr, "[ipc] %-16s cmd 0x%08X (id 0x%04X)\n", s->nombre, p.cab, p.id);
    int e = ipc_decodificar(&p);
    if (e) {
        fprintf(stderr, "[ipc] %s: peticion mal formada 0x%08X (error %d)\n", s->nombre, p.cab, e);
        ipc_respuesta(&p, 1, 0, IPC_RES_CAB_MALA);
        return;
    }
    s->atender(&p);
}
