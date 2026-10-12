/* Rasterizador OpenGL del port: ejecuta en la GPU del PC los dibujos que decodifica el interprete PICA.
 * (9 oct: primera pasada; 9-10 oct, agente R: uber-shader TEV + luz + estado completo, ver raster_uber.c)
 *
 * Sincronizacion con la memoria emulada (la VRAM del 3DS):
 *  - un render target (RT) por direccion de color: textura RGBA8 + D24S8 en un FBO, en coordenadas PICA
 *    (fb_ancho x fb_alto; 240x400 en las pantallas). Al crearlo se sube lo que haya en memoria.
 *  - dibujar deja el RT "sucio" (la GPU tiene pixeles que la memoria aun no).
 *  - gsp_antes_de_leer: si lo que se va a leer solapa un RT sucio -> glReadPixels + embaldosar a memoria.
 *  - gsp_tras_fill: un MemoryFill que tapa todo el RT con el mismo ancho de pixel es un glClear; si no, se resube
 *    la memoria (que ya tiene el relleno).
 * Orientacion (leida en Azahar, sw_framebuffer.cpp DrawPixel y sw_rasterizer.cpp): fila GL y <-> fila de memoria
 * (alto-1-y); texturas SIN voltear (texturas.c ya invierte y el muestreo de la PICA invierte otra vez). La y de
 * pantalla de la PICA es la y de GL (origen abajo), asi que el sentido de giro (culling) y la tijera van directos.
 * Entradas del shader (shader_unit.cpp LoadInput): registro v[permutacion[a]] <- atributo a, a < num_entradas.
 *
 * 8 oct 2026 (agente A, tanda D3D12 paso 1): este archivo es la capa COMUN (decodifica la PICA200) y ya no toca la API
 * grafica: habla con raster_backend.h; el codigo GL vive en raster_backend_gl.c (incluido al final). Las referencias de
 * este comentario a glReadPixels / glClear / FBO se leen ahora como rt_leer / rt_limpiar / superficie del backend.
 *
 * Estado que se emula: TEV 6 etapas + buffer, luz por fragmento, texturas 0-2 (2D y proyeccion en la unidad 0,
 * mipmaps, 8 modos de envoltura, borde), alpha test, niebla, tijera, culling, plano de recorte, viewport,
 * profundidad (escala/offset, w-buffer), stencil, blend / logic op, mascaras, OUTMAP, modo inmediato.
 * Fuera: geometry shader de la PICA, texturas cubo / sombra / procedural (tex3), gas, modo sombra.
 */
#define WIN32_LEAN_AND_MEAN
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

#define DIR_GLSL "extraido\\shaders\\glsl\\"

/* ------------------------------------------------------------------ backend de GPU (raster_backend.h)
   Esta capa NO ve la API grafica: todo pasa por la tabla 'rb' (RasterBackend), que se elige con SM3DL_BACKEND (ver
   elegir_backend, al final). El backend GL (raster_backend_gl.c) se incluye al FINAL del archivo, asi que en este codigo
   no existe ni un simbolo de OpenGL: si alguien lo usara, no compilaria. */
static const RasterBackend *g_rb;
static const RasterBackend *elegir_backend(void);
#define rb (g_rb ? g_rb : elegir_backend())

/* CINTA DE INTERMEDIOS (H1, 10 oct; solo D3D12, ver raster_d3d12_dibujar.inc y agentes_dx12\H1.md): interp.c pone en
   raster_cinta_j el numero del dibujo del cuadro mientras lo GRABA (-1 = no se graba); el backend D3D12 guarda lo que
   armo para la GPU y raster_cinta_dibujar() lo re-emite en cada intermedio con otro b0, sin pasar por esta capa. */
int raster_cinta_j = -1;
static void cinta_nada(int j);
static uint64_t g_v_unicos;   /* vertices decodificados por el camino con indices (rango unico) */

/* arnes de pruebas (agentes_noche/R): si no es NULL, todo dibujo usa este .vert en vez del de programas.tsv, y
   g_prueba_tev compila el fragment shader con PRUEBA_TEV (luz primaria/secundaria = salidas del vertice) */
static const char *g_vert_forzado;
static int g_prueba_tev;

static void logr(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void logr(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fputs("[raster] ", stderr);
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
}

/* avisos que se repiten por dibujo: solo la primera vez */
enum { AV_GS, AV_TOPO, AV_FILL_SUCIO, AV_FMT_RT, AV_MEM_VTX, AV_MEM_IDX, AV_TEX, AV_FRAG, AV_TEX_TIPO, AV_TEX3,
       AV_GAS, AV_N };
static uint8_t g_avisado[AV_N];
#define AVISO_UNA_VEZ(k, ...) do { if (!g_avisado[k]) { g_avisado[k] = 1; logr(__VA_ARGS__); } } while (0)

#include "raster_uber.c"
#include "texturas_hd.h"

/* crea el dispositivo la primera vez; 1 si esta listo */
static int iniciar_gl(void) { return rb->iniciar(); }

/* el contexto es del hilo que lo creo; todas las fibras del juego corren en ese hilo, pero el backend lo comprueba */
static int contexto_actual(void) { return rb->contexto_actual(); }

static uint32_t fnv(const uint32_t *p, size_t n)
{
    uint32_t h = 2166136261u;
    for (size_t k = 0; k < n; k++) { h ^= p[k]; h *= 16777619u; }
    return h;
}

/* ------------------------------------------------------------------ programas */
typedef struct { char vert[64]; uint32_t main, palabras, fnv; } FilaPrograma;
static FilaPrograma g_tabla[64];
static int g_ntabla = -1;

static void cargar_tabla(void)
{
    g_ntabla = 0;
    FILE *f = fopen(DIR_GLSL "programas.tsv", "r");
    if (!f) { logr("no abre " DIR_GLSL "programas.tsv (correr desde la raiz del proyecto)"); return; }
    char l[256];
    while (fgets(l, sizeof l, f) && g_ntabla < 64) {
        FilaPrograma *p = &g_tabla[g_ntabla];
        if (l[0] == '#') continue;
        if (sscanf(l, "%63s %u %u %x", p->vert, &p->main, &p->palabras, &p->fnv) == 4 && p->palabras <= 4096)
            g_ntabla++;
    }
    fclose(f);
    logr("%d programas en la tabla", g_ntabla);
}

/* Programa = (vertex shader del juego envuelto) + (fragment shader especializado por clave) + (GS de flip si hay
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

static char *leer_texto(const char *ruta)
{
    FILE *f = fopen(ruta, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *s = malloc((size_t)n + 1);
    if (s && fread(s, 1, (size_t)n, f) != (size_t)n) { free(s); s = NULL; }
    if (s) s[n] = 0;
    fclose(f);
    return s;
}

static double reloj(void);

/* reemplaza todas las apariciones de a por b (nuevo malloc; libera s) */
static char *reemplazar(char *s, const char *a, const char *b)
{
    size_t la = strlen(a), lb = strlen(b), n = 0;
    for (const char *p = s; (p = strstr(p, a)) != NULL; p += la) n++;
    char *r = malloc(strlen(s) + n * (lb > la ? lb - la : 0) + 1), *w = r;
    if (!r) { free(s); return NULL; }
    const char *p = s, *q;
    while ((q = strstr(p, a)) != NULL) {
        memcpy(w, p, (size_t)(q - p)); w += q - p;
        memcpy(w, b, lb); w += lb;
        p = q + la;
    }
    strcpy(w, p);
    free(s);
    return r;
}

/* .vert generado -> vertex shader del rasterizador: version 450, salidas pica_oN a globales, main -> pica_vmain,
   y el envoltorio de OUTMAP al final */
static char *envolver_vert(char *v)
{
    v = reemplazar(v, "#version 330 core", "#version 450 core");
    if (v) v = reemplazar(v, "out vec4 pica_o", "vec4 pica_o");
    if (v) v = reemplazar(v, "void main() {", "void pica_vmain() {");
    if (!v) return NULL;
    char *r = malloc(strlen(v) + sizeof VERT_ENVOLTORIO);
    if (r) { strcpy(r, v); strcat(r, VERT_ENVOLTORIO); }
    free(v);
    return r;
}

/* P2 (10 oct): atajos por SELLO (pica.h). La partida del dueno pagaba "programa" 5,4 s / 8,48 M dibujos (~0,6 us):
   fnv de 512 palabras de codigo + clave_frag + fnv + busqueda lineal en ~176 fs y ~195 programas, en CADA dibujo, aunque
   entre dibujos casi nunca cambian. Ahora: si el sello del grupo es el mismo que la ultima vez, la respuesta es la misma
   (el sello viaja con el dato: la restauracion de interp.c trae ambos). Sello 0 o estado que no es pica.e -> lento. */
static int vs_para_lento(const PicaShader *vs);
/* SM3DL_SIN_SELLOS=1: apaga los atajos (camino de antes) para medir A/B con el mismo exe */
static int sellos_on(void)
{
    static int on = -1;
    if (on < 0) { const char *s = getenv("SM3DL_SIN_SELLOS"); on = !(s && *s && *s != '0'); }
    return on;
}
static uint64_t g_m_svs;
static uint32_t g_m_ent;
static int g_m_iv;
static int vs_para(const PicaShader *vs)
{
    const int sellable = sellos_on() && vs == &pica.e.vs && pica.sello_vs && !g_vert_forzado;
    if (sellable && pica.sello_vs == g_m_svs && vs->entrada == g_m_ent)
        return g_m_iv >= 0 && g_vs[g_m_iv].malo ? -1 : g_m_iv;   /* malo puede marcarse despues (programa_para) */
    int iv = vs_para_lento(vs);
    g_m_svs = sellable ? pica.sello_vs : 0; g_m_ent = vs->entrada; g_m_iv = iv;
    return iv;
}

/* vertex shader del programa del juego (por codigo + entrada), envuelto; -1 si no se puede */
static int vs_para_lento(const PicaShader *vs)
{
    uint32_t clave = g_vert_forzado ? fnv((const uint32_t *)g_vert_forzado, 16) : fnv(vs->codigo, 512);
    for (int k = 0; k < g_nvs; k++)
        if (g_vs[k].clave == clave && g_vs[k].entrada == vs->entrada) return g_vs[k].malo ? -1 : k;
    if (g_nvs >= 64) return -1;
    if (g_ntabla < 0) cargar_tabla();
    VsCache *c = &g_vs[g_nvs];
    memset(c, 0, sizeof *c);
    c->clave = clave;
    c->entrada = vs->entrada;
    c->malo = 1;
    char *v = NULL;
    if (g_vert_forzado) {
        v = malloc(strlen(g_vert_forzado) + 1);
        strcpy(v, g_vert_forzado);
        snprintf(c->nombre, sizeof c->nombre, "vert forzado (arnes)");
    } else {
        for (int k = 0; k < g_ntabla && !v; k++) {
            const FilaPrograma *f = &g_tabla[k];
            if (f->main == vs->entrada && fnv(vs->codigo, f->palabras) == f->fnv) {
                char ruta[160];
                snprintf(ruta, sizeof ruta, DIR_GLSL "%s", f->vert);
                v = leer_texto(ruta);
                if (!v) logr("no abre %s", ruta);
                snprintf(c->nombre, sizeof c->nombre, "%s", f->vert);
            }
        }
        if (!v && !c->nombre[0]) {
            logr("programa desconocido: fnv512 %08X entrada %u (no esta en programas.tsv)", clave, vs->entrada);
            /* volcado para ubicarlo en el ROM (tools: buscar su .shbin de origen): codigo + swizzles, 4096 c/u */
            char ruta[160];
            CreateDirectoryA("extraido\\shaders\\desconocidos", NULL);
            snprintf(ruta, sizeof ruta, "extraido\\shaders\\desconocidos\\%08X_e%u.bin", clave, vs->entrada);
            FILE *fd = fopen(ruta, "wb");
            if (fd) {
                fwrite(vs->codigo, 4, 4096, fd);
                fwrite(vs->swizzles, 4, 4096, fd);
                fclose(fd);
            }
        }
    }
    char *txt = v ? envolver_vert(v) : NULL;
    if (txt) {   /* se compila al armar el programa, solo si no hay binario guardado */
        c->src = txt;
        c->hsrc = fnv_texto(txt);
        c->malo = 0;
    }
    g_nvs++;
    return c->malo ? -1 : g_nvs - 1;
}

/* clave del fragment shader: la ESTRUCTURA de la etapa de fragmentos (lo que se vuelve constante al especializar) */
static uint32_t clave_frag(const uint32_t *r, uint32_t *k)
{
    static const uint16_t base[6] = { 0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8 };
    uint32_t n = 0;
    k[n++] = (uint32_t)g_prueba_tev;
    if (g_frag_uniforme) { k[n++] = 0xFFFFFFFFu; return n; }
    for (int j = 0; j < 6; j++) {
        const uint32_t *t = &r[base[j]];
        k[n++] = t[0]; k[n++] = t[1]; k[n++] = t[2]; k[n++] = t[4];
    }
    int luz = (r[0x1C6] & 1) == 0;
    k[n++] = (uint32_t)luz;
    if (luz && !g_prueba_tev) {
        k[n++] = r[0x1C3]; k[n++] = r[0x1C4]; k[n++] = r[0x1D0]; k[n++] = r[0x1D1]; k[n++] = r[0x1D2];
        k[n++] = r[0x1C2] & 7;
    }
    return n;
}

static int fs_para_lento(const uint32_t *r);
static uint64_t g_m_sfrag;
static int g_m_tev, g_m_ifs;
static uint32_t g_fs_epoca, g_m_fs_epoca;   /* sube cuando la cache de fs se vacia (los indices viejos no valen) */
static int fs_para(const uint32_t *r)
{
    const int sellable = sellos_on() && r == pica.reg && pica.sello_frag;
    if (sellable && pica.sello_frag == g_m_sfrag && g_prueba_tev == g_m_tev && g_fs_epoca == g_m_fs_epoca)
        return g_m_ifs >= 0 && g_fs[g_m_ifs].malo ? -1 : g_m_ifs;   /* malo puede marcarse despues (programa_para) */
    int ifs = fs_para_lento(r);
    g_m_sfrag = sellable ? pica.sello_frag : 0; g_m_tev = g_prueba_tev; g_m_fs_epoca = g_fs_epoca; g_m_ifs = ifs;
    return ifs;
}

static int fs_para_lento(const uint32_t *r)
{
    uint32_t k[MAX_CLAVE], n = clave_frag(r, k), h = fnv(k, n);
    for (int j = 0; j < g_nfs; j++)
        if (g_fs[j].hash == h && g_fs[j].n == n && !memcmp(g_fs[j].k, k, n * 4)) return g_fs[j].malo ? -1 : j;
    if (g_nfs >= MAX_FS) {   /* cache llena: se tiran todos los programas y fragment shaders y se rehacen a demanda */
        logr("%d fragment shaders: se descartan y se rehacen", g_nfs);
        for (int j = 0; j < g_nprog; j++) rb->prog_destruir(g_prog[j].prog);
        g_nprog = 0;
        for (int j = 0; j < g_nfs; j++) { if (g_fs[j].fs) rb->etapa_destruir(g_fs[j].fs); free(g_fs[j].src); }
        g_nfs = 0;
        g_fs_epoca++;   /* P2: invalida el atajo de fs_para */
    }
    FsCache *c = &g_fs[g_nfs++];
    memset(c, 0, sizeof *c);
    c->hash = h; c->n = n;
    memcpy(c->k, k, n * 4);
    char cab[1600];
    int m = snprintf(cab, sizeof cab, "#version 450 core\n%s", g_prueba_tev ? "#define PRUEBA_TEV\n" : "");
    if (!g_frag_uniforme) {
        static const uint16_t base[6] = { 0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8 };
        m += snprintf(cab + m, sizeof cab - m, "#define ESPECIALIZADO\nconst uvec4 tev[6] = uvec4[6](");
        for (int j = 0; j < 6; j++) {
            const uint32_t *t = &r[base[j]];
            m += snprintf(cab + m, sizeof cab - m, "uvec4(%uu, %uu, %uu, %uu)%s", t[0], t[1], t[2], t[4],
                          j < 5 ? ", " : ");\n");
        }
        if ((r[0x1C6] & 1) == 0 && !g_prueba_tev)
            m += snprintf(cab + m, sizeof cab - m,
                          "#define LUZ\nconst int luz_n = %u;\nconst uint luz_c0 = %uu;\nconst uint luz_c1 = %uu;\n"
                          "const uint luz_abs = %uu;\nconst uint luz_ent = %uu;\nconst uint luz_esc = %uu;\n"
                          "const int luz_mues = %d;\n", (r[0x1C2] & 7) + 1, r[0x1C3], r[0x1C4], r[0x1D0], r[0x1D1],
                          r[0x1D2], luz_mues_de(r[0x1C3], r[0x1C4]));
    }
    char *txt = malloc((size_t)m + sizeof FRAG_UBER);
    memcpy(txt, cab, (size_t)m);
    memcpy(txt + m, FRAG_UBER, sizeof FRAG_UBER);
#ifdef SABOTEAR_FRAGMENTO   /* solo el arnes de pruebas (agentes_noche/R/prueba_raster.c) lo define */
    txt = SABOTEAR_FRAGMENTO(txt);
#endif
    c->src = txt;
    c->hsrc = fnv_texto(txt);
    c->malo = 0;
    return c->malo ? -1 : g_nfs - 1;
}

static void olvidar_programas(void)
{
    for (int k = 0; k < g_nprog; k++) rb->prog_destruir(g_prog[k].prog);
    g_nprog = 0;
}


/* ------------------------------------------------------------------ cache de programas enlazados en disco
   La hace el backend (prog_cargar_cache / prog_guardar_cache; en GL con glProgramBinary, ver raster_backend_gl.c): la
   cache de shaders del driver de Intel es POR NOMBRE DE EXE (81 s recompilando en un exe nuevo); con ella cada programa
   enlazado se guarda en extraido\shaders\cache_gl\ y se carga en milisegundos en cualquier exe.
   SM3DL_SIN_CACHE_GL=1 la apaga. Aqui solo se cuenta. */
static uint32_t g_bin_cargados, g_bin_compilados, g_bin_rechazados;
static double g_t_compilar;

static uint32_t fnv_texto(const char *t)
{
    uint32_t h = 2166136261u;
    for (; *t; t++) { h ^= (uint8_t)*t; h *= 16777619u; }
    return h;
}

static Programa *programa_para(const PicaShader *vs, const uint32_t *r)
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
    /* P2: primero el programa de la vez anterior (se valida solo: cada trio vs/fs/gs vive en UNA entrada) */
    static int m_k = -1;
    if (sellos_on() && m_k >= 0 && m_k < g_nprog && g_prog[m_k].vs == iv && g_prog[m_k].fs == ifs && g_prog[m_k].gs == gs)
        return &g_prog[m_k];
    for (int k = 0; k < g_nprog; k++)
        if (g_prog[k].vs == iv && g_prog[k].fs == ifs && g_prog[k].gs == gs) { m_k = k; return &g_prog[k]; }
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

/* ------------------------------------------------------------------ render targets */
typedef struct {
    uint32_t color_dir, depth_dir;
    uint16_t w, h;
    uint8_t fmt;              /* GSP_* */
    uint8_t depth_fmt;        /* PICA: 0 D16, 2 D24, 3 D24S8 */
    RbRT *rt;                 /* superficie de color RGBA8 + D24S8 (w*s x h*s) */
    int sucio;
    uint8_t s;                /* resolucion interna: el FBO mide (w*s) x (h*s); la memoria del juego sigue w x h */
} Rt;
static Rt g_rt[16];
static int g_nrt;

/* ------------------------------------------------------------------ resolucion interna (7 oct)
   SM3DL_RESOLUCION / raster_escala(s): los RT se dibujan s veces mas grandes. Lo que el JUEGO ve sigue nativo: al
   bajar un RT a su memoria (o a un DisplayTransfer) la GPU lo reduce primero a w x h (blit lineal = promedio, una
   especie de SSAA). Para la PANTALLA, cada DisplayTransfer que sale de un RT guarda ademas una copia en alta
   (g_alta) y la ventana la pide con raster_alta(). */
static int g_esc = 1, g_s_actual = 1;

/* cronometros del agente A (definidos mas abajo, junto a reloj) */
enum { CR_BAJAR, CR_BAJAR_LEER, CR_LIGAR, CR_DIF_EMITIR, CR_DIF_ESPERA, CR_DIF_RESTO, CR_SUBIR, CR_SUBIR_EXP,
       CR_COPIAR_ALTA, CR_ALTA, CR_ALTA_LEER, CR_ESCALA, CR_N };
enum { GQ_DIB = RB_GQ_DIB, GQ_LIGAR = RB_GQ_LIGAR, GQ_COPIAR = RB_GQ_COPIAR, GQ_GIRO = RB_GQ_GIRO,
       GQ_SUBIR = RB_GQ_SUBIR, GQ_N = RB_GQ_N };   /* los mismos numeros que el backend */
static int crono_on(void);
static void cr_sumar(int k, double t0);
static void gq_ini(int cat);
static void gq_fin(void);

/* deja listo para LEER (rt_leer) el RT a su tamano nativo: el propio RT si s == 1; si no, el backend lo reduce en la
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

static const uint8_t PICA_A_GSP[8] = { GSP_RGBA8, GSP_RGB8, GSP_RGB5A1, GSP_RGB565, GSP_RGBA4, 0xFF, 0xFF, 0xFF };

static uint32_t rt_bytes(const Rt *t) { return (uint32_t)t->w * t->h * (uint32_t)gsp_bytes_pixel(t->fmt); }
static uint32_t rt_bytes_tiles(const Rt *t)
{ return ((t->w + 7u) & ~7u) * ((t->h + 7u) & ~7u) * (uint32_t)gsp_bytes_pixel(t->fmt); }
static uint32_t rt_bytes_depth(const Rt *t)
{
    static const uint8_t bpp[4] = { 2, 0, 3, 4 };
    return (uint32_t)t->w * t->h * bpp[t->depth_fmt & 3];
}

static int g_motivo, g_desde_textura;
static void completar_solapes(uint32_t fisica, uint32_t tam);
static void subir_color(Rt *t)
{
    completar_solapes(t->color_dir, rt_bytes(t));
    double c0 = reloj();
    uint32_t bpp = (uint32_t)gsp_bytes_pixel(t->fmt), tam = rt_bytes(t);
    /* m con ancho y alto redondeados a 8 (9 oct, hallazgo de E2): con h o w no multiplo de 8 el offset morton de la
       ultima fila de tiles cae despues de 'tam' y se leia/escribia fuera del buffer (caida en ~1-3 % del arnes). */
    uint8_t *m = calloc(1, rt_bytes_tiles(t)), *rgba = malloc((size_t)t->w * t->h * 4);
    if (m && rgba && gsp_leer_fisica(t->color_dir, m, tam) == 0) {
        for (uint32_t y = 0; y < t->h; y++)
            for (uint32_t x = 0; x < t->w; x++)
                gsp_decodificar_pixel(t->fmt, m + gsp_offset_morton(x, t->h - 1 - y, t->w, bpp),
                                      rgba + ((size_t)y * t->w + x) * 4);
        if (t->s <= 1) {
            rb->rt_subir(t->rt, 0, 0, t->w, t->h, rgba);
        } else {   /* resolucion interna: cada pixel de la memoria ocupa s x s en el RT */
            double ce = reloj();
            uint32_t s = t->s, W = t->w * s, H = t->h * s;
            uint32_t *g = malloc((size_t)W * H * 4);
            if (g) {
                const uint32_t *o = (const uint32_t *)rgba;
                for (uint32_t y = 0; y < H; y++)
                    for (uint32_t x = 0; x < W; x++) g[(size_t)y * W + x] = o[(size_t)(y / s) * t->w + x / s];
                rb->rt_subir(t->rt, 0, 0, (int)W, (int)H, g);
                free(g);
            }
            if (crono_on()) cr_sumar(CR_SUBIR_EXP, ce);
        }
    }
    free(m);
    free(rgba);
    if (crono_on()) cr_sumar(CR_SUBIR, c0);
}

static double g_t_dibujar, g_t_bajar;   /* segundos acumulados (medicion) */
/* tramos de dibujar(): 0 programa, 1 indices+vertices, 2 texturas, 3 LUTs de luz, 4 resto de uniforms, 5 BufferData+Draw */
static double g_tramo[6];
static double g_v_bloques, g_v_decod, g_v_rt;   /* dentro de vertices: leer bloques, decodificar, rt_para */
/* P3: contadores del camino de vertices (log "[raster]   vtx-P3" junto a "tramos") */
static uint64_t g_p3_directos, g_p3_stage, g_p3_no_host, g_p3_no_tramo, g_p3_bytes_dir, g_p3_bytes_tot;
static uint64_t g_p3_elem, g_p3_idx_host, g_p3_idx_n, g_p3_abanicos;
static int g_p3_sin = -1, g_p3_sab;   /* SM3DL_P3_SIN=1: camino de antes (copias); SM3DL_P3_SABOTAJE=1 */
/* SM3DL_P3_AB=1: alterna dibujo a dibujo camino de antes / nuevo y cronometra cada uno aparte (inmune al ruido de otras
   corridas en la PC): [0] = antes, [1] = P3; tiempos: vertices (= tramo), armar_crudo, envio */
static int g_p3_ab;
static double g_p3_ab_t[2][3];
static uint64_t g_p3_ab_n[2];
static void p3_env(void)
{
    if (g_p3_sin >= 0) return;
    const char *s = getenv("SM3DL_P3_SIN");
    g_p3_sin = s && *s && *s != '0';
    s = getenv("SM3DL_P3_SABOTAJE");
    g_p3_sab = s ? atoi(s) : 0;
    s = getenv("SM3DL_P3_AB");
    g_p3_ab = s && *s && *s != '0';   /* 1 = vertices corridos 4 bytes, 2 = indices cambiados */
}
/* buffer propio que crece (antes malloc/free en cada dibujo); dibujar() no es reentrante */
static void *p3_crecer(void **buf, uint32_t *cap, size_t bytes)
{
    if (bytes > *cap) {
        size_t nuevo = bytes < 4096 ? 4096 : bytes + bytes / 2;
        if (nuevo > 0xFFFFFFFFu) return NULL;
        void *b = realloc(*buf, nuevo);
        if (!b) return NULL;
        *buf = b;
        *cap = (uint32_t)nuevo;
    }
    return *buf;
}
static uint64_t g_v_n;
static uint32_t g_luts_subidas, g_tex_subidas, g_n_bajar;
static double g_t_leer;   /* parte de bajar que es glReadPixels (espera a la GPU) */
static double reloj(void)
{
    static LARGE_INTEGER f;
    LARGE_INTEGER c;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}

/* ------------------------------------------------------------------ cronometros del agente A (7 oct noche)
   SM3DL_A_CRONO=1: cada 300 vblanks, linea "[raster] crono" con ms POR VBLANK de cada seccion que espera a la GPU o
   trabaja por pixel del RT grande (CPU, tiempo de pared del hilo), y el tiempo de GPU medido con GL_TIME_ELAPSED
   (queries asincronas en anillo: se cosechan cuando ya estan, nunca se espera). Los dibujos se muestrean 1 de cada 8. */
static const char *CR_NOMBRE[CR_N] = { "bajar", "bajar.leer", "ligar_nativo", "dif.emitir", "dif.espera", "dif.resto",
                                        "subir", "subir.expandir", "copiar_alta", "alta", "alta.leer", "escala" };
static const char *GQ_NOMBRE[GQ_N] = { "dibujos(x8)", "ligar_nativo", "copiar_alta", "giro", "subir" };
static int g_crono = -1;
static double g_cr[CR_N];
static uint32_t g_crn[CR_N];
static double g_gq[GQ_N];
static uint32_t g_gqn[GQ_N];
static uint32_t g_q_perdidas;   /* queries de GPU que no cupieron en el anillo del backend */
static int crono_on(void)
{
    if (g_crono < 0) { const char *e = getenv("SM3DL_A_CRONO"); g_crono = e && *e && *e != '0'; }
    return g_crono;
}
static void cr_sumar(int k, double t0) { g_cr[k] += reloj() - t0; g_crn[k]++; }
static void gq_ini(int cat) { rb->gpu_crono_ini(cat); }
static void gq_fin(void) { rb->gpu_crono_fin(); }
static double g_t_dibujar_cr;   /* copia de g_t_dibujar en el ultimo reporte */
static void crono_reporte(unsigned vblank)
{
    static unsigned v0, proximo = 300;
    static double t0, dib0, cr0[CR_N], gq0[GQ_N];
    static uint32_t crn0[CR_N];
    if (!crono_on() || vblank < proximo) return;
    rb->gpu_crono_leer(g_gq, g_gqn, &g_q_perdidas);   /* el backend cosecha las queries ya listas */
    double t = reloj();
    if (t0 > 0 && vblank > v0) {
        double dv = vblank - v0;
        char b[1600];
        int n = snprintf(b, sizeof b, "crono x%d v%u-%u: pared %.2f ms/vblank, dibujar %.2f | CPU ms/vblank:", g_esc, v0,
                         vblank, 1000 * (t - t0) / dv, 1000 * (g_t_dibujar - dib0) / dv);
        for (int k = 0; k < CR_N && n < (int)sizeof b - 80; k++)
            if (g_crn[k] != crn0[k])
                n += snprintf(b + n, sizeof b - n, " %s %.3f (%.2f/v)", CR_NOMBRE[k], 1000 * (g_cr[k] - cr0[k]) / dv, (g_crn[k] - crn0[k]) / dv);
        n += snprintf(b + n, sizeof b - n, " | GPU ms/vblank:");
        for (int k = 0; k < GQ_N && n < (int)sizeof b - 60; k++)
            n += snprintf(b + n, sizeof b - n, " %s %.3f", GQ_NOMBRE[k], 1000 * (g_gq[k] - gq0[k]) / dv);
        if (n < (int)sizeof b - 40) snprintf(b + n, sizeof b - n, " (queries perdidas %u)", g_q_perdidas);
        logr("%s", b);
    }
    v0 = vblank; t0 = t; dib0 = g_t_dibujar;
    memcpy(cr0, g_cr, sizeof cr0); memcpy(crn0, g_crn, sizeof crn0); memcpy(gq0, g_gq, sizeof gq0);
    proximo = vblank - vblank % 300 + 300;
    (void)g_t_dibujar_cr;
}

static void bajar_color(Rt *t)
{
    completar_solapes(t->color_dir, rt_bytes(t));
    double t0 = reloj();
    uint32_t bpp = (uint32_t)gsp_bytes_pixel(t->fmt), tam = rt_bytes(t);
    /* m con ancho y alto redondeados a 8 (9 oct, hallazgo de E2): con h o w no multiplo de 8 el offset morton de la
       ultima fila de tiles cae despues de 'tam' y se leia/escribia fuera del buffer (caida en ~1-3 % del arnes). */
    uint8_t *m = calloc(1, rt_bytes_tiles(t)), *rgba = malloc((size_t)t->w * t->h * 4);
    if (m && rgba) {
        RbRT *src = ligar_nativo(t);   /* resolucion interna: el juego ve el RT reducido a su tamano */
        double tr = reloj();
        rb->rt_leer(src, t->w, t->h, RB_FMT_RGBA8, rgba);
        g_t_leer += reloj() - tr;
        if (crono_on()) cr_sumar(CR_BAJAR_LEER, tr);
        g_n_bajar++;
        if (g_n_bajar <= 6 || g_n_bajar % 500 == 0) logr("bajar sincrono %u: RT 0x%08X %ux%u (motivo %d)", g_n_bajar, t->color_dir, t->w, t->h, g_motivo);
        /* SM3DL_VOLCAR_RT=<carpeta> (depuracion, 7 oct): RT chicos leidos como textura -> <dir>\rt_<dir>_<fmt>_<w>x<h>_<n>.rgba
           (RGBA8 tal cual lo devolvio GL, fila 0 abajo) para ver si su contenido se dibujo antes de que el juego lo use. */
        {
            static const char *dv = (const char *)1;
            static unsigned n_volc;
            if (dv == (const char *)1) dv = getenv("SM3DL_VOLCAR_RT");
            if (dv && *dv && t->w <= 128 && t->h <= 128 && n_volc < 400) {
                char ruta[300];
                snprintf(ruta, sizeof ruta, "%s\\rt_%08X_f%u_%ux%u_%04u.rgba", dv, t->color_dir, t->fmt, t->w, t->h, n_volc++);
                FILE *fv = fopen(ruta, "wb");
                if (fv) { fwrite(rgba, 4, (size_t)t->w * t->h, fv); fclose(fv); }
            }
        }
        for (uint32_t y = 0; y < t->h; y++)
            for (uint32_t x = 0; x < t->w; x++)
                gsp_codificar_pixel(t->fmt, rgba + ((size_t)y * t->w + x) * 4,
                                    m + gsp_offset_morton(x, t->h - 1 - y, t->w, bpp));
        gsp_escribir_fisica(t->color_dir, m, tam);
    }
    free(m);
    free(rgba);
    t->sucio = 0;
    g_t_bajar += reloj() - t0;
    if (crono_on()) cr_sumar(CR_BAJAR, t0);
}

static void destruir_rt(Rt *t)
{
    rb->rt_destruir(t->rt);
    t->rt = NULL;
}

static Rt *rt_para(const PicaEstado *e)
{
    uint8_t fmt = PICA_A_GSP[e->color_formato & 7];
    if (fmt == 0xFF || e->fb_ancho == 0 || e->fb_alto == 0 || e->fb_ancho > 1024 || e->fb_alto > 1024) {
        AVISO_UNA_VEZ(AV_FMT_RT, "render target no soportado: formato %u, %ux%u", e->color_formato, e->fb_ancho,
                      e->fb_alto);
        return NULL;
    }
    Rt *t = NULL;
    for (int k = 0; k < g_nrt; k++)
        if (g_rt[k].color_dir == e->color_dir) { t = &g_rt[k]; break; }
    if (t && t->w == e->fb_ancho && t->h == e->fb_alto && t->fmt == fmt && t->s == g_esc) {
        t->depth_dir = e->depth_dir;
        t->depth_fmt = e->depth_formato;
        return t;
    }
    if (t) {   /* misma direccion con otra forma: volcar lo pendiente y rehacer */
        if (t->sucio) bajar_color(t);
        destruir_rt(t);
    } else {
        if (g_nrt >= 16) { if (g_rt[0].sucio) bajar_color(&g_rt[0]); destruir_rt(&g_rt[0]); t = &g_rt[0]; }
        else t = &g_rt[g_nrt++];
    }
    memset(t, 0, sizeof *t);
    t->color_dir = e->color_dir;
    t->depth_dir = e->depth_dir;
    t->depth_fmt = e->depth_formato;
    t->w = e->fb_ancho;
    t->h = e->fb_alto;
    t->fmt = fmt;
    t->s = (uint8_t)g_esc;
    t->rt = rb->rt_crear(t->w * t->s, t->h * t->s, 1, RB_RT_NEAREST);
    if (!t->rt) { t->w = 0; return NULL; }
    rb->rt_limpiar(t->rt, RB_LIMPIAR_DS, NULL, 1.0, 0);
    subir_color(t);
    logr("render target 0x%08X %ux%u formato %u (depth 0x%08X formato %u)", t->color_dir, t->w, t->h,
         e->color_formato, t->depth_dir, t->depth_fmt);
    return t;
}

static int solapa(uint32_t a0, uint32_t a1, uint32_t b0, uint32_t b1) { return a0 < b1 && b0 < a1; }

/* ------------------------------------------------------------------ DisplayTransfer diferido (PBO + fence)
   Antes: cada DisplayTransfer de un RT sucio hacia glReadPixels sincrono (~6 ms de espera a la GPU, 40 % del tiempo).
   Ahora la lectura va a un PBO con fence y el transfer se COMPLETA despues (FIFO): cuando alguien lee o escribe su
   entrada o su salida (la presentacion en el vblank lee la salida), cuando hace falta el hueco, o con el siguiente
   que lo pise. Mientras, la CPU sigue con el juego. SM3DL_SIN_DIFERIDO=1 vuelve al camino sincrono. */
#define MAX_DIF 4
typedef struct {
    RbLectura *lec;   /* buffer de lectura + fence (se reusa en el hueco libre de la cola) */
    uint32_t ent, sal, te, ts, w, h;
    uint32_t rdir, rbytes;   /* el RT entero que se leyo (la entrada del transfer cae dentro: ambas pantallas comparten RT) */
    uint8_t fmt;
    int escribir_rt;   /* 0 si un MemoryFill que tapa todo el RT llego despues: la memoria del RT ya no es esta */
    GspTransfer tr;
} Diferido;
static Diferido g_dif[MAX_DIF];
static int g_ndif, g_dif_activo = -1;
static uint32_t g_n_dif, g_n_dif_espera;
static double g_t_dif;

static uint32_t g_por_motivo[6];

static void completar_dif(int k);

/* completa en orden los pendientes 0..k (FIFO: una salida mas vieja nunca pisa a una mas nueva) */
static void completar_hasta(int k)
{
    for (int j = 0; j <= k; j++) completar_dif(0);
}

static void completar_dif(int k)
{
    (void)k;
    if (g_ndif == 0) return;
    Diferido *d = &g_dif[0];
    double t0 = reloj();
    if (!rb->lectura_esperar(d->lec, 0)) {
        g_n_dif_espera++;
        g_por_motivo[g_motivo]++;
        rb->lectura_esperar(d->lec, 5000000000ull);
    }
    rb->lectura_cerrar(d->lec);
    double c1 = reloj();
    if (crono_on()) cr_sumar(CR_DIF_ESPERA, t0);
    uint32_t bpp = (uint32_t)gsp_bytes_pixel(d->fmt);
    /* la entrada puede pasarse del final del RT (pantalla de abajo: 240x400 desde la fila 80, recortada a 320) */
    uint32_t fin = d->ent - d->rdir + d->te, total = fin > d->rbytes ? fin : d->rbytes;
    uint8_t *m = malloc(total), *b = malloc(d->ts);
    const uint8_t *rgba = rb->lectura_mapear(d->lec, (size_t)d->w * d->h * 4);
    if (m && b && rgba) {
        memset(m, 0, total);
        if (total > d->rbytes) gsp_leer_fisica(d->rdir + d->rbytes, m + d->rbytes, total - d->rbytes);
        for (uint32_t y = 0; y < d->h; y++)
            for (uint32_t x = 0; x < d->w; x++)
                gsp_codificar_pixel(d->fmt, rgba + ((size_t)y * d->w + x) * 4,
                                    m + gsp_offset_morton(x, d->h - 1 - y, d->w, bpp));
        if (d->escribir_rt) gsp_escribir_fisica(d->rdir, m, d->rbytes);
        if (gsp_leer_fisica(d->sal, b, d->ts) == 0 && gsp_display_transfer(m + (d->ent - d->rdir), b, &d->tr) == 0)
            gsp_escribir_fisica(d->sal, b, d->ts);
    }
    rb->lectura_desmapear(d->lec);
    free(m);
    free(b);
    RbLectura *lec = d->lec;
    memmove(&g_dif[0], &g_dif[1], (size_t)(g_ndif - 1) * sizeof *d);
    g_ndif--;
    g_dif[g_ndif].lec = lec;   /* el buffer de lectura queda para reusar en el hueco libre */
    g_t_dif += reloj() - t0;
    if (crono_on()) cr_sumar(CR_DIF_RESTO, c1);
}

/* completa (en orden) todo pendiente cuya entrada o salida solape [fisica, fisica+tam) */
static void completar_solapes(uint32_t fisica, uint32_t tam)
{
    int ultimo = -1;
    for (int k = 0; k < g_ndif; k++) {
        Diferido *d = &g_dif[k];
        if (solapa(fisica, fisica + tam, d->sal, d->sal + d->ts) ||
            (d->escribir_rt && solapa(fisica, fisica + tam, d->rdir, d->rdir + d->rbytes)))
            ultimo = k;
    }
    if (ultimo >= 0) completar_hasta(ultimo);
}

/* ------------------------------------------------------------------ pantalla en alta resolucion
   Cada DisplayTransfer que sale de un RT con s > 1 deja una copia del RT entero en alta (por direccion de salida).
   La ventana la pide para el framebuffer que presenta (raster_alta). Como el transfer y la presentacion giran la
   imagen (la 3DS guarda la pantalla en columnas), el mapeo pantalla -> texel se CALCULA una vez: se pasa por el
   mismo gsp_display_transfer + gsp_framebuffer_a_rgba una imagen sintetica que lleva sus coordenadas en el color
   (3 pasadas de 4 bits, para sobrevivir a formatos de 4-5 bits por canal) y se ajusta una afin de +-1. */
typedef struct {
    uint32_t sal, ent_off, te, ts;
    uint16_t w, h;
    uint8_t fmt, s;
    GspTransfer tr;
    RbRT *rt;                   /* copia en alta del RT (RGBA8) */
    int valido;
    uint32_t gen;               /* sube con cada copia: raster_alta no rehace un cuadro que no cambio */
    int mapa;                   /* 0 sin calcular, 1 ok, -1 no afin (no se usa) */
    uint32_t m_fmt, m_stride, m_ancho, m_alto;
    int ox, oy, a00, a01, a10, a11;   /* texel(x,y) = o + A * pixel(X,Y) */
} Alta;
#define N_ALTA 8
static Alta g_alta[N_ALTA];
static uint32_t g_alta_reloj[N_ALTA], g_alta_t;

static void copiar_alta(const Rt *t, uint32_t ent, uint32_t sal, const GspTransfer *tr, uint32_t te, uint32_t ts)
{
    if (t->s <= 1) return;
    /* solo transfers cuya entrada cae entera en el RT (la de arriba): la de abajo se sale del RT y va nativa */
    if (ent - t->color_dir + te > rt_bytes(t)) return;
    int k = -1;
    for (int j = 0; j < N_ALTA && k < 0; j++)
        if (g_alta[j].valido && g_alta[j].sal == sal) k = j;
    if (k < 0) {
        k = 0;
        for (int j = 1; j < N_ALTA; j++)
            if (g_alta_reloj[j] < g_alta_reloj[k]) k = j;
    }
    Alta *a = &g_alta[k];
    g_alta_reloj[k] = ++g_alta_t;
    int igual = a->valido && a->w == t->w && a->h == t->h && a->s == t->s && a->fmt == t->fmt &&
                a->ent_off == ent - t->color_dir && a->te == te && a->ts == ts && !memcmp(&a->tr, tr, sizeof *tr);
    if (!a->rt || a->w != t->w || a->h != t->h || a->s != t->s) {
        if (a->rt) rb->rt_destruir(a->rt);
        a->rt = rb->rt_crear(t->w * t->s, t->h * t->s, 0, 0);
        if (!a->rt) { a->valido = 0; return; }
    }
    if (!igual) a->mapa = 0;
    a->sal = sal; a->ent_off = ent - t->color_dir; a->te = te; a->ts = ts;
    a->w = t->w; a->h = t->h; a->s = t->s; a->fmt = t->fmt; a->tr = *tr;
    a->valido = 1;
    a->gen++;
    double c0 = reloj();
    gq_ini(GQ_COPIAR);
    rb->copiar(a->rt, t->rt, 0, 0, t->w * t->s, t->h * t->s, 0, 0, t->w * t->s, t->h * t->s, 0);
    gq_fin();
    if (crono_on()) cr_sumar(CR_COPIAR_ALTA, c0);
}

static int calcular_mapa(Alta *a, uint32_t fmt, uint32_t stride, uint32_t ancho, uint32_t alto)
{
    a->m_fmt = fmt; a->m_stride = stride; a->m_ancho = ancho; a->m_alto = alto;
    a->mapa = -1;
    uint32_t bpp = (uint32_t)gsp_bytes_pixel(a->fmt), rbytes = (uint32_t)a->w * a->h * bpp;
    if (a->ent_off + a->te > rbytes) return 0;   /* la entrada se sale del RT (pantalla de abajo): no se soporta */
    uint32_t tam_fb = stride * (ancho > alto ? ancho : alto) + 4096;
    if (tam_fb < a->ts) tam_fb = a->ts;
    uint8_t *m = calloc(rbytes, 1), *fb = calloc(tam_fb, 1), *rgba = malloc((size_t)ancho * alto * 4);
    uint16_t *cx = calloc((size_t)ancho * alto, 2), *cy = calloc((size_t)ancho * alto, 2);
    int ok = m && fb && rgba && cx && cy;
    for (int pasada = 0; ok && pasada < 3; pasada++) {
        for (uint32_t y = 0; y < a->h; y++)
            for (uint32_t x = 0; x < a->w; x++) {
                uint8_t c[4] = { (uint8_t)(((x >> (4 * pasada)) & 15) * 17), (uint8_t)(((y >> (4 * pasada)) & 15) * 17), 128, 255 };
                gsp_codificar_pixel(a->fmt, c, m + gsp_offset_morton(x, a->h - 1 - y, a->w, bpp));
            }
        memset(fb, 0, tam_fb);
        if (gsp_display_transfer(m + a->ent_off, fb, &a->tr) != 0) { ok = 0; break; }
        gsp_framebuffer_a_rgba(fb, (int)fmt, stride, ancho, alto, rgba);
        for (uint32_t k = 0; k < ancho * alto; k++) {
            cx[k] |= (uint16_t)(((rgba[4 * k] + 8) / 17) << (4 * pasada));
            cy[k] |= (uint16_t)(((rgba[4 * k + 1] + 8) / 17) << (4 * pasada));
        }
    }
    if (ok && ancho > 1 && alto > 1) {
        int x0 = cx[0], y0 = cy[0];
        int a00 = cx[1] - x0, a10 = cy[1] - y0, a01 = cx[ancho] - x0, a11 = cy[ancho] - y0;
        int unidad = abs(a00) + abs(a01) == 1 && abs(a10) + abs(a11) == 1;
        for (uint32_t Y = 0; ok && unidad && Y < alto; Y++)
            for (uint32_t X = 0; X < ancho; X++)
                if (cx[Y * ancho + X] != x0 + a00 * (int)X + a01 * (int)Y || cy[Y * ancho + X] != y0 + a10 * (int)X + a11 * (int)Y) {
                    ok = 0;
                    break;
                }
        if (ok && unidad) {
            a->ox = x0; a->oy = y0; a->a00 = a00; a->a01 = a01; a->a10 = a10; a->a11 = a11;
            a->mapa = 1;
        }
    }
    logr("pantalla en alta: mapa %s (salida 0x%08X %ux%u formato %u, RT %ux%u x%u: texel = (%d,%d) + [%d %d; %d %d] * pixel)",
         a->mapa == 1 ? "OK" : "NO AFIN (se usa la nativa)", a->sal, ancho, alto, fmt, a->w, a->h, a->s, a->ox, a->oy,
         a->a00, a->a01, a->a10, a->a11);
    free(m); free(fb); free(rgba); free(cx); free(cy);
    return a->mapa == 1;
}

/* Giro de la pantalla en alta EN LA GPU (7 oct): antes se leia el RT grande con glReadPixels y se giraba pixel a pixel
   en la CPU en CADA vblank (a 4x: ~3 ms leer + ~10 ms girar por cuadro, x60 vblanks = el juego se quedaba sin tiempo y
   parecia congelado). Ahora un triangulo de pantalla completa aplica la misma afin (texel = o + A * pixel) y se lee una
   sola vez ya girado y en BGRA (lo que pinta la ventana). Unidad de textura 5: el raster usa 0-3. */
static RbRT *g_giro_rt;      /* la pantalla girada (ws x hs, RGBA8) */
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

/* la pantalla 'dir_fisica' en alta: devuelve s (>1) y *rgba = BGRA (ancho*s x alto*s, fila 0 arriba, A = 255), o 0 si
   no hay. Si el cuadro no cambio desde la ultima llamada devuelve el mismo bufer sin tocar la GPU.
   SM3DL_ALTA_CPU=1: el camino viejo (giro en la CPU), para comparar. */
static int raster_alta_sinc(uint32_t dir_fisica, uint32_t fmt, uint32_t stride, uint32_t ancho, uint32_t alto, const uint8_t **rgba)
{
    static uint8_t *sal, *hi;
    static size_t tam_sal, tam_hi;
    static const Alta *ult_a;
    static uint32_t ult_gen, ult_ancho, ult_alto;
    static int cpu = -1;
    static double t_alta;
    static unsigned n_alta;
    if (cpu < 0) { const char *e = getenv("SM3DL_ALTA_CPU"); cpu = e && *e && *e != '0'; }
    if (g_esc <= 1 || !contexto_actual()) return 0;
    Alta *a = NULL;
    for (int k = 0; k < N_ALTA; k++)
        if (g_alta[k].valido && g_alta[k].sal == dir_fisica && g_alta[k].s == g_esc) a = &g_alta[k];
    if (!a) return 0;
    if (a->mapa == 0 || a->m_fmt != fmt || a->m_stride != stride || a->m_ancho != ancho || a->m_alto != alto) {
        calcular_mapa(a, fmt, stride, ancho, alto);
        ult_a = NULL;
    }
    if (a->mapa != 1) return 0;
    uint32_t s = a->s, W = a->w * s, H = a->h * s, ws = ancho * s, hs = alto * s;
    if (!cpu && sal && ult_a == a && ult_gen == a->gen && ult_ancho == ancho && ult_alto == alto) { *rgba = sal; return (int)s; }
    if ((size_t)ws * hs * 4 > tam_sal) { free(sal); tam_sal = (size_t)ws * hs * 4; sal = malloc(tam_sal); }
    if (!sal) return 0;
    double t0 = reloj();
    if (cpu) {
        if ((size_t)W * H * 4 > tam_hi) { free(hi); tam_hi = (size_t)W * H * 4; hi = malloc(tam_hi); }
        if (!hi) return 0;
        rb->rt_leer(a->rt, (int)W, (int)H, RB_FMT_RGBA8, hi);
        const uint32_t *o = (const uint32_t *)hi;
        uint8_t *d = sal;
        for (uint32_t Yh = 0; Yh < hs; Yh++) {
            float v = (Yh + 0.5f) / s - 0.5f;
            for (uint32_t Xh = 0; Xh < ws; Xh++, d += 4) {
                float u = (Xh + 0.5f) / s - 0.5f;
                float tx = a->ox + 0.5f + a->a00 * u + a->a01 * v, ty = a->oy + 0.5f + a->a10 * u + a->a11 * v;
                int ix = (int)(tx * s), iy = (int)(ty * s);
                if (ix < 0) ix = 0;
                if (iy < 0) iy = 0;
                if (ix >= (int)W) ix = W - 1;
                if (iy >= (int)H) iy = H - 1;
                const uint8_t *p = (const uint8_t *)&o[(size_t)iy * W + ix];
                d[0] = p[2]; d[1] = p[1]; d[2] = p[0]; d[3] = 0xFF;
            }
        }
    } else {
        if (!giro_gpu(a, ws, hs)) { ult_a = NULL; return 0; }
        g_giro_sucio = 1;   /* g_giro_rt ya no es el cuadro que recuerda el camino asincrono */
        double cl = reloj();
        rb->rt_leer(g_giro_rt, (int)ws, (int)hs, RB_FMT_BGRA8, sal);
        if (crono_on()) cr_sumar(CR_ALTA_LEER, cl);
        /* el siguiente dibujo del raster vuelve a poner FBO, viewport, estado, programa y VAO (dibujar() lo hace siempre) */
        /* SM3DL_ALTA_VERIFICAR=1: compara EN EL MISMO PROCESO contra el giro de la CPU (=2: sabotea un pixel de la GPU) */
        static int verif = -1;
        static unsigned n_verif, n_mal;
        if (verif < 0) { const char *e = getenv("SM3DL_ALTA_VERIFICAR"); verif = e ? atoi(e) : 0; }
        if (verif) {
            if ((size_t)W * H * 4 > tam_hi) { free(hi); tam_hi = (size_t)W * H * 4; hi = malloc(tam_hi); }
            uint8_t *ref = malloc((size_t)ws * hs * 4);
            if (hi && ref) {
                if (verif == 2) sal[4 * ((size_t)(hs / 2) * ws + ws / 2)] ^= 1;
                rb->rt_leer(a->rt, (int)W, (int)H, RB_FMT_RGBA8, hi);
                const uint32_t *o = (const uint32_t *)hi;
                uint8_t *d = ref;
                for (uint32_t Yh = 0; Yh < hs; Yh++) {
                    float v = (Yh + 0.5f) / s - 0.5f;
                    for (uint32_t Xh = 0; Xh < ws; Xh++, d += 4) {
                        float u = (Xh + 0.5f) / s - 0.5f;
                        float tx = a->ox + 0.5f + a->a00 * u + a->a01 * v, ty = a->oy + 0.5f + a->a10 * u + a->a11 * v;
                        int ix = (int)(tx * s), iy = (int)(ty * s);
                        if (ix < 0) ix = 0;
                        if (iy < 0) iy = 0;
                        if (ix >= (int)W) ix = W - 1;
                        if (iy >= (int)H) iy = H - 1;
                        const uint8_t *p = (const uint8_t *)&o[(size_t)iy * W + ix];
                        d[0] = p[2]; d[1] = p[1]; d[2] = p[0]; d[3] = 0xFF;
                    }
                }
                size_t malos = 0;
                for (size_t k = 0; k < (size_t)ws * hs * 4; k++) malos += ref[k] != sal[k];
                n_verif++;
                if (malos) n_mal++;
                if (malos && n_mal == 20) {   /* volcado para analizar: <cwd>\alta_gpu.bgra y alta_cpu.bgra (ws x hs) */
                    FILE *f1 = fopen("alta_gpu.bgra", "wb"), *f2 = fopen("alta_cpu.bgra", "wb");
                    if (f1) { fwrite(sal, 4, (size_t)ws * hs, f1); fclose(f1); }
                    if (f2) { fwrite(ref, 4, (size_t)ws * hs, f2); fclose(f2); }
                    logr("VERIFICAR volcado %ux%u", ws, hs);
                }
                if (malos || n_verif % 60 == 0)
                    logr("VERIFICAR alta x%u: cuadro %u, %zu bytes distintos GPU vs CPU (cuadros con diferencia: %u de %u)", s, n_verif, malos, n_mal, n_verif);
            }
            free(ref);
        }
    }
    t_alta += reloj() - t0;
    if (crono_on()) cr_sumar(CR_ALTA, t0);
    if (++n_alta % 300 == 0) logr("pantalla en alta x%u (%s): %.2f ms por cuadro nuevo, %u cuadros", s, cpu ? "CPU" : "GPU", 1000 * t_alta / n_alta, n_alta);
    ult_a = a; ult_gen = a->gen; ult_ancho = ancho; ult_alto = alto;
    *rgba = sal;
    return (int)s;
}

/* ------------------------------------------------------------------ pantalla en alta ASINCRONA (agente A, 7 oct noche)
   Medido (SM3DL_A_CRONO, 4x): el glReadPixels del giro era la unica espera a la GPU que crece con la resolucion:
   ~1,2-1,6 ms por vblank (2,6-3,2 ms por cuadro nuevo) parado el hilo esperando que la GPU termine TODO el cuadro.
   Ahora la lectura va a un PBO con fence (anillo de 3) y se entrega cuando la GPU ya termino: la ventana recibe el
   cuadro anterior mientras el nuevo no esta (1 vblank de retraso como mucho). SM3DL_ALTA_ASINC=0 = camino sincrono.
   La misma textura girada (g_giro_tex) se ofrece a la ventana sin bajarla: raster_alta_textura (API PARA B). */
static int g_alta_cr_n;
static const Alta *g_giro_a;            /* que cuadro tiene hoy g_giro_tex */
static uint32_t g_giro_gen, g_giro_ancho, g_giro_alto;
#define GIRO_ES(a_, ws_, hs_) (!g_giro_sucio && g_giro_a == (a_) && g_giro_gen == (a_)->gen && g_giro_ancho == (ws_) && g_giro_alto == (hs_))

/* el giro en la GPU (mismo shader y estado que raster_alta_sinc) a g_giro_rt, sin leer */
static int alta_girar(Alta *a, uint32_t ws, uint32_t hs)
{
    if (!giro_gpu(a, ws, hs)) return 0;
    g_giro_a = a; g_giro_gen = a->gen; g_giro_ancho = ws; g_giro_alto = hs; g_giro_sucio = 0;
    return 1;
}

/* referencia en la CPU (el camino viejo): BGRA ws x hs fila 0 arriba, desde la copia en alta a->tex */
static int alta_ref_cpu(const Alta *a, uint32_t ws, uint32_t hs, uint8_t *ref)
{
    uint32_t s = a->s, W = a->w * s, H = a->h * s;
    uint8_t *hi = malloc((size_t)W * H * 4);
    if (!hi) return 0;
    rb->rt_leer(a->rt, (int)W, (int)H, RB_FMT_RGBA8, hi);
    const uint32_t *o = (const uint32_t *)hi;
    uint8_t *d = ref;
    for (uint32_t Yh = 0; Yh < hs; Yh++) {
        float v = (Yh + 0.5f) / s - 0.5f;
        for (uint32_t Xh = 0; Xh < ws; Xh++, d += 4) {
            float u = (Xh + 0.5f) / s - 0.5f;
            float tx = a->ox + 0.5f + a->a00 * u + a->a01 * v, ty = a->oy + 0.5f + a->a10 * u + a->a11 * v;
            int ix = (int)(tx * s), iy = (int)(ty * s);
            if (ix < 0) ix = 0;
            if (iy < 0) iy = 0;
            if (ix >= (int)W) ix = W - 1;
            if (iy >= (int)H) iy = H - 1;
            const uint8_t *p = (const uint8_t *)&o[(size_t)iy * W + ix];
            d[0] = p[2]; d[1] = p[1]; d[2] = p[0]; d[3] = 0xFF;
        }
    }
    free(hi);
    return 1;
}

static int alta_verif(void)
{
    static int v = -1;
    if (v < 0) { const char *e = getenv("SM3DL_ALTA_VERIFICAR"); v = e ? atoi(e) : 0; }
    return v;
}

int raster_alta_textura(uint32_t dir_fisica, uint32_t fmt, uint32_t stride, uint32_t ancho, uint32_t alto,
                        unsigned *tex_gl, int *s_sal, uint32_t *gen);
/* anillo de 4: como mucho 2 pendientes al emitir, asi el ultimo entregado (que la ventana esta leyendo directo del
   mapeo persistente, sin copia) nunca es el hueco que se reusa */
#define N_APBO 4
typedef struct {
    RbLectura *lec;          /* buffer de lectura + fence; cero copia = buffer persistente y coherente (GL 4.4 BufferStorage) */
    uint32_t ws, hs, s;
    uint8_t *ref;            /* SM3DL_ALTA_VERIFICAR: el giro de la CPU del MISMO cuadro, tomado al emitir */
} AltaPbo;
static AltaPbo g_apbo[N_APBO];
static int g_apbo_ini, g_apbo_n;
static int g_cero_copia = -1;   /* SM3DL_ALTA_CERO_COPIA=0: map + memcpy a un bufer propio (paso 2) */
static const uint8_t *g_entregado;   /* cero copia: lo ultimo entregado (apunta al mapeo de su buffer) */

/* entrega el pendiente mas viejo a 'sal' (esperando si 'esperar'); 1 si entrego */
static int apbo_entregar(uint8_t *sal, uint32_t *sws, uint32_t *shs, uint32_t *ss, int esperar)
{
    if (!g_apbo_n) return 0;
    AltaPbo *p = &g_apbo[g_apbo_ini];
    if (!rb->lectura_lista(p->lec)) {
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
        *sws = p->ws; *shs = p->hs; *ss = p->s;
        ok = 1;
        if (p->ref) {   /* verificacion en el mismo proceso: lo entregado (GPU, asincrono) contra la CPU del mismo cuadro */
            static unsigned n_verif, n_mal;
            size_t ksab = alta_verif() == 2 ? 4 * ((size_t)(p->hs / 2) * p->ws + p->ws / 2) : (size_t)-1;   /* sabotaje */
            size_t malos = 0, color = 0;
            for (size_t k = 0; k < bytes; k++) {
                uint8_t v = (uint8_t)(e[k] ^ (k == ksab));
                malos += p->ref[k] != v;
                color += (k & 3) != 3 && v > 16;
            }
            n_verif++;
            if (malos) n_mal++;
            if (malos || n_verif % 60 == 0)
                logr("VERIFICAR alta ASINC%s x%u: cuadro %u, %zu bytes distintos GPU vs CPU (cuadros con diferencia: %u de %u; %.0f %% de canales con color)",
                     mapa ? " cero-copia" : "", p->s, n_verif, malos, n_mal, n_verif, 100.0 * color / (bytes / 4 * 3));
        }
    }
    if (!mapa && !m) rb->lectura_desmapear(p->lec);   /* el mapeo fallo: suelta el buffer */
    free(p->ref);
    p->ref = NULL;
    g_apbo_ini = (g_apbo_ini + 1) % N_APBO;
    g_apbo_n--;
    return ok;
}

/* Interpolacion de cuadros en vivo (gsp_interp.inc, 7 oct): guarda (modo 0), restaura (1) o descarta (2) la copia en
   alta de la salida 'sal'. La re-ejecucion del cuadro intermedio pisa esa copia; tras mostrarlo se vuelve a la del
   cuadro real con una copia en la GPU (sin re-dibujar: no puede pisar el trabajo del cuadro siguiente).
   Una RANURA POR FRAMEBUFFER (hasta 4): con el ojo derecho fuera el juego se adelanta y puede haber varios cuadros
   con su intermedio pendiente a la vez (triple bufer). */
extern int interp_vivo;   /* interp.c: interpolacion de cuadros encendida (menu / sm3dl_ajustes.ini / SM3DL_INTERP) */
void raster_alta_instantanea(uint32_t sal, int modo)
{
    static struct { uint32_t sal; RbRT *rt; int w, h, valida; uint8_t *ref; size_t tam_ref; } r[4];
    static unsigned n_ok, n_mal;
    if (g_esc <= 1 || !contexto_actual()) return;
    int k = -1;
    for (int j = 0; j < 4; j++) if (r[j].valida && r[j].sal == sal) k = j;
    if (modo == 2) { if (k >= 0) r[k].valida = 0; return; }
    Alta *a = NULL;
    for (int j = 0; j < N_ALTA; j++)
        if (g_alta[j].valido && g_alta[j].sal == sal && g_alta[j].s == g_esc) a = &g_alta[j];
    if (!a || !a->rt) { if (k >= 0) r[k].valida = 0; return; }
    int W = a->w * a->s, H = a->h * a->s;
    RbRT *origen, *destino;
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
    /* SM3DL_INTERP_VERIFICAR=1: la copia en alta restaurada tiene que ser IDENTICA a la del cuadro real (leida al
       guardar); =2 sabotea un byte de la referencia para ver fallar la comparacion */
    static int verif = -1;
    if (verif < 0) { const char *s = getenv("SM3DL_INTERP_VERIFICAR"); verif = s ? atoi(s) : 0; }
    if (verif) {
        size_t tam = (size_t)W * H * 4;
        if (tam > r[k].tam_ref) { free(r[k].ref); r[k].ref = malloc(tam); r[k].tam_ref = r[k].ref ? tam : 0; }
        uint8_t *x = r[k].ref ? malloc(tam) : NULL;
        if (x) {
            rb->rt_leer(a->rt, W, H, RB_FMT_RGBA8, modo == 1 ? x : r[k].ref);
            if (modo == 0 && verif == 2) r[k].ref[tam / 2] ^= 1;
            if (modo == 1) {
                if (memcmp(x, r[k].ref, tam)) n_mal++; else n_ok++;
                if ((n_ok + n_mal) % 300 == 0)
                    logr("VERIFICAR interp: copia en alta restaurada %u veces identica, %u con diferencias", n_ok, n_mal);
            }
            free(x);
        }
    }
}

int raster_alta(uint32_t dir_fisica, uint32_t fmt, uint32_t stride, uint32_t ancho, uint32_t alto, const uint8_t **rgba)
{
    static int asinc = -1;
    static uint8_t *sal;
    static size_t tam_sal;
    static uint32_t sal_ws, sal_hs, sal_s;      /* lo que hay hoy en 'sal' */
    static const Alta *emit_a;
    static uint32_t emit_gen, emit_ws, emit_hs;  /* el ultimo cuadro emitido */
    if (asinc < 0) {
        const char *e = getenv("SM3DL_ALTA_ASINC"), *c = getenv("SM3DL_ALTA_CPU");
        asinc = !(e && *e == '0') && !(c && *c && *c != '0');
        logr("pantalla en alta: lectura %s", asinc ? "ASINCRONA (PBO + fence, SM3DL_ALTA_ASINC=0 la apaga)" : "sincrona");
    }
    /* con interpolacion en vivo, sincrona: la asincrona entrega con 1 vblank de retraso y el intermedio (que se
       muestra UN solo vblank) llegaria tarde o se saltaria */
    if (!asinc || interp_vivo) return raster_alta_sinc(dir_fisica, fmt, stride, ancho, alto, rgba);
    if (g_esc <= 1 || !contexto_actual()) return 0;
    Alta *a = NULL;
    for (int k = 0; k < N_ALTA; k++)
        if (g_alta[k].valido && g_alta[k].sal == dir_fisica && g_alta[k].s == g_esc) a = &g_alta[k];
    if (!a) return 0;
    if (a->mapa == 0 || a->m_fmt != fmt || a->m_stride != stride || a->m_ancho != ancho || a->m_alto != alto) {
        calcular_mapa(a, fmt, stride, ancho, alto);
        emit_a = NULL;
    }
    if (a->mapa != 1) return 0;
    uint32_t s = a->s, ws = ancho * s, hs = alto * s;
    size_t bytes = (size_t)ws * hs * 4;
    if (bytes > tam_sal) { free(sal); tam_sal = bytes; sal = malloc(tam_sal); sal_ws = 0; }
    if (!sal) return 0;
    double t0 = reloj();
    if (!(emit_a == a && emit_gen == a->gen && emit_ws == ws && emit_hs == hs)) {   /* cuadro nuevo: girar y emitir */
        while (g_apbo_n >= N_APBO - 2) apbo_entregar(sal, &sal_ws, &sal_hs, &sal_s, 1);
        if (!GIRO_ES(a, ws, hs) && !alta_girar(a, ws, hs)) {
            emit_a = NULL;
            return 0;
        }
        AltaPbo *p = &g_apbo[(g_apbo_ini + g_apbo_n) % N_APBO];
        if (g_cero_copia < 0) {
            const char *e = getenv("SM3DL_ALTA_CERO_COPIA");
            g_cero_copia = !(e && *e == '0');
            logr("pantalla en alta: %s", g_cero_copia ? "cero copia (PBO persistente; SM3DL_ALTA_CERO_COPIA=0 la apaga)" : "map + memcpy");
        }
        if (!p->lec) p->lec = rb->lectura_crear();
        const uint8_t *mapa_antes = rb->lectura_mapa_persistente(p->lec);
        int pers_ok = 1;
        /* giro -> buffer de lectura + fence (cero copia: buffer persistente; storage inmutable, si no alcanza se rehace) */
        int emitido = rb->lectura_emitir(p->lec, g_giro_rt, (int)ws, (int)hs, RB_FMT_BGRA8, g_cero_copia > 0, &pers_ok);
        if (g_cero_copia > 0 && !pers_ok) g_cero_copia = 0;
        if (emitido == 2 && g_entregado == mapa_antes) g_entregado = NULL;   /* el mapeo viejo ya no existe */
        p->ws = ws; p->hs = hs; p->s = s;
        p->ref = NULL;
        if (alta_verif() && (p->ref = malloc(bytes)) && !alta_ref_cpu(a, ws, hs, p->ref)) { free(p->ref); p->ref = NULL; }
        if (p->ref) {   /* prueba de la API PARA B: la textura que devuelve raster_alta_textura == la referencia CPU */
            unsigned tex = 0; int sa = 0; uint32_t gen = 0;
            uint8_t *t = malloc(bytes);
            int r = raster_alta_textura(dir_fisica, fmt, stride, ancho, alto, &tex, &sa, &gen);
            if (t && r == (int)s && tex == rb->rt_id_nativo(g_giro_rt) && gen == a->gen) {
                rb->rt_volcar_bgra(g_giro_rt, (int)ws, (int)hs, t);
                if (alta_verif() == 3) t[4 * ((size_t)(hs / 3) * ws + ws / 3) + 1] ^= 4;   /* sabotaje de la prueba de la API */
                size_t malos = 0;
                for (size_t k = 0; k < bytes; k++) malos += t[k] != p->ref[k];
                static unsigned n_api, n_api_mal;
                n_api++;
                if (malos) n_api_mal++;
                if (malos || n_api % 60 == 0)
                    logr("VERIFICAR API textura x%u: cuadro %u, %zu bytes distintos textura vs CPU (cuadros con diferencia: %u de %u)", s, n_api, malos, n_api_mal, n_api);
            } else {
                logr("VERIFICAR API textura: raster_alta_textura devolvio %d (tex %u/%u, gen %u/%u)", r, tex, rb->rt_id_nativo(g_giro_rt), gen, a->gen);
            }
            free(t);
        }
        g_apbo_n++;
        emit_a = a; emit_gen = a->gen; emit_ws = ws; emit_hs = hs;
    }
    /* entregar todo lo que la GPU ya termino (el mas nuevo queda en 'sal'); si en 'sal' no hay nada de este tamano
       (primer cuadro o cambio de resolucion), esperar: mejor un tiron una vez que mostrar la nativa */
    while (apbo_entregar(sal, &sal_ws, &sal_hs, &sal_s, 0)) {}
    while ((sal_ws != ws || sal_hs != hs || sal_s != s) && g_apbo_n) apbo_entregar(sal, &sal_ws, &sal_hs, &sal_s, 1);
    if (crono_on()) cr_sumar(CR_ALTA, t0);
    if (sal_ws != ws || sal_hs != hs || sal_s != s) return 0;
    *rgba = g_cero_copia > 0 && g_entregado ? g_entregado : sal;
    (void)g_alta_cr_n;
    return (int)s;
}

/* ------------------------------------------------------------------ API PARA B: presentar por GL sin bajar la imagen
   Ver agentes_7oct\A.md "API PARA B". */
int raster_alta_textura(uint32_t dir_fisica, uint32_t fmt, uint32_t stride, uint32_t ancho, uint32_t alto,
                        unsigned *tex_gl, int *s_sal, uint32_t *gen)
{
    if (g_esc <= 1 || !contexto_actual()) return 0;
    Alta *a = NULL;
    for (int k = 0; k < N_ALTA; k++)
        if (g_alta[k].valido && g_alta[k].sal == dir_fisica && g_alta[k].s == g_esc) a = &g_alta[k];
    if (!a) return 0;
    if (a->mapa == 0 || a->m_fmt != fmt || a->m_stride != stride || a->m_ancho != ancho || a->m_alto != alto)
        calcular_mapa(a, fmt, stride, ancho, alto);
    if (a->mapa != 1) return 0;
    uint32_t s = a->s, ws = ancho * s, hs = alto * s;
    if (!GIRO_ES(a, ws, hs)) {
        double t0 = reloj();
        if (!alta_girar(a, ws, hs)) return 0;
        if (crono_on()) cr_sumar(CR_ALTA, t0);
    }
    if (tex_gl) *tex_gl = rb->rt_id_nativo(g_giro_rt);
    if (s_sal) *s_sal = (int)s;
    if (gen) *gen = a->gen;
    return (int)s;
}

/* deja el contexto GL del raster actual sobre 'dc' (le pone el mismo pixel format si no tiene; una ventana solo
   admite SetPixelFormat UNA vez). Devuelve 1 si quedo. Despues la ventana puede dibujar en el framebuffer 0 y hacer
   SwapBuffers(dc). El raster sigue dibujando en sus FBO sin importar en que DC quede el contexto. */
int raster_gl_hacer_actual(void *hdc) { return rb->hacer_actual_dc(hdc); }

/* copia g_giro_tex (lo ultimo de raster_alta_textura) al rectangulo [x0,x1)x[y0,y1) del framebuffer 0 del DC actual
   (coordenadas GL: y hacia ARRIBA, origen abajo a la izquierda). lineal != 0: filtro GL_LINEAR; si no, NEAREST.
   No hace SwapBuffers. Deja ligado el framebuffer 0. */
int raster_alta_a_ventana(int x0, int y0, int x1, int y1, int lineal)
{
    if (!contexto_actual() || !g_giro_rt) return 0;
    rb->copiar(NULL, g_giro_rt, 0, 0, g_giro_w, g_giro_h, x0, y0, x1, y1, lineal);
    return 1;
}

/* cambia la resolucion interna (1-8): baja lo pendiente a la memoria y rehace los RT (se recrean al dibujar) */
void raster_escala(int s)
{
    if (s < 1) s = 1;
    if (s > 8) s = 8;   /* 10 oct: hasta 8x */
    if (s == g_esc) return;
    double c0 = reloj();
    if (contexto_actual()) {
        if (g_ndif > 0) completar_hasta(g_ndif - 1);
        for (int k = 0; k < g_nrt; k++) {
            if (g_rt[k].sucio) bajar_color(&g_rt[k]);
            destruir_rt(&g_rt[k]);
        }
        g_nrt = 0;
        for (int k = 0; k < N_ALTA; k++) g_alta[k].valido = 0;
    }
    logr("resolucion interna %dx", s);
    g_esc = s;
    if (crono_on()) cr_sumar(CR_ESCALA, c0);
}

static int transfer_diferido(uint32_t ent, uint32_t sal, const GspTransfer *tr, uint32_t te, uint32_t ts)
{
    if (g_dif_activo < 0) {
        const char *s = getenv("SM3DL_SIN_DIFERIDO");
        g_dif_activo = !(s && *s && *s != '0');
        logr("DisplayTransfer diferido %s", g_dif_activo ? "activo" : "apagado (SM3DL_SIN_DIFERIDO)");
    }
    if (!g_dif_activo || !contexto_actual()) return 0;
    Rt *t = NULL;
    for (int k = 0; k < g_nrt; k++)
        if (ent >= g_rt[k].color_dir && ent < g_rt[k].color_dir + rt_bytes(&g_rt[k])) { t = &g_rt[k]; break; }
    if (!t) return 0;
    copiar_alta(t, ent, sal, tr, te, ts);   /* resolucion interna: la pantalla guarda su copia grande */
    int pendiente = 0;
    for (int k = 0; k < g_ndif; k++)
        if (g_dif[k].rdir == t->color_dir && g_dif[k].escribir_rt) pendiente = 1;
    if (!t->sucio && !pendiente) return 0;   /* la memoria ya esta al dia: el camino de siempre no espera */
    if (ent + te > t->color_dir + rt_bytes(t))
        for (int k = 0; k < g_nrt; k++)
            if (&g_rt[k] != t && g_rt[k].sucio &&
                solapa(t->color_dir + rt_bytes(t), ent + te, g_rt[k].color_dir, g_rt[k].color_dir + rt_bytes(&g_rt[k])))
                return 0;
    /* lo pendiente que toque esta entrada o esta salida va primero (orden de la memoria) */
    g_motivo = 3;
    if (g_ndif >= MAX_DIF) completar_hasta(0);
    double c0 = reloj();
    Diferido *d = &g_dif[g_ndif];
    if (!d->lec) d->lec = rb->lectura_crear();
    RbRT *fuente = ligar_nativo(t);   /* resolucion interna: el transfer ve el RT reducido */
    rb->lectura_emitir(d->lec, fuente, t->w, t->h, RB_FMT_RGBA8, 0, NULL);
    if (crono_on()) cr_sumar(CR_DIF_EMITIR, c0);
    d->ent = ent; d->sal = sal; d->te = te; d->ts = ts;
    d->w = t->w; d->h = t->h; d->fmt = t->fmt;
    d->rdir = t->color_dir; d->rbytes = rt_bytes(t);
    for (int k = 0; k < g_ndif; k++)   /* el nuevo escribe el RT despues y mas al dia: los viejos ya no */
        if (g_dif[k].rdir == d->rdir) g_dif[k].escribir_rt = 0;
    d->escribir_rt = 1;
    d->tr = *tr;
    g_ndif++;
    g_n_dif++;
    t->sucio = 0;
    return 1;
}

static void antes_de_escribir(uint32_t fisica, uint32_t tam)
{
    if (!contexto_actual() || g_ndif == 0) return;
    /* un MemoryFill que tapa TODO un RT pendiente: la memoria de ese RT ya no importa (no hay que esperar por ella) */
    for (int k = 0; k < g_ndif; k++) {
        Diferido *d = &g_dif[k];
        if (fisica <= d->rdir && fisica + tam >= d->rdir + d->rbytes) d->escribir_rt = 0;
    }
    int ultimo = -1;
    for (int k = 0; k < g_ndif; k++) {
        Diferido *d = &g_dif[k];
        if (solapa(fisica, fisica + tam, d->sal, d->sal + d->ts) ||
            (d->escribir_rt && solapa(fisica, fisica + tam, d->rdir, d->rdir + d->rbytes)))
            ultimo = k;
    }
    g_motivo = 1;
    if (ultimo >= 0) completar_hasta(ultimo);
}

static void antes_de_leer(uint32_t fisica, uint32_t tam)
{
    if (!contexto_actual()) return;
    g_motivo = g_desde_textura ? 5 : 0;
    if (gsp_presentando) {
        /* presentacion: solo lo que la GPU YA termino (prefijo de la cola), sin esperar */
        while (g_ndif > 0) {
            if (!rb->lectura_lista(g_dif[0].lec)) break;
            completar_dif(0);
        }
    } else {
        completar_solapes(fisica, tam);
    }
    for (int k = 0; k < g_nrt; k++) {
        Rt *t = &g_rt[k];
        if (t->sucio && solapa(fisica, fisica + tam, t->color_dir, t->color_dir + rt_bytes(t))) bajar_color(t);
    }
}

static void tras_fill(uint32_t ini, uint32_t fin, uint32_t valor, uint32_t control)
{
    if (!contexto_actual()) return;
    uint32_t ancho_fill = (control & 0x200) ? 4 : (control & 0x100) ? 3 : 2;
    for (int k = 0; k < g_nrt; k++) {
        Rt *t = &g_rt[k];
        uint32_t c0 = t->color_dir, c1 = c0 + rt_bytes(t);
        if (solapa(ini, fin, c0, c1)) {
            if (ini <= c0 && fin >= c1 && ancho_fill == (uint32_t)gsp_bytes_pixel(t->fmt)) {
                uint8_t b[4] = { (uint8_t)valor, (uint8_t)(valor >> 8), (uint8_t)(valor >> 16), (uint8_t)(valor >> 24) };
                uint8_t c[4];
                gsp_decodificar_pixel(t->fmt, b, c);
                float cf[4] = { c[0] / 255.0f, c[1] / 255.0f, c[2] / 255.0f, c[3] / 255.0f };
                rb->rt_limpiar(t->rt, RB_LIMPIAR_COLOR, cf, 0.0, 0);
            } else {
                if (t->sucio) AVISO_UNA_VEZ(AV_FILL_SUCIO, "MemoryFill parcial sobre un RT con dibujo pendiente "
                                            "(0x%08X-0x%08X sobre 0x%08X): se pierde lo dibujado", ini, fin, c0);
                subir_color(t);
            }
            t->sucio = 0;
        }
        uint32_t d0 = t->depth_dir, d1 = d0 + rt_bytes_depth(t);
        if (d0 && solapa(ini, fin, d0, d1) && ini <= d0 && fin >= d1) {
            double z;
            int s = 0;
            if (t->depth_fmt == 0) z = (valor & 0xFFFF) / 65535.0;
            else { z = (valor & 0xFFFFFF) / 16777215.0; s = (int)(valor >> 24); }
            rb->rt_limpiar(t->rt, RB_LIMPIAR_DS, NULL, z, s);
        }
    }
}

/* ------------------------------------------------------------------ texturas */
/* nivel de mip k: (ancho>>k) x (alto>>k), seguidos en memoria; la PICA no baja de 8x8 */
static int tex_niveles(const PicaTextura *x)
{
    int n = 1 + x->lod_max;
    while (n > 1 && ((x->ancho >> (n - 1)) < 8 || (x->alto >> (n - 1)) < 8)) n--;
    return n;
}

/* P1: tam = bytes de todos los mips en memoria; vista = contenido validado (hash) en el cuadro `cuadro` y sin aviso de
   escritura desde entonces; hd = texhd_activo() al validarla */
typedef struct { uint32_t dir, w, h, fmt, niveles, hash, gen; RbTex *tex; uint32_t uso; uint32_t tam, cuadro; int vista, hd; } TexCache;
static TexCache g_tex[256];
static uint32_t g_reloj;
/* T2: generacion de la cache. Subirla invalida todas las entradas (se re-suben al primer uso, reusando su RbTex: sin fugas). */
static uint32_t g_tex_gen = 1;
static uint32_t g_texhd_log;
/* Para el menu (T7): al encender/apagar "Texturas HD" fuerza que cada textura se vuelva a subir (con o sin reemplazo). */
void raster_tex_hd_recargar(void) { g_tex_gen++; }

/* P1 (10 oct): ATAJO de textura_para. Medido por H1 en la partida del duenio: 8,48 M dibujos en 59 s, tramo "texturas"
   17,8 s porque cada dibujo copiaba y hasheaba (FNV) la textura ENTERA con todos sus mips para saber si cambio. Ahora
   una entrada ya validada se devuelve sin leer memoria mientras (1) no llegue un aviso de escritura que la solape y
   (2) no cambie el cuadro. (1) = gsp_tras_escribir (gsp.c): TODA escritura de la GPU emulada (fill, transfer,
   texcopy, DMA, bajada de un RT por antes_de_leer -> render a textura, copias de la re-ejecucion) y las escrituras de
   CPU que el juego avisa como en el 3DS real (Flush/InvalidateDataCache, GX CacheFlush). (2) = gsp_cuadro_tex, +1 en
   la transfer de abajo y NO en las re-ejecuciones del 144: red para las escrituras de CPU SIN aviso (van directo a
   rt_pagina; nadie las ve): una vez por cuadro real se re-hashea como antes; en los intermedios nunca (mismo cuadro).
   Limite: una escritura de CPU sin flush en MEDIO de un cuadro sobre una textura ya usada en ese cuadro no se ve hasta
   el siguiente (en el 3DS real tampoco seria coherente sin flush). Medirlo: SM3DL_P1_VERIFICAR=1 hashea igual en cada
   atajo y cuenta "errores" (log [p1-tex]). SM3DL_P1_ATAJO=0 = camino de antes. SM3DL_P1_SABOTAJE=1 = se ignoran avisos
   y frontera (debe verse fallar: contenido nuevo en la misma direccion no se re-sube). */
extern void (*gsp_tras_escribir)(uint32_t fisica, uint32_t tam);
extern uint32_t gsp_cuadro_tex;
static int g_p1_modo = -1, g_p1_sab;   /* modo: 0 sin atajo, 1 atajo, 2 atajo + verificacion */
static uint64_t g_p1_llamadas, g_p1_atajos, g_p1_validas, g_p1_avisos, g_p1_errores;
static uint8_t g_tex_pista[1024];      /* direccion -> indice en g_tex (pista; siempre se comprueba la entrada) */
static void tex_tras_escribir(uint32_t f, uint32_t tam)
{
    if (g_p1_sab) return;
    uint32_t fin = f + tam < f ? 0xFFFFFFFFu : f + tam;
    for (int k = 0; k < 256; k++) {
        TexCache *c = &g_tex[k];
        if (c->vista && solapa(f, fin, c->dir, c->dir + c->tam)) { c->vista = 0; g_p1_avisos++; }
    }
}
static void p1_iniciar(void)
{
    const char *s = getenv("SM3DL_P1_ATAJO");
    g_p1_modo = s && *s ? (atoi(s) ? 1 : 0) : 1;   /* vacia = sin poner (Start-Process puede pasar "") */
    s = getenv("SM3DL_P1_VERIFICAR");
    if (g_p1_modo && s && atoi(s)) g_p1_modo = 2;
    s = getenv("SM3DL_P1_SABOTAJE");
    g_p1_sab = s ? atoi(s) : 0;
    logr("[p1-tex] atajo de texturas: modo %d%s", g_p1_modo, g_p1_sab ? " (SABOTAJE: sin avisos ni frontera)" : "");
}

static RbTex *textura_para(const PicaTextura *x, int *niveles_sal)
{
    int niveles = tex_niveles(x);
    size_t tam = 0;
    for (int k = 0; k < niveles; k++) tam += tex_tamano(x->ancho >> k, x->alto >> k, x->formato);
    if (!tam || x->ancho > 1024 || x->alto > 1024) {
        AVISO_UNA_VEZ(AV_TEX, "textura no soportada: formato %u %ux%u", x->formato, x->ancho, x->alto);
        return 0;
    }
    *niveles_sal = niveles;
    const int niveles_orig = niveles;
    g_desde_textura = 1;
    antes_de_leer(x->direccion, (uint32_t)tam);   /* puede ser un render target (render a textura): su bajada avisa (P1) */
    g_desde_textura = 0;
    if (g_p1_modo < 0) p1_iniciar();
    const int hd_on = texhd_activo();
    g_reloj++;
    if (!(++g_p1_llamadas & 0x3FFFF))
        logr("[p1-tex] %llu usos: %llu atajos, %llu re-validadas sin cambio, %u subidas, %llu avisos, %llu ERRORES (cambio sin aviso)",
             (unsigned long long)g_p1_llamadas, (unsigned long long)g_p1_atajos, (unsigned long long)g_p1_validas, g_tex_subidas,
             (unsigned long long)g_p1_avisos, (unsigned long long)g_p1_errores);
    const uint32_t cuadro = g_p1_sab ? 0u : gsp_cuadro_tex;
    /* pista por la clave entera (la misma direccion con otro tamanio / mips es otra entrada); si falla, recorrido */
    const unsigned pista = ((x->direccion ^ (x->ancho << 20) ^ (x->alto << 8) ^ (x->formato << 4) ^ ((uint32_t)niveles << 28)) *
                            2654435761u) >> 22;
#define P1_ES(c) ((c)->tex && (c)->dir == x->direccion && (c)->w == x->ancho && (c)->h == x->alto && (c)->fmt == x->formato && \
                  (c)->niveles == (uint32_t)niveles)
    TexCache *ya = &g_tex[g_tex_pista[pista]];
    if (g_p1_modo && !P1_ES(ya)) {
        ya = NULL;
        for (int k = 0; k < 256; k++) if (P1_ES(&g_tex[k])) { ya = &g_tex[k]; g_tex_pista[pista] = (uint8_t)k; break; }
    }
#undef P1_ES
    const int ya_vale = g_p1_modo && ya && ya->vista && ya->cuadro == cuadro && ya->gen == g_tex_gen && ya->hd == hd_on;
    if (ya_vale && g_p1_modo == 1) { ya->uso = g_reloj; g_p1_atajos++; return ya->tex; }
    uint8_t *m = malloc(tam);
    if (!m || gsp_leer_fisica(x->direccion, m, (uint32_t)tam) != 0) { free(m); return 0; }
    uint32_t h = fnv((const uint32_t *)m, tam / 4);
    TexCache *libre = &g_tex[0];
    h ^= hd_on ? 0x9E3779B9u : 0u;   /* T2: la misma textura con HD encendido/apagado es otro contenido */
    if (ya_vale) {   /* modo 2: el atajo se habria tomado; se comprueba contra el hash de verdad */
        if (ya->hash == h) { ya->uso = g_reloj; g_p1_atajos++; free(m); return ya->tex; }
        if (g_p1_errores++ < 8)
            logr("[p1-tex] ERROR: textura 0x%08X %ux%u fmt %u cambio sin aviso en el cuadro %u", x->direccion, x->ancho, x->alto,
                 x->formato, cuadro);
    }
    for (int k = 0; k < 256; k++) {
        TexCache *c = &g_tex[k];
        if (c->tex && c->dir == x->direccion && c->w == x->ancho && c->h == x->alto && c->fmt == x->formato &&
            c->niveles == (uint32_t)niveles) {
            if (c->hash != h || c->gen != g_tex_gen) { libre = c; break; }       /* misma textura, contenido nuevo: reusar la entrada */
            c->uso = g_reloj;
            c->vista = 1; c->cuadro = cuadro; c->hd = hd_on; g_tex_pista[pista] = (uint8_t)k; g_p1_validas++;   /* P1 */
            free(m);
            return c->tex;
        }
        if (c->uso < libre->uso) libre = c;
    }
    /* se decodifican todos los niveles de mip primero (se corta en el primero que falla) y el backend los sube juntos */
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
    int sub_w = x->ancho, sub_h = x->alto, sub_n = niveles;
    const uint8_t *const *sub_px = nivel;
    if (niveles > 0 && (hd_on || texhd_volcando())) {
        /* clave = FNV-1a por palabras sobre el nivel 0 CRUDO (contrato texturas_hd.h) */
        uint32_t clave = fnv((const uint32_t *)m, tex_tamano(x->ancho, x->alto, x->formato) / 4);
        if (texhd_volcando()) texhd_volcar(clave, x->ancho, x->alto, (int)x->formato, nivel[0]);
        int W = 0, H = 0, nh = 0;
        const uint8_t *const *hp = NULL;
        if (hd_on && texhd_buscar(clave, x->ancho, x->alto, (int)x->formato, &W, &H, &nh, &hp) && nh > 0 && W > 0 && H > 0 && hp) {
            if (nh > 16) nh = 16;
            sub_w = W; sub_h = H; sub_px = hp;
            /* un original sin mips (niveles == 1) sigue sin mips: el muestreo no cambia, solo la nitidez */
            sub_n = niveles > 1 ? nh : 1;
        }
        if (!(++g_texhd_log & 255)) {
            uint32_t r = 0, b = 0;
            texhd_estadisticas(&r, &b);
            logr("texturas HD: %u reemplazadas de %u buscadas", r, b);
        }
    }
    libre->tex = rb->tex_cargar_mips(libre->tex, sub_w, sub_h, sub_n, sub_px);
    libre->dir = x->direccion; libre->w = x->ancho; libre->h = x->alto; libre->fmt = x->formato;
    libre->niveles = (uint32_t)niveles_orig;
    libre->hash = h; libre->gen = g_tex_gen; libre->uso = g_reloj;
    libre->tam = (uint32_t)tam; libre->vista = niveles > 0; libre->cuadro = cuadro; libre->hd = hd_on;   /* P1 */
    g_tex_pista[pista] = (uint8_t)(libre - g_tex);
    free(m);
    free(rgba);
    return niveles > 0 ? libre->tex : 0;
}

/* muestreador de la unidad (filtros, envoltura, LOD, borde): el backend lo traduce (GL: glTexParameter; D3D12: sampler) */
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

/* modo de la unidad k para el shader: 0 apagada, 1 muestrear (textura enlazada), 2 direccion 0 */
static int preparar_unidad(const PicaEstado *e, int k, int *proy)
{
    const PicaTextura *x = &e->tex[k];
    rb->tex_enlazar(k, NULL, NULL);   /* selecciona la unidad k */
    if (!x->activa) return 0;
    if (k == 0 && x->tipo != 0) {
        if (x->tipo == 3) *proy = 1;
        else if (x->tipo == 5) return 0;
        else {
            AVISO_UNA_VEZ(AV_TEX_TIPO, "textura 0 de tipo %u (cubo / sombra) sin soporte: se lee como 0", x->tipo);
            return 0;
        }
    }
    if (x->direccion == 0) return 2;
    int niveles = 1;
    RbTex *t = textura_para(x, &niveles);
    if (!t) return 0;
    RbMuestreador m;
    muestreador_de(x, niveles, &m);
    rb->tex_enlazar(k, t, &m);
    return 1;
}

/* ------------------------------------------------------------------ LUTs de luz */
static RbTex *g_tex_luts;
static uint32_t g_luts_ver = 0xFFFFFFFFu;
/* cache de tablas de luz por CONTENIDO: el juego alterna pocas tablas distintas entre materiales, pero las re-escribe
   en cada uno (~1.500 tablas/s). Cada tabla (256 entradas) vive en una fila de una textura 256 x LUT_FILAS; el shader
   la busca por luz_fila[t]. Solo se sube una tabla que nunca se vio (o que salio de la cache). */
#define LUT_FILAS 1024
#define LUT_CUBOS 4096
static uint32_t g_lut_fila[24];               /* fila actual de cada tabla t */
static uint32_t g_lut_copia[24][256];         /* contenido de la tabla t cuando se resolvio su fila */
static uint32_t g_fila_cont[LUT_FILAS][256];  /* contenido de cada fila */
static uint32_t g_fila_hash[LUT_FILAS];
static int g_fila_usada[LUT_FILAS];
static int32_t g_cubo[LUT_CUBOS];              /* hash -> fila + 1 (sondeo lineal; 0 = vacio) */
static uint32_t g_fila_siguiente;              /* reemplazo en ronda */
static int g_luts_listas;

static void cubo_quitar(uint32_t fila)
{
    uint32_t h = g_fila_hash[fila] & (LUT_CUBOS - 1);
    for (uint32_t k = 0; k < LUT_CUBOS; k++, h = (h + 1) & (LUT_CUBOS - 1))
        if (g_cubo[h] == (int32_t)fila + 1) {
            /* borrar en sondeo lineal: re-insertar lo que sigue en el racimo */
            g_cubo[h] = 0;
            for (uint32_t j = (h + 1) & (LUT_CUBOS - 1); g_cubo[j]; j = (j + 1) & (LUT_CUBOS - 1)) {
                int32_t f = g_cubo[j];
                g_cubo[j] = 0;
                uint32_t i = g_fila_hash[f - 1] & (LUT_CUBOS - 1);
                while (g_cubo[i]) i = (i + 1) & (LUT_CUBOS - 1);
                g_cubo[i] = f;
            }
            return;
        }
}

static uint32_t fila_para(const uint32_t *tabla, const uint32_t *ocupadas, int nocup)
{
    uint32_t h = fnv(tabla, 256), i = h & (LUT_CUBOS - 1);
    while (g_cubo[i]) {
        uint32_t f = (uint32_t)g_cubo[i] - 1;
        if (g_fila_hash[f] == h && !memcmp(g_fila_cont[f], tabla, 1024)) return f;
        i = (i + 1) & (LUT_CUBOS - 1);
    }
    /* nueva: una fila libre, o la siguiente en ronda que no use ahora otra tabla de este dibujo */
    uint32_t f;
    for (;;) {
        f = g_fila_siguiente;
        g_fila_siguiente = (g_fila_siguiente + 1) % LUT_FILAS;
        int ocupada = 0;
        for (int k = 0; k < nocup; k++) if (ocupadas[k] == f) ocupada = 1;
        if (!ocupada) break;
    }
    if (g_fila_usada[f]) cubo_quitar(f);
    g_fila_usada[f] = 1;
    memcpy(g_fila_cont[f], tabla, 1024);
    g_fila_hash[f] = h;
    i = h & (LUT_CUBOS - 1);
    while (g_cubo[i]) i = (i + 1) & (LUT_CUBOS - 1);
    g_cubo[i] = (int32_t)f + 1;
    static float rg[256 * 2];
    for (int k = 0; k < 256; k++) {   /* bits 0-11 valor 0.12, 12-22 |diferencia| 0.11, 23 signo */
        uint32_t w = tabla[k];
        float d = ((w >> 12) & 0x7FF) / 2047.0f;
        rg[k * 2] = (w & 0xFFF) / 4095.0f;
        rg[k * 2 + 1] = (w >> 23) & 1 ? -d : d;
    }
    rb->tex_subir(g_tex_luts, 0, (int)f, 256, 1, RB_FMT_RG32F, 0, rg);
    g_luts_subidas++;
    return f;
}

static double r1_lut_t[3];   /* R1: 0 enlaces (2 tex_enlazar), 1 bucle completo, 2 fila_para */
static uint64_t r1_lut_n[4];  /* R1: 0 llamadas, 1 recorridos del bucle, 2 recorridos con e != pica.e, 3 tablas memcmp-eadas */
static void preparar_luts(const PicaEstado *e)
{
    double r1_q0 = reloj();
    rb->tex_enlazar(3, NULL, NULL);   /* unidad 3 = LUTs de luz */
    if (!g_tex_luts) g_tex_luts = rb->tex_crear(256, LUT_FILAS, RB_FMT_RG32F, RB_TEX_NEAREST);
    rb->tex_enlazar(3, g_tex_luts, NULL);
    r1_lut_n[0]++;
    double r1_q1 = reloj();
    r1_lut_t[0] += r1_q1 - r1_q0;
    if (g_luts_ver == e->luz_lut_ver) return;
    r1_lut_n[1]++;
    if (!(e == &pica.e)) r1_lut_n[2]++;
    /* P2 (10 oct): luz_lut_ver sube con CUALQUIER tabla; antes se comparaban las 24 (24 KB de memcmp) en cada cambio.
       Ahora la tabla cuyo sello (pica.h) no cambio desde que se resolvio se salta sin mirarla. */
    static uint64_t sello_visto[24];
    static int visto_ini;
    if (!visto_ini) { for (int t = 0; t < 24; t++) sello_visto[t] = ~0ull; visto_ini = 1; }
    const int sellable = sellos_on() && e == &pica.e;
    /* R1 (10 oct): sello 0 = tabla que NUNCA se escribio (pica.c lo reparte solo cuando una escritura CAMBIA un valor; el
       unico camino de escritura; memset de pica lo deja en 0 junto con el contenido). Antes `s &&` excluia el 0: las ~22 de
       24 tablas que el juego no usa se comparaban con memcmp (1 KB c/u) en CADA recorrido (~7 us por recorrido, 29 % de
       los dibujos con luz: ~2 us por dibujo con luz). Ahora el 0 tambien vale como sello visto (centinela ~0 = nunca visto).
       SM3DL_R1_SIN=1 vuelve a la condicion de antes. */
    static int r1_sin_l = -1, r1_sabotaje = -1, r1_verif = -1;
    if (r1_verif < 0) { const char *q = getenv("SM3DL_R1_VERIFICAR"); r1_verif = q && *q && *q != '0'; }
    if (r1_sabotaje < 0) { const char *q = getenv("SM3DL_R1_SABOTAJE"); r1_sabotaje = q && *q && *q != '0'; }
    if (r1_sin_l < 0) { const char *q = getenv("SM3DL_R1_SIN"); r1_sin_l = q && *q && *q != '0'; }
    for (int t = 0; t < 24; t++) {
        const uint64_t s = sellable ? pica.sello_lut[t] : 0;
        if (g_luts_listas && sellable && (s || !r1_sin_l) && s == sello_visto[t]) {
            if (r1_verif && memcmp(g_lut_copia[t], e->luz_lut[t], 1024)) r1_lut_n[3] += 1000000000ull;   /* atajo equivocado: 1e9 por error */
            continue;
        }
        if (r1_sabotaje && g_luts_listas && t >= 4) continue;   /* SABOTAJE: nunca mira las tablas >= 4 tras la primera vez */
        sello_visto[t] = sellable ? s : ~0ull;
        r1_lut_n[3]++;
        if (g_luts_listas && !memcmp(g_lut_copia[t], e->luz_lut[t], 1024)) continue;
        memcpy(g_lut_copia[t], e->luz_lut[t], 1024);
        double r1_q2 = reloj();
        g_lut_fila[t] = fila_para(e->luz_lut[t], g_lut_fila, g_luts_listas ? 24 : t);
        r1_lut_t[2] += reloj() - r1_q2;
    }
    r1_lut_t[1] += reloj() - r1_q1;
    g_luts_listas = 1;
    g_luts_ver = e->luz_lut_ver;
}

/* muestreadores soportados por la config de luz (Azahar regs_lighting.h IsLightingSamplerSupported) */
static int luz_soporta(uint32_t cfg, int m)
{
    switch (m) {
    case 0: return cfg != 1;                                   /* D0 */
    case 1: return cfg != 0 && cfg != 1 && cfg != 5;           /* D1 */
    case 8: return cfg != 2 && cfg != 3;                       /* SP */
    case 3: return cfg != 0 && cfg != 2 && cfg != 4;           /* FR */
    case 6: return cfg != 3;                                   /* RR */
    case 4: case 5: return cfg == 4 || cfg == 5 || cfg == 8;   /* RB, RG */
    }
    return 0;
}

/* bit n = muestreador n en uso; los bits de apagado de config1: D0 16, D1 17, FR 19, RR 20, RG 21, RB 22 */
static int luz_mues_de(uint32_t c0, uint32_t c1)
{
    uint32_t cfg = (c0 >> 4) & 0xF;
    int mues = 0;
    static const struct { int m, bit; } AP[6] = { { 0, 16 }, { 1, 17 }, { 3, 19 }, { 6, 20 }, { 5, 21 }, { 4, 22 } };
    for (int k = 0; k < 6; k++)
        if (luz_soporta(cfg, AP[k].m) && !((c1 >> AP[k].bit) & 1)) mues |= 1 << AP[k].m;
    if (luz_soporta(cfg, 8)) mues |= 1 << 8;   /* el apagado del spot es por luz (config1 bits 8-15) */
    return mues;
}

/* color de 10 bits por canal de la PICA -> (r, g, b, 0) */
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
    /* R1 (10 oct): SM3DL_R1_PERFIL=1 cronometra por partes (QPC) y SM3DL_R1_SIN=1 vuelve al camino de antes (A/B en el mismo exe) */
    static int r1_perfil = -1;
    static double r1_t[4];          /* 0 preparar_luts, 1 armado de cl, 2 constantes(b3), 3 total */
    static uint64_t r1_n[4];        /* 0 dibujos con luz, 1 sin luz, 2 armados evitados, 3 armados hechos */
    if (r1_perfil < 0) {
        const char *s1 = getenv("SM3DL_R1_PERFIL");
        r1_perfil = s1 && *s1 && *s1 != '0';
    }
    double r1_a = r1_perfil ? reloj() : 0, r1_b = 0, r1_c = 0;
    int on = (r[0x1C6] & 1) == 0;
    cl.luz_on = on;
    if (on) {
        preparar_luts(e);
        if (r1_perfil) r1_b = reloj();
        r1_n[3]++;
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
    if (r1_perfil) r1_c = reloj();
    rb->constantes(p->prog, RB_BLOQUE_LUZ, &cl);
    if (r1_perfil) {
        double z = reloj();
        r1_n[on ? 0 : 1]++;
        if (on) { r1_t[0] += r1_b - r1_a; r1_t[1] += r1_c - r1_b; }
        r1_t[2] += z - r1_c;
        r1_t[3] += z - r1_a;
        static uint64_t k;
        if (++k % 200000 == 0)
            logr("[R1] lut(us/llamada: enlaces %.3f bucle %.3f fila_para %.3f) llamadas %llu bucle %llu (e!=pica.e %llu) memcmp+1e9*errores %llu | luz: %llu con luz (%llu armados, %llu evitados) %llu sin luz | us/dibujo: luts %.3f armado %.3f b3 %.3f total(todos) %.3f",
                 r1_lut_t[0] * 1e6 / r1_lut_n[0], r1_lut_t[1] * 1e6 / r1_lut_n[0], r1_lut_t[2] * 1e6 / r1_lut_n[0],
                 (unsigned long long)r1_lut_n[0], (unsigned long long)r1_lut_n[1], (unsigned long long)r1_lut_n[2], (unsigned long long)r1_lut_n[3],
                 (unsigned long long)r1_n[0], (unsigned long long)r1_n[3], (unsigned long long)r1_n[2], (unsigned long long)r1_n[1],
                 r1_t[0] * 1e6 / (r1_n[0] ? r1_n[0] : 1), r1_t[1] * 1e6 / (r1_n[0] ? r1_n[0] : 1),
                 r1_t[2] * 1e6 / (double)(r1_n[0] + r1_n[1]), r1_t[3] * 1e6 / (double)(r1_n[0] + r1_n[1]));
    }
}

/* ------------------------------------------------------------------ vertices */
/* llena sal[n][16][4]: los 16 registros de entrada del vertex shader de cada vertice */
static void permutar(const PicaEstado *e, float atr[16][4], float *r)
{
    memset(r, 0, 64 * sizeof(float));
    for (uint32_t a = 0; a < e->vs.num_entradas && a < 16; a++)
        memcpy(r + 4 * (e->vs.permutacion[a] & 15), atr[a], 16);
}

/* rango != 0: se decodifica cada vertice de imin..imax UNA vez (sal[k] = vertice imin+k), para glDrawElements */
static int g_elementos = -1;   /* SM3DL_SIN_ELEMENTOS=1: siempre glDrawArrays (camino viejo) */
static uint32_t cuenta_de(int rango, uint32_t imin, uint32_t imax, uint32_t n) { return rango ? imax - imin + 1 : n; }
static int armar_vertices(const PicaEstado *e, const uint32_t *ind, uint32_t n, float *sal, int rango)
{
    static const uint8_t TAM_ELEM[4] = { 1, 1, 2, 4 };
    const PicaVertices *v = &e->vtx;
    double tv0 = reloj();
    uint32_t imin = 0xFFFFFFFFu, imax = 0;
    for (uint32_t k = 0; k < n; k++) { if (ind[k] < imin) imin = ind[k]; if (ind[k] > imax) imax = ind[k]; }

    /* fuente de cada atributo: (bloque leido, offset dentro del vertice, stride) */
    struct { const uint8_t *datos; uint32_t off, stride; int hay; } fuente[12];
    memset(fuente, 0, sizeof fuente);
    uint8_t *bloques[12] = { 0 };
    int ok = 1;
    for (int j = 0; j < 12 && ok; j++) {
        uint32_t nc = v->loader[j].num_comp, off = 0, stride = v->loader[j].stride;
        if (!nc) continue;
        for (uint32_t c = 0; c < nc && c < 12; c++) {
            uint32_t a = v->loader[j].comp[c];
            if (a < 12) {
                uint32_t te = TAM_ELEM[v->formato[a] & 3];
                off = (off + te - 1) & ~(te - 1);
                fuente[a].off = off;
                fuente[a].stride = stride;
                fuente[a].hay = 1;
                off += te * v->componentes[a];
            } else {
                off = (off + 3) & ~3u;
                off += (a - 11) * 4;
            }
        }
        uint32_t ini = v->base_fisica + v->loader[j].offset + imin * stride;
        uint32_t tam = (imax - imin) * stride + (off > stride ? off : stride);
        if (!tam) continue;
        bloques[j] = malloc(tam);
        if (!bloques[j] || gsp_leer_fisica(ini, bloques[j], tam) != 0) {
            AVISO_UNA_VEZ(AV_MEM_VTX, "vertices fuera de memoria: loader %d 0x%08X (%u bytes)", j, ini, tam);
            ok = 0;
            break;
        }
        for (uint32_t c = 0; c < nc && c < 12; c++)
            if (v->loader[j].comp[c] < 12) fuente[v->loader[j].comp[c]].datos = bloques[j];
    }
    double tb = reloj();
    g_v_bloques += tb - tv0;
    g_v_n += cuenta_de(rango, imin, imax, n);
    uint32_t cuenta = rango ? imax - imin + 1 : n;
    int na = e->vs.num_entradas < 16 ? (int)e->vs.num_entradas : 16;   /* permutar solo copia a < num_entradas */
    for (uint32_t k = 0; k < cuenta && ok; k++) {
        float atr[16][4];
        uint32_t ix = rango ? imin + k : ind[k];
        for (int a = 0; a < na; a++) {
            const PicaVec4 *f = &e->atr_fijo[a];
            if ((v->mascara_fijos >> a) & 1u || a >= 12 || !fuente[a].hay) {
                atr[a][0] = f->x; atr[a][1] = f->y; atr[a][2] = f->z; atr[a][3] = f->w;
                continue;
            }
            const uint8_t *p = fuente[a].datos + (size_t)(ix - imin) * fuente[a].stride + fuente[a].off;
            uint32_t nc = v->componentes[a];
            for (uint32_t c = 0; c < 4; c++) {
                float x = c == 3 ? 1.0f : 0.0f;
                if (c < nc) switch (v->formato[a] & 3) {
                    case PICA_ATR_BYTE: x = (float)(int8_t)p[c]; break;
                    case PICA_ATR_UBYTE: x = (float)p[c]; break;
                    case PICA_ATR_SHORT: { int16_t s; memcpy(&s, p + 2 * c, 2); x = (float)s; break; }
                    default: memcpy(&x, p + 4 * c, 4); break;
                }
                atr[a][c] = x;
            }
        }
        permutar(e, atr, sal + (size_t)k * 64);
    }
    for (int j = 0; j < 12; j++) free(bloques[j]);
    g_v_decod += reloj() - tb;
    return ok;
}

/* Camino NATIVO de vertices (7 oct): los bloques de cada loader se suben TAL CUAL estan en la memoria del juego y
 * la GPU convierte byte/ubyte/short/float con glVertexAttribPointer (sin normalizar = igual que (float)int8 del
 * camino en CPU; los componentes que faltan salen (0,0,0,1) igual que alla). El atributo a va a la location
 * permutacion[a] (= registro de entrada v[k] del .vert); las locations sin atributo quedan en 0 como en permutar().
 * Deja g_vao_crudo enlazado. Devuelve 0 si no aplica (stride 0, memoria fuera de mapa): se usa armar_vertices.
 * SM3DL_VTX_CPU=1 fuerza el camino viejo. Los indices del dibujo van relativos a imin. */
static int g_vtx_cpu = -1;
static int armar_crudo(const PicaEstado *e, uint32_t imin, uint32_t imax)
{
    static const uint8_t TAM_ELEM[4] = { 1, 1, 2, 4 };
    static uint8_t *stage;
    static uint32_t stage_tam;
    const PicaVertices *v = &e->vtx;
    double tv0 = reloj();
    struct { uint32_t off, stride, loader; int hay; } fuente[12];
    uint32_t ini[12], tam[12], boff[12], total = 0;
    memset(fuente, 0, sizeof fuente);
    for (int j = 0; j < 12; j++) {
        uint32_t nc = v->loader[j].num_comp, off = 0, stride = v->loader[j].stride;
        tam[j] = 0;
        if (!nc) continue;
        if (!stride) return 0;   /* GL entiende stride 0 como "empaquetado": no es lo mismo */
        for (uint32_t c = 0; c < nc && c < 12; c++) {
            uint32_t a = v->loader[j].comp[c];
            if (a < 12) {
                uint32_t te = TAM_ELEM[v->formato[a] & 3];
                off = (off + te - 1) & ~(te - 1);
                fuente[a].off = off;
                fuente[a].stride = stride;
                fuente[a].loader = (uint32_t)j;
                fuente[a].hay = 1;
                off += te * v->componentes[a];
            } else {
                off = (off + 3) & ~3u;
                off += (a - 11) * 4;
            }
        }
        ini[j] = v->base_fisica + v->loader[j].offset + imin * stride;
        tam[j] = (imax - imin) * stride + (off > stride ? off : stride);
        total = (total + 3) & ~3u;
        boff[j] = total;
        total += tam[j];
    }
    if (!total) return 0;
    /* P3 (10 oct): SIN COPIA DOBLE. Antes: memoria del 3DS -> stage (gsp_leer_fisica, "bloques" 3,5 s en la partida del
       dueno) -> anillo de subida (memcpy del backend, dentro de "decod"). Si los bloques de todos los loaders caen en
       un tramo [lo, hi) contiguo en el anfitrion, no mucho mas grande que lo que se copiaba (<= total + total/4 + 64)
       y cada bloque empieza a multiplo de 4 de lo (D3D12 exige bind_off & 3 == 0), el backend copia DIRECTO de la
       memoria del juego: mismos bytes en el mismo orden relativo de cada loader -> mismos pixeles. Si no, el stage de
       siempre. SM3DL_P3_SIN=1: siempre el stage (camino de antes, para comparar). SM3DL_P3_SABOTAJE=1: el camino
       directo corre los datos 4 bytes (la verificacion DEBE ver pixeles distintos). */
    p3_env();
    const uint8_t *datos = NULL;
    uint32_t bytes = total;
    if (!g_p3_sin) {
        uint32_t lo = 0xFFFFFFFFu, hi = 0;
        for (int j = 0; j < 12; j++)
            if (tam[j]) {
                if (ini[j] < lo) lo = ini[j];
                if (ini[j] + tam[j] > hi) hi = ini[j] + tam[j];
            }
        int alin = 1;
        for (int j = 0; j < 12; j++) if (tam[j] && ((ini[j] - lo) & 3u)) alin = 0;
        if (alin && hi > lo && hi - lo <= total + total / 4 + 64) {
            const uint8_t *h = gsp_fisica_a_host(lo, hi - lo);
            if (h) {
                datos = h;
                bytes = hi - lo;
                for (int j = 0; j < 12; j++) if (tam[j]) boff[j] = ini[j] - lo + (g_p3_sab == 1 && ini[j] - lo + 4 < bytes ? 4u : 0u);
                g_p3_directos++;
                g_p3_bytes_dir += bytes;
            } else g_p3_no_host++;
        } else g_p3_no_tramo++;
    }
    if (!datos) {
        if (total > stage_tam) {
            uint8_t *s = realloc(stage, total);
            if (!s) return 0;
            stage = s;
            stage_tam = total;
        }
        for (int j = 0; j < 12; j++)
            if (tam[j] && gsp_leer_fisica(ini[j], stage + boff[j], tam[j]) != 0) {
                AVISO_UNA_VEZ(AV_MEM_VTX, "vertices fuera de memoria: loader %d 0x%08X (%u bytes)", j, ini[j], tam[j]);
                return 0;
            }
        datos = stage;
        g_p3_stage++;
    }
    g_p3_bytes_tot += total;
    double tb = reloj();
    g_v_bloques += tb - tv0;
    /* formato por location (el "layout"): 0 = sin arreglo (valor constante); si no tamanno|tipo|binding|offset.
       Un VAO por layout distinto, reutilizado: el driver valida el formato UNA vez y por dibujo solo cambian los
       buffers (glBindVertexBuffer), que es lo barato. Las constantes (glVertexAttrib4f) son estado del contexto. */
    RbVerticesCrudos vc;   /* lo que se le pasa al backend; lay[]/cte[] son sus campos */
    memset(&vc, 0, sizeof vc);
    uint32_t *lay = vc.layout;
    float (*cte)[4] = vc.cte;
    int na = e->vs.num_entradas < 16 ? (int)e->vs.num_entradas : 16;
    for (int a = 0; a < na; a++) {   /* en orden: si dos atributos caen en la misma location gana el ultimo */
        int loc = e->vs.permutacion[a] & 15;
        uint32_t nc = a < 12 ? v->componentes[a] : 0;
        if ((v->mascara_fijos >> a) & 1u || a >= 12 || !fuente[a].hay || nc == 0) {
            const PicaVec4 *f = &e->atr_fijo[a];
            lay[loc] = 0;
            if (a < 12 && !((v->mascara_fijos >> a) & 1u) && fuente[a].hay && nc == 0) {
                cte[loc][0] = cte[loc][1] = cte[loc][2] = 0.0f; cte[loc][3] = 1.0f;   /* igual que el camino CPU */
            } else {
                cte[loc][0] = f->x; cte[loc][1] = f->y; cte[loc][2] = f->z; cte[loc][3] = f->w;
            }
            continue;
        }
        lay[loc] = 0x80000000u | ((nc > 4 ? 4 : nc) << 24) | ((v->formato[a] & 3u) << 20) |
                   (fuente[a].loader << 16) | (fuente[a].off & 0xFFFFu);
        static int sab = -1;   /* SM3DL_VTX_SABOTAJE=1: tipo equivocado en el atributo 0 (la verificacion DEBE fallar) */
        if (sab < 0) { const char *s = getenv("SM3DL_VTX_SABOTAJE"); sab = s && *s && *s != '0'; }
        if (sab && a == 0) lay[loc] ^= 1u << 20;
    }
    /* SM3DL_VTX_VERIFICAR=1: cada 97 dibujos, simula en C lo que la GPU leera con este layout (offsets, strides,
       tipos, permutacion, constantes) y lo compara bit a bit con armar_vertices (el camino CPU ya verificado). La
       conversion byte/short -> float sin normalizar es exacta por especificacion de GL: lo que se prueba es el mapeo. */
    static int verif = -1;
    static unsigned n_verif, n_mal, cuenta;
    if (verif < 0) { const char *s = getenv("SM3DL_VTX_VERIFICAR"); verif = s && *s && *s != '0'; }
    if (verif && ++cuenta % 97 == 0) {
        uint32_t nv = imax - imin + 1;
        uint32_t *ix = malloc((size_t)nv * 4);
        float *ref = malloc((size_t)nv * 64 * sizeof(float));
        if (ix && ref) {
            for (uint32_t k = 0; k < nv; k++) ix[k] = imin + k;
            if (armar_vertices(e, ix, nv, ref, 1)) {
                int malo = 0;
                for (uint32_t k = 0; k < nv && !malo; k++)
                    for (int L = 0; L < 16 && !malo; L++) {
                        float s[4] = { 0.0f, 0.0f, 0.0f, 1.0f };
                        if (!lay[L]) memcpy(s, cte[L], sizeof s);
                        else {
                            uint32_t nc = (lay[L] >> 24) & 7, ti = (lay[L] >> 20) & 3, j = (lay[L] >> 16) & 15;
                            const uint8_t *p = datos + boff[j] + (size_t)k * v->loader[j].stride + (lay[L] & 0xFFFF);
                            for (uint32_t c = 0; c < nc; c++)
                                switch (ti) {
                                    case 0: s[c] = (float)(int8_t)p[c]; break;
                                    case 1: s[c] = (float)p[c]; break;
                                    case 2: { int16_t h; memcpy(&h, p + 2 * c, 2); s[c] = (float)h; break; }
                                    default: memcpy(&s[c], p + 4 * c, 4); break;
                                }
                        }
                        if (memcmp(s, ref + (size_t)k * 64 + 4 * L, sizeof s)) {
                            const float *r = ref + (size_t)k * 64 + 4 * L;
                            if (++n_mal <= 10)
                                logr("VTX DISTINTO: vertice %u loc %d layout %08X: gpu (%g %g %g %g) cpu (%g %g %g %g)",
                                     k, L, lay[L], s[0], s[1], s[2], s[3], r[0], r[1], r[2], r[3]);
                            malo = 1;
                        }
                    }
                n_verif++;
                if (n_verif % 500 == 0 || n_verif <= 2)
                    logr("verificacion de vertices: %u dibujos comparados, %u distintos", n_verif, n_mal);
            }
        }
        free(ix);
        free(ref);
    }
    vc.datos = datos;
    vc.bytes = bytes;
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

/* modo inmediato: las entradas ya vienen en e->inm (atributo a del vertice v) */
static void armar_inmediato(const PicaEstado *e, float *sal)
{
    for (uint32_t k = 0; k < 3; k++) {
        float atr[16][4];
        for (int a = 0; a < 16; a++) {
            const PicaVec4 *f = &e->inm[k][a];
            atr[a][0] = f->x; atr[a][1] = f->y; atr[a][2] = f->z; atr[a][3] = f->w;
        }
        permutar(e, atr, sal + (size_t)k * 64);
    }
}

/* ------------------------------------------------------------------ estado de fragmentos */
/* estado de fragmentos/rasterizador -> RbEstado (inmutable, tipo PSO; ver raster_backend.h). Los enteros van tal cual
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

/* constantes de todo el pipeline, leidas de los registros en cada dibujo y mandadas por BLOQUES (RbCb*) */
static void subir_uniforms(const Programa *p, const PicaEstado *e, const uint32_t *r)
{
    /* vertex shader (bloque b0) */
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
    int32_t *omap = cv.omap;
    for (int k = 0; k < 24; k++) omap[k] = -1;
    int regs_o[16], no = 0;
    for (int k = 0; k < 16; k++) if ((e->vs.mascara_salida >> k) & 1) regs_o[no++] = k;
    uint32_t total = r[0x04F] & 7;
    for (uint32_t a = 0; a < total && a < 7 && (int)a < no; a++)
        for (int c = 0; c < 4; c++) {
            uint32_t s = (r[0x050 + a] >> (8 * c)) & 0x1F;
            if (s < 24) omap[s] = regs_o[a] * 4 + c;
        }
    static int depurar = -1;
    static uint32_t ndep;
    if (depurar < 0) { const char *s = getenv("SM3DL_RASTER_DEPURAR"); depurar = s ? atoi(s) : 0; }
    if (ndep < (uint32_t)depurar) {
        ndep++;
        fprintf(stderr, "[raster-dep] mask %04X total %u omap", e->vs.mascara_salida, total);
        for (int k = 0; k < 24; k++) fprintf(stderr, " %d", omap[k]);
        fprintf(stderr, "\n[raster-dep]   tev");
        static const uint16_t bs[6] = { 0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8 };
        for (int k = 0; k < 6; k++)
            fprintf(stderr, " [%08X %08X %08X %08X %08X]", r[bs[k]], r[bs[k] + 1], r[bs[k] + 2], r[bs[k] + 3],
                    r[bs[k] + 4]);
        fprintf(stderr, " upd %08X buf %08X tex %X tipo0 %u dir0 %08X fmt0 %u alfa %u/%u/%u blend %u\n", r[0xE0],
                r[0xFD], r[0x80] & 7, e->tex[0].tipo, e->tex[0].direccion, e->tex[0].formato, e->alpha_test,
                e->alpha_func, e->alpha_ref, e->blend_activo);
    }
    cv.clip_on = (int)(r[0x047] & 1);
    cv.clip_coef[0] = pica_f24(r[0x048]); cv.clip_coef[1] = pica_f24(r[0x049]);
    cv.clip_coef[2] = pica_f24(r[0x04A]); cv.clip_coef[3] = pica_f24(r[0x04B]);
    rb->constantes(p->prog, RB_BLOQUE_V, &cv);

    /* TEV y operaciones de fragmento (bloque b1) */
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

    /* texturas */
    int proy = 0;
    double tt0 = reloj();
    int m0 = preparar_unidad(e, 0, &proy), m1 = preparar_unidad(e, 1, &proy), m2 = preparar_unidad(e, 2, &proy);
    g_tramo[2] += reloj() - tt0;
    cf.tex_modo[0] = m0; cf.tex_modo[1] = m1; cf.tex_modo[2] = m2; cf.tex_modo[3] = e->tex2_usa_coord1;
    cf.tex0_proy = proy;
    if ((r[0x080] >> 10) & 1) AVISO_UNA_VEZ(AV_TEX3, "textura procedural (tex3) pedida: sin soporte, vale 0");

    /* operaciones de fragmento */
    cf.alfa_func = e->alpha_test ? e->alpha_func : -1;
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
    double tl0 = reloj();
    subir_luz(p, e, r);
    g_tramo[3] += reloj() - tl0;
}

/* ------------------------------------------------------------------ el dibujo */
static void dibujar(const PicaEstado *e)
{
    const uint32_t *r = pica.reg;
    if (raster_cinta_j >= 0) cinta_nada(raster_cinta_j);   /* H1: si no llega a dibujarse, queda "no se dibujo" */
    if (!iniciar_gl() || !contexto_actual()) return;
    double t_ini = reloj();
    if (e->usa_gs) { AVISO_UNA_VEZ(AV_GS, "dibujo con geometry shader de la PICA: se salta"); return; }
    uint32_t topo = e->inm_n ? 0 : e->idx.topologia;
    if (topo == 3) topo = 0;   /* "shader" sin GS de la PICA = lista de triangulos (Azahar primitive_assembly.cpp) */
    if (topo > 2) { AVISO_UNA_VEZ(AV_TOPO, "topologia %u: se salta", topo); return; }
    if (e->modo_fragmento != 0) { AVISO_UNA_VEZ(AV_FRAG, "modo de fragmento %u: se salta", e->modo_fragmento); return; }
    uint32_t n = e->inm_n ? e->inm_n : e->idx.num_vertices;
    if (n == 0 || n > (1u << 20)) return;
    int luz = (r[0x1C6] & 1) == 0;
    Programa *p = programa_para(&e->vs, r);
    g_tramo[0] += reloj() - t_ini;
    if (!p) return;
    double trt = reloj();
    Rt *t = rt_para(e);
    g_v_rt += reloj() - trt;
    if (!t) return;

    int rango = 0;
    uint32_t nv = n, base = 0;
    if (g_elementos < 0) {
        const char *s = getenv("SM3DL_SIN_ELEMENTOS");
        g_elementos = !(s && *s && *s != '0');
    }
    if (g_vtx_cpu < 0) {
        const char *s = getenv("SM3DL_VTX_CPU");
        g_vtx_cpu = s && *s && *s != '0';
        logr("vertices: %s", g_vtx_cpu ? "camino CPU (SM3DL_VTX_CPU)" : "camino nativo (formatos del PICA en la GPU)");
    }
    int crudo = 0;   /* 1: g_vao_crudo listo, los indices van relativos a base */
    static void *ind_buf;
    static uint32_t ind_cap;
    p3_env();
    static uint32_t p3_alt;
    if (g_p3_ab) g_p3_sin = (int)(++p3_alt & 1);
    int ind_rel = 0;   /* P3: ind ya relativo a base (el envio no resta) */
    double t_crudo = 0.0;
    uint32_t *ind = p3_crecer(&ind_buf, &ind_cap, (size_t)n * 4);
    float *vb = NULL;
    if (!ind) goto fin;
    if (e->inm_n) {
        if (!(vb = malloc((size_t)n * 64 * sizeof(float)))) goto fin;
        armar_inmediato(e, vb);
    } else {
        /* P3 (10 oct): antes malloc + gsp_leer_fisica + conversion a 32 bits + min/max + (en el envio) "ind -= base":
           4 pasadas y 2 mallocs por dibujo. Ahora: los indices se leen DIRECTO de la memoria del juego si el tramo es
           contiguo (si no, copia a un buffer propio), min/max sobre los de 8/16 bits, y UNA conversion que ya los deja
           relativos a imin cuando va por el camino nativo. Dibujos sin indices: imin/imax salen del vertex_offset
           (ind solo se llena si hace falta el camino CPU). Mismos indices que antes -> mismos pixeles. */
        uint32_t imin = 0xFFFFFFFFu, imax = 0;
        const uint8_t *ib = NULL;
        int u16 = e->idx.es_u16 != 0;
        if (g_p3_sin) {   /* SM3DL_P3_SIN / A-B: la secuencia de ANTES de P3, tal cual (malloc, 3 pasadas, resta en el envio) */
            if (e->idx.es_elements) {
                uint32_t tam = n * (u16 ? 2u : 1u), dir = e->vtx.base_fisica + e->idx.offset;
                uint8_t *b = malloc(tam);
                if (!b || gsp_leer_fisica(dir, b, tam) != 0) {
                    AVISO_UNA_VEZ(AV_MEM_IDX, "indices fuera de memoria: 0x%08X (%u bytes)", dir, tam);
                    free(b);
                    goto fin;
                }
                for (uint32_t k = 0; k < n; k++) {
                    if (u16) { uint16_t s; memcpy(&s, b + 2 * k, 2); ind[k] = s; }
                    else ind[k] = b[k];
                }
                free(b);
            } else {
                for (uint32_t k = 0; k < n; k++) ind[k] = e->idx.vertex_offset + k;
            }
            for (uint32_t k = 0; k < n; k++) { if (ind[k] < imin) imin = ind[k]; if (ind[k] > imax) imax = ind[k]; }
        } else if (e->idx.es_elements) {
            static void *ib_buf;
            static uint32_t ib_cap;
            uint32_t tam = n * (u16 ? 2u : 1u), dir = e->vtx.base_fisica + e->idx.offset;
            ib = g_p3_sin ? NULL : gsp_fisica_a_host(dir, tam);
            if (ib) g_p3_idx_host++;
            else {
                uint8_t *b = p3_crecer(&ib_buf, &ib_cap, tam);
                if (!b || gsp_leer_fisica(dir, b, tam) != 0) {
                    AVISO_UNA_VEZ(AV_MEM_IDX, "indices fuera de memoria: 0x%08X (%u bytes)", dir, tam);
                    goto fin;
                }
                ib = b;
            }
            if (u16) {
                uint16_t mn = 0xFFFF, mx = 0;
                for (uint32_t k = 0; k < n; k++) {
                    uint16_t s;
                    memcpy(&s, ib + 2 * k, 2);
                    mn = s < mn ? s : mn;
                    mx = s > mx ? s : mx;
                }
                imin = mn; imax = mx;
            } else {
                uint8_t mn = 0xFF, mx = 0;
                for (uint32_t k = 0; k < n; k++) { mn = ib[k] < mn ? ib[k] : mn; mx = ib[k] > mx ? ib[k] : mx; }
                imin = mn; imax = mx;
            }
            g_p3_elem++;
            g_p3_idx_n += n;
        } else {
            imin = e->idx.vertex_offset;
            imax = e->idx.vertex_offset + n - 1;
        }
        if (topo == 2) g_p3_abanicos++;
        double tc0 = reloj();
        int va_crudo = !g_vtx_cpu && imax - imin < (1u << 20) && armar_crudo(e, imin, imax);
        t_crudo = reloj() - tc0;
        if (g_p3_sin) {
            /* ind ya esta absoluto (camino de antes) */
        } else if (e->idx.es_elements) {
            ind_rel = va_crudo;   /* ib sigue valido: armar_crudo no escribe la memoria del juego ni ib_buf */
            uint32_t resta = va_crudo ? imin : 0u;
            if (u16)
                for (uint32_t k = 0; k < n; k++) { uint16_t s; memcpy(&s, ib + 2 * k, 2); ind[k] = (uint32_t)s - resta; }
            else
                for (uint32_t k = 0; k < n; k++) ind[k] = (uint32_t)ib[k] - resta;
            if (g_p3_sab == 2 && va_crudo) for (uint32_t k = 2; k < n; k += 3) ind[k] = ind[k - 2];   /* sabotaje: indices cambiados */
        } else if (!va_crudo) {
            for (uint32_t k = 0; k < n; k++) ind[k] = e->idx.vertex_offset + k;
        }
        if (va_crudo) {
            crudo = 1;
            base = imin;
            nv = imax - imin + 1;
            g_v_n += nv;
            g_v_unicos += nv;
        } else {
            if (e->idx.es_elements)   /* los indices repiten vertices: rango unico si sale a cuenta */
                if (imax - imin + 1 < n && g_elementos) { rango = 1; nv = imax - imin + 1; base = imin; }
            if (!(vb = malloc((size_t)cuenta_de(rango, imin, imax, n) * 64 * sizeof(float)))) goto fin;
            if (!armar_vertices(e, ind, n, vb, rango)) goto fin;
            if (rango) g_v_unicos += nv;
        }
    }

    double tv = reloj();
    g_tramo[1] += tv - t_ini - 0;
    g_s_actual = t->s;   /* resolucion interna: viewport y tijera en pixeles del RT grande */
    rb->fijar_destino(t->rt, e->viewport_x * t->s, e->viewport_y * t->s, (int)(e->viewport_ancho * t->s),
                      (int)(e->viewport_alto * t->s));
    RbEstado est;
    estado_de(e, r, &est);
    rb->fijar_estado(&est);
    rb->prog_usar(p->prog);
    double tu = reloj();
    subir_uniforms(p, e, r);
    double td = reloj();
    g_tramo[4] += (td - tu) - 0;
    static uint32_t n_muestra;
    int muestra = crono_on() && (++n_muestra & 7) == 0;
    if (muestra) gq_ini(GQ_DIB);
    if (crudo) {   /* el layout y los bloques ya los dejo armar_crudo en el backend */
        if (e->idx.es_elements && !ind_rel) for (uint32_t k = 0; k < n; k++) ind[k] -= base;   /* solo el camino de antes */
        rb->dibujar(topo, n, e->idx.es_elements ? ind : NULL);   /* P3: ind ya viene relativo a base */   /* sin indices: ind[k] = vertex_offset + k = base + k */
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
    if (muestra) gq_fin();
    g_tramo[5] += reloj() - td;
    if (g_p3_ab) {
        int m = !g_p3_sin;
        g_p3_ab_t[m][0] += tv - t_ini;   /* incluye programa: igual en los dos */
        g_p3_ab_t[m][1] += t_crudo;
        g_p3_ab_t[m][2] += reloj() - td;
        g_p3_ab_n[m]++;
    }
    t->sucio = 1;

    static uint32_t dibujados;
    if (++dibujados <= 3 || dibujados % 3000 == 0) {
        unsigned err = rb->ultimo_error();
        logr("dibujo %u: %u vertices topo %u al RT 0x%08X, viewport %d,%d %gx%g, z %g/%g, luz %d, gl error 0x%X; "
             "tiempo dibujar %.2f s, bajar %.2f s", dibujados, n, topo, t->color_dir, e->viewport_x, e->viewport_y,
             e->viewport_ancho, e->viewport_alto, e->depth_escala, e->depth_offset, luz, err, g_t_dibujar, g_t_bajar);
        logr("  tramos: programa %.2f vertices %.2f texturas %.2f luts %.2f (subidas %u) uniforms %.2f envio %.2f; "
             "[programas: %u del disco, %u compilados (%.1f s), %u rechazados] [vtx: bloques %.2f decod %.2f rt %.2f, %llu vertices, %llu por rango] texturas subidas %u, fs %d, programas %d; bajar %u veces, leer %.2f s; diferidos %u (esperaron %u: leer %u escribir %u transfer %u llena %u rt %u tex %u) %.2f s", g_tramo[0], g_tramo[1] - g_tramo[0], g_tramo[2], g_tramo[3], g_luts_subidas,
             g_tramo[4] - g_tramo[2] - g_tramo[3], g_tramo[5], g_bin_cargados, g_bin_compilados, g_t_compilar, g_bin_rechazados, g_v_bloques, g_v_decod, g_v_rt, (unsigned long long)g_v_n, (unsigned long long)g_v_unicos, g_tex_subidas, g_nfs, g_nprog, g_n_bajar, g_t_leer, g_n_dif, g_n_dif_espera, g_por_motivo[0], g_por_motivo[1], g_por_motivo[2], g_por_motivo[3], g_por_motivo[4], g_por_motivo[5], g_t_dif);
        logr("  vtx-P3: %s; vertices directos %llu / stage %llu (sin tramo %llu, no contiguo %llu), bytes subidos %llu de %llu "
             "por loaders; elementos %llu (%llu indices, %llu directos), abanicos %llu", g_p3_sin ? "APAGADO (SM3DL_P3_SIN)" : "activo",
             (unsigned long long)g_p3_directos, (unsigned long long)g_p3_stage, (unsigned long long)g_p3_no_tramo,
             (unsigned long long)g_p3_no_host, (unsigned long long)(g_p3_bytes_dir), (unsigned long long)g_p3_bytes_tot,
             (unsigned long long)g_p3_elem, (unsigned long long)g_p3_idx_n, (unsigned long long)g_p3_idx_host,
             (unsigned long long)g_p3_abanicos);
        if (g_p3_ab && g_p3_ab_n[0] && g_p3_ab_n[1])
            logr("  vtx-P3 A/B (us por dibujo): ANTES %llu dibujos: vertices %.3f crudo %.3f envio %.3f | P3 %llu dibujos: "
                 "vertices %.3f crudo %.3f envio %.3f", (unsigned long long)g_p3_ab_n[0], 1e6 * g_p3_ab_t[0][0] / g_p3_ab_n[0],
                 1e6 * g_p3_ab_t[0][1] / g_p3_ab_n[0], 1e6 * g_p3_ab_t[0][2] / g_p3_ab_n[0], (unsigned long long)g_p3_ab_n[1],
                 1e6 * g_p3_ab_t[1][0] / g_p3_ab_n[1], 1e6 * g_p3_ab_t[1][1] / g_p3_ab_n[1], 1e6 * g_p3_ab_t[1][2] / g_p3_ab_n[1]);
    }
fin:
    free(vb);
    g_t_dibujar += reloj() - t_ini;
}

static unsigned g_raster_desde;
static void enganchar(void);

void raster_iniciar(void)
{
    const char *s = getenv("SM3DL_SIN_RASTER");
    if (s && *s && *s != '0') { logr("apagado por SM3DL_SIN_RASTER"); return; }
    s = getenv("SM3DL_RESOLUCION");
    if (s && atoi(s) > 1) raster_escala(atoi(s));
    s = getenv("SM3DL_RASTER_DESDE");
    if (s && atol(s) > 0) { g_raster_desde = (unsigned)atol(s); logr("sin enganchar hasta el vblank %u", g_raster_desde); return; }
    enganchar();
}

void raster_vblank(unsigned vblank)
{
    crono_reporte(vblank);
    if (g_raster_desde && vblank >= g_raster_desde) {
        logr("enganchado en el vblank %u (SM3DL_RASTER_DESDE)", vblank);
        g_raster_desde = 0;
        enganchar();
    }
}

static void enganchar(void)
{
    pica_raster = dibujar;
    gsp_antes_de_leer = antes_de_leer;
    gsp_tras_escribir = tex_tras_escribir;   /* P1: avisos de escritura -> cache de texturas */
    gsp_tras_fill = tras_fill;
    gsp_transfer_diferido = transfer_diferido;
    gsp_antes_de_escribir = antes_de_escribir;
}

#include "presentador_gl.inc"

/* ------------------------------------------------------------------ seleccion del backend (SM3DL_BACKEND=gl|d3d12)
   El D3D12 es el destino del plan (pasos 3-9); hoy solo existe la interfaz: este STUB avisa y cae a GL. Cuando exista,
   rb_d3d12_obtener() devolvera su tabla (raster_backend_d3d12.c, que tambien se incluira desde aqui). */
#ifdef SM3DL_CON_D3D12   /* compilar.py --d3d12 (8 oct noche): backend en raster_backend_d3d12.c, incluido al final */
const RasterBackend *rb_d3d12_obtener(void);
#else
static const RasterBackend *rb_d3d12_obtener(void) { return NULL; }
#endif

#ifdef SM3DL_CON_D3D12
static const RasterBackend *dx_cinta_envolver(const RasterBackend *b);   /* raster_d3d12_dibujar.inc (H1) */
#endif
static const RasterBackend *elegir_backend(void)
{
    const char *s = getenv("SM3DL_BACKEND");
    const RasterBackend *b = NULL;
    if (s && !_stricmp(s, "d3d12")) {
        b = rb_d3d12_obtener();
#ifdef SM3DL_CON_D3D12
        if (b) b = dx_cinta_envolver(b);   /* H1: destruir / re-subir texturas o RT invalida la cinta del cuadro */
#endif
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
#ifdef SM3DL_CON_D3D12
#include "raster_backend_d3d12.c"
#endif

/* ------------------------------------------------------------------ cinta de intermedios (H1): interfaz para interp.c
   GL: no hay cinta (todo devuelve 0 / no hace nada) y los intermedios siguen por la re-ejecucion de siempre. */
#ifdef SM3DL_CON_D3D12
static int cinta_d3d12(void) { return g_rb && g_rb->dibujar == dx_dibujar && dx.estado == 1; }
static void cinta_nada(int j) { if (cinta_d3d12()) dx_cinta_nada(j); }
void raster_cinta_empezar(void) { if (cinta_d3d12()) dx_cinta_empezar(); }
int raster_cinta_lista(int n) { return cinta_d3d12() && dx_cinta_lista(n); }
void raster_cinta_dibujar(int j, const float *c) { if (cinta_d3d12()) dx_cinta_dibujar(j, c); }
void raster_cinta_cifras(char *b, size_t n) { if (cinta_d3d12()) dx_cinta_cifras(b, n); else if (n) *b = 0; }
#else
static void cinta_nada(int j) { (void)j; }
void raster_cinta_empezar(void) {}
int raster_cinta_lista(int n) { (void)n; return 0; }
void raster_cinta_dibujar(int j, const float *c) { (void)j; (void)c; }
void raster_cinta_cifras(char *b, size_t n) { if (n) *b = 0; }
#endif
