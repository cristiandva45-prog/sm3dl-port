r"""(H1) gsp_interp.inc: SM3DL_D3D12_REPETIR_VOLCAR=<dir> vuelca los pares (cinta / re-ejecucion) con diferencias."""
import os
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
p = os.path.join(RAIZ, "recomp", "gpu", "gsp_interp.inc")
s = open(p, encoding="utf-8").read()
a = """    free(a);
    n++;
    malos += px > 0;"""
assert s.count(a) == 1
s = s.replace(a, """    {   /* SM3DL_D3D12_REPETIR_VOLCAR=<dir>: los primeros 8 pares con diferencias (BGRA, 400s x 240s, fila 0 arriba) */
        static const char *dv = (const char *)1;
        static int nv;
        if (dv == (const char *)1) dv = getenv("SM3DL_D3D12_REPETIR_VOLCAR");
        if (dv && *dv && px && nv < 8) {
            char r[600];
            nv++;
            for (int q = 0; q < 2; q++) {
                snprintf(r, sizeof r, "%s\\\\par%02d_%s_%dx%d_%upx.bgra", dv, nv, q ? "lento" : "cinta", 400 * s, 240 * s, px);
                FILE *fv = fopen(r, "wb");
                if (fv) { fwrite(q ? hi : a, 1, tam, fv); fclose(fv); }
            }
        }
    }
    free(a);
    n++;
    malos += px > 0;""")
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
