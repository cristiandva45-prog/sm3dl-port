r"""Deriva agentes_dx12\E2\prueba_e2.c del arnes de A (agentes_dx12\A\prueba_equiv.c) con reemplazos EXACTOS (aborta si
un texto viejo no aparece las veces esperadas). Uso (desde agentes_dx12\E2): py -I tools\parche_arnes.py
Se corre UNA vez sobre la copia sembrada; lo que sigue se edita a mano en prueba_e2.c."""
p = "prueba_e2.c"
s = open(p, encoding="utf-8").read()


def rep(viejo, nuevo, n=1):
    global s
    c = s.count(viejo)
    if c != n:
        raise SystemExit("aparece %d veces (esperaba %d): %r" % (c, n, viejo[:80]))
    s = s.replace(viejo, nuevo)


rep('''#include <string.h>

#include "raster_gl.c"

int interp_vivo;

#ifdef VERSION_ANTES
#define FBO_DE(t) ((t)->fbo)
#else
#define FBO_DE(t) ((t)->rt->fbo)
#endif
''', '''#include <string.h>

#include "raster_gl.c"

int interp_vivo;

/* ---------------------------------------------------------------- tabla envuelta: volcado de los textos de shader */
static RasterBackend e2_tabla;
static RbEtapa *(*e2_etapa_orig)(int tipo, const char *src, const char *nombre);
static const char *e2_dir_glsl;
static unsigned e2_nvolcados, e2_netapas, e2_netapas_mal;
static RbEtapa *e2_etapa_compilar(int tipo, const char *src, const char *nombre)
{
    if (e2_dir_glsl && src) {
        char ruta[600];
        static const char *const pre[3] = { "V", "F", "G" }, *const ext[3] = { "vert", "frag", "geom" };
        int t = tipo == RB_ETAPA_FS ? 1 : tipo == RB_ETAPA_GS ? 2 : 0;
        snprintf(ruta, sizeof ruta, "%s\\\\%s_%08X.%s", e2_dir_glsl, pre[t], fnv_texto(src), ext[t]);
        FILE *fv = fopen(ruta, "wb");
        if (fv) { fwrite(src, 1, strlen(src), fv); fclose(fv); e2_nvolcados++; }
    }
    RbEtapa *e = e2_etapa_orig(tipo, src, nombre);
    e2_netapas++;
    if (!e) e2_netapas_mal++;
    return e;
}

/* ---------------------------------------------------------------- ventana propia (oculta) para los dos backends */
static HWND e2_hwnd;
static HDC e2_dc;
static int e2_ventana(void)
{
    WNDCLASSA wc = { 0 };
    wc.lpfnWndProc = DefWindowProcA;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "sm3dl_e2";
    wc.style = CS_OWNDC;
    RegisterClassA(&wc);
    e2_hwnd = CreateWindowA("sm3dl_e2", "E2", WS_POPUP, 0, 0, 64, 64, NULL, NULL, wc.hInstance, NULL);
    if (!e2_hwnd) return 0;
    e2_dc = GetDC(e2_hwnd);
    return e2_dc != NULL;
}

/* espera a que la GPU termine todo lo emitido (determinismo de la lectura asincrona de la pantalla en alta) */
static void e2_sincronizar(void)
{
    if (g_rb && !strcmp(g_rb->nombre, rb_gl_obtener()->nombre)) { glFinish(); return; }
#ifdef SM3DL_CON_D3D12
    if (dx.estado > 0) d3d_esperar_valor(d3d_vaciar());
#endif
}
''')

rep('''static FILE *out;
static void vuelca(const void *p, size_t n) { fwrite(p, 1, n, out); }
static void vuelca32(uint32_t v) { fwrite(&v, 4, 1, out); }
''', '''static FILE *out, *mapa;
static uint32_t g_op_n, g_op_cod;
static long g_off;
static int e2_sab, e2_sab_r_hecho;
static void segmento(char tipo, int fmt, size_t n)
{
    fprintf(mapa, "%u %u %ld %zu %c %d\\n", g_op_n, g_op_cod, g_off, n, tipo, fmt);
    g_off += (long)n;
}
/* tipo P = pixeles RGBA8/BGRA8; M = memoria del 3DS en el formato GSP fmt */
static void vuelca_tipo(const void *p, size_t n, char tipo, int fmt)
{
    int bytewise = tipo == 'P' || (tipo == 'M' && (fmt == GSP_RGBA8 || fmt == GSP_RGB8));
    if ((e2_sab == 1 || e2_sab == 2) && bytewise && n) {
        uint8_t *c = malloc(n);
        memcpy(c, p, n);
        if (e2_sab == 1) for (size_t k = 0; k < n; k++) c[k] ^= 1;
        else if (tipo == 'P') c[n / 2] = (uint8_t)(c[n / 2] < 128 ? c[n / 2] + 2 : c[n / 2] - 2);
        fwrite(c, 1, n, out);
        free(c);
    } else {
        fwrite(p, 1, n, out);
    }
    segmento(tipo, fmt, n);
}
static void vuelca_px(const void *p, size_t n) { vuelca_tipo(p, n, 'P', 0); }
static void vuelca32(uint32_t v)
{
    if (e2_sab == 3 && !e2_sab_r_hecho) { v++; e2_sab_r_hecho = 1; }
    fwrite(&v, 4, 1, out);
    segmento('R', 0, 4);
}
''')

rep('''    if (argc < 3) { fprintf(stderr, "uso: prueba_equiv guion.bin salida.bin\\n"); return 1; }''',
    '''    if (argc < 3) { fprintf(stderr, "uso: prueba_e2 guion.bin salida.bin\\n"); return 1; }''')
rep('''    out = fopen(argv[2], "wb");
''', '''    out = fopen(argv[2], "wb");
    {
        char rm[600];
        snprintf(rm, sizeof rm, "%s.mapa", argv[2]);
        mapa = fopen(rm, "w");
        const char *s = getenv("E2_SABOTAJE");
        e2_sab = s ? atoi(s) : 0;
        if (e2_sab) fprintf(stderr, "[arnes] E2_SABOTAJE=%d (prueba del comparador)\\n", e2_sab);
        e2_dir_glsl = getenv("E2_VOLCAR_GLSL");
    }
    if (!out || !mapa) return 1;
''')
rep('''    raster_iniciar();
    if (!iniciar_gl()) return 2;
''', '''    raster_iniciar();
    elegir_backend();
    e2_tabla = *g_rb;
    e2_etapa_orig = e2_tabla.etapa_compilar;
    e2_tabla.etapa_compilar = e2_etapa_compilar;
    g_rb = &e2_tabla;
    if (!iniciar_gl()) { fprintf(stderr, "[arnes] backend %s: iniciar FALLO\\n", g_rb->nombre); return 2; }
    if (!e2_ventana()) { fprintf(stderr, "[arnes] ventana propia fallo\\n"); return 3; }
    if (!raster_gl_hacer_actual(e2_dc)) fprintf(stderr, "[arnes] backend %s: hacer_actual_dc FALLO (sin ventana)\\n", g_rb->nombre);
''')
rep('''        uint32_t op = g[i++];
        if (op == 0) break;''', '''        uint32_t op = g[i++];
        g_op_n++;
        g_op_cod = op;
        if (op == 0) break;''')
rep('''            Rt *t = rt_actual();
            uint8_t *px = malloc((size_t)w * h * 4);
            gl.BindFramebuffer(GL_FRAMEBUFFER, FBO_DE(t));
            glReadPixels((GLint)x, (GLint)y, (GLsizei)w, (GLsizei)h, GL_RGBA, GL_UNSIGNED_BYTE, px);
            vuelca(px, (size_t)w * h * 4);
            free(px);''', '''            Rt *t = rt_actual();
            uint32_t W = x + w, H = y + h;
            uint8_t *todo = calloc((size_t)W * H, 4), *px = malloc((size_t)w * h * 4);
            int ok = t && t->rt ? rb->rt_leer(t->rt, (int)W, (int)H, RB_FMT_RGBA8, todo) : 0;
            if (!ok) memset(todo, 0xEE, (size_t)W * H * 4);   /* lectura fallida: patron que no coincide con nada */
            for (uint32_t r = 0; r < h; r++) memcpy(px + (size_t)r * w * 4, todo + ((size_t)(y + r) * W + x) * 4, (size_t)w * 4);
            vuelca_px(px, (size_t)w * h * 4);
            free(px); free(todo);''')
rep('''            Rt *t = rt_actual();
            gl.BindFramebuffer(GL_FRAMEBUFFER, FBO_DE(t));
            glDisable(GL_SCISSOR_TEST);
            glColorMask(1, 1, 1, 1);
            glClearColor((c & 255) / 255.0f, ((c >> 8) & 255) / 255.0f, ((c >> 16) & 255) / 255.0f, (c >> 24) / 255.0f);
            glClear(GL_COLOR_BUFFER_BIT);
            glDepthMask(1);
            glStencilMask(0xFF);
            glClearDepth(1.0);
            glClearStencil(0);
            glClear(GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);''', '''            Rt *t = rt_actual();
            float col[4] = { (c & 255) / 255.0f, ((c >> 8) & 255) / 255.0f, ((c >> 16) & 255) / 255.0f, (c >> 24) / 255.0f };
            if (t && t->rt) rb->rt_limpiar(t->rt, RB_LIMPIAR_COLOR | RB_LIMPIAR_DS, col, 1.0, 0);''')
rep('''            rt_actual();
            antes_de_leer(dir, nb);
            uint8_t *b = malloc(nb);
            if (gsp_leer_fisica(dir, b, nb) != 0) memset(b, 0xEE, nb);
            vuelca(b, nb);''', '''            Rt *t = rt_actual();
            int fmt = t && t->color_dir == dir ? t->fmt : GSP_RGBA8;
            antes_de_leer(dir, nb);
            uint8_t *b = malloc(nb);
            if (gsp_leer_fisica(dir, b, nb) != 0) memset(b, 0xEE, nb);
            vuelca_tipo(b, nb, 'M', fmt);''')
rep('''            glFinish();   /* determinismo''', '''            e2_sincronizar();   /* determinismo''')
rep('''            if (s > 0 && rgba) vuelca(rgba,''', '''            if (s > 0 && rgba) vuelca_px(rgba,''')
rep('''            vuelca(p, (size_t)w * h * 4);
            free(p);
            i += 2;''', '''            vuelca_px(p, (size_t)w * h * 4);
            free(p);
            i += 2;''')
rep('''            vuelca32((uint32_t)raster_pres_mostrar(g_dc, 0));''', '''            vuelca32((uint32_t)raster_pres_mostrar(e2_dc, 0));''')
rep('''    fclose(out);
    GLenum err = glGetError();
    fprintf(stderr, "[arnes] %u dibujos, %d fragment shaders, %d programas, gl error 0x%X, inmediatos %u, errores pica %u\\n",
            dibujos, g_nfs, g_nprog, err, pica.e.inm_triangulos, pica.e.errores);
    return err != 0;''', '''    fclose(out);
    fclose(mapa);
    unsigned err = rb->ultimo_error();
    fprintf(stderr, "[arnes] backend %s: %u dibujos, %d fragment shaders, %d programas, error 0x%X, inmediatos %u, errores pica %u, "
            "etapas %u (%u fallidas), %u textos volcados\\n", g_rb->nombre, dibujos, g_nfs, g_nprog, err, pica.e.inm_triangulos,
            pica.e.errores, e2_netapas, e2_netapas_mal, e2_nvolcados);
    return err != 0;''')
if "vuelca(" in s:
    raise SystemExit("queda un vuelca( sin tipo")
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
