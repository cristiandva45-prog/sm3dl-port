/* PRUEBA DEL PRESENTADOR D3D12 (8 oct noche): ventana 1200x720; "juego" 1600x960 (4x) escalado nitido a la ventana,
 * HUD premultiplicado de 400x240 encima (nitido) e interfaz premultiplicada del tamano de la ventana. Se lee lo
 * compuesto y se compara contra la MISMA composicion hecha en la CPU (muestreo por punto en el centro del pixel +
 * mezcla ONE, 1-a). Tolerancia: +-1 nivel (la mezcla de la GPU es en float); en el muestreo, si el centro cae justo en
 * la frontera entre dos texeles, vale cualquiera de los dos.
 * SM3DL_D3D_SABOTAJE=1: la base va 3 px corrida -> "muy distintos" TIENE que pasar del 1 % (umbral del pres-verif GL). */
#include "d3d12_presentador.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

enum { VW = 1200, VH = 720, JW = 1600, JH = 960, HW = 400, HH = 240 };
static uint8_t g_juego[JW * JH * 4], g_hud[HW * HH * 4], g_ui[VW * VH * 4], g_leido[VW * VH * 4];

static LRESULT CALLBACK proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_CLOSE) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(h, m, w, l);
}

static void premult(uint8_t *p, int b, int g, int r, int a) { p[0] = (uint8_t)(b * a / 255); p[1] = (uint8_t)(g * a / 255); p[2] = (uint8_t)(r * a / 255); p[3] = (uint8_t)a; }

/* texel(es) candidato(s) para el centro del pixel x de un destino de 'd' sobre una fuente de 's' */
static void candidatos(int x, int d, int s, int *a, int *b)
{
    double u = (x + 0.5) * s / d, f = floor(u);
    *a = *b = (int)f;
    if (u - f < 1e-3 && f > 0) *b = (int)f - 1;
}

int main(void)
{
    int sab = getenv("SM3DL_D3D_SABOTAJE") != NULL;
    /* imagenes de prueba con detalle fino (para que un corrimiento se note) */
    for (int y = 0; y < JH; y++)
        for (int x = 0; x < JW; x++) {
            uint8_t *p = g_juego + ((size_t)y * JW + x) * 4;
            p[0] = (uint8_t)(x * 7 + y * 3); p[1] = (uint8_t)((x ^ y) * 5); p[2] = (uint8_t)(((x / 8 + y / 8) & 1) ? 230 : 20); p[3] = 255;
        }
    for (int y = 0; y < HH; y++)
        for (int x = 0; x < HW; x++) {
            uint8_t *p = g_hud + ((size_t)y * HW + x) * 4;
            if (x > 20 && x < 140 && y > 10 && y < 40) premult(p, 255, 255, 255, 160);   /* recuadro del HUD */
            else if ((x - 300) * (x - 300) + (y - 200) * (y - 200) < 900) premult(p, 30, 200, 250, 255);
            else memset(p, 0, 4);
        }
    for (int y = 0; y < VH; y++)
        for (int x = 0; x < VW; x++) {
            uint8_t *p = g_ui + ((size_t)y * VW + x) * 4;
            if (x > 1100 && y < 100) premult(p, 200, 200, 200, 200); else memset(p, 0, 4);   /* "tuerca" */
        }
    WNDCLASSA wc = { 0 };
    wc.lpfnWndProc = proc; wc.hInstance = GetModuleHandleA(NULL); wc.lpszClassName = "prueba_d3d12_pres";
    RegisterClassA(&wc);
    RECT r = { 0, 0, VW, VH };
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    HWND hw = CreateWindowA("prueba_d3d12_pres", "prueba presentador D3D12", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 60, 60,
                            r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    if (!hw || !d3d_iniciar(hw, VW, VH)) return 1;
    d3d_pso_cache_abrir("prueba_pso_cache.bin");
    ID3D12GraphicsCommandList *l = d3d_empezar_cuadro(1);
    D3dTextura juego;
    d3d_tex_crear(&juego, DXGI_FORMAT_B8G8R8A8_UNORM, JW, JH, 0, 0);
    d3d_tex_subir(l, &juego, 0, 0, JW, JH, g_juego, JW * 4);
    d3dp_guardar(l, &juego, 3);   /* por la ranura, como el modo Monitor */
    LARGE_INTEGER f, t0, t1;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t0);
    d3dp_empezar(l);
    int c = sab ? 3 : 0;
    d3dp_base(l, d3dp_ranura(3), c, 0, VW + c, VH, 0, 0);
    d3dp_subir(l, 0, g_hud, HW, HH, 0, 0, HW, HH);
    d3dp_capa(l, 0, 0, 0, VW, VH, 0);
    d3dp_subir(l, 1, g_ui, VW, VH, 1100, 0, VW, 100);   /* solo la zona sucia (el resto queda en 0 por la creacion) */
    d3dp_capa(l, 1, 0, 0, VW, VH, 0);
    QueryPerformanceCounter(&t1);
    double ms_cpu = (double)(t1.QuadPart - t0.QuadPart) * 1000.0 / (double)f.QuadPart;
    d3dp_leer(l, g_leido);
    d3d_terminar_cuadro(1);
    /* referencia en la CPU */
    uint32_t malos = 0, grandes = 0;
    for (int y = 0; y < VH; y++)
        for (int x = 0; x < VW; x++) {
            int xa, xb, ya, yb, hxa, hxb, hya, hyb;
            candidatos(x, VW, JW, &xa, &xb);
            candidatos(y, VH, JH, &ya, &yb);
            candidatos(x, VW, HW, &hxa, &hxb);
            candidatos(y, VH, HH, &hya, &hyb);
            const uint8_t *g = g_leido + ((size_t)y * VW + x) * 4, *u = g_ui + ((size_t)y * VW + x) * 4;
            int mejor = 999;
            for (int q = 0; q < 16 && mejor > 1; q++) {
                int sx = q & 1 ? xb : xa, sy = q & 2 ? yb : ya, hx = q & 4 ? hxb : hxa, hy = q & 8 ? hyb : hya;
                const uint8_t *b = g_juego + ((size_t)sy * JW + sx) * 4, *h = g_hud + ((size_t)hy * HW + hx) * 4;
                int m = 0;
                for (int k = 0; k < 3; k++) {
                    double v = h[k] + b[k] * (255 - h[3]) / 255.0;
                    v = u[k] + v * (255 - u[3]) / 255.0;
                    int d = abs(g[k] - (int)(v + 0.5));
                    if (d > m) m = d;
                }
                if (m < mejor) mejor = m;
            }
            malos += mejor > 1;
            grandes += mejor > 64;
        }
    fprintf(stderr, "[prueba-pres] %s: %u px distintos (>1 nivel), %u muy distintos (>64) de %d (%.3f %%); umbral 1 %% -> %s; "
            "componer (CPU, encolar) %.2f ms\n", sab ? "SABOTAJE base 3 px" : "normal", malos, grandes, VW * VH,
            100.0 * grandes / (VW * VH), grandes * 100u > (uint32_t)(VW * VH) ? "DISTINTA" : "IGUAL", ms_cpu);
    Sleep(500);
    d3d_pso_cache_guardar();
    d3d_cerrar();
    DestroyWindow(hw);
    return 0;
}
