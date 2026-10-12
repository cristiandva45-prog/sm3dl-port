"""Migracion de raster_gl.c (8 oct 2026, agente A, tanda D3D12 paso 1): parte de raster_gl.c.antes_dx12_A y deja la capa
comun hablando solo con el backend (raster_backend.h). Cada reemplazo exige que el texto viejo exista EXACTAMENTE una vez.
Uso (desde la raiz del proyecto): py -I agentes_dx12\\A\\tools\\migrar_raster.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from util import rd, wr, sub

R = 'recomp/render/'
T = rd(R + 'raster_gl.c.antes_dx12_A')


def rep(t, ini, fin, nuevo):
    """reemplaza desde 'ini' (unico) hasta el primer 'fin' que le sigue (incluido)"""
    assert t.count(ini) == 1, ('inicio no unico', t.count(ini), ini[:70])
    i = t.index(ini)
    j = t.index(fin, i)
    assert j >= i
    return t[:i] + nuevo + t[j + len(fin):]


# ----------------------------------------------------------------------------------------------- cabecera
T = rep(T, '#define WIN32_LEAN_AND_MEAN', 'extern void (*pica_raster)(const PicaEstado *e);\n', '''#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pica.h"
#include "texturas.h"
#include "gsp.h"
#include "raster_gl.h"
#include "raster_backend.h"

extern void (*pica_raster)(const PicaEstado *e);
''')

T = rep(T, '/* ------------------------------------------------------------------ funciones GL > 1.1 */',
        'static uint64_t g_v_unicos;   /* vertices decodificados por el camino con indices (rango unico) */\n', '''/* ------------------------------------------------------------------ backend de GPU (raster_backend.h)
   Esta capa NO ve la API grafica: todo pasa por la tabla 'rb' (RasterBackend), que se elige con SM3DL_BACKEND (ver
   elegir_backend, al final). El backend GL (raster_backend_gl.c) se incluye al FINAL del archivo, asi que en este codigo
   no existe ni un simbolo de OpenGL: si alguien lo usara, no compilaria. */
static const RasterBackend *g_rb;
static const RasterBackend *elegir_backend(void);
#define rb (g_rb ? g_rb : elegir_backend())

static uint64_t g_v_unicos;   /* vertices decodificados por el camino con indices (rango unico) */
''')

T = rep(T, 'static int iniciar_gl(void)\n{',
        '        logr("wglMakeCurrent fallo (%lu): otro hilo del SO?", GetLastError());\n        return 0;\n    }\n    return 1;\n}\n',
        '''/* crea el dispositivo la primera vez; 1 si esta listo */
static int iniciar_gl(void) { return rb->iniciar(); }

/* el contexto es del hilo que lo creo; todas las fibras del juego corren en ese hilo, pero el backend lo comprueba */
static int contexto_actual(void) { return rb->contexto_actual(); }
''')

# ----------------------------------------------------------------------------------------------- programas
T = rep(T, '/* uniforms del programa: (campo, nombre GLSL) */', 'static uint32_t fnv_texto(const char *t);\n', '''/* Programa = (vertex shader del juego envuelto) + (fragment shader especializado por clave) + (GS de flip si hay
   luz). Los VS y FS compilados se guardan aparte y se reutilizan entre programas. Los uniforms de antes son ahora
   BLOQUES DE CONSTANTES (RbCbVertice/Fragmento/Niebla/Luz): los reparte el backend (en GL: los mismos glUniform*). */
/* src/hsrc: el texto se guarda y se compila SOLO si el programa no esta en la cache de binarios (ver abajo) */
typedef struct { uint32_t clave, entrada; RbEtapa *vs; int malo; char nombre[64]; char *src; uint32_t hsrc; } VsCache;
static VsCache g_vs[64];
static int g_nvs;

#define MAX_CLAVE 40
typedef struct { uint32_t hash, n, k[MAX_CLAVE]; RbEtapa *fs; int malo; char *src; uint32_t hsrc; } FsCache;
#define MAX_FS 1024
static FsCache g_fs[MAX_FS];
static int g_nfs;
static RbEtapa *g_gs_flip;

typedef struct {
    int vs, fs, gs;           /* indices en g_vs / g_fs; gs = variante con geometry shader de flip de cuaternion */
    RbProg *prog;
} Programa;
#define MAX_PROG 1024
static Programa g_prog[MAX_PROG];
static int g_nprog;
/* SM3DL_RASTER_UBER=1: un solo fragment shader con TODO por uniforms (sin especializar; mas lento, mismo resultado) */
static int g_frag_uniforme = -1;
static int luz_mues_de(uint32_t c0, uint32_t c1);
static uint32_t fnv_texto(const char *t);
''')

T = rep(T, 'static double reloj(void);\nstatic GLuint compilar(', '    return s;\n}\n', 'static double reloj(void);\n')

T = sub(T, '''        for (int j = 0; j < g_nprog; j++) gl.DeleteProgram(g_prog[j].prog);
        g_nprog = 0;
        for (int j = 0; j < g_nfs; j++) { if (g_fs[j].fs) gl.DeleteShader(g_fs[j].fs); free(g_fs[j].src); }''',
        '''        for (int j = 0; j < g_nprog; j++) rb->prog_destruir(g_prog[j].prog);
        g_nprog = 0;
        for (int j = 0; j < g_nfs; j++) { if (g_fs[j].fs) rb->etapa_destruir(g_fs[j].fs); free(g_fs[j].src); }''')
T = sub(T, '    for (int k = 0; k < g_nprog; k++) gl.DeleteProgram(g_prog[k].prog);\n',
        '    for (int k = 0; k < g_nprog; k++) rb->prog_destruir(g_prog[k].prog);\n')

T = rep(T, '/* ------------------------------------------------------------------ cache de programas enlazados en disco',
        'static uint32_t g_bin_driver;\n', '''/* ------------------------------------------------------------------ cache de programas enlazados en disco
   La hace el backend (prog_cargar_cache / prog_guardar_cache; en GL con glProgramBinary, ver raster_backend_gl.c): la
   cache de shaders del driver de Intel es POR NOMBRE DE EXE (81 s recompilando en un exe nuevo); con ella cada programa
   enlazado se guarda en extraido\\shaders\\cache_gl\\ y se carga en milisegundos en cualquier exe.
   SM3DL_SIN_CACHE_GL=1 la apaga. Aqui solo se cuenta. */
static uint32_t g_bin_cargados, g_bin_compilados, g_bin_rechazados;
static double g_t_compilar;
''')

T = rep(T, 'static void binario_ruta(', '    return p;\n}\n', '''static Programa *programa_para(const PicaShader *vs, const uint32_t *r)
{
    if (g_frag_uniforme < 0) {
        const char *s = getenv("SM3DL_RASTER_UBER");
        g_frag_uniforme = s && *s && *s != '0';
        if (g_frag_uniforme) logr("fragment shader uber por uniforms (sin especializar)");
    }
    int gs = (r[0x1C6] & 1) == 0;   /* con luz: GS de flip del cuaternion */
    int iv = vs_para(vs);
    if (iv < 0) return NULL;
    int ifs = fs_para(r);
    if (ifs < 0) return NULL;
    for (int k = 0; k < g_nprog; k++)
        if (g_prog[k].vs == iv && g_prog[k].fs == ifs && g_prog[k].gs == gs) return &g_prog[k];
    if (gs && !g_gs_flip && !(g_gs_flip = rb->etapa_compilar(RB_ETAPA_GS, GEOM_FLIP, "geometria (flip)"))) return NULL;
    if (g_nprog >= MAX_PROG) { logr("%d programas: se descartan y se rehacen", g_nprog); olvidar_programas(); }
    Programa *p = &g_prog[g_nprog];
    memset(p, 0, sizeof *p);
    p->vs = iv; p->fs = ifs; p->gs = gs;
    int rechazado = 0;
    p->prog = rb->prog_cargar_cache(g_vs[iv].hsrc, g_fs[ifs].hsrc, gs, &rechazado);
    if (rechazado) g_bin_rechazados++;
    if (p->prog) g_bin_cargados++;
    if (!p->prog) {
        double tl = reloj();
        if (!g_vs[iv].vs && !(g_vs[iv].vs = rb->etapa_compilar(RB_ETAPA_VS, g_vs[iv].src, g_vs[iv].nombre))) {
            g_vs[iv].malo = 1;
            return NULL;
        }
        if (!g_fs[ifs].fs && !(g_fs[ifs].fs = rb->etapa_compilar(RB_ETAPA_FS, g_fs[ifs].src, "fragmento"))) {
            g_fs[ifs].malo = 1;
            return NULL;
        }
        p->prog = rb->prog_enlazar(g_vs[iv].vs, g_fs[ifs].fs, gs ? g_gs_flip : NULL, g_vs[iv].nombre);
        if (!p->prog) return NULL;
        g_bin_compilados++;
        g_t_compilar += reloj() - tl;
        rb->prog_guardar_cache(p->prog, g_vs[iv].hsrc, g_fs[ifs].hsrc, gs);
    }
    g_nprog++;
    static int avisos;
    if (++avisos <= 8 || avisos % 50 == 0)
        logr("programa %d: %s + fragmento %d%s (%d fragment shaders)", g_nprog, g_vs[iv].nombre, ifs,
             gs ? " + GS flip" : "", g_nfs);
    return p;
}
''')

# ----------------------------------------------------------------------------------------------- render targets
T = sub(T, '    GLuint fbo, tex, rb;\n', '    RbRT *rt;                 /* superficie de color RGBA8 + D24S8 (w*s x h*s) */\n')
T = rep(T, '/* FBO de trabajo a tamano nativo (para reducir un RT grande antes de leerlo) */',
        '    if (crono_on()) cr_sumar(CR_LIGAR, c0);\n}\n', '''/* deja listo para LEER (rt_leer) el RT a su tamano nativo: el propio RT si s == 1; si no, el backend lo reduce en la
   GPU (blit lineal = promedio) a una superficie de trabajo a tamano nativo */
static RbRT *ligar_nativo(const Rt *t)
{
    if (t->s <= 1) return t->rt;
    double c0 = reloj();
    gq_ini(GQ_LIGAR);
    RbRT *f = rb->rt_reducir(t->rt, t->w, t->h);
    gq_fin();
    if (crono_on()) cr_sumar(CR_LIGAR, c0);
    return f;
}
''')
T = sub(T, 'enum { GQ_DIB, GQ_LIGAR, GQ_COPIAR, GQ_GIRO, GQ_SUBIR, GQ_N };',
        'enum { GQ_DIB = RB_GQ_DIB, GQ_LIGAR = RB_GQ_LIGAR, GQ_COPIAR = RB_GQ_COPIAR, GQ_GIRO = RB_GQ_GIRO,\n       GQ_SUBIR = RB_GQ_SUBIR, GQ_N = RB_GQ_N };   /* los mismos numeros que el backend */')
T = sub(T, '''        glBindTexture(GL_TEXTURE_2D, t->tex);
        if (t->s <= 1) {
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, t->w, t->h, GL_RGBA, GL_UNSIGNED_BYTE, rgba);''',
        '''        if (t->s <= 1) {
            rb->rt_subir(t->rt, 0, 0, t->w, t->h, rgba);''')
T = sub(T, '                glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, (GLsizei)W, (GLsizei)H, GL_RGBA, GL_UNSIGNED_BYTE, g);',
        '                rb->rt_subir(t->rt, 0, 0, (int)W, (int)H, g);')

# ----------------------------------------------------------------------------------------------- cronometros
T = rep(T, '#define GQ_RING 512', 'static int g_q_activa = -1;\n',
        'static uint32_t g_q_perdidas;   /* queries de GPU que no cupieron en el anillo del backend */\n')
T = rep(T, 'static void gq_cosechar(void)\n{', '    g_q_fin++;\n}\n', '''static void gq_ini(int cat) { rb->gpu_crono_ini(cat); }
static void gq_fin(void) { rb->gpu_crono_fin(); }
''')
T = sub(T, '    if (g_estado > 0 && wglGetCurrentContext() == g_ctx) gq_cosechar();\n',
        '    rb->gpu_crono_leer(g_gq, g_gqn, &g_q_perdidas);   /* el backend cosecha las queries ya listas */\n')

T = sub(T, '''        ligar_nativo(t);   /* resolucion interna: el juego ve el RT reducido a su tamano */
        double tr = reloj();
        glReadPixels(0, 0, t->w, t->h, GL_RGBA, GL_UNSIGNED_BYTE, rgba);''',
        '''        RbRT *src = ligar_nativo(t);   /* resolucion interna: el juego ve el RT reducido a su tamano */
        double tr = reloj();
        rb->rt_leer(src, t->w, t->h, RB_FMT_RGBA8, rgba);''')
T = rep(T, 'static void destruir_rt(Rt *t)\n{', '    glDeleteTextures(1, &t->tex);\n}\n', '''static void destruir_rt(Rt *t)
{
    rb->rt_destruir(t->rt);
    t->rt = NULL;
}
''')
T = rep(T, '    glGenTextures(1, &t->tex);\n    glBindTexture(GL_TEXTURE_2D, t->tex);\n    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, t->w * t->s',
        '    glClear(GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);\n', '''    t->rt = rb->rt_crear(t->w * t->s, t->h * t->s, 1, RB_RT_NEAREST);
    if (!t->rt) { t->w = 0; return NULL; }
    rb->rt_limpiar(t->rt, RB_LIMPIAR_DS, NULL, 1.0, 0);
''')

# ----------------------------------------------------------------------------------------------- diferidos
T = sub(T, '    GLuint pbo;\n    GLsync fence;\n', '    RbLectura *lec;   /* buffer de lectura + fence (se reusa en el hueco libre de la cola) */\n')
T = sub(T, '''    GLenum r = gl.ClientWaitSync(d->fence, GL_SYNC_FLUSH_COMMANDS_BIT, 0);
    if (r == GL_TIMEOUT_EXPIRED) {
        g_n_dif_espera++;
        g_por_motivo[g_motivo]++;
        gl.ClientWaitSync(d->fence, GL_SYNC_FLUSH_COMMANDS_BIT, 5000000000ull);
    }
    gl.DeleteSync(d->fence);''', '''    if (!rb->lectura_esperar(d->lec, 0)) {
        g_n_dif_espera++;
        g_por_motivo[g_motivo]++;
        rb->lectura_esperar(d->lec, 5000000000ull);
    }
    rb->lectura_cerrar(d->lec);''')
T = sub(T, '''    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, d->pbo);
    const uint8_t *rgba = gl.MapBufferRange(GL_PIXEL_PACK_BUFFER, 0, (GLsizeiptr)d->w * d->h * 4, GL_MAP_READ_BIT);''',
        '    const uint8_t *rgba = rb->lectura_mapear(d->lec, (size_t)d->w * d->h * 4);')
T = sub(T, '''    if (rgba) gl.UnmapBuffer(GL_PIXEL_PACK_BUFFER);
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
''', '    rb->lectura_desmapear(d->lec);\n')
T = sub(T, '    GLuint pbo = d->pbo;\n', '    RbLectura *lec = d->lec;\n')
T = sub(T, '    g_dif[g_ndif].pbo = pbo;   /* el PBO queda para reusar en el hueco libre */\n',
        '    g_dif[g_ndif].lec = lec;   /* el buffer de lectura queda para reusar en el hueco libre */\n')

# ----------------------------------------------------------------------------------------------- pantalla en alta
T = sub(T, '    GLuint tex, fbo;\n    int valido;', '    RbRT *rt;                   /* copia en alta del RT (RGBA8) */\n    int valido;')
T = sub(T, '''    if (!a->tex || a->w != t->w || a->h != t->h || a->s != t->s) {
        if (a->tex) { gl.DeleteFramebuffers(1, &a->fbo); glDeleteTextures(1, &a->tex); }
        glGenTextures(1, &a->tex);
        glBindTexture(GL_TEXTURE_2D, a->tex);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, t->w * t->s, t->h * t->s, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
        gl.GenFramebuffers(1, &a->fbo);
        gl.BindFramebuffer(GL_FRAMEBUFFER, a->fbo);
        gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, a->tex, 0);
    }''', '''    if (!a->rt || a->w != t->w || a->h != t->h || a->s != t->s) {
        if (a->rt) rb->rt_destruir(a->rt);
        a->rt = rb->rt_crear(t->w * t->s, t->h * t->s, 0, 0);
        if (!a->rt) { a->valido = 0; return; }
    }''')
T = sub(T, '''    gl.BindFramebuffer(GL_READ_FRAMEBUFFER, t->fbo);
    gl.BindFramebuffer(GL_DRAW_FRAMEBUFFER, a->fbo);
    glDisable(GL_SCISSOR_TEST);
    gq_ini(GQ_COPIAR);
    gl.BlitFramebuffer(0, 0, t->w * t->s, t->h * t->s, 0, 0, t->w * t->s, t->h * t->s, GL_COLOR_BUFFER_BIT, GL_NEAREST);
    gq_fin();
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
''', '''    gq_ini(GQ_COPIAR);
    rb->copiar(a->rt, t->rt, 0, 0, t->w * t->s, t->h * t->s, 0, 0, t->w * t->s, t->h * t->s, 0);
    gq_fin();
''')

T = rep(T, 'static GLuint g_giro_prog, g_giro_vao, g_giro_fbo, g_giro_tex;', '    return 1;\n}\n', '''static RbRT *g_giro_rt;      /* la pantalla girada (ws x hs, RGBA8) */
static int g_giro_w, g_giro_h;
static int g_giro_sucio;
static int giro_listo(int w, int h)
{
    if (!g_giro_rt || g_giro_w != w || g_giro_h != h) {
        if (g_giro_rt) rb->rt_destruir(g_giro_rt);
        g_giro_rt = rb->rt_crear(w, h, 0, 0);
        g_giro_w = w; g_giro_h = h;
        if (!g_giro_rt) return 0;
    }
    return 1;
}

/* el giro en la GPU de la copia en alta 'a' (afin texel = o + A * pixel, ver RbGiro) a g_giro_rt, sin leer. El
   programa del giro es interno del backend. */
static int giro_gpu(const Alta *a, uint32_t ws, uint32_t hs)
{
    uint32_t s = a->s, W = a->w * s, H = a->h * s;
    if (!giro_listo((int)ws, (int)hs)) return 0;
    RbGiro g = { (int)ws, (int)hs, (int)W, (int)H, (int)s, a->ox, a->oy, a->a00, a->a01, a->a10, a->a11 };
    gq_ini(GQ_GIRO);
    int ok = rb->girar(g_giro_rt, a->rt, &g);
    gq_fin();
    return ok;
}
''')

# raster_alta_sinc
T = sub(T, '''        gl.BindFramebuffer(GL_FRAMEBUFFER, a->fbo);
        glReadPixels(0, 0, (GLsizei)W, (GLsizei)H, GL_RGBA, GL_UNSIGNED_BYTE, hi);
        const uint32_t *o = (const uint32_t *)hi;
        uint8_t *d = sal;''', '''        rb->rt_leer(a->rt, (int)W, (int)H, RB_FMT_RGBA8, hi);
        const uint32_t *o = (const uint32_t *)hi;
        uint8_t *d = sal;''')
T = rep(T, '        if (!giro_listo((int)ws, (int)hs)) { ult_a = NULL; return 0; }\n        GLint unidad_antes = 0;',
        '        /* el siguiente dibujo del raster vuelve a poner FBO, viewport, estado, programa y VAO (dibujar() lo hace siempre) */\n',
        '''        if (!giro_gpu(a, ws, hs)) { ult_a = NULL; return 0; }
        g_giro_sucio = 1;   /* g_giro_rt ya no es el cuadro que recuerda el camino asincrono */
        double cl = reloj();
        rb->rt_leer(g_giro_rt, (int)ws, (int)hs, RB_FMT_BGRA8, sal);
        if (crono_on()) cr_sumar(CR_ALTA_LEER, cl);
        /* el siguiente dibujo del raster vuelve a poner FBO, viewport, estado, programa y VAO (dibujar() lo hace siempre) */
''')
T = sub(T, '''                gl.BindFramebuffer(GL_FRAMEBUFFER, a->fbo);
                glReadPixels(0, 0, (GLsizei)W, (GLsizei)H, GL_RGBA, GL_UNSIGNED_BYTE, hi);
                const uint32_t *o = (const uint32_t *)hi;
                uint8_t *d = ref;''', '''                rb->rt_leer(a->rt, (int)W, (int)H, RB_FMT_RGBA8, hi);
                const uint32_t *o = (const uint32_t *)hi;
                uint8_t *d = ref;''')
T = sub(T, '''    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
    t_alta += reloj() - t0;''', '''    t_alta += reloj() - t0;''')

# alta_girar y referencia CPU
T = rep(T, '/* el giro en la GPU (mismo shader y estado que raster_alta_sinc) a g_giro_tex, sin leer */',
        '    g_giro_a = a; g_giro_gen = a->gen; g_giro_ancho = ws; g_giro_alto = hs; g_giro_sucio = 0;\n    return 1;\n}\n',
        '''/* el giro en la GPU (mismo shader y estado que raster_alta_sinc) a g_giro_rt, sin leer */
static int alta_girar(Alta *a, uint32_t ws, uint32_t hs)
{
    if (!giro_gpu(a, ws, hs)) return 0;
    g_giro_a = a; g_giro_gen = a->gen; g_giro_ancho = ws; g_giro_alto = hs; g_giro_sucio = 0;
    return 1;
}
''')
T = sub(T, '''    gl.BindFramebuffer(GL_FRAMEBUFFER, a->fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, (GLsizei)W, (GLsizei)H, GL_RGBA, GL_UNSIGNED_BYTE, hi);
    const uint32_t *o = (const uint32_t *)hi;''', '''    rb->rt_leer(a->rt, (int)W, (int)H, RB_FMT_RGBA8, hi);
    const uint32_t *o = (const uint32_t *)hi;''')

# anillo de lecturas asincronas
T = sub(T, '''typedef struct {
    GLuint pbo;
    GLsync f;
    uint32_t ws, hs, s;
    uint8_t *ref;            /* SM3DL_ALTA_VERIFICAR: el giro de la CPU del MISMO cuadro, tomado al emitir */
    uint8_t *map;            /* cero copia: mapeo persistente y coherente (GL 4.4 BufferStorage) */
    size_t cap;
} AltaPbo;''', '''typedef struct {
    RbLectura *lec;          /* buffer de lectura + fence; cero copia = buffer persistente y coherente (GL 4.4 BufferStorage) */
    uint32_t ws, hs, s;
    uint8_t *ref;            /* SM3DL_ALTA_VERIFICAR: el giro de la CPU del MISMO cuadro, tomado al emitir */
} AltaPbo;''')
T = sub(T, 'static const uint8_t *g_entregado;   /* cero copia: lo ultimo entregado (apunta al mapeo de su PBO) */',
        'static const uint8_t *g_entregado;   /* cero copia: lo ultimo entregado (apunta al mapeo de su buffer) */')
T = rep(T, '    GLint st = 0;\n    gl.GetSynciv(p->f, GL_SYNC_STATUS, 1, NULL, &st);\n    if (st != GL_SIGNALED) {',
        '        else gl.UnmapBuffer(GL_PIXEL_PACK_BUFFER);\n', '''    if (!rb->lectura_lista(p->lec)) {
        if (!esperar) return 0;
        double c0 = reloj();
        rb->lectura_esperar(p->lec, 5000000000ull);
        if (crono_on()) cr_sumar(CR_ALTA_LEER, c0);
    }
    rb->lectura_cerrar(p->lec);
    size_t bytes = (size_t)p->ws * p->hs * 4;
    const uint8_t *mapa = rb->lectura_mapa_persistente(p->lec), *m = NULL;
    if (mapa) {
        m = mapa;   /* coherente + fence cumplido: lo escrito por la GPU ya se ve; sin copia */
    } else {
        m = rb->lectura_mapear(p->lec, bytes);
        if (m) memcpy(sal, m, bytes);
    }
    int ok = 0;
    if (m) {
        const uint8_t *e = mapa ? mapa : sal;
        if (mapa) g_entregado = mapa;
        else rb->lectura_desmapear(p->lec);
''')
T = sub(T, 'p->map ? " cero-copia" : "", p->s,', 'mapa ? " cero-copia" : "", p->s,')
T = sub(T, '    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);\n    free(p->ref);', '    if (!mapa && !m) rb->lectura_desmapear(p->lec);   /* el mapeo fallo: suelta el buffer */\n    free(p->ref);')

# instantanea
T = rep(T, '    static struct { uint32_t sal; GLuint tex, fbo; int w, h, valida; uint8_t *ref; size_t tam_ref; } r[4];',
        '    static struct { uint32_t sal; GLuint tex, fbo; int w, h, valida; uint8_t *ref; size_t tam_ref; } r[4];\n',
        '    static struct { uint32_t sal; RbRT *rt; int w, h, valida; uint8_t *ref; size_t tam_ref; } r[4];\n')
T = sub(T, '    if (!a || !a->fbo) { if (k >= 0) r[k].valida = 0; return; }', '    if (!a || !a->rt) { if (k >= 0) r[k].valida = 0; return; }')
T = rep(T, '    if (modo == 0) {\n        if (k < 0) for (int j = 0; j < 4 && k < 0; j++) if (!r[j].valida) k = j;',
        '    glDisable(GL_SCISSOR_TEST);\n    gl.BlitFramebuffer(0, 0, W, H, 0, 0, W, H, GL_COLOR_BUFFER_BIT, GL_NEAREST);\n', '''    RbRT *origen, *destino;
    if (modo == 0) {
        if (k < 0) for (int j = 0; j < 4 && k < 0; j++) if (!r[j].valida) k = j;
        if (k < 0) k = 0;   /* no deberia pasar: gsp_interp.inc tiene como mucho 4 pendientes */
        if (!r[k].rt || r[k].w != W || r[k].h != H) {
            if (r[k].rt) rb->rt_destruir(r[k].rt);
            r[k].rt = rb->rt_crear(W, H, 0, 0);
            r[k].w = W; r[k].h = H;
            if (!r[k].rt) return;
        }
        r[k].sal = sal;
        origen = a->rt; destino = r[k].rt;
        r[k].valida = 1;
    } else {
        if (k < 0 || r[k].w != W || r[k].h != H) return;
        origen = r[k].rt; destino = a->rt;
        a->gen++;   /* la ventana tiene que volver a leerla */
        r[k].valida = 0;
    }
    rb->copiar(destino, origen, 0, 0, W, H, 0, 0, W, H, 0);
''')
T = sub(T, '''            gl.BindFramebuffer(GL_FRAMEBUFFER, a->fbo);
            glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, modo == 1 ? x : r[k].ref);''',
        '            rb->rt_leer(a->rt, W, H, RB_FMT_RGBA8, modo == 1 ? x : r[k].ref);')
T = sub(T, '''            free(x);
        }
    }
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
}''', '''            free(x);
        }
    }
}''')

# raster_alta (asincrona)
T = rep(T, '        if (g_cero_copia && (!p->map || p->cap < bytes)) {   /* storage inmutable: si no alcanza, se rehace */',
        '        glFlush();\n        p->ws = ws; p->hs = hs; p->s = s;\n', '''        if (!p->lec) p->lec = rb->lectura_crear();
        const uint8_t *mapa_antes = rb->lectura_mapa_persistente(p->lec);
        int pers_ok = 1;
        /* giro -> buffer de lectura + fence (cero copia: buffer persistente; storage inmutable, si no alcanza se rehace) */
        int emitido = rb->lectura_emitir(p->lec, g_giro_rt, (int)ws, (int)hs, RB_FMT_BGRA8, g_cero_copia > 0, &pers_ok);
        if (g_cero_copia > 0 && !pers_ok) g_cero_copia = 0;
        if (emitido == 2 && g_entregado == mapa_antes) g_entregado = NULL;   /* el mapeo viejo ya no existe */
        p->ws = ws; p->hs = hs; p->s = s;
''')
T = sub(T, '''            if (t && r == (int)s && tex == g_giro_tex && gen == a->gen) {
                glBindTexture(GL_TEXTURE_2D, tex);
                glPixelStorei(GL_PACK_ALIGNMENT, 4);
                glGetTexImage(GL_TEXTURE_2D, 0, GL_BGRA, GL_UNSIGNED_BYTE, t);''',
        '''            if (t && r == (int)s && tex == rb->rt_id_nativo(g_giro_rt) && gen == a->gen) {
                rb->rt_volcar_bgra(g_giro_rt, (int)ws, (int)hs, t);''')
T = sub(T, 'r, tex, g_giro_tex, gen, a->gen);', 'r, tex, rb->rt_id_nativo(g_giro_rt), gen, a->gen);')
T = sub(T, '''    while ((sal_ws != ws || sal_hs != hs || sal_s != s) && g_apbo_n) apbo_entregar(sal, &sal_ws, &sal_hs, &sal_s, 1);
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
''', '''    while ((sal_ws != ws || sal_hs != hs || sal_s != s) && g_apbo_n) apbo_entregar(sal, &sal_ws, &sal_hs, &sal_s, 1);
''')

# API publica de presentacion
T = sub(T, '''        if (!alta_girar(a, ws, hs)) return 0;
        gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
''', '''        if (!alta_girar(a, ws, hs)) return 0;
''')
T = sub(T, '    if (tex_gl) *tex_gl = g_giro_tex;', '    if (tex_gl) *tex_gl = rb->rt_id_nativo(g_giro_rt);')
T = rep(T, 'int raster_gl_hacer_actual(void *hdc)\n{', '    return 1;\n}\n',
        'int raster_gl_hacer_actual(void *hdc) { return rb->hacer_actual_dc(hdc); }\n')
T = rep(T, 'int raster_alta_a_ventana(int x0, int y0, int x1, int y1, int lineal)\n{', '    return 1;\n}\n', '''int raster_alta_a_ventana(int x0, int y0, int x1, int y1, int lineal)
{
    if (!contexto_actual() || !g_giro_rt) return 0;
    rb->copiar(NULL, g_giro_rt, 0, 0, g_giro_w, g_giro_h, x0, y0, x1, y1, lineal);
    return 1;
}
''')

# transfer diferido, antes_de_leer, tras_fill
T = sub(T, '''    uint32_t bytes = (uint32_t)t->w * t->h * 4;
    if (!d->pbo) gl.GenBuffers(1, &d->pbo);
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, d->pbo);
    gl.BufferData(GL_PIXEL_PACK_BUFFER, bytes, NULL, GL_STREAM_READ);
    ligar_nativo(t);   /* resolucion interna: el transfer ve el RT reducido */
    glReadPixels(0, 0, t->w, t->h, GL_RGBA, GL_UNSIGNED_BYTE, (void *)0);
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    d->fence = gl.FenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    glFlush();
''', '''    if (!d->lec) d->lec = rb->lectura_crear();
    RbRT *fuente = ligar_nativo(t);   /* resolucion interna: el transfer ve el RT reducido */
    rb->lectura_emitir(d->lec, fuente, t->w, t->h, RB_FMT_RGBA8, 0, NULL);
''')
T = sub(T, '''            GLint st = 0;
            gl.GetSynciv(g_dif[0].fence, GL_SYNC_STATUS, 1, NULL, &st);
            if (st != GL_SIGNALED) break;
''', '            if (!rb->lectura_lista(g_dif[0].lec)) break;\n')
T = sub(T, '''                gl.BindFramebuffer(GL_FRAMEBUFFER, t->fbo);
                glDisable(GL_SCISSOR_TEST);
                glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
                glClearColor(c[0] / 255.0f, c[1] / 255.0f, c[2] / 255.0f, c[3] / 255.0f);
                glClear(GL_COLOR_BUFFER_BIT);
''', '''                float cf[4] = { c[0] / 255.0f, c[1] / 255.0f, c[2] / 255.0f, c[3] / 255.0f };
                rb->rt_limpiar(t->rt, RB_LIMPIAR_COLOR, cf, 0.0, 0);
''')
T = sub(T, '''            gl.BindFramebuffer(GL_FRAMEBUFFER, t->fbo);
            glDisable(GL_SCISSOR_TEST);
            glDepthMask(GL_TRUE);
            glStencilMask(0xFF);
            glClearDepth(z);
            glClearStencil(s);
            glClear(GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
''', '            rb->rt_limpiar(t->rt, RB_LIMPIAR_DS, NULL, z, s);\n')

# ----------------------------------------------------------------------------------------------- texturas
T = sub(T, 'typedef struct { uint32_t dir, w, h, fmt, niveles, hash; GLuint tex; uint32_t uso; } TexCache;',
        'typedef struct { uint32_t dir, w, h, fmt, niveles, hash; RbTex *tex; uint32_t uso; } TexCache;')
T = sub(T, 'static GLuint textura_para(const PicaTextura *x, int *niveles_sal)', 'static RbTex *textura_para(const PicaTextura *x, int *niveles_sal)')
T = rep(T, '    uint8_t *rgba = malloc((size_t)x->ancho * x->alto * 4);\n    if (!rgba) { free(m); return 0; }\n    g_tex_subidas++;',
        '    return niveles > 0 ? libre->tex : 0;\n}\n', '''    /* se decodifican todos los niveles de mip primero (se corta en el primero que falla) y el backend los sube juntos */
    size_t total_px = 0;
    if (niveles > 16) niveles = 16;
    for (int k = 0; k < niveles; k++) total_px += (size_t)(x->ancho >> k) * (x->alto >> k) * 4;
    uint8_t *rgba = malloc(total_px);
    if (!rgba) { free(m); return 0; }
    g_tex_subidas++;
    const uint8_t *nivel[16];
    size_t off = 0, off_px = 0;
    int hechos = 0;
    for (int k = 0; k < niveles; k++) {
        int w = x->ancho >> k, hh = x->alto >> k;
        size_t t = tex_tamano(w, hh, x->formato);
        if (tex_decodificar(m + off, t, w, hh, x->formato, rgba + off_px) != 0) break;
        nivel[k] = rgba + off_px;
        hechos++;
        off_px += (size_t)w * hh * 4;
        off += t;
    }
    niveles = hechos;
    libre->tex = rb->tex_cargar_mips(libre->tex, x->ancho, x->alto, niveles, nivel);
    libre->dir = x->direccion; libre->w = x->ancho; libre->h = x->alto; libre->fmt = x->formato;
    libre->niveles = (uint32_t)*niveles_sal;
    libre->hash = h; libre->uso = g_reloj;
    free(m);
    free(rgba);
    return niveles > 0 ? libre->tex : 0;
}
''')
T = rep(T, 'static void parametros_textura(const PicaTextura *x, int niveles)\n{', '    glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, borde);\n}\n', '''/* muestreador de la unidad (filtros, envoltura, LOD, borde): el backend lo traduce (GL: glTexParameter; D3D12: sampler) */
static void muestreador_de(const PicaTextura *x, int niveles, RbMuestreador *m)
{
    m->mag_lineal = x->mag_lineal ? 1 : 0;
    m->min_lineal = x->min_lineal ? 1 : 0;
    m->mip = niveles > 1 ? (x->mip_lineal ? 2 : 1) : 0;
    m->wrap_s = x->wrap_s; m->wrap_t = x->wrap_t;
    m->lod_min = x->lod_min; m->lod_max = x->lod_max;
    m->lod_bias = x->lod_bias;
    m->color_borde = x->color_borde;
}
''')
T = sub(T, '    gl.ActiveTexture(GL_TEXTURE0 + k);\n    if (!x->activa) return 0;', '    rb->tex_enlazar(k, NULL, NULL);   /* selecciona la unidad k */\n    if (!x->activa) return 0;')
T = sub(T, '''    GLuint t = textura_para(x, &niveles);
    if (!t) return 0;
    glBindTexture(GL_TEXTURE_2D, t);
    parametros_textura(x, niveles);
    return 1;''', '''    RbTex *t = textura_para(x, &niveles);
    if (!t) return 0;
    RbMuestreador m;
    muestreador_de(x, niveles, &m);
    rb->tex_enlazar(k, t, &m);
    return 1;''')

# LUTs de luz
T = sub(T, 'static GLuint g_tex_luts;', 'static RbTex *g_tex_luts;')
T = sub(T, '    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, (GLint)f, 256, 1, GL_RG, GL_FLOAT, rg);', '    rb->tex_subir(g_tex_luts, 0, (int)f, 256, 1, RB_FMT_RG32F, 0, rg);')
T = sub(T, '''    gl.ActiveTexture(GL_TEXTURE3);
    if (!g_tex_luts) {
        glGenTextures(1, &g_tex_luts);
        glBindTexture(GL_TEXTURE_2D, g_tex_luts);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RG32F, 256, LUT_FILAS, 0, GL_RG, GL_FLOAT, NULL);
    }
    glBindTexture(GL_TEXTURE_2D, g_tex_luts);''', '''    rb->tex_enlazar(3, NULL, NULL);   /* unidad 3 = LUTs de luz */
    if (!g_tex_luts) g_tex_luts = rb->tex_crear(256, LUT_FILAS, RB_FMT_RG32F, RB_TEX_NEAREST);
    rb->tex_enlazar(3, g_tex_luts, NULL);''')

T = rep(T, 'static void vec_color10(const Programa *p, int k, int j, uint32_t c)\n{', '        gl.Uniform1i(p->u_luz[k][9], (int)(L[9] & 0xF));\n    }\n}\n', '''/* color de 10 bits por canal de la PICA -> (r, g, b, 0) */
static void vec_color10(float *v, uint32_t c)
{
    v[0] = ((c >> 20) & 0x3FF) / 255.0f;
    v[1] = ((c >> 10) & 0x3FF) / 255.0f;
    v[2] = (c & 0x3FF) / 255.0f;
    v[3] = 0.0f;
}

/* bloque de constantes de las luces (b3); luz_on = 0 deja el resto sin leer */
static void subir_luz(const Programa *p, const PicaEstado *e, const uint32_t *r)
{
    static RbCbLuz cl;
    int on = (r[0x1C6] & 1) == 0;
    cl.luz_on = on;
    if (on) {
        preparar_luts(e);
        memcpy(cl.luz_fila, g_lut_fila, sizeof cl.luz_fila);
        uint32_t c0 = r[0x1C3], c1 = r[0x1C4];
        int n = (int)(r[0x1C2] & 7) + 1;
        cl.luz_n = n;
        vec_color10(cl.luz_amb, r[0x1C0]);
        cl.luz_c0 = c0;
        cl.luz_c1 = c1;
        cl.luz_abs = r[0x1D0];
        cl.luz_ent = r[0x1D1];
        cl.luz_esc = r[0x1D2];
        cl.luz_mues = luz_mues_de(c0, c1);
        for (int k = 0; k < n; k++) {
            int num = (int)((r[0x1D9] >> (4 * k)) & 7);
            const uint32_t *L = &r[0x140 + 0x10 * num];
            RbLuz *z = &cl.luz[k];
            vec_color10(z->esp0, L[0]);
            vec_color10(z->esp1, L[1]);
            vec_color10(z->dif, L[2]);
            vec_color10(z->amb, L[3]);
            z->pos[0] = pica_f16(L[4] & 0xFFFF); z->pos[1] = pica_f16(L[4] >> 16); z->pos[2] = pica_f16(L[5] & 0xFFFF); z->pos[3] = 0.0f;
            int32_t sx = (int32_t)(L[6] << 19) >> 19, sy = (int32_t)(L[6] << 3) >> 19, sz = (int32_t)(L[7] << 19) >> 19;
            z->spot[0] = sx / 2047.0f; z->spot[1] = sy / 2047.0f; z->spot[2] = sz / 2047.0f; z->spot[3] = 0.0f;
            z->da_escala = pica_f20(L[0xB]);
            z->da_sesgo = pica_f20(L[0xA]);
            z->num = num;
            z->cfg = (int)(L[9] & 0xF);
        }
    }
    rb->constantes(p->prog, RB_BLOQUE_LUZ, &cl);
}
''')

# ----------------------------------------------------------------------------------------------- vertices (camino nativo)
T = sub(T, '    static const GLenum TIPO[4] = { GL_BYTE, GL_UNSIGNED_BYTE, GL_SHORT, GL_FLOAT };\n', '')
T = sub(T, '''    uint32_t lay[16];
    float cte[16][4];
    int es_cte[16];
    memset(lay, 0, sizeof lay);
    memset(cte, 0, sizeof cte);
    for (int k = 0; k < 16; k++) es_cte[k] = 1;
''', '''    RbVerticesCrudos vc;   /* lo que se le pasa al backend; lay[]/cte[] son sus campos */
    memset(&vc, 0, sizeof vc);
    uint32_t *lay = vc.layout;
    float (*cte)[4] = vc.cte;
''')
T = sub(T, '            lay[loc] = 0;\n            es_cte[loc] = 1;\n', '            lay[loc] = 0;\n')
T = sub(T, '        es_cte[loc] = 0;\n        lay[loc] = 0x80000000u', '        lay[loc] = 0x80000000u')
T = rep(T, '    static struct { uint32_t lay[16]; GLuint vao; } cache[128];', '        if (++avisos <= 4 || avisos % 16 == 0) logr("layout de vertices %d nuevo", ncache);\n    }\n', '')
T = rep(T, '    g_vao_crudo = cache[iv].vao;', '    g_v_decod += reloj() - tb;\n    return 1;\n}\n', '''    vc.datos = stage;
    vc.bytes = total;
    for (int j = 0; j < 12; j++)
        if (tam[j]) {
            vc.bind_mask |= (uint16_t)(1u << j);
            vc.bind_off[j] = boff[j];
            vc.bind_stride[j] = v->loader[j].stride;
        }
    if (!rb->vertices_crudos(&vc)) return 0;   /* el backend arma el layout (VAO / input layout) y sube los bloques */
    g_v_decod += reloj() - tb;
    return 1;
}
''')

# ----------------------------------------------------------------------------------------------- estado de fragmentos
T = rep(T, 'static const GLenum FUNC_PRUEBA[8]', '        glLogicOp(LOGICA[e->logic_op & 15]);\n    }\n}\n', '''/* estado de fragmentos/rasterizador -> RbEstado (inmutable, tipo PSO; ver raster_backend.h). Los enteros van tal cual
   los codifica la PICA: las tablas de traduccion viven en cada backend. */
static void estado_de(const PicaEstado *e, const uint32_t *r, RbEstado *s)
{
    memset(s, 0, sizeof *s);
    /* culling: la y de pantalla PICA = y de GL, antihorario = cara de frente. 1 conserva los horarios (descarta los
       antihorarios), 2 conserva los antihorarios. */
    s->cull = (e->culling == 1 || e->culling == 2) ? e->culling : 0;
    s->clip_dist = (r[0x047] & 1) ? 1 : 0;
    int escribe_ds = e->depth_escritura != 0;
    /* sin prueba = ALWAYS (la prueba de profundidad nunca se apaga: en GL apagarla apaga tambien la escritura) */
    s->depth_func = e->depth_test ? (e->depth_func & 7) : RB_CMP_ALWAYS;
    s->depth_write = (e->depth_write && escribe_ds) ? 1 : 0;
    /* stencil: solo con D24S8 (sw_rasterizer DoDepthStencilTest); compara (ref & imask) op (stencil & imask) */
    if (e->stencil_test && e->depth_formato == 3) {
        s->stencil_on = 1;
        s->stencil_func = e->stencil_func & 7;
        s->stencil_ref = e->stencil_ref;
        s->stencil_imask = e->stencil_imask;
        s->stencil_fail = e->stencil_fail & 7;
        s->stencil_zfail = e->stencil_zfail & 7;
        s->stencil_zpass = e->stencil_zpass & 7;
        s->stencil_wmask = escribe_ds ? e->stencil_wmask : 0;
    }
    s->color_mask = e->color_escritura ? e->color_mask : 0;
    s->blend_on = e->blend_activo ? 1 : 0;
    if (e->blend_activo) {
        s->eq_rgb = e->blend_eq_rgb & 7;
        s->eq_a = e->blend_eq_a & 7;
        s->src_rgb = e->blend_src_rgb & 15;
        s->dst_rgb = e->blend_dst_rgb & 15;
        s->src_a = e->blend_src_a & 15;
        s->dst_a = e->blend_dst_a & 15;
        s->blend_color = e->blend_color;
    } else {
        s->logic_op = e->logic_op & 15;
    }
}
''')

# ----------------------------------------------------------------------------------------------- uniforms -> bloques
T = sub(T, '''/* uniforms de todo el pipeline, leidos de los registros en cada dibujo */''',
        '''/* constantes de todo el pipeline, leidas de los registros en cada dibujo y mandadas por BLOQUES (RbCb*) */''')
T = sub(T, '''    /* vertex shader */
    gl.Uniform4fv(p->u.c, 96, &e->vs.f[0].x);
    GLint ints[16];
    for (int k = 0; k < 4; k++) {
        ints[4 * k + 0] = e->vs.i[k][0];
        ints[4 * k + 1] = (int8_t)e->vs.i[k][1];
        ints[4 * k + 2] = (int8_t)e->vs.i[k][2];
        ints[4 * k + 3] = e->vs.i[k][3];
    }
    gl.Uniform4iv(p->u.i, 4, ints);
    GLint bools[16];
    for (int k = 0; k < 16; k++) bools[k] = (e->vs.b >> k) & 1;
    gl.Uniform1iv(p->u.b, 16, bools);
    /* OUTMAP: salida k de OUTMAP = k-esimo registro activo de OUTMAP_MASK (shader_unit WriteOutput) */
    GLint omap[24];''', '''    /* vertex shader (bloque b0) */
    RbCbVertice cv;
    memset(&cv, 0, sizeof cv);
    memcpy(cv.c, &e->vs.f[0].x, sizeof cv.c);
    for (int k = 0; k < 4; k++) {
        cv.i[k][0] = e->vs.i[k][0];
        cv.i[k][1] = (int8_t)e->vs.i[k][1];
        cv.i[k][2] = (int8_t)e->vs.i[k][2];
        cv.i[k][3] = e->vs.i[k][3];
    }
    for (int k = 0; k < 16; k++) cv.b[k] = (e->vs.b >> k) & 1;
    /* OUTMAP: salida k de OUTMAP = k-esimo registro activo de OUTMAP_MASK (shader_unit WriteOutput) */
    int32_t *omap = cv.omap;''')
T = sub(T, '    gl.Uniform1iv(p->u.omap, 24, omap);\n', '')
T = sub(T, '''    gl.Uniform1i(p->u.clip_on, (int)(r[0x047] & 1));
    gl.Uniform4f(p->u.clip_coef, pica_f24(r[0x048]), pica_f24(r[0x049]), pica_f24(r[0x04A]), pica_f24(r[0x04B]));
''', '''    cv.clip_on = (int)(r[0x047] & 1);
    cv.clip_coef[0] = pica_f24(r[0x048]); cv.clip_coef[1] = pica_f24(r[0x049]);
    cv.clip_coef[2] = pica_f24(r[0x04A]); cv.clip_coef[3] = pica_f24(r[0x04B]);
    rb->constantes(p->prog, RB_BLOQUE_V, &cv);
''')
T = sub(T, '''    /* TEV */
    static const uint16_t base[6] = { 0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8 };
    GLuint tev[24], cons[6];
    for (int k = 0; k < 6; k++) {
        const uint32_t *t = &r[base[k]];
        tev[4 * k] = t[0]; tev[4 * k + 1] = t[1]; tev[4 * k + 2] = t[2]; tev[4 * k + 3] = t[4];
        cons[k] = t[3];
    }
    gl.Uniform4uiv(p->u.tev, 6, tev);
    gl.Uniform1uiv(p->u.tev_const, 6, cons);
    gl.Uniform1ui(p->u.tev_buf, r[0x0FD]);
    gl.Uniform1ui(p->u.tev_upd, r[0x0E0]);
''', '''    /* TEV y operaciones de fragmento (bloque b1) */
    RbCbFragmento cf;
    memset(&cf, 0, sizeof cf);
    static const uint16_t base[6] = { 0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8 };
    for (int k = 0; k < 6; k++) {
        const uint32_t *t = &r[base[k]];
        cf.tev[k][0] = t[0]; cf.tev[k][1] = t[1]; cf.tev[k][2] = t[2]; cf.tev[k][3] = t[4];
        cf.tev_const[k] = t[3];
    }
    cf.tev_buf = r[0x0FD];
    cf.tev_upd = r[0x0E0];
''')
T = sub(T, '''    gl.Uniform4i(p->u.tex_modo, m0, m1, m2, e->tex2_usa_coord1);
    gl.Uniform1i(p->u.tex0_proy, proy);
''', '''    cf.tex_modo[0] = m0; cf.tex_modo[1] = m1; cf.tex_modo[2] = m2; cf.tex_modo[3] = e->tex2_usa_coord1;
    cf.tex0_proy = proy;
''')
T = sub(T, '''    gl.Uniform1i(p->u.alfa_func, e->alpha_test ? e->alpha_func : -1);
    gl.Uniform1i(p->u.alfa_ref, e->alpha_ref);
    gl.Uniform1f(p->u.z_escala, e->depth_escala);
    gl.Uniform1f(p->u.z_offset, e->depth_offset);
    gl.Uniform1i(p->u.wbuffer, e->depthmap_activo == 0);   /* 0x06D bit 0: 0 = w-buffer, 1 = z-buffer */
    gl.Uniform1i(p->u.tijera_modo, e->scissor_modo);
    gl.Uniform4i(p->u.tijera, e->scissor_x0 * g_s_actual, e->scissor_y0 * g_s_actual, (e->scissor_x1 + 1) * g_s_actual,
                 (e->scissor_y1 + 1) * g_s_actual);
    int niebla = e->niebla == 5;
    if (e->niebla == 7) AVISO_UNA_VEZ(AV_GAS, "modo gas (niebla 7) sin soporte");
    gl.Uniform1i(p->u.niebla, niebla);
    if (niebla) {
        gl.Uniform1i(p->u.niebla_flip, (int)((r[0x0E0] >> 16) & 1));
        gl.Uniform1ui(p->u.niebla_color, r[0x0E1]);
        static float lut[256];
        static uint32_t ver = 0xFFFFFFFFu;
        if (ver != e->niebla_lut_ver) {   /* bits 0-12 diferencia s1.1.11, 13-23 valor 0.0.11 */
            for (int k = 0; k < 128; k++) {
                uint32_t w = e->niebla_lut[k];
                lut[2 * k] = ((w >> 13) & 0x7FF) / 2047.0f;
                lut[2 * k + 1] = (float)((int32_t)(w << 19) >> 19) / 2047.0f;
            }
            ver = e->niebla_lut_ver;
        }
        gl.Uniform2fv(p->u.niebla_lut, 128, lut);
    }
''', '''    cf.alfa_func = e->alpha_test ? e->alpha_func : -1;
    cf.alfa_ref = e->alpha_ref;
    cf.z_escala = e->depth_escala;
    cf.z_offset = e->depth_offset;
    cf.wbuffer = e->depthmap_activo == 0;   /* 0x06D bit 0: 0 = w-buffer, 1 = z-buffer */
    cf.tijera_modo = e->scissor_modo;
    cf.tijera[0] = e->scissor_x0 * g_s_actual; cf.tijera[1] = e->scissor_y0 * g_s_actual;
    cf.tijera[2] = (e->scissor_x1 + 1) * g_s_actual; cf.tijera[3] = (e->scissor_y1 + 1) * g_s_actual;
    int niebla = e->niebla == 5;
    if (e->niebla == 7) AVISO_UNA_VEZ(AV_GAS, "modo gas (niebla 7) sin soporte");
    cf.niebla = niebla;
    if (niebla) {
        cf.niebla_flip = (int)((r[0x0E0] >> 16) & 1);
        cf.niebla_color = r[0x0E1];
    }
    rb->constantes(p->prog, RB_BLOQUE_F, &cf);
    if (niebla) {   /* LUT de niebla (bloque b2) */
        static RbCbNiebla cn;
        static uint32_t ver = 0xFFFFFFFFu;
        if (ver != e->niebla_lut_ver) {   /* bits 0-12 diferencia s1.1.11, 13-23 valor 0.0.11 */
            for (int k = 0; k < 128; k++) {
                uint32_t w = e->niebla_lut[k];
                cn.lut[k][0] = ((w >> 13) & 0x7FF) / 2047.0f;
                cn.lut[k][1] = (float)((int32_t)(w << 19) >> 19) / 2047.0f;
            }
            ver = e->niebla_lut_ver;
        }
        rb->constantes(p->prog, RB_BLOQUE_NIEBLA, &cn);
    }
''')

# ----------------------------------------------------------------------------------------------- dibujar
T = sub(T, '    static const GLenum MODO[3] = { GL_TRIANGLES, GL_TRIANGLE_STRIP, GL_TRIANGLE_FAN };\n', '')
T = sub(T, '''    gl.BindFramebuffer(GL_FRAMEBUFFER, t->fbo);
    g_s_actual = t->s;   /* resolucion interna: viewport y tijera en pixeles del RT grande */
    glViewport(e->viewport_x * t->s, e->viewport_y * t->s, (GLsizei)(e->viewport_ancho * t->s),
               (GLsizei)(e->viewport_alto * t->s));
    aplicar_estado(e, r);
    gl.UseProgram(p->prog);''', '''    g_s_actual = t->s;   /* resolucion interna: viewport y tijera en pixeles del RT grande */
    rb->fijar_destino(t->rt, e->viewport_x * t->s, e->viewport_y * t->s, (int)(e->viewport_ancho * t->s),
                      (int)(e->viewport_alto * t->s));
    RbEstado est;
    estado_de(e, r, &est);
    rb->fijar_estado(&est);
    rb->prog_usar(p->prog);''')
T = rep(T, '    if (crudo) {\n        gl.BindVertexArray(g_vao_crudo);', 'dibujado:\n', '''    if (crudo) {   /* el layout y los bloques ya los dejo armar_crudo en el backend */
        if (e->idx.es_elements) for (uint32_t k = 0; k < n; k++) ind[k] -= base;
        rb->dibujar(topo, n, e->idx.es_elements ? ind : NULL);   /* sin indices: ind[k] = vertex_offset + k = base + k */
        goto dibujado;
    }
    rb->vertices_floats(vb, nv);
    if (rango) {
        for (uint32_t k = 0; k < n; k++) ind[k] -= base;
        rb->dibujar(topo, n, ind);
    } else {
        rb->dibujar(topo, n, NULL);
    }
dibujado:
''')
T = sub(T, '        GLenum err = glGetError();\n', '        unsigned err = rb->ultimo_error();\n')

# ----------------------------------------------------------------------------------------------- final
T = sub(T, '#include "presentador_gl.inc"\n', '''#include "presentador_gl.inc"

/* ------------------------------------------------------------------ seleccion del backend (SM3DL_BACKEND=gl|d3d12)
   El D3D12 es el destino del plan (pasos 3-9); hoy solo existe la interfaz: este STUB avisa y cae a GL. Cuando exista,
   rb_d3d12_obtener() devolvera su tabla (raster_backend_d3d12.c, que tambien se incluira desde aqui). */
static const RasterBackend *rb_d3d12_obtener(void) { return NULL; }

static const RasterBackend *elegir_backend(void)
{
    const char *s = getenv("SM3DL_BACKEND");
    const RasterBackend *b = NULL;
    if (s && !_stricmp(s, "d3d12")) {
        b = rb_d3d12_obtener();
        if (!b) logr("SM3DL_BACKEND=d3d12: backend D3D12 NO IMPLEMENTADO todavia (paso 1: solo la interfaz); uso gl");
    } else if (s && *s && _stricmp(s, "gl")) {
        logr("SM3DL_BACKEND=%s desconocido (gl | d3d12); uso gl", s);
    }
    if (!b) b = rb_gl_obtener();
    logr("backend de GPU: %s", b->nombre);
    g_rb = b;
    return b;
}

/* el backend GL va al FINAL: lo de arriba (capa comun) no puede nombrar nada de OpenGL */
#include "raster_backend_gl.c"
''')

wr(R + 'raster_gl.c', T)
print('raster_gl.c migrado:', len(T.split('\n')), 'lineas')
