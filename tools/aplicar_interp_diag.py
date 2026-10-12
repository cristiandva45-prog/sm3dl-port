"""Diagnostico F9 de la interpolacion (8 oct, pozo de veneno del W2-2). Parchea interp.c y gsp_interp.inc.
En vivo a 60: al pulsar F9, el siguiente cuadro guarda en sesion_juego\\diag\\<n>\\ el intermedio, B y C reales, y por
cada dibujo su decision de mezcla, su HUELLA EN PANTALLA (pixeles que cambian si ese dibujo NO se mezcla) y los
uniforms que cambian entre B y C. Asi se encuentra el dibujo que se ve mal sin adivinar."""
import os
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp")

def parchear(ruta, pares):
    t = open(ruta, encoding="utf-8").read()
    for a, b in pares:
        assert t.count(a) == 1, (ruta, a[:80])
        t = b.join(t.split(a))
    open(ruta + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
    os.replace(ruta + ".tmp", ruta)

DIAG_C = r'''
/* ---- diagnostico F9 (8 oct): por dibujo de la re-ejecucion, su decision y sus uniforms de B (pareja) y C ---- */
typedef struct { const char *prog; int dec, prof, cam; uint32_t h; PicaVec4 a[96], c[96]; } DiagDib;
#define MAX_DIAG 1024
static DiagDib *g_diag;
static int g_ndiag, g_diag_on, g_excluir = -1, g_idx;
static void diag_reg(int idx, const InterpPrograma *p, int dec, int cam, const PicaEstado *e, const PicaVec4 *a, const PicaVec4 *c)
{
    if (!g_diag_on || idx >= MAX_DIAG) return;
    if (!g_diag && !(g_diag = calloc(MAX_DIAG, sizeof *g_diag))) return;
    DiagDib *d = &g_diag[idx];
    d->prog = p ? p->nombre : "?";
    d->dec = dec; d->prof = e->depth_test; d->cam = cam; d->h = huella(e);
    memcpy(d->c, c, sizeof d->c);
    if (a) memcpy(d->a, a, sizeof d->a); else memcpy(d->a, c, sizeof d->a);
    if (idx + 1 > g_ndiag) g_ndiag = idx + 1;
}
static void diag_modo(int on, int excluir) { g_diag_on = on; g_excluir = excluir; if (on) g_ndiag = 0; }
static int diag_n(void) { return g_ndiag; }
static const char *DEC[] = { "2D-sin-mezcla", "sin-pareja", "repetido-vetado", "MEZCLADO" };
static void diag_linea(FILE *f, int k, uint32_t px, int x0, int y0, int x1, int y1)
{
    if (k >= g_ndiag || !g_diag) return;
    const DiagDib *d = &g_diag[k];
    fprintf(f, "dibujo %3d  %-40s %-16s prof=%d cam=%d huella=%08X  pantalla: %6u px", k, d->prog, DEC[d->dec], d->prof, d->cam, d->h, px);
    if (px) fprintf(f, " en x %d-%d y %d-%d", x0, x1, y0, y1);
    fprintf(f, "\n");
    if (!px) return;
    const InterpPrograma *p = NULL;
    for (int j = 0; j < N_INTERP_PROGRAMAS; j++) if (g_programas[j].nombre == d->prog) p = &g_programas[j];
    for (int r = 0; r < 96; r++) {
        const PicaVec4 *a = &d->a[r], *c = &d->c[r];
        if (!memcmp(a, c, sizeof *a)) continue;
        fprintf(f, "    c%-2d clase %d  B (%10.5f %10.5f %10.5f %10.5f)  C (%10.5f %10.5f %10.5f %10.5f)\n", r, p ? p->clase[r] : 9,
                a->x, a->y, a->z, a->w, c->x, c->y, c->z, c->w);
    }
}
'''

parchear(os.path.join(R, "render", "interp.c"), [
    ("static uint32_t g_solo_cam, g_cortes, g_reconocidos, g_desconocidos, g_tex_real;\n",
     "static uint32_t g_solo_cam, g_cortes, g_reconocidos, g_desconocidos, g_tex_real;\n" + DIAG_C),
    # indice del dibujo dentro de la re-ejecucion
    ("    static int cercano = -1, mezclar_2d = -1, repetidos = -1, saltos = -1;\n",
     "    int idx = g_idx++;\n    static int cercano = -1, mezclar_2d = -1, repetidos = -1, saltos = -1;\n"),
    ("    if (!e->depth_test && !mezclar_2d) {\n        g_sin_mezcla++;\n",
     "    if (!e->depth_test && !mezclar_2d) {\n        g_sin_mezcla++;\n        diag_reg(idx, semantica ? programa(e) : NULL, 0, 0, e, NULL, e->vs.f);\n"),
    ("    int sin_pareja = k == g_n[r];\n    if (sin_pareja) g_sueltos++;",
     "    int sin_pareja = k == g_n[r], vetado = 0;\n    if (sin_pareja) g_sueltos++;"),
    ("if (d_orden >= 0 && d_otro < 0.5 * d_orden) { g_vetados++; sin_pareja = 1; }",
     "if (d_orden >= 0 && d_otro < 0.5 * d_orden) { g_vetados++; sin_pareja = 1; vetado = 1; }"),
    ("if ((nr > 1 || nc > 1) && (repetidos == 0 || nr != nc)) { g_vetados++; sin_pareja = 1; }",
     "if ((nr > 1 || nc > 1) && (repetidos == 0 || nr != nc)) { g_vetados++; sin_pareja = 1; vetado = 1; }"),
    ("        if (prog && mezclar_camara(e, prog, r, cur, g_t)) g_solo_cam++;\n",
     "        int cam = idx != g_excluir && prog && mezclar_camara(e, prog, r, cur, g_t);\n        g_solo_cam += cam;\n"
     "        diag_reg(idx, prog, vetado ? 2 : 1, cam, e, vetado ? g_tab[r][k].f : NULL, guardado);\n"),
    ("    const PicaVec4 *a = g_tab[r][k].f;\n    float t = g_t;\n",
     "    const PicaVec4 *a = g_tab[r][k].f;\n    diag_reg(idx, prog, 3, 1, e, a, guardado);\n"
     "    if (idx == g_excluir) { if (pica_raster) pica_raster(e); return; }   /* diagnostico: este dibujo, real */\n"
     "    float t = g_t;\n"),
    # reiniciar el indice en cada re-ejecucion
    ("        g_t = t;\n        memset(g_usado, 0, sizeof g_usado);\n",
     "        g_t = t;\n        g_idx = 0;\n        memset(g_usado, 0, sizeof g_usado);\n"),
    ("    gsp_interp_leer_alta = leer_alta;\n",
     "    gsp_interp_leer_alta = leer_alta;\n    gsp_interp_diag = diag_modo;\n    gsp_interp_diag_n = diag_n;\n    gsp_interp_diag_linea = diag_linea;\n"),
    ("extern int *gsp_interp_vivo;\n",
     "extern int *gsp_interp_vivo;\nextern void (*gsp_interp_diag)(int on, int excluir);\nextern int (*gsp_interp_diag_n)(void);\n"
     "extern void (*gsp_interp_diag_linea)(FILE *f, int k, uint32_t px, int x0, int y0, int x1, int y1);\n"),
])

DIAG_GSP = r'''
/* DIAGNOSTICO F9 (8 oct, pozo de veneno): ver tools\aplicar_interp_diag.py */
void (*gsp_interp_diag)(int on, int excluir);
int (*gsp_interp_diag_n)(void);
void (*gsp_interp_diag_linea)(FILE *f, int k, uint32_t px, int x0, int y0, int x1, int y1);
__declspec(dllimport) short __stdcall GetAsyncKeyState(int tecla);
int _mkdir(const char *ruta);
static void vivo_diag(u32 sal, u32 ts)
{
    static int n_diag;
    if (!gsp_interp_diag) return;
    char d[300], r[340];
    _mkdir("sesion_juego");
    _mkdir("sesion_juego\\diag");
    snprintf(d, sizeof d, "sesion_juego\\diag\\%02d", ++n_diag);
    _mkdir(d);
    u8 *mid = malloc(ts), *tmp = malloc(ts);
    if (!mid || !tmp) { free(mid); free(tmp); return; }
    gsp_interp_diag(1, -1);
    repetir_cuadro(3, 0.5f, -1, sal, ts, mid);
    int n = gsp_interp_diag_n();
    gsp_interp_diag(0, -1);
    volcar_en(d, "mid", mid, ts);
    volcar_en(d, "B", g_imgs[1], ts);
    volcar_en(d, "C", g_imgs[2], ts);
    snprintf(r, sizeof r, "%s\\dibujos.txt", d);
    FILE *f = fopen(r, "w");
    if (f) {
        fprintf(f, "vblank %u: %d dibujos. pantalla = pixeles que cambian si ESE dibujo no se mezcla (x 0-399, y 0-239 desde arriba)\n", E.vblanks, n);
        for (int k = 0; k < n; k++) {
            gsp_interp_diag(0, k);
            repetir_cuadro(3, 0.5f, -1, sal, ts, tmp);
            u32 px = 0;
            int x0 = 9999, y0 = 9999, x1 = -1, y1 = -1;
            for (u32 i = 0; i + 1 < ts && i / 480u < 400u; i += 2) {
                if (tmp[i] == mid[i] && tmp[i + 1] == mid[i + 1]) continue;
                int x = (int)(i / 480u), y = 239 - (int)((i % 480u) / 2u);
                px++;
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
                if (y < y0) y0 = y;
                if (y > y1) y1 = y;
            }
            gsp_interp_diag_linea(f, k, px, x0, y0, x1, y1);
        }
        fclose(f);
    }
    gsp_interp_diag(0, -1);
    repetir_cuadro(3, 0.5f, -1, sal, ts, NULL);   /* deja otra vez el intermedio completo en el framebuffer */
    fprintf(stderr, "[diag] F9: %d dibujos volcados en %s\n", n, d);
    free(mid);
    free(tmp);
}
'''

parchear(os.path.join(R, "gpu", "gsp_interp.inc"), [
    ("static void vivo_cerrar(u32 sal, u32 ts)\n{", DIAG_GSP + "\nstatic void vivo_cerrar(u32 sal, u32 ts)\n{"),
    ("    g_n_hechos++;\n",
     "    g_n_hechos++;\n    if (GetAsyncKeyState(0x78) & 1) vivo_diag(sal, ts);   /* F9 */\n"),
])
print("ok")
