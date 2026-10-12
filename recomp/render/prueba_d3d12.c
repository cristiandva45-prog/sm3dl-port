/* PRUEBA DE LA BASE D3D12 (8 oct noche): ventana 800x480, limpia a un color que cambia por cuadro y presenta con la
 * swap chain flip + objeto de latencia. Mide el intervalo entre presentaciones (QPC) y los refrescos sin imagen nueva
 * de DXGI. Liviana: solo ClearRenderTargetView. Uso:
 *   prueba_d3d12.exe [segundos=4] [vsync=1]
 *   SM3DL_D3D_SABOTAJE=1: duerme 12 ms cada 7 cuadros -> la medicion TIENE que ver refrescos perdidos. */
#include "d3d12_base.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

static LRESULT CALLBACK proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_CLOSE) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(h, m, w, l);
}

int main(int argc, char **argv)
{
    int seg = argc > 1 ? atoi(argv[1]) : 4, vsync = argc > 2 ? atoi(argv[2]) : 1;
    int sabotaje = getenv("SM3DL_D3D_SABOTAJE") != NULL;
    WNDCLASSA wc = { 0 };
    wc.lpfnWndProc = proc; wc.hInstance = GetModuleHandleA(NULL); wc.lpszClassName = "prueba_d3d12";
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    RegisterClassA(&wc);
    RECT r = { 0, 0, 800, 480 };
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    HWND hw = CreateWindowA("prueba_d3d12", "prueba D3D12", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100,
                            r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    if (!hw || !d3d_iniciar(hw, 800, 480)) { fprintf(stderr, "[prueba] no se pudo iniciar\n"); return 1; }
    LARGE_INTEGER f, t0, ta, t;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t0);
    ta = t0;
    double suma = 0, suma2 = 0, peor = 0;
    unsigned n = 0, largos = 0;
    for (unsigned k = 0;; k++) {
        MSG m;
        while (PeekMessageA(&m, NULL, 0, 0, PM_REMOVE)) { if (m.message == WM_QUIT) goto fin; DispatchMessageA(&m); }
        QueryPerformanceCounter(&t);
        if ((t.QuadPart - t0.QuadPart) / f.QuadPart >= seg) break;
        ID3D12GraphicsCommandList *l = d3d_empezar_cuadro(vsync);
        if (!l) break;
        float c[4] = { (k % 144) / 144.0f, 0.2f, 1.0f - (k % 144) / 144.0f, 1.0f };
        ID3D12GraphicsCommandList_ClearRenderTargetView(l, d3d_rtv_atras(), c, 0, NULL);
        if (sabotaje && k % 7 == 6) Sleep(12);
        if (!d3d_terminar_cuadro(vsync)) break;
        QueryPerformanceCounter(&t);
        double ms = (double)(t.QuadPart - ta.QuadPart) * 1000.0 / (double)f.QuadPart;
        ta = t;
        if (k >= 30) {   /* sin el arranque */
            n++; suma += ms; suma2 += ms * ms;
            if (ms > peor) peor = ms;
        }
    }
fin:;
    double media = n ? suma / n : 0, desv = n ? sqrt(suma2 / n - media * media) : 0;
    /* largos = intervalos > 1,5 x la media */
    (void)largos;
    fprintf(stderr, "[prueba] %s, vsync %d%s: %u cuadros medidos, intervalo medio %.3f ms (%.1f Hz), desv %.3f ms, peor %.2f ms; DXGI: %u presentaciones, %u refrescos sin imagen nueva\n",
            g_d3d.nombre_gpu, vsync, sabotaje ? ", SABOTAJE" : "", n, media, media > 0 ? 1000.0 / media : 0, desv, peor,
            g_d3d.presentados, g_d3d.perdidos);
    d3d_cerrar();
    DestroyWindow(hw);
    return 0;
}
