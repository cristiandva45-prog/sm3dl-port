"""Mezcla de MATRICES como rotacion (8 oct, hojas del W2-1 salian como rayas). Parchea recomp/render/interp.c.
Antes cada valor de una matriz 3x4 se mezclaba por separado: dos rotaciones muy distintas (una hoja que gira rapido)
dan a medio camino una matriz APLASTADA (la raya). Ahora, por cada matriz (WrldMtx, NormMtx, ViewMtx, cada hueso):
  - la traslacion (columna w) se mezcla siempre;
  - si la parte 3x3 cambia poco (< ~43 grados de rotacion), se mezcla y se le devuelve a cada columna su largo
    (escala) mezclado, para que no se encoja;
  - si cambia mucho, la rotacion va con su valor REAL (ese objeto gira a 30, pero no se deforma).
Y UnivReg en un objeto SIN esqueleto (IsSmoSk/IsRgdSk apagados) no son huesos: va con su valor real.
SM3DL_INTERP_MATRICES=0 lo apaga (para comparar)."""
import os
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp", "render")
f = os.path.join(R, "interp.c")
t = open(f, encoding="utf-8").read()

FUNC = r'''
static uint32_t g_mat_mezcladas, g_mat_grandes, g_huesos_real;
/* o, a (pareja = cuadro anterior), c (actual): 3 filas de una matriz 3x4 (xyz = fila de la 3x3, w = traslacion) */
static void mezclar_matriz(PicaVec4 *o, const PicaVec4 *a, const PicaVec4 *c, float t)
{
    double dif = 0, na = 0, nc = 0;
    for (int i = 0; i < 3; i++) {
        const float *x = &a[i].x, *y = &c[i].x;
        for (int j = 0; j < 3; j++) {
            double d = (double)y[j] - x[j];
            dif += d * d;
            na += (double)x[j] * x[j];
            nc += (double)y[j] * y[j];
        }
        o[i].w = a[i].w + (c[i].w - a[i].w) * t;
    }
    double n = na > nc ? na : nc;
    /* rotacion pura: |R1-R2|^2 = 4(1-cos th) y |R|^2 = 3 -> 0,36 * 3 = 1,08 = th ~ 43 grados */
    if (n <= 0 || dif > 0.36 * n) {
        for (int i = 0; i < 3; i++) { o[i].x = c[i].x; o[i].y = c[i].y; o[i].z = c[i].z; }
        g_mat_grandes++;
        return;
    }
    float m[3][3];
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) m[i][j] = (&a[i].x)[j] + ((&c[i].x)[j] - (&a[i].x)[j]) * t;
    for (int j = 0; j < 3; j++) {
        double la = 0, lc = 0, lm = 0;
        for (int i = 0; i < 3; i++) {
            la += (double)(&a[i].x)[j] * (&a[i].x)[j];
            lc += (double)(&c[i].x)[j] * (&c[i].x)[j];
            lm += (double)m[i][j] * m[i][j];
        }
        la = sqrt(la); lc = sqrt(lc); lm = sqrt(lm);
        if (lm > 1e-12) {
            float s = (float)((la + (lc - la) * t) / lm);
            for (int i = 0; i < 3; i++) m[i][j] *= s;
        }
    }
    for (int i = 0; i < 3; i++) { o[i].x = m[i][0]; o[i].y = m[i][1]; o[i].z = m[i][2]; }
    g_mat_mezcladas++;
}
'''

pares = [
    ("static void dibujo(PicaEstado *e)\n{", FUNC + "\nstatic void dibujo(PicaEstado *e)\n{"),
    # despues del bucle valor por valor: huesos sin esqueleto -> real; matrices -> como rotacion
    ("        else po[j] = pa[j] + d * t;\n    }\n    if (pica_raster) pica_raster(e);\n    memcpy(e->vs.f, guardado, sizeof guardado);\n}",
     "        else po[j] = pa[j] + d * t;\n    }\n"
     "    static int matrices = -1;\n"
     "    if (matrices < 0) { const char *s = getenv(\"SM3DL_INTERP_MATRICES\"); matrices = !(s && *s == '0'); }\n"
     "    if (prog && matrices) {\n"
     "        int con_piel = (e->vs.b & prog->piel) != 0, en_cuat = (e->vs.b & prog->quat) != 0;\n"
     "        for (int q = 0; q < 96; q++)\n"
     "            if (prog->clase[q] == 5 && !con_piel) { e->vs.f[q] = guardado[q]; g_huesos_real++; }\n"
     "        for (int q = 0; q + 2 < 96; q++) {\n"
     "            if (!prog->bloque[q]) continue;\n"
     "            if (prog->clase[q] == 5 && (!con_piel || en_cuat)) continue;   /* sin esqueleto: real; cuaterniones: valor por valor */\n"
     "            if (prog->clase[q] == 2) continue;\n"
     "            mezclar_matriz(&e->vs.f[q], &a[q], &guardado[q], t);\n"
     "        }\n"
     "    }\n"
     "    if (pica_raster) pica_raster(e);\n    memcpy(e->vs.f, guardado, sizeof guardado);\n}"),
    ("%u valores de textura animada sin mezclar; programas",
     "%u valores de textura animada sin mezclar, matrices %u mezcladas como rotacion y %u con giro grande (real), %u huesos de objetos sin esqueleto (real); programas"),
    ("g_solo_cam, g_cortes, g_tex_real, g_reconocidos, g_desconocidos);",
     "g_solo_cam, g_cortes, g_tex_real, g_mat_mezcladas, g_mat_grandes, g_huesos_real, g_reconocidos, g_desconocidos);"),
    ("g_saltos = g_solo_cam = g_cortes = g_tex_real = 0;",
     "g_saltos = g_solo_cam = g_cortes = g_tex_real = g_mat_mezcladas = g_mat_grandes = g_huesos_real = 0;"),
]
for a, b in pares:
    assert t.count(a) == 1, a[:90]
    t = b.join(t.split(a))
open(f + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
os.replace(f + ".tmp", f)
print("ok")
