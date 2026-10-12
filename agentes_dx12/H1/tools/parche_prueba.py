r"""(H1) parche de prueba_h1.c: cronometro del intermedio y variante "textura re-subida" (H1_ESPERA_INVALIDA)."""
import os
p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prueba_h1.c")
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, a
    s = s.replace(a, b)


rep("""            uint32_t d0 = g_dibujos;
            gsp_interp_repetir(3, t);
            ejecutar(g_ini_c, g_fin_c, 0);
            gsp_interp_repetir(0, t);
            uint8_t *lento""", """            uint32_t d0 = g_dibujos;
            LARGE_INTEGER q0, q1, q2, q3, qf;
            QueryPerformanceFrequency(&qf);
            QueryPerformanceCounter(&q0);
            gsp_interp_repetir(3, t);
            ejecutar(g_ini_c, g_fin_c, 0);
            gsp_interp_repetir(0, t);
            QueryPerformanceCounter(&q1);
            uint8_t *lento""")
rep("""            limpiar(g_ult_limpiar);
            gsp_interp_repetir(3, t);
            int lista = gsp_interp_rapido_listo && gsp_interp_rapido_listo();
            if (lista) gsp_interp_rapido_op(0);
            gsp_interp_repetir(0, t);
            uint8_t *rapido = leer_rt(&w2, &h2);
            if (!real""", """            limpiar(g_ult_limpiar);
            QueryPerformanceCounter(&q2);
            gsp_interp_repetir(3, t);
            int lista = gsp_interp_rapido_listo && gsp_interp_rapido_listo();
            if (lista) gsp_interp_rapido_op(0);
            gsp_interp_repetir(0, t);
            QueryPerformanceCounter(&q3);
            fprintf(stderr, "[h1] CPU del intermedio: re-ejecucion %.3f ms, cinta %.3f ms (%u dibujos; sin las lecturas)\\n",
                    1e3 * (double)(q1.QuadPart - q0.QuadPart) / qf.QuadPart, 1e3 * (double)(q3.QuadPart - q2.QuadPart) / qf.QuadPart,
                    g_dibujos - d0);
            uint8_t *rapido = leer_rt(&w2, &h2);
            if (!real""")
rep("""            if (!lista) {
                fprintf(stderr, "[h1] cinta NO lista (%s)%s\\n", g_es_d3d12 ? "MAL en D3D12" : "esperado en GL", cif[0] ? cif : "");
                if (g_es_d3d12) g_fallas++;
            } else {""", """            int espera_inv = getenv("H1_ESPERA_INVALIDA") != NULL;
            if (!lista) {
                fprintf(stderr, "[h1] cinta NO lista (%s) %s\\n", !g_es_d3d12 ? "esperado en GL" : espera_inv ? "esperado: textura re-subida" : "MAL en D3D12", cif);
                if (g_es_d3d12 && !espera_inv) g_fallas++;
            } else if (espera_inv) {
                fprintf(stderr, "[h1] la cinta quedo lista aunque una textura usada se re-subio: MAL\\n");
                g_fallas++;
            } else {""")
rep("""            if (!lista && g_es_d3d12) g_fallas++;""", """            if (!lista && g_es_d3d12 && !getenv("H1_ESPERA_INVALIDA")) g_fallas++;""")
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("parche ok")
