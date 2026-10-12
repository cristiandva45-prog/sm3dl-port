"""Particulas por cercania mutua (8 oct, video del dueno: nubes del pozo de veneno y hojas saltando de lugar).
code_2AC800 lleva una matriz 3x4 por particula en los registros de clase 6; entre cuadros las particulas nacen,
mueren y se reordenan, asi que mezclar por numero de casilla mezclaba particulas DISTINTAS. Ahora cada particula del
cuadro actual busca la mas cercana (por posicion) del anterior y solo se mezclan si la eleccion es MUTUA; si no, la
particula va en su posicion real. SM3DL_INTERP_PARTICULAS=0: ninguna particula se mezcla (solo la camara)."""
import os
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp", "render")
f = os.path.join(R, "interp.c")
t = open(f, encoding="utf-8").read()

FUNC = r'''
static uint32_t g_part_mezcladas, g_part_reales;
#define MAX_PART 32
/* o = salida (ya con los valores reales de C en las casillas de particula), a = pareja (cuadro anterior), c = actual */
static void mezclar_particulas(PicaVec4 *o, const PicaVec4 *a, const PicaVec4 *c, const uint8_t *clase, float t)
{
    int ini = -1, n = 0;
    for (int q = 0; q < 96; q++)
        if (clase[q] == 6) { if (ini < 0) ini = q; n++; }
    int np = n / 3;
    if (ini < 0 || np <= 0) return;
    if (np > MAX_PART) np = MAX_PART;
    int de_c[MAX_PART], de_a[MAX_PART];
    for (int lado = 0; lado < 2; lado++) {
        const PicaVec4 *x = lado ? a : c, *y = lado ? c : a;
        int *sal = lado ? de_a : de_c;
        for (int k = 0; k < np; k++) {
            double mejor = 1e300;
            sal[k] = -1;
            const PicaVec4 *p = &x[ini + 3 * k];
            for (int j = 0; j < np; j++) {
                const PicaVec4 *q = &y[ini + 3 * j];
                double dx = (double)p[0].w - q[0].w, dy = (double)p[1].w - q[1].w, dz = (double)p[2].w - q[2].w;
                double d = dx * dx + dy * dy + dz * dz;
                if (d < mejor) { mejor = d; sal[k] = j; }
            }
        }
    }
    for (int k = 0; k < np; k++) {
        int j = de_c[k];
        if (j >= 0 && de_a[j] == k) { mezclar_matriz(&o[ini + 3 * k], &a[ini + 3 * j], &c[ini + 3 * k], t); g_part_mezcladas++; }
        else g_part_reales++;
    }
}
'''

pares = [
    ("static void dibujo(PicaEstado *e)\n{", FUNC + "\nstatic void dibujo(PicaEstado *e)\n{"),
    ("        if (cl == 2) { po[j] = pc[j]; g_tex_real += d != 0; continue; }",
     "        if (cl == 2) { po[j] = pc[j]; g_tex_real += d != 0; continue; }\n"
     "        if (cl == 6) { po[j] = pc[j]; continue; }                          /* particula: abajo, por cercania */"),
    ("    if (prog && matrices) {\n",
     "    static int particulas = -1;\n"
     "    if (particulas < 0) { const char *s = getenv(\"SM3DL_INTERP_PARTICULAS\"); particulas = !(s && *s == '0'); }\n"
     "    if (prog && particulas) mezclar_particulas(e->vs.f, a, guardado, prog->clase, t);\n"
     "    if (prog && matrices) {\n"),
    ("%u huesos de objetos sin esqueleto (real); programas",
     "%u huesos de objetos sin esqueleto (real), particulas %u mezcladas y %u sin pareja mutua; programas"),
    ("g_mat_mezcladas, g_mat_grandes, g_huesos_real, g_reconocidos, g_desconocidos);",
     "g_mat_mezcladas, g_mat_grandes, g_huesos_real, g_part_mezcladas, g_part_reales, g_reconocidos, g_desconocidos);"),
    ("g_mat_mezcladas = g_mat_grandes = g_huesos_real = 0;",
     "g_mat_mezcladas = g_mat_grandes = g_huesos_real = g_part_mezcladas = g_part_reales = 0;"),
]
for x, y in pares:
    assert t.count(x) == 1, x[:90]
    t = y.join(t.split(x))
# la funcion de particulas usa mezclar_matriz: tiene que quedar DESPUES de ella
assert t.index("static void mezclar_matriz(") < t.index("static void mezclar_particulas(")
open(f + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
os.replace(f + ".tmp", f)
print("ok")
