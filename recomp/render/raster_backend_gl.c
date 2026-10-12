/* Backend OpenGL 4.5 del rasterizador (8 oct 2026, agente A de la tanda D3D12, paso 1). Contrato: raster_backend.h.
 *
 * Es el codigo GL de raster_gl.c MOVIDO aqui sin cambiar la secuencia de llamadas GL (mismo orden, mismos valores):
 * es el backend de REFERENCIA contra el que se comparara el D3D12 pixel a pixel. Se incluye con #include desde
 * raster_gl.c (una sola unidad de compilacion): usa logr / reloj / fnv_texto / crono_on de la capa comun.
 *
 * SM3DL_BACKEND_SABOTAJE=n (prueba de que la comparacion por pixel DETECTA diferencias; solo para verificar):
 *   1 = la mascara de color de TODO dibujo pierde el canal azul (cambia la imagen en cualquier camino);
 *   2 = la imagen de la base se corre 1 px a la derecha al copiarla a la ventana (camino de presentacion por GPU);
 *   3 = las dos. Con 0 / sin definir no se toca nada. */
#include <GL/gl.h>
#include <GL/glext.h>
#include <GL/wglext.h>
#include "raster_backend.h"

#ifndef GL_UNPACK_ROW_LENGTH
#define GL_UNPACK_ROW_LENGTH 0x0CF2
#endif
#ifndef GL_TEXTURE_MAX_ANISOTROPY
#define GL_TEXTURE_MAX_ANISOTROPY 0x84FE          /* core 4.6 / EXT_texture_filter_anisotropic: mismo valor */
#endif
#ifndef GL_MAX_TEXTURE_MAX_ANISOTROPY
#define GL_MAX_TEXTURE_MAX_ANISOTROPY 0x84FF
#endif

/* T1-ANISO-INICIO */
/* ------------------------------------------------------------------ filtrado anisotropico (T1, 9 oct 2026)
   n = 1 (apagado, comportamiento de siempre byte a byte), 2, 4, 8, 16. Lo leen los DOS backends (el D3D12 lo ve: se
   incluye en la misma unidad de compilacion). SM3DL_ANISO=<n> fuerza (gana sobre raster_aniso_fijar). Se aplica SOLO a las
   texturas del juego con muestreador PICA (RbMuestreador) con min Y mag lineales y mip != "vecino" (D3D12 no tiene
   anisotropico con mip punto: ANISOTROPIC fuerza mip lineal; por paridad GL tampoco lo aplica ahi). No se aplica a las
   LUTs (tex_enlazar con m=NULL), a la unidad de giro ni a las capas de interfaz (no pasan por parametros_textura). */
static int g_aniso_n = 1;
static int g_aniso_env = -2;                       /* -2 sin leer, 0 sin variable */

static int aniso_normalizar(int n)                 /* -> 1,2,4,8,16 (potencia de 2 por debajo) */
{
    if (n >= 16) return 16;
    if (n >= 8) return 8;
    if (n >= 4) return 4;
    if (n >= 2) return 2;
    return 1;
}

void raster_aniso_fijar(int n) { g_aniso_n = aniso_normalizar(n); }

int raster_aniso(void)
{
    if (g_aniso_env == -2) {
        const char *s = getenv("SM3DL_ANISO");
        g_aniso_env = (s && *s) ? aniso_normalizar(atoi(s)) : 0;
        if (g_aniso_env) logr("SM3DL_ANISO=%d: anisotropico forzado", g_aniso_env);
    }
    return g_aniso_env ? g_aniso_env : g_aniso_n;
}

/* el nivel EFECTIVO para un muestreador PICA (1 = no se aplica); sin contexto GL (lo usa tambien la prueba) */
static int aniso_para_muestreador(const RbMuestreador *m)
{
    return (m->min_lineal && m->mag_lineal && m->mip != 1) ? raster_aniso() : 1;
}
/* T1-ANISO-FIN */

/* ------------------------------------------------------------------ funciones GL > 1.1 */
#define FUNCIONES_GL(X) \
    X(PFNGLCREATESHADERPROC, CreateShader) X(PFNGLSHADERSOURCEPROC, ShaderSource) \
    X(PFNGLCOMPILESHADERPROC, CompileShader) X(PFNGLGETSHADERIVPROC, GetShaderiv) \
    X(PFNGLGETSHADERINFOLOGPROC, GetShaderInfoLog) X(PFNGLDELETESHADERPROC, DeleteShader) \
    X(PFNGLCREATEPROGRAMPROC, CreateProgram) X(PFNGLATTACHSHADERPROC, AttachShader) \
    X(PFNGLLINKPROGRAMPROC, LinkProgram) X(PFNGLGETPROGRAMIVPROC, GetProgramiv) \
    X(PFNGLGETPROGRAMINFOLOGPROC, GetProgramInfoLog) X(PFNGLUSEPROGRAMPROC, UseProgram) \
    X(PFNGLGETUNIFORMLOCATIONPROC, GetUniformLocation) X(PFNGLUNIFORM4FVPROC, Uniform4fv) \
    X(PFNGLUNIFORM4IVPROC, Uniform4iv) X(PFNGLUNIFORM1IVPROC, Uniform1iv) X(PFNGLUNIFORM1IPROC, Uniform1i) \
    X(PFNGLUNIFORM1FPROC, Uniform1f) X(PFNGLUNIFORM4IPROC, Uniform4i) X(PFNGLUNIFORM1UIPROC, Uniform1ui) \
    X(PFNGLUNIFORM1UIVPROC, Uniform1uiv) X(PFNGLUNIFORM4UIVPROC, Uniform4uiv) X(PFNGLUNIFORM2FVPROC, Uniform2fv) \
    X(PFNGLUNIFORM3FPROC, Uniform3f) X(PFNGLUNIFORM4FPROC, Uniform4f) \
    X(PFNGLGENBUFFERSPROC, GenBuffers) X(PFNGLDELETEBUFFERSPROC, DeleteBuffers) X(PFNGLBINDBUFFERPROC, BindBuffer) \
    X(PFNGLBUFFERDATAPROC, BufferData) X(PFNGLGENVERTEXARRAYSPROC, GenVertexArrays) \
    X(PFNGLBINDVERTEXARRAYPROC, BindVertexArray) X(PFNGLENABLEVERTEXATTRIBARRAYPROC, EnableVertexAttribArray) \
    X(PFNGLVERTEXATTRIBPOINTERPROC, VertexAttribPointer) X(PFNGLGENFRAMEBUFFERSPROC, GenFramebuffers) \
    X(PFNGLBINDFRAMEBUFFERPROC, BindFramebuffer) X(PFNGLFRAMEBUFFERTEXTURE2DPROC, FramebufferTexture2D) \
    X(PFNGLFRAMEBUFFERRENDERBUFFERPROC, FramebufferRenderbuffer) \
    X(PFNGLCHECKFRAMEBUFFERSTATUSPROC, CheckFramebufferStatus) X(PFNGLGENRENDERBUFFERSPROC, GenRenderbuffers) \
    X(PFNGLBINDRENDERBUFFERPROC, BindRenderbuffer) X(PFNGLRENDERBUFFERSTORAGEPROC, RenderbufferStorage) \
    X(PFNGLDELETEFRAMEBUFFERSPROC, DeleteFramebuffers) X(PFNGLDELETERENDERBUFFERSPROC, DeleteRenderbuffers) \
    X(PFNGLBLENDEQUATIONSEPARATEPROC, BlendEquationSeparate) X(PFNGLBLENDFUNCSEPARATEPROC, BlendFuncSeparate) \
    X(PFNGLBLENDCOLORPROC, BlendColor) X(PFNGLACTIVETEXTUREPROC, ActiveTexture) \
    X(PFNGLFENCESYNCPROC, FenceSync) X(PFNGLCLIENTWAITSYNCPROC, ClientWaitSync) X(PFNGLDELETESYNCPROC, DeleteSync) X(PFNGLGETSYNCIVPROC, GetSynciv) X(PFNGLGETSTRINGIPROC, GetStringi) \
    X(PFNGLGETPROGRAMBINARYPROC, GetProgramBinary) X(PFNGLPROGRAMBINARYPROC, ProgramBinary) \
    X(PFNGLPROGRAMPARAMETERIPROC, ProgramParameteri) \
    X(PFNGLMAPBUFFERRANGEPROC, MapBufferRange) X(PFNGLUNMAPBUFFERPROC, UnmapBuffer) \
    X(PFNGLSTENCILFUNCSEPARATEPROC, StencilFuncSeparate) X(PFNGLSTENCILOPSEPARATEPROC, StencilOpSeparate)     X(PFNGLDELETEPROGRAMPROC, DeleteProgram) \
    X(PFNGLDISABLEVERTEXATTRIBARRAYPROC, DisableVertexAttribArray) X(PFNGLVERTEXATTRIB4FPROC, VertexAttrib4f) \
    X(PFNGLVERTEXATTRIBFORMATPROC, VertexAttribFormat) X(PFNGLVERTEXATTRIBBINDINGPROC, VertexAttribBinding) \
    X(PFNGLBINDVERTEXBUFFERPROC, BindVertexBuffer) X(PFNGLBLITFRAMEBUFFERPROC, BlitFramebuffer) \
    X(PFNGLGENQUERIESPROC, GenQueries) X(PFNGLQUERYCOUNTERPROC, QueryCounter) \
    X(PFNGLBEGINQUERYPROC, BeginQuery) X(PFNGLENDQUERYPROC, EndQuery) X(PFNGLBUFFERSTORAGEPROC, BufferStorage) \
    X(PFNGLGETQUERYOBJECTIVPROC, GetQueryObjectiv) X(PFNGLGETQUERYOBJECTUI64VPROC, GetQueryObjectui64v)
#define DECLARAR(t, n) t n;
static struct { FUNCIONES_GL(DECLARAR) PFNGLCLIPCONTROLPROC ClipControl; } gl;

static int g_estado;          /* 0 sin iniciar, 1 listo, -1 fallo (no se reintenta) */
static HWND g_ventana;
static HDC g_dc;
static HGLRC g_ctx;
static GLuint g_vao, g_vbo, g_ebo;
static GLuint g_vao_crudo, g_vbo_crudo;   /* camino nativo de vertices: VAO del dibujo actual */
static GLuint g_vao_actual;               /* el VAO que usa dibujar() */
static int g_sab_rb;                         /* SM3DL_BACKEND_SABOTAJE */

struct RbTex { GLuint id; };
struct RbRT { GLuint fbo, tex, rbo; int w, h; };   /* rbo: renderbuffer D24S8 (0 si es solo color) */
struct RbEtapa { GLuint id; };
struct RbLectura { GLuint pbo; GLsync fence; uint8_t *map; size_t cap; int mapeado; };

/* uniforms del programa: (campo, nombre GLSL) */
#define UNIFORMES(X) \
    X(c, "pica_c") X(i, "pica_i") X(b, "pica_b") X(omap, "omap") X(clip_on, "clip_on") X(clip_coef, "clip_coef") \
    X(tev, "tev") X(tev_const, "tev_const") X(tev_buf, "tev_buf") X(tev_upd, "tev_upd") \
    X(tex0, "tex0") X(tex1, "tex1") X(tex2, "tex2") X(tex_modo, "tex_modo") X(tex0_proy, "tex0_proy") \
    X(alfa_func, "alfa_func") X(alfa_ref, "alfa_ref") X(z_escala, "z_escala") X(z_offset, "z_offset") \
    X(wbuffer, "wbuffer") X(tijera_modo, "tijera_modo") X(tijera, "tijera") \
    X(niebla, "niebla") X(niebla_flip, "niebla_flip") X(niebla_color, "niebla_color") X(niebla_lut, "niebla_lut") \
    X(luz_on, "luz_on") X(luz_n, "luz_n") X(luz_amb, "luz_amb") X(luz_c0, "luz_c0") X(luz_c1, "luz_c1") \
    X(luz_abs, "luz_abs") X(luz_ent, "luz_ent") X(luz_esc, "luz_esc") X(luz_mues, "luz_mues") \
    X(luz_luts, "luz_luts") X(luz_fila, "luz_fila")
#define CAMPO_U(c, n) GLint c;
static const char *const LUZ_CAMPOS[10] = { "esp0", "esp1", "dif", "amb", "pos", "spot", "da_escala", "da_sesgo",
                                            "num", "cfg" };
struct RbProg {
    GLuint prog;
    struct { UNIFORMES(CAMPO_U) } u;
    GLint u_luz[8][10];
};

/* ------------------------------------------------------------------ contexto */
static int gl_iniciar(void)
{
    if (g_estado) return g_estado > 0;
    g_estado = -1;
    {
        const char *s = getenv("SM3DL_BACKEND_SABOTAJE");
        g_sab_rb = s ? atoi(s) : 0;
        if (g_sab_rb) logr("SM3DL_BACKEND_SABOTAJE=%d: backend GL SABOTEADO a proposito (prueba de la comparacion por pixel)", g_sab_rb);
    }
    HINSTANCE ins = GetModuleHandleA(NULL);
    WNDCLASSA wc;
    memset(&wc, 0, sizeof wc);
    wc.style = CS_OWNDC;
    wc.lpfnWndProc = DefWindowProcA;
    wc.hInstance = ins;
    wc.lpszClassName = "sm3dl_gl";
    RegisterClassA(&wc);
    g_ventana = CreateWindowA("sm3dl_gl", "SM3DL", WS_OVERLAPPEDWINDOW, 0, 0, 64, 64, NULL, NULL, ins, NULL);
    if (!g_ventana) { logr("CreateWindow fallo (%lu)", GetLastError()); return 0; }
    g_dc = GetDC(g_ventana);
    PIXELFORMATDESCRIPTOR pfd;
    memset(&pfd, 0, sizeof pfd);
    pfd.nSize = sizeof pfd;
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cDepthBits = 24;
    pfd.cStencilBits = 8;
    int pf = ChoosePixelFormat(g_dc, &pfd);
    if (!pf || !SetPixelFormat(g_dc, pf, &pfd)) { logr("SetPixelFormat fallo"); return 0; }
    HGLRC tmp = wglCreateContext(g_dc);
    if (!tmp || !wglMakeCurrent(g_dc, tmp)) { logr("wglCreateContext fallo"); return 0; }
    PFNWGLCREATECONTEXTATTRIBSARBPROC cca =
        (PFNWGLCREATECONTEXTATTRIBSARBPROC)(void *)wglGetProcAddress("wglCreateContextAttribsARB");
    int at[] = { WGL_CONTEXT_MAJOR_VERSION_ARB, 4, WGL_CONTEXT_MINOR_VERSION_ARB, 5,
                 WGL_CONTEXT_PROFILE_MASK_ARB, WGL_CONTEXT_CORE_PROFILE_BIT_ARB, 0 };
    g_ctx = cca ? cca(g_dc, NULL, at) : NULL;
    if (!g_ctx) { logr("sin contexto GL 4.5 core"); wglMakeCurrent(NULL, NULL); wglDeleteContext(tmp); return 0; }
    wglMakeCurrent(g_dc, g_ctx);
    wglDeleteContext(tmp);
    int faltan = 0;
#define CARGAR(t, n) if (!(gl.n = (t)(void *)wglGetProcAddress("gl" #n))) { logr("falta gl" #n); faltan++; }
    FUNCIONES_GL(CARGAR)
    CARGAR(PFNGLCLIPCONTROLPROC, ClipControl)
#undef CARGAR
    if (faltan) return 0;
    logr("GL %s | %s", (const char *)glGetString(GL_VERSION), (const char *)glGetString(GL_RENDERER));
    {
        GLint next = 0;
        glGetIntegerv(GL_NUM_EXTENSIONS, &next);
        for (GLint k = 0; k < next; k++) {
            const char *x = (const char *)gl.GetStringi(GL_EXTENSIONS, (GLuint)k);
            if (x && (strstr(x, "parallel") || strstr(x, "program_binary") || strstr(x, "get_program")))
                logr("extension: %s", x);
        }
        logr("%d extensiones", next);
    }
    /* el envoltorio del .vert da gl_Position = (x, y, -z, w): la z de clip de la PICA [-w, 0] queda en [0, w] */
    gl.ClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE);
    gl.GenVertexArrays(1, &g_vao);
    gl.BindVertexArray(g_vao);
    gl.GenBuffers(1, &g_vbo);
    gl.GenBuffers(1, &g_ebo);
    gl.BindBuffer(GL_ARRAY_BUFFER, g_vbo);
    for (int k = 0; k < 16; k++) {   /* los 16 registros de entrada v0..v15 intercalados, vec4 cada uno */
        gl.EnableVertexAttribArray(k);
        gl.VertexAttribPointer(k, 4, GL_FLOAT, GL_FALSE, 16 * 16, (const void *)(uintptr_t)(16 * k));
    }
    gl.GenBuffers(1, &g_vbo_crudo);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    g_vao_actual = g_vao;
    g_estado = 1;
    return 1;
}

static int gl_listo(void) { return g_estado > 0; }

/* el contexto es del hilo que lo creo; todas las fibras del juego corren en ese hilo, pero se comprueba */
static int gl_contexto_actual(void)
{
    if (g_estado <= 0) return 0;
    if (wglGetCurrentContext() != g_ctx && !wglMakeCurrent(g_dc, g_ctx)) {
        logr("wglMakeCurrent fallo (%lu): otro hilo del SO?", GetLastError());
        return 0;
    }
    return 1;
}

static int gl_es_actual(void) { return g_estado > 0 && wglGetCurrentContext() == g_ctx; }

/* deja el contexto GL del raster actual sobre 'dc' (le pone el mismo pixel format si no tiene; una ventana solo
   admite SetPixelFormat UNA vez). Devuelve 1 si quedo. Despues la ventana puede dibujar en el framebuffer 0 y hacer
   SwapBuffers(dc). El raster sigue dibujando en sus FBO sin importar en que DC quede el contexto. */
static int gl_hacer_actual_dc(void *hdc)
{
    HDC dc = (HDC)hdc;
    if (g_estado <= 0 || !dc) return 0;
    if (GetPixelFormat(dc) == 0) {
        PIXELFORMATDESCRIPTOR pfd;
        int pf = GetPixelFormat(g_dc);
        if (!pf || !DescribePixelFormat(g_dc, pf, sizeof pfd, &pfd) || !SetPixelFormat(dc, pf, &pfd)) {
            logr("raster_gl_hacer_actual: SetPixelFormat fallo (%lu)", GetLastError());
            return 0;
        }
    }
    if (!wglMakeCurrent(dc, g_ctx)) { logr("raster_gl_hacer_actual: wglMakeCurrent fallo (%lu)", GetLastError()); return 0; }
    return 1;
}

static unsigned gl_ultimo_error(void) { return (unsigned)glGetError(); }

/* ------------------------------------------------------------------ shaders */
static GLuint compilar(GLenum tipo, const char *src, const char *nombre)
{
    double t0 = reloj();
    GLuint s = gl.CreateShader(tipo);
    gl.ShaderSource(s, 1, &src, NULL);
    gl.CompileShader(s);
    GLint ok = 0;
    gl.GetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (reloj() - t0 > 0.05)
        logr("compilar %s (%s, %u bytes): %.3f s", nombre, tipo == GL_FRAGMENT_SHADER ? "frag" : tipo == GL_VERTEX_SHADER ? "vert" : "geom",
             (unsigned)strlen(src), reloj() - t0);
    if (!ok) {
        char log[4096];
        gl.GetShaderInfoLog(s, sizeof log, NULL, log);
        logr("%s no compila:\n%s", nombre, log);
        gl.DeleteShader(s);
        return 0;
    }
    return s;
}

static RbEtapa *gl_etapa_compilar(int tipo, const char *src, const char *nombre)
{
    GLenum t = tipo == RB_ETAPA_VS ? GL_VERTEX_SHADER : tipo == RB_ETAPA_FS ? GL_FRAGMENT_SHADER : GL_GEOMETRY_SHADER;
    GLuint s = compilar(t, src, nombre);
    if (!s) return NULL;
    RbEtapa *e = malloc(sizeof *e);
    if (!e) { gl.DeleteShader(s); return NULL; }
    e->id = s;
    return e;
}

static void gl_etapa_destruir(RbEtapa *e)
{
    if (!e) return;
    gl.DeleteShader(e->id);
    free(e);
}

/* ------------------------------------------------------------------ cache de programas enlazados en disco
   La cache de shaders del driver de Intel es POR NOMBRE DE EXE (sm3dl_vel.exe caliente, sm3dl.exe recompilaba todo:
   81 s). Con GL_ARB_get_program_binary cada programa enlazado se guarda en extraido\shaders\cache_gl\ con nombre =
   hash(texto del vert) + hash(texto del frag) + GS + hash(version del driver), y se carga en milisegundos en
   cualquier exe. Si el driver lo rechaza (otra version), se compila y se re-guarda. SM3DL_SIN_CACHE_GL=1 la apaga. */
#define DIR_CACHE_GL "extraido\\shaders\\cache_gl\\"
static int g_bin_activo = -1;
static uint32_t g_bin_driver;

static void binario_ruta(char *ruta, size_t tam, uint32_t hv, uint32_t hf, int gs)
{
    snprintf(ruta, tam, DIR_CACHE_GL "%08X_%08X_%d_%08X.bin", hv, hf, gs, g_bin_driver);
}

static int binario_iniciar(void)
{
    if (g_bin_activo < 0) {
        const char *s = getenv("SM3DL_SIN_CACHE_GL");
        g_bin_activo = !(s && *s && *s != '0');
        const char *v = (const char *)glGetString(GL_VERSION), *r = (const char *)glGetString(GL_RENDERER);
        g_bin_driver = fnv_texto(v ? v : "") ^ (fnv_texto(r ? r : "") * 31u);
        CreateDirectoryA("extraido\\shaders\\cache_gl", NULL);
        logr("cache de programas en disco %s (driver %08X)", g_bin_activo ? "activa" : "apagada", g_bin_driver);
    }
    return g_bin_activo;
}

/* ubica los uniforms y fija las unidades de textura (0-2 texturas PICA, 3 LUTs de luz) */
static void prog_ubicar(RbProg *p)
{
#define UBICAR(c, n) p->u.c = gl.GetUniformLocation(p->prog, n);
    UNIFORMES(UBICAR)
#undef UBICAR
    for (int k = 0; k < 8; k++)
        for (int j = 0; j < 10; j++) {
            char n[32];
            snprintf(n, sizeof n, "luz[%d].%s", k, LUZ_CAMPOS[j]);
            p->u_luz[k][j] = gl.GetUniformLocation(p->prog, n);
        }
    gl.UseProgram(p->prog);   /* unidades de textura fijas */
    gl.Uniform1i(p->u.tex0, 0);
    gl.Uniform1i(p->u.tex1, 1);
    gl.Uniform1i(p->u.tex2, 2);
    gl.Uniform1i(p->u.luz_luts, 3);
}

static RbProg *gl_prog_cargar_cache(uint32_t hv, uint32_t hf, int gs, int *rechazado)
{
    if (rechazado) *rechazado = 0;
    if (!binario_iniciar()) return NULL;
    char ruta[192];
    binario_ruta(ruta, sizeof ruta, hv, hf, gs);
    FILE *f = fopen(ruta, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *b = n > 4 ? malloc((size_t)n) : NULL;
    GLuint prog = 0;
    if (b && fread(b, 1, (size_t)n, f) == (size_t)n) {
        GLenum formato;
        memcpy(&formato, b, 4);
        prog = gl.CreateProgram();
        gl.ProgramBinary(prog, formato, b + 4, (GLsizei)(n - 4));
        GLint ok = 0;
        gl.GetProgramiv(prog, GL_LINK_STATUS, &ok);
        if (!ok) { gl.DeleteProgram(prog); prog = 0; if (rechazado) *rechazado = 1; }
    }
    free(b);
    fclose(f);
    if (!prog) return NULL;
    RbProg *p = calloc(1, sizeof *p);
    if (!p) { gl.DeleteProgram(prog); return NULL; }
    p->prog = prog;
    prog_ubicar(p);
    return p;
}

static RbProg *gl_prog_enlazar(RbEtapa *vs, RbEtapa *fs, RbEtapa *gs, const char *nombre)
{
    GLuint prog = gl.CreateProgram();
    gl.ProgramParameteri(prog, GL_PROGRAM_BINARY_RETRIEVABLE_HINT, GL_TRUE);
    gl.AttachShader(prog, vs->id);
    gl.AttachShader(prog, fs->id);
    if (gs) gl.AttachShader(prog, gs->id);
    gl.LinkProgram(prog);
    GLint ok = 0;
    gl.GetProgramiv(prog, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[4096];
        gl.GetProgramInfoLog(prog, sizeof log, NULL, log);
        logr("%s no enlaza:\n%s", nombre, log);
        gl.DeleteProgram(prog);
        return NULL;
    }
    RbProg *p = calloc(1, sizeof *p);
    if (!p) { gl.DeleteProgram(prog); return NULL; }
    p->prog = prog;
    prog_ubicar(p);
    return p;
}

static void gl_prog_guardar_cache(RbProg *p, uint32_t hv, uint32_t hf, int gs)
{
    if (!binario_iniciar()) return;
    GLint n = 0;
    gl.GetProgramiv(p->prog, GL_PROGRAM_BINARY_LENGTH, &n);
    if (n <= 0) return;
    uint8_t *b = malloc((size_t)n + 4);
    if (!b) return;
    GLenum formato = 0;
    GLsizei hecho = 0;
    gl.GetProgramBinary(p->prog, n, &hecho, &formato, b + 4);
    memcpy(b, &formato, 4);
    char ruta[192], tmp[200];
    binario_ruta(ruta, sizeof ruta, hv, hf, gs);
    snprintf(tmp, sizeof tmp, "%s.tmp", ruta);
    FILE *f = fopen(tmp, "wb");
    if (f) {
        int bien = fwrite(b, 1, (size_t)hecho + 4, f) == (size_t)hecho + 4;
        bien &= fclose(f) == 0;
        if (bien) MoveFileExA(tmp, ruta, MOVEFILE_REPLACE_EXISTING);
        else remove(tmp);
    }
    free(b);
}

static void gl_prog_destruir(RbProg *p)
{
    if (!p) return;
    gl.DeleteProgram(p->prog);
    free(p);
}

static void gl_prog_usar(RbProg *p) { gl.UseProgram(p->prog); }

/* ------------------------------------------------------------------ constantes: los glUniform* de siempre, por bloque */
static void gl_constantes(RbProg *p, int bloque, const void *datos)
{
    switch (bloque) {
    case RB_BLOQUE_V: {
        const RbCbVertice *c = datos;
        gl.Uniform4fv(p->u.c, 96, &c->c[0][0]);
        gl.Uniform4iv(p->u.i, 4, (const GLint *)&c->i[0][0]);
        gl.Uniform1iv(p->u.b, 16, (const GLint *)c->b);
        gl.Uniform1iv(p->u.omap, 24, (const GLint *)c->omap);
        gl.Uniform1i(p->u.clip_on, c->clip_on);
        gl.Uniform4f(p->u.clip_coef, c->clip_coef[0], c->clip_coef[1], c->clip_coef[2], c->clip_coef[3]);
        break;
    }
    case RB_BLOQUE_F: {
        const RbCbFragmento *c = datos;
        gl.Uniform4uiv(p->u.tev, 6, (const GLuint *)&c->tev[0][0]);
        gl.Uniform1uiv(p->u.tev_const, 6, (const GLuint *)c->tev_const);
        gl.Uniform1ui(p->u.tev_buf, c->tev_buf);
        gl.Uniform1ui(p->u.tev_upd, c->tev_upd);
        gl.Uniform4i(p->u.tex_modo, c->tex_modo[0], c->tex_modo[1], c->tex_modo[2], c->tex_modo[3]);
        gl.Uniform1i(p->u.tex0_proy, c->tex0_proy);
        gl.Uniform1i(p->u.alfa_func, c->alfa_func);
        gl.Uniform1i(p->u.alfa_ref, c->alfa_ref);
        gl.Uniform1f(p->u.z_escala, c->z_escala);
        gl.Uniform1f(p->u.z_offset, c->z_offset);
        gl.Uniform1i(p->u.wbuffer, c->wbuffer);
        gl.Uniform1i(p->u.tijera_modo, c->tijera_modo);
        gl.Uniform4i(p->u.tijera, c->tijera[0], c->tijera[1], c->tijera[2], c->tijera[3]);
        gl.Uniform1i(p->u.niebla, c->niebla);
        if (c->niebla) {
            gl.Uniform1i(p->u.niebla_flip, c->niebla_flip);
            gl.Uniform1ui(p->u.niebla_color, c->niebla_color);
        }
        break;
    }
    case RB_BLOQUE_NIEBLA: {
        const RbCbNiebla *c = datos;
        gl.Uniform2fv(p->u.niebla_lut, 128, &c->lut[0][0]);
        break;
    }
    case RB_BLOQUE_LUZ: {
        const RbCbLuz *c = datos;
        gl.Uniform1i(p->u.luz_on, c->luz_on);
        if (!c->luz_on) break;
        gl.Uniform1iv(p->u.luz_fila, 24, (const GLint *)c->luz_fila);
        int n = c->luz_n;
        gl.Uniform1i(p->u.luz_n, n);
        gl.Uniform3f(p->u.luz_amb, c->luz_amb[0], c->luz_amb[1], c->luz_amb[2]);
        gl.Uniform1ui(p->u.luz_c0, c->luz_c0);
        gl.Uniform1ui(p->u.luz_c1, c->luz_c1);
        gl.Uniform1ui(p->u.luz_abs, c->luz_abs);
        gl.Uniform1ui(p->u.luz_ent, c->luz_ent);
        gl.Uniform1ui(p->u.luz_esc, c->luz_esc);
        gl.Uniform1i(p->u.luz_mues, c->luz_mues);
        for (int k = 0; k < n; k++) {
            const RbLuz *L = &c->luz[k];
            gl.Uniform3f(p->u_luz[k][0], L->esp0[0], L->esp0[1], L->esp0[2]);
            gl.Uniform3f(p->u_luz[k][1], L->esp1[0], L->esp1[1], L->esp1[2]);
            gl.Uniform3f(p->u_luz[k][2], L->dif[0], L->dif[1], L->dif[2]);
            gl.Uniform3f(p->u_luz[k][3], L->amb[0], L->amb[1], L->amb[2]);
            gl.Uniform3f(p->u_luz[k][4], L->pos[0], L->pos[1], L->pos[2]);
            gl.Uniform3f(p->u_luz[k][5], L->spot[0], L->spot[1], L->spot[2]);
            gl.Uniform1f(p->u_luz[k][6], L->da_escala);
            gl.Uniform1f(p->u_luz[k][7], L->da_sesgo);
            gl.Uniform1i(p->u_luz[k][8], L->num);
            gl.Uniform1i(p->u_luz[k][9], L->cfg);
        }
        break;
    }
    }
}

/* ------------------------------------------------------------------ texturas */
static RbTex *gl_tex_crear(int w, int h, int fmt, int banderas)
{
    RbTex *t = calloc(1, sizeof *t);
    if (!t) return NULL;
    glGenTextures(1, &t->id);
    glBindTexture(GL_TEXTURE_2D, t->id);
    if (banderas & RB_TEX_NEAREST) {
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    }
    if (banderas & RB_TEX_LINEAR_CLAMP) {
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    }
    if (fmt == RB_FMT_RG32F) glTexImage2D(GL_TEXTURE_2D, 0, GL_RG32F, w, h, 0, GL_RG, GL_FLOAT, NULL);
    else if (fmt == RB_FMT_BGRA8) glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_BGRA, GL_UNSIGNED_BYTE, NULL);
    else glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    return t;
}

static void gl_tex_destruir(RbTex *t)
{
    if (!t) return;
    glDeleteTextures(1, &t->id);
    free(t);
}

static void gl_tex_subir(RbTex *t, int x, int y, int w, int h, int fmt, int fila_px, const void *datos)
{
    glBindTexture(GL_TEXTURE_2D, t->id);
    if (fmt == RB_FMT_RG32F) {
        glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, GL_RG, GL_FLOAT, datos);
    } else if (fmt == RB_FMT_BGRA8) {
        glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
        if (fila_px) glPixelStorei(GL_UNPACK_ROW_LENGTH, fila_px);
        glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, GL_BGRA, GL_UNSIGNED_BYTE, datos);
        if (fila_px) glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
    } else {
        glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, GL_RGBA, GL_UNSIGNED_BYTE, datos);
    }
}

static RbTex *gl_tex_cargar_mips(RbTex *t, int w, int h, int niveles, const uint8_t *const *rgba)
{
    if (!t) {
        t = calloc(1, sizeof *t);
        if (!t) return NULL;
    }
    if (!t->id) glGenTextures(1, &t->id);
    glBindTexture(GL_TEXTURE_2D, t->id);
    for (int k = 0; k < niveles; k++)
        glTexImage2D(GL_TEXTURE_2D, k, GL_RGBA8, w >> k, h >> k, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba[k]);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_BASE_LEVEL, 0);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, niveles > 0 ? niveles - 1 : 0);
    return t;
}

static void parametros_textura(const RbMuestreador *x)
{
    /* PICA: 0 ClampToEdge 1 ClampToBorder 2 Repeat 3 MirroredRepeat 4 ClampToEdge2 5 ClampToBorder2 6-7 Repeat */
    static const GLint envolver[8] = { GL_CLAMP_TO_EDGE, GL_CLAMP_TO_BORDER, GL_REPEAT, GL_MIRRORED_REPEAT,
                                       GL_CLAMP_TO_EDGE, GL_CLAMP_TO_BORDER, GL_REPEAT, GL_REPEAT };
    GLint min = x->min_lineal ? GL_LINEAR : GL_NEAREST;
    if (x->mip)
        min = x->min_lineal ? (x->mip == 2 ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR_MIPMAP_NEAREST)
                            : (x->mip == 2 ? GL_NEAREST_MIPMAP_LINEAR : GL_NEAREST_MIPMAP_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, x->mag_lineal ? GL_LINEAR : GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, min);
    {   /* anisotropico (T1): siempre se fija (n o 1.0) porque el parametro vive en la textura y n puede cambiar en caliente */
        static float maximo = 0.0f;
        if (maximo == 0.0f) {
            glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY, &maximo);
            if (glGetError() != GL_NO_ERROR || maximo < 1.0f) maximo = 1.0f;
            logr("anisotropico GL: maximo del driver %.0fx", maximo);
        }
        float n = (float)aniso_para_muestreador(x);
        if (n > maximo) n = maximo;
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY, n);
    }
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, envolver[x->wrap_s & 7]);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, envolver[x->wrap_t & 7]);
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_LOD, (float)x->lod_min);
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_LOD, (float)x->lod_max);
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_LOD_BIAS, x->lod_bias / 256.0f);
    float borde[4] = { (x->color_borde & 0xFF) / 255.0f, ((x->color_borde >> 8) & 0xFF) / 255.0f,
                       ((x->color_borde >> 16) & 0xFF) / 255.0f, (x->color_borde >> 24) / 255.0f };
    glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, borde);
}

static void gl_tex_enlazar(int unidad, RbTex *t, const RbMuestreador *m)
{
    gl.ActiveTexture(GL_TEXTURE0 + unidad);
    if (!t) return;
    glBindTexture(GL_TEXTURE_2D, t->id);
    if (m) parametros_textura(m);
}

/* ------------------------------------------------------------------ superficies */
static RbRT *gl_rt_crear(int w, int h, int con_ds, int banderas)
{
    RbRT *r = calloc(1, sizeof *r);
    if (!r) return NULL;
    r->w = w;
    r->h = h;
    glGenTextures(1, &r->tex);
    glBindTexture(GL_TEXTURE_2D, r->tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    if (banderas & RB_RT_NEAREST) {
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    }
    if (con_ds) {
        gl.GenRenderbuffers(1, &r->rbo);
        gl.BindRenderbuffer(GL_RENDERBUFFER, r->rbo);
        gl.RenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, w, h);
    }
    gl.GenFramebuffers(1, &r->fbo);
    gl.BindFramebuffer(GL_FRAMEBUFFER, r->fbo);
    gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, r->tex, 0);
    if (con_ds) {
        gl.FramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, r->rbo);
        GLenum st = gl.CheckFramebufferStatus(GL_FRAMEBUFFER);
        if (st != GL_FRAMEBUFFER_COMPLETE) logr("FBO incompleto 0x%X", st);
    }
    return r;
}

static void gl_rt_destruir(RbRT *r)
{
    if (!r) return;
    gl.DeleteFramebuffers(1, &r->fbo);
    gl.DeleteRenderbuffers(1, &r->rbo);
    glDeleteTextures(1, &r->tex);
    free(r);
}

static void gl_rt_subir(RbRT *r, int x, int y, int w, int h, const void *rgba)
{
    glBindTexture(GL_TEXTURE_2D, r->tex);
    glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
}

static void gl_rt_limpiar(RbRT *r, int mascara, const float color[4], double z, int stencil)
{
    gl.BindFramebuffer(GL_FRAMEBUFFER, r->fbo);
    glDisable(GL_SCISSOR_TEST);
    GLbitfield m = 0;
    if (mascara & RB_LIMPIAR_COLOR) {
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glClearColor(color[0], color[1], color[2], color[3]);
        m |= GL_COLOR_BUFFER_BIT;
    }
    if (mascara & RB_LIMPIAR_DS) {
        glDepthMask(GL_TRUE);
        glStencilMask(0xFF);
        glClearDepth(z);
        glClearStencil(stencil);
        m |= GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT;
    }
    glClear(m);
}

/* FBO de trabajo a tamano nativo (para reducir un RT grande antes de leerlo) */
static RbRT *fbo_nativo(int w, int h)
{
    static RbRT c[6];
    for (int k = 0; k < 6; k++)
        if (c[k].fbo && c[k].w == w && c[k].h == h) return &c[k];
    int k = 0;
    while (k < 5 && c[k].fbo) k++;
    if (c[k].fbo) { gl.DeleteFramebuffers(1, &c[k].fbo); glDeleteTextures(1, &c[k].tex); }
    c[k].w = w; c[k].h = h;
    glGenTextures(1, &c[k].tex);
    glBindTexture(GL_TEXTURE_2D, c[k].tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    gl.GenFramebuffers(1, &c[k].fbo);
    gl.BindFramebuffer(GL_FRAMEBUFFER, c[k].fbo);
    gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, c[k].tex, 0);
    return &c[k];
}

/* resolucion interna: reduce el RT grande (promedio lineal) a su tamano nativo w x h; devuelve la superficie a leer */
static RbRT *gl_rt_reducir(RbRT *t, int w, int h)
{
    RbRT *f = fbo_nativo(w, h);
    gl.BindFramebuffer(GL_READ_FRAMEBUFFER, t->fbo);
    gl.BindFramebuffer(GL_DRAW_FRAMEBUFFER, f->fbo);
    glDisable(GL_SCISSOR_TEST);
    gl.BlitFramebuffer(0, 0, t->w, t->h, 0, 0, w, h, GL_COLOR_BUFFER_BIT, GL_LINEAR);
    gl.BindFramebuffer(GL_FRAMEBUFFER, f->fbo);
    return f;
}

static int gl_rt_leer(RbRT *r, int w, int h, int fmt, void *dst)
{
    gl.BindFramebuffer(GL_FRAMEBUFFER, r->fbo);
    if (fmt == RB_FMT_BGRA8) {
        glPixelStorei(GL_PACK_ALIGNMENT, 4);
        glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, dst);
    } else {
        glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, dst);
    }
    return 1;
}

/* lee el framebuffer 0 (BGRA, fila 0 ABAJO) para verificar lo presentado; antes de mostrar */
static int gl_rt_leer_ventana(int w, int h, void *bgra)
{
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadBuffer(GL_BACK);
    glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, bgra);
    return 1;
}

static void gl_copiar(RbRT *dst, RbRT *src, int sx0, int sy0, int sx1, int sy1, int dx0, int dy0, int dx1, int dy1,
                      int lineal)
{
    if (!dst && (g_sab_rb & 2)) { dx0++; dx1++; }   /* SABOTAJE 2: la base de la ventana se corre 1 px */
    gl.BindFramebuffer(GL_READ_FRAMEBUFFER, src->fbo);
    gl.BindFramebuffer(GL_DRAW_FRAMEBUFFER, dst ? dst->fbo : 0);
    glDisable(GL_SCISSOR_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    gl.BlitFramebuffer(sx0, sy0, sx1, sy1, dx0, dy0, dx1, dy1, GL_COLOR_BUFFER_BIT, lineal ? GL_LINEAR : GL_NEAREST);
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
}

static unsigned gl_rt_id_nativo(RbRT *r) { return r ? r->tex : 0; }

static int gl_rt_volcar_bgra(RbRT *r, int w, int h, void *dst)
{
    (void)w; (void)h;
    glBindTexture(GL_TEXTURE_2D, r->tex);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glGetTexImage(GL_TEXTURE_2D, 0, GL_BGRA, GL_UNSIGNED_BYTE, dst);
    return 1;
}

/* ------------------------------------------------------------------ lecturas de vuelta (PBO + fence) */
static RbLectura *gl_lectura_crear(void) { return calloc(1, sizeof(RbLectura)); }

static void gl_lectura_destruir(RbLectura *l)
{
    if (!l) return;
    if (l->pbo) gl.DeleteBuffers(1, &l->pbo);
    free(l);
}

static int gl_lectura_emitir(RbLectura *p, RbRT *rt, int w, int h, int fmt, int persistente, int *persistente_ok)
{
    size_t bytes = (size_t)w * h * 4;
    int rehecho = 0;
    if (persistente_ok) *persistente_ok = persistente;
    if (persistente && (!p->map || p->cap < bytes)) {   /* storage inmutable: si no alcanza, se rehace */
        if (p->pbo) {
            rehecho = 1;
            if (p->map) { gl.BindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo); gl.UnmapBuffer(GL_PIXEL_PACK_BUFFER); }
            gl.DeleteBuffers(1, &p->pbo);
            p->pbo = 0; p->map = NULL; p->cap = 0;
        }
        const GLbitfield fl = GL_MAP_READ_BIT | GL_MAP_PERSISTENT_BIT | GL_MAP_COHERENT_BIT;
        gl.GenBuffers(1, &p->pbo);
        gl.BindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
        gl.BufferStorage(GL_PIXEL_PACK_BUFFER, (GLsizeiptr)bytes, NULL, fl);
        p->map = gl.MapBufferRange(GL_PIXEL_PACK_BUFFER, 0, (GLsizeiptr)bytes, fl);
        p->cap = bytes;
        if (!p->map) {
            logr("pantalla en alta: mapeo persistente fallo (0x%X): vuelvo a map + memcpy", glGetError());
            if (persistente_ok) *persistente_ok = 0;
            gl.DeleteBuffers(1, &p->pbo);
            p->pbo = 0; p->cap = 0;
        }
    }
    if (!p->pbo) gl.GenBuffers(1, &p->pbo);
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, p->pbo);
    if (!p->map) gl.BufferData(GL_PIXEL_PACK_BUFFER, (GLsizeiptr)bytes, NULL, GL_STREAM_READ);
    gl.BindFramebuffer(GL_FRAMEBUFFER, rt->fbo);
    if (fmt == RB_FMT_BGRA8) {
        glPixelStorei(GL_PACK_ALIGNMENT, 4);
        glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, (void *)0);
    } else {
        glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, (void *)0);
    }
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    p->fence = gl.FenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    glFlush();
    return rehecho ? 2 : 1;
}

static int gl_lectura_lista(RbLectura *l)
{
    GLint st = 0;
    gl.GetSynciv(l->fence, GL_SYNC_STATUS, 1, NULL, &st);
    return st == GL_SIGNALED;
}

static int gl_lectura_esperar(RbLectura *l, uint64_t ns)
{
    GLenum r = gl.ClientWaitSync(l->fence, GL_SYNC_FLUSH_COMMANDS_BIT, ns);
    return r != GL_TIMEOUT_EXPIRED;
}

static void gl_lectura_cerrar(RbLectura *l)
{
    gl.DeleteSync(l->fence);
    l->fence = 0;
}

static const uint8_t *gl_lectura_mapa_persistente(RbLectura *l) { return l->map; }

static const uint8_t *gl_lectura_mapear(RbLectura *l, size_t bytes)
{
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, l->pbo);
    const uint8_t *m = gl.MapBufferRange(GL_PIXEL_PACK_BUFFER, 0, (GLsizeiptr)bytes, GL_MAP_READ_BIT);
    l->mapeado = m != NULL;
    return m;
}

static void gl_lectura_desmapear(RbLectura *l)
{
    if (l->mapeado) { gl.UnmapBuffer(GL_PIXEL_PACK_BUFFER); l->mapeado = 0; }
    gl.BindBuffer(GL_PIXEL_PACK_BUFFER, 0);
}

/* ------------------------------------------------------------------ estado de fragmentos */
static const GLenum FUNC_PRUEBA[8] = { GL_NEVER, GL_ALWAYS, GL_EQUAL, GL_NOTEQUAL, GL_LESS, GL_LEQUAL, GL_GREATER,
                                       GL_GEQUAL };
static const GLenum FACTOR[16] = { GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR, GL_DST_COLOR,
                                   GL_ONE_MINUS_DST_COLOR, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_DST_ALPHA,
                                   GL_ONE_MINUS_DST_ALPHA, GL_CONSTANT_COLOR, GL_ONE_MINUS_CONSTANT_COLOR,
                                   GL_CONSTANT_ALPHA, GL_ONE_MINUS_CONSTANT_ALPHA, GL_SRC_ALPHA_SATURATE, GL_ONE };
static const GLenum ECUACION[8] = { GL_FUNC_ADD, GL_FUNC_SUBTRACT, GL_FUNC_REVERSE_SUBTRACT, GL_MIN, GL_MAX,
                                    GL_FUNC_ADD, GL_FUNC_ADD, GL_FUNC_ADD };
static const GLenum LOGICA[16] = { GL_CLEAR, GL_AND, GL_AND_REVERSE, GL_COPY, GL_SET, GL_COPY_INVERTED, GL_NOOP,
                                   GL_INVERT, GL_NAND, GL_OR, GL_NOR, GL_XOR, GL_EQUIV, GL_AND_INVERTED,
                                   GL_OR_REVERSE, GL_OR_INVERTED };
static const GLenum STENCIL_OP[8] = { GL_KEEP, GL_ZERO, GL_REPLACE, GL_INCR, GL_DECR, GL_INVERT, GL_INCR_WRAP,
                                      GL_DECR_WRAP };

static void gl_fijar_destino(RbRT *rt, int vx, int vy, int vw, int vh)
{
    gl.BindFramebuffer(GL_FRAMEBUFFER, rt->fbo);
    glViewport(vx, vy, (GLsizei)vw, (GLsizei)vh);
}

static void gl_fijar_estado(const RbEstado *e)
{
    glDisable(GL_SCISSOR_TEST);   /* la tijera la hace el shader (modos dentro / fuera) */
    /* culling: la y de pantalla PICA = y de GL, antihorario = cara de frente (glFrontFace por defecto).
       1 conserva los horarios (descarta los antihorarios), 2 conserva los antihorarios. */
    if (e->cull == 1 || e->cull == 2) {
        glEnable(GL_CULL_FACE);
        glFrontFace(GL_CCW);
        glCullFace(e->cull == 1 ? GL_FRONT : GL_BACK);
    } else {
        glDisable(GL_CULL_FACE);
    }
    if (e->clip_dist) glEnable(GL_CLIP_DISTANCE0); else glDisable(GL_CLIP_DISTANCE0);
    glEnable(GL_DEPTH_TEST);   /* sin prueba = ALWAYS (en GL, apagar la prueba apaga tambien la escritura) */
    glDepthFunc(FUNC_PRUEBA[e->depth_func & 7]);
    glDepthMask(e->depth_write ? GL_TRUE : GL_FALSE);
    /* stencil: solo con D24S8 (sw_rasterizer DoDepthStencilTest); compara (ref & imask) op (stencil & imask) */
    if (e->stencil_on) {
        glEnable(GL_STENCIL_TEST);
        gl.StencilFuncSeparate(GL_FRONT_AND_BACK, FUNC_PRUEBA[e->stencil_func & 7], e->stencil_ref, e->stencil_imask);
        gl.StencilOpSeparate(GL_FRONT_AND_BACK, STENCIL_OP[e->stencil_fail & 7], STENCIL_OP[e->stencil_zfail & 7],
                             STENCIL_OP[e->stencil_zpass & 7]);
        glStencilMask(e->stencil_wmask);
    } else {
        glDisable(GL_STENCIL_TEST);
    }
    uint8_t cm = e->color_mask;
    if (g_sab_rb & 1) cm &= (uint8_t)~4u;   /* SABOTAJE 1: ningun dibujo escribe el canal azul */
    glColorMask(cm & 1, (cm >> 1) & 1, (cm >> 2) & 1, (cm >> 3) & 1);
    if (e->blend_on) {
        glDisable(GL_COLOR_LOGIC_OP);
        glEnable(GL_BLEND);
        gl.BlendEquationSeparate(ECUACION[e->eq_rgb & 7], ECUACION[e->eq_a & 7]);
        gl.BlendFuncSeparate(FACTOR[e->src_rgb & 15], FACTOR[e->dst_rgb & 15], FACTOR[e->src_a & 15],
                             FACTOR[e->dst_a & 15]);
        uint32_t b = e->blend_color;
        gl.BlendColor((b & 0xFF) / 255.0f, ((b >> 8) & 0xFF) / 255.0f, ((b >> 16) & 0xFF) / 255.0f, (b >> 24) / 255.0f);
    } else {
        glDisable(GL_BLEND);
        glEnable(GL_COLOR_LOGIC_OP);
        glLogicOp(LOGICA[e->logic_op & 15]);
    }
}

/* ------------------------------------------------------------------ vertices y dibujo */
/* Camino NATIVO (7 oct): ver el comentario de armar_crudo en raster_gl.c. Un VAO por layout distinto, reutilizado: el
   driver valida el formato UNA vez y por dibujo solo cambian los buffers (glBindVertexBuffer), que es lo barato. Las
   constantes (glVertexAttrib4f) son estado del contexto. */
static int gl_vertices_crudos(const RbVerticesCrudos *v)
{
    static const GLenum TIPO[4] = { GL_BYTE, GL_UNSIGNED_BYTE, GL_SHORT, GL_FLOAT };
    static struct { uint32_t lay[16]; GLuint vao; } cache[128];
    static int ncache;
    int iv = -1;
    for (int k = 0; k < ncache && iv < 0; k++)
        if (!memcmp(cache[k].lay, v->layout, sizeof v->layout)) iv = k;
    if (iv < 0) {
        if (ncache >= 128) return 0;   /* no deberia pasar: el juego tiene pocos layouts */
        iv = ncache++;
        memcpy(cache[iv].lay, v->layout, sizeof v->layout);
        gl.GenVertexArrays(1, &cache[iv].vao);
        gl.BindVertexArray(cache[iv].vao);
        for (GLuint k = 0; k < 16; k++) {
            uint32_t lay = v->layout[k];
            if (!lay) continue;
            gl.EnableVertexAttribArray(k);
            gl.VertexAttribFormat(k, (GLint)((lay >> 24) & 7), TIPO[(lay >> 20) & 3], GL_FALSE, lay & 0xFFFF);
            gl.VertexAttribBinding(k, (lay >> 16) & 15);
        }
        static int avisos;
        if (++avisos <= 4 || avisos % 16 == 0) logr("layout de vertices %d nuevo", ncache);
    }
    g_vao_crudo = cache[iv].vao;
    gl.BindVertexArray(g_vao_crudo);
    gl.BindBuffer(GL_ARRAY_BUFFER, g_vbo_crudo);
    gl.BufferData(GL_ARRAY_BUFFER, (GLsizeiptr)v->bytes, v->datos, GL_STREAM_DRAW);
    for (int j = 0; j < 12; j++)
        if ((v->bind_mask >> j) & 1) gl.BindVertexBuffer((GLuint)j, g_vbo_crudo, (GLintptr)v->bind_off[j], (GLsizei)v->bind_stride[j]);
    for (GLuint k = 0; k < 16; k++)
        if (!v->layout[k]) gl.VertexAttrib4f(k, v->cte[k][0], v->cte[k][1], v->cte[k][2], v->cte[k][3]);
    g_vao_actual = g_vao_crudo;
    return 1;
}

static void gl_vertices_floats(const float *vb, uint32_t nv)
{
    gl.BindVertexArray(g_vao);
    gl.BindBuffer(GL_ARRAY_BUFFER, g_vbo);
    gl.BufferData(GL_ARRAY_BUFFER, (GLsizeiptr)nv * 64 * sizeof(float), vb, GL_STREAM_DRAW);
    g_vao_actual = g_vao;
}

static void gl_dibujar(int topologia, uint32_t n, const uint32_t *indices)
{
    static const GLenum MODO[3] = { GL_TRIANGLES, GL_TRIANGLE_STRIP, GL_TRIANGLE_FAN };
    gl.BindVertexArray(g_vao_actual);
    if (indices) {
        gl.BindBuffer(GL_ELEMENT_ARRAY_BUFFER, g_ebo);
        gl.BufferData(GL_ELEMENT_ARRAY_BUFFER, (GLsizeiptr)n * 4, indices, GL_STREAM_DRAW);
        glDrawElements(MODO[topologia], (GLsizei)n, GL_UNSIGNED_INT, (void *)0);
    } else {
        glDrawArrays(MODO[topologia], 0, (GLsizei)n);
    }
}

/* ------------------------------------------------------------------ giro de la pantalla en alta, presentacion */
/* Unidad de textura 5: el raster usa 0-3. */
static GLuint g_giro_prog, g_giro_vao;
static GLint g_giro_u[5];   /* alta, o, A, s, WH */

static int giro_programa(void)
{
    if (g_giro_prog) return 1;
    static const char *vs = "#version 450 core\n"
        "void main() { gl_Position = vec4(float((gl_VertexID & 1) * 4 - 1), float((gl_VertexID & 2) * 2 - 1), 0.0, 1.0); }\n";
    static const char *fs = "#version 450 core\n"
        "uniform sampler2D alta; uniform vec4 o; uniform vec4 A; uniform float s; uniform vec4 WH;\n"
        "out vec4 c;\n"
        "void main() {\n"
        "    float u = (floor(gl_FragCoord.x) + 0.5) / s - 0.5, v = (floor(gl_FragCoord.y) + 0.5) / s - 0.5;\n"
        "    float tx = o.x + 0.5 + A.x * u + A.y * v, ty = o.y + 0.5 + A.z * u + A.w * v;\n"
        "    ivec2 i = clamp(ivec2(int(tx * s), int(ty * s)), ivec2(0), ivec2(WH.xy) - 1);\n"
        "    c = vec4(texelFetch(alta, i, 0).rgb, 1.0);\n"
        "}\n";
    GLuint v = compilar(GL_VERTEX_SHADER, vs, "giro_alta.vert"), f = compilar(GL_FRAGMENT_SHADER, fs, "giro_alta.frag");
    if (!v || !f) return 0;
    GLuint p = gl.CreateProgram();
    gl.AttachShader(p, v);
    gl.AttachShader(p, f);
    gl.LinkProgram(p);
    GLint ok = 0;
    gl.GetProgramiv(p, GL_LINK_STATUS, &ok);
    gl.DeleteShader(v);
    gl.DeleteShader(f);
    if (!ok) { logr("giro_alta no enlaza"); return 0; }
    g_giro_prog = p;
    g_giro_u[0] = gl.GetUniformLocation(p, "alta");
    g_giro_u[1] = gl.GetUniformLocation(p, "o");
    g_giro_u[2] = gl.GetUniformLocation(p, "A");
    g_giro_u[3] = gl.GetUniformLocation(p, "s");
    g_giro_u[4] = gl.GetUniformLocation(p, "WH");
    gl.GenVertexArrays(1, &g_giro_vao);
    return 1;
}

static int gl_girar(RbRT *dst, RbRT *alta, const RbGiro *g)
{
    if (!giro_programa()) return 0;
    GLint unidad_antes = 0;
    glGetIntegerv(GL_ACTIVE_TEXTURE, &unidad_antes);
    gl.BindFramebuffer(GL_FRAMEBUFFER, dst->fbo);
    glViewport(0, 0, (GLsizei)g->ws, (GLsizei)g->hs);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_STENCIL_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_CULL_FACE);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    gl.UseProgram(g_giro_prog);
    gl.ActiveTexture(GL_TEXTURE5);
    glBindTexture(GL_TEXTURE_2D, alta->tex);
    /* copiar_alta crea la textura sin filtro: con el MIN_FILTER por defecto (mipmaps) queda INCOMPLETA y texelFetch
       da 0 (pantalla negra; lo destapo SM3DL_ALTA_VERIFICAR) */
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    gl.Uniform1i(g_giro_u[0], 5);
    gl.Uniform4f(g_giro_u[1], (float)g->ox, (float)g->oy, 0.0f, 0.0f);
    gl.Uniform4f(g_giro_u[2], (float)g->a00, (float)g->a01, (float)g->a10, (float)g->a11);
    gl.Uniform1f(g_giro_u[3], (float)g->s);
    gl.Uniform4f(g_giro_u[4], (float)g->W, (float)g->H, 0.0f, 0.0f);
    gl.BindVertexArray(g_giro_vao);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    gl.ActiveTexture((GLenum)unidad_antes);
    return 1;
}

/* empieza una presentacion: framebuffer 0 del tamano de la ventana, en negro */
static void gl_ventana_empezar(int w, int h)
{
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
    glViewport(0, 0, w, h);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_STENCIL_TEST);
    glDisable(GL_CULL_FACE);
    glDisable(GL_BLEND);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
}

static GLuint g_capa_prog, g_capa_vao;
static GLint g_capa_u[3];

/* dibuja la capa (premultiplicada) encima, en el rectangulo [x0,x1)x[y0,y1) de la ventana (y0 desde ARRIBA) */
static int gl_pres_capa(RbTex *capa, int x0, int y0, int x1, int y1, int lineal, int vw, int vh)
{
    if (!g_capa_prog) {
        static const char *vs = "#version 450 core\n"
            "uniform vec4 R;\n"   /* rectangulo en NDC: x0 y0 x1 y1 */
            "out vec2 uv;\n"
            "void main() {\n"
            "    vec2 k = vec2(gl_VertexID & 1, gl_VertexID >> 1);\n"
            "    uv = vec2(k.x, 1.0 - k.y);\n"   /* la textura guarda la fila 0 ARRIBA */
            "    gl_Position = vec4(mix(R.x, R.z, k.x), mix(R.y, R.w, k.y), 0.0, 1.0);\n"
            "}\n";
        static const char *fs = "#version 450 core\n"
            "uniform sampler2D capa;\n"
            "in vec2 uv; out vec4 c;\n"
            "void main() { c = texture(capa, uv); }\n";
        GLuint v = compilar(GL_VERTEX_SHADER, vs, "pres_capa.vert"), f = compilar(GL_FRAGMENT_SHADER, fs, "pres_capa.frag");
        if (!v || !f) return 0;
        GLuint p = gl.CreateProgram();
        gl.AttachShader(p, v);
        gl.AttachShader(p, f);
        gl.LinkProgram(p);
        GLint ok = 0;
        gl.GetProgramiv(p, GL_LINK_STATUS, &ok);
        gl.DeleteShader(v);
        gl.DeleteShader(f);
        if (!ok) { logr("pres_capa no enlaza"); return 0; }
        g_capa_prog = p;
        g_capa_u[0] = gl.GetUniformLocation(p, "R");
        g_capa_u[1] = gl.GetUniformLocation(p, "capa");
        gl.GenVertexArrays(1, &g_capa_vao);
    }
    gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
    glViewport(0, 0, vw, vh);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_STENCIL_TEST);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    gl.BlendEquationSeparate(GL_FUNC_ADD, GL_FUNC_ADD);
    gl.BlendFuncSeparate(GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    gl.UseProgram(g_capa_prog);
    gl.BindVertexArray(g_capa_vao);
    gl.ActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, capa->id);
    GLint filtro = lineal ? GL_LINEAR : GL_NEAREST;
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filtro);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filtro);
    gl.Uniform1i(g_capa_u[1], 0);
    float W = (float)vw, H = (float)vh;
    gl.Uniform4f(g_capa_u[0], 2.0f * x0 / W - 1.0f, 1.0f - 2.0f * y1 / H, 2.0f * x1 / W - 1.0f, 1.0f - 2.0f * y0 / H);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glDisable(GL_BLEND);
    gl.BindVertexArray(0);
    gl.UseProgram(0);
    return 1;
}

/* termina la presentacion: SwapBuffers con el intervalo pedido (1 = esperar al refresco del monitor, 0 = no) */
static int gl_presentar(void *hdc, int intervalo)
{
    typedef BOOL (WINAPI *PFNSWAPINT)(int);
    static PFNSWAPINT swap_int;
    static int pedido = -1, buscado;
    if (!hdc) return 0;
    if (!buscado) { buscado = 1; swap_int = (PFNSWAPINT)(void *)wglGetProcAddress("wglSwapIntervalEXT"); }
    if (swap_int && intervalo != pedido) { swap_int(intervalo); pedido = intervalo; }
    return SwapBuffers((HDC)hdc) ? 1 : 0;
}

/* ------------------------------------------------------------------ cronometros de GPU (SM3DL_A_CRONO)
   Queries GL_TIME_ELAPSED asincronas en anillo: se cosechan cuando ya estan, nunca se espera. */
#define GQ_RING 512
static double g_gq[RB_GQ_N];
static uint32_t g_gqn[RB_GQ_N];
static GLuint g_q[GQ_RING];
static uint8_t g_q_cat[GQ_RING];
static uint32_t g_q_ini, g_q_fin, g_q_perdidas;
static int g_q_activa = -1;

static void gq_cosechar(void)
{
    while (g_q_ini != g_q_fin) {
        GLuint q = g_q[g_q_ini % GQ_RING];
        GLint listo = 0;
        gl.GetQueryObjectiv(q, GL_QUERY_RESULT_AVAILABLE, &listo);
        if (!listo) break;
        GLuint64 ns = 0;
        gl.GetQueryObjectui64v(q, GL_QUERY_RESULT, &ns);
        int c = g_q_cat[g_q_ini % GQ_RING];
        g_gq[c] += ns * 1e-9 * (c == RB_GQ_DIB ? 8 : 1);
        g_gqn[c]++;
        g_q_ini++;
    }
}

static void gl_gpu_crono_ini(int cat)
{
    if (!crono_on() || g_q_activa >= 0) return;
    if (!g_q[0]) gl.GenQueries(GQ_RING, g_q);
    if (g_q_fin - g_q_ini >= GQ_RING) gq_cosechar();
    if (g_q_fin - g_q_ini >= GQ_RING) { g_q_perdidas++; return; }
    g_q_cat[g_q_fin % GQ_RING] = (uint8_t)cat;
    gl.BeginQuery(GL_TIME_ELAPSED, g_q[g_q_fin % GQ_RING]);
    g_q_activa = cat;
}

static void gl_gpu_crono_fin(void)
{
    if (g_q_activa < 0) return;
    gl.EndQuery(GL_TIME_ELAPSED);
    g_q_activa = -1;
    g_q_fin++;
}

static void gl_gpu_crono_leer(double seg[RB_GQ_N], uint32_t n[RB_GQ_N], uint32_t *perdidas)
{
    if (gl_es_actual()) gq_cosechar();
    memcpy(seg, g_gq, sizeof g_gq);
    memcpy(n, g_gqn, sizeof g_gqn);
    *perdidas = g_q_perdidas;
}

/* ------------------------------------------------------------------ la tabla */
static const RasterBackend RB_GL = {
    .nombre = "gl",
    .iniciar = gl_iniciar,
    .listo = gl_listo,
    .contexto_actual = gl_contexto_actual,
    .es_actual = gl_es_actual,
    .hacer_actual_dc = gl_hacer_actual_dc,
    .ultimo_error = gl_ultimo_error,
    .etapa_compilar = gl_etapa_compilar,
    .etapa_destruir = gl_etapa_destruir,
    .prog_cargar_cache = gl_prog_cargar_cache,
    .prog_enlazar = gl_prog_enlazar,
    .prog_guardar_cache = gl_prog_guardar_cache,
    .prog_destruir = gl_prog_destruir,
    .prog_usar = gl_prog_usar,
    .constantes = gl_constantes,
    .tex_crear = gl_tex_crear,
    .tex_destruir = gl_tex_destruir,
    .tex_subir = gl_tex_subir,
    .tex_cargar_mips = gl_tex_cargar_mips,
    .tex_enlazar = gl_tex_enlazar,
    .rt_crear = gl_rt_crear,
    .rt_destruir = gl_rt_destruir,
    .rt_subir = gl_rt_subir,
    .rt_limpiar = gl_rt_limpiar,
    .rt_reducir = gl_rt_reducir,
    .rt_leer = gl_rt_leer,
    .rt_leer_ventana = gl_rt_leer_ventana,
    .copiar = gl_copiar,
    .rt_id_nativo = gl_rt_id_nativo,
    .rt_volcar_bgra = gl_rt_volcar_bgra,
    .lectura_crear = gl_lectura_crear,
    .lectura_destruir = gl_lectura_destruir,
    .lectura_emitir = gl_lectura_emitir,
    .lectura_lista = gl_lectura_lista,
    .lectura_esperar = gl_lectura_esperar,
    .lectura_cerrar = gl_lectura_cerrar,
    .lectura_mapa_persistente = gl_lectura_mapa_persistente,
    .lectura_mapear = gl_lectura_mapear,
    .lectura_desmapear = gl_lectura_desmapear,
    .fijar_destino = gl_fijar_destino,
    .fijar_estado = gl_fijar_estado,
    .vertices_crudos = gl_vertices_crudos,
    .vertices_floats = gl_vertices_floats,
    .dibujar = gl_dibujar,
    .girar = gl_girar,
    .ventana_empezar = gl_ventana_empezar,
    .pres_capa = gl_pres_capa,
    .presentar = gl_presentar,
    .gpu_crono_ini = gl_gpu_crono_ini,
    .gpu_crono_fin = gl_gpu_crono_fin,
    .gpu_crono_leer = gl_gpu_crono_leer,
};

const RasterBackend *rb_gl_obtener(void) { return &RB_GL; }
