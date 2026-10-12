r"""(H1) alto_rapido_verificar: arregla el modo 2 (el repetir de vuelta pisaba la copia antes de leerla) y agrega la
REFERENCIA: la copia en alta del cuadro REAL (antes del primer intermedio) contra cinta y re-ejecucion en modo 2."""
import os
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
p = os.path.join(RAIZ, "recomp", "gpu", "gsp_interp.inc")
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a
    s = s.replace(a, b)


rep("""    g_rapido_forzar = -1;
    u32 r0 = g_n_rapido;
    repetir_cuadro(vm, t, -1, sal, ts, NULL);""", """    u8 *real = NULL;   /* modo 2: la copia en alta del REAL C (todavia no hubo intermedio en este cuadro) */
    if (vm == 2 && gsp_interp_leer_alta) {
        int s0 = gsp_interp_leer_alta(sal, fmt, stride, &hi);
        size_t t0 = s0 > 1 && hi ? (size_t)400u * s0 * 240u * s0 * 4u : 0;
        if (t0 && (real = malloc(t0))) memcpy(real, hi, t0);
    }
    g_rapido_forzar = -1;
    u32 r0 = g_n_rapido;
    repetir_cuadro(vm, t, -1, sal, ts, NULL);""")
rep("""    g_rapido_forzar = -1;
    if (vm == 2) repetir_cuadro(3, t, -1, sal, ts, NULL);   /* deja el intermedio de siempre */
    int s2 = gsp_interp_leer_alta ? gsp_interp_leer_alta(sal, fmt, stride, &hi) : 0;
    if (!a || s2 != s || !hi) { free(a); return; }""", """    g_rapido_forzar = -1;
    int s2 = gsp_interp_leer_alta ? gsp_interp_leer_alta(sal, fmt, stride, &hi) : 0;
    if (!a || s2 != s || !hi) { free(a); free(real); if (vm == 2) repetir_cuadro(3, t, -1, sal, ts, NULL); return; }
    if (real) {   /* contra el REAL: cuantos px se aparta cada camino sin mezclar */
        u32 pc = 0, pl = 0;
        for (size_t k = 0; k < tam; k += 4) {
            pc += memcmp(a + k, real + k, 3) != 0;
            pl += memcmp(hi + k, real + k, 3) != 0;
        }
        static u32 nr, mc, ml;
        nr++; mc += pc > 0; ml += pl > 0;
        if (pc || pl || nr <= 3 || nr % 20 == 0)
            fprintf(stderr, "[alto-rapido-real] %u: sin mezclar contra el REAL C: cinta %u px, re-ejecucion %u px (cuadros con diferencia: cinta %u, re-ejecucion %u)\\n",
                    nr, pc, pl, mc, ml);
        free(real);
    }""")
rep("""    free(a);
    n++;
    malos += px > 0;""", """    free(a);
    if (vm == 2) { repetir_cuadro(3, t, -1, sal, ts, NULL); hi = NULL; }   /* deja el intermedio de siempre */
    n++;
    malos += px > 0;""")
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
