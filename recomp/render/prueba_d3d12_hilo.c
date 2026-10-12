/* PROTOTIPO DEL PASO 7 (8 oct noche): presentacion en un HILO APARTE, independiente del ritmo del juego.
 *   - hilo "juego": cada ~33,4 ms (30 FPS) publica un estado {t_ms, x} de una barra que se mueve a velocidad
 *     constante; con TEMBLOR (+-3 ms, como el cierre real de los cuadros) y TIRONES (cada 97 cuadros, 60 ms);
 *   - hilo de presentacion (el principal): espera el objeto de latencia de la swap chain, calcula el instante en que
 *     se VERA la imagen (proximo refresco + 1), y dibuja la barra interpolada entre los dos estados que rodean
 *     (ese instante - RETRASO). RETRASO = 1 cuadro de juego + margen: siempre hay un estado posterior.
 * Mide el paso de la barra entre refrescos contra el ideal (velocidad x periodo), igual que [alto-paso].
 * Uso: prueba_d3d12_hilo.exe [segundos=8]. SM3DL_D3D_SABOTAJE=1: interpola con t = k/5 fijos (lo viejo) -> el error
 * TIENE que subir. SM3DL_D3D_SIN_TEMBLOR=1: juego perfecto (referencia). */
#include "d3d12_base.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define VEL 0.25          /* px por ms de juego: ~1,7 px por refresco de 144 Hz */
#define CUADRO_MS 33.367  /* 30 FPS del 3DS (2 vblanks de 59,83 Hz) */

typedef struct { double t, x; } Estado;
static volatile LONG g_n;          /* estados publicados */
static Estado g_est[64];           /* anillo */
static volatile LONG g_fin;
static LARGE_INTEGER g_f;

static double ahora_ms(void) { LARGE_INTEGER t; QueryPerformanceCounter(&t); return (double)t.QuadPart * 1000.0 / (double)g_f.QuadPart; }

static DWORD WINAPI hilo_juego(LPVOID p)
{
    (void)p;
    int temblor = !getenv("SM3DL_D3D_SIN_TEMBLOR");
    double t0 = ahora_ms(), prox = t0;
    unsigned k = 0;
    srand(12345);
    while (!g_fin) {
        prox += CUADRO_MS;
        double objetivo = prox + (temblor ? ((rand() % 601) - 300) / 100.0 : 0.0);   /* +-3 ms */
        if (temblor && k % 97 == 96) objetivo += 60.0;                                  /* tiron */
        while (ahora_ms() < objetivo - 1.5) Sleep(1);
        while (ahora_ms() < objetivo) YieldProcessor();
        /* el estado es del tiempo de JUEGO (k cuadros), no del reloj: la barra avanza VEL*CUADRO_MS por cuadro */
        Estado e = { t0 + (double)k * CUADRO_MS, (double)k * CUADRO_MS * VEL };
        g_est[(g_n) % 64] = e;
        InterlockedIncrement(&g_n);
        if (temblor && k % 97 == 96) prox += 60.0;   /* tras un tiron el juego no recupera el tiempo perdido */
        k++;
    }
    return 0;
}

static LRESULT CALLBACK proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_CLOSE) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(h, m, w, l);
}

int main(int argc, char **argv)
{
    int seg = argc > 1 ? atoi(argv[1]) : 8, sabotaje = getenv("SM3DL_D3D_SABOTAJE") != NULL;
    QueryPerformanceFrequency(&g_f);
    timeBeginPeriod(1);
    WNDCLASSA wc = { 0 };
    wc.lpfnWndProc = proc; wc.hInstance = GetModuleHandleA(NULL); wc.lpszClassName = "prueba_d3d12_hilo";
    RegisterClassA(&wc);
    RECT r = { 0, 0, 800, 200 };
    AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
    HWND hw = CreateWindowA("prueba_d3d12_hilo", "prueba hilo de presentacion", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100,
                            r.right - r.left, r.bottom - r.top, NULL, NULL, wc.hInstance, NULL);
    if (!hw || !d3d_iniciar(hw, 800, 200)) return 1;
    HANDLE hj = CreateThread(NULL, 0, hilo_juego, NULL, 0, NULL);
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_ABOVE_NORMAL);
    double per = 1000.0 / 144.0;   /* se corrige con lo medido */
    double t_ini = ahora_ms(), t_ult = 0, x_ant = -1, err = 0, ult_present = 0;
    unsigned pasos = 0, rep = 0, dobles = 0, n_pres = 0;
    double retraso = CUADRO_MS + 8.0;   /* margen para el temblor de +-3 ms */
    while (ahora_ms() - t_ini < seg * 1000.0) {
        MSG m;
        while (PeekMessageA(&m, NULL, 0, 0, PM_REMOVE)) { if (m.message == WM_QUIT) goto fin; DispatchMessageA(&m); }
        ID3D12GraphicsCommandList *l = d3d_empezar_cuadro(1);
        if (!l) break;
        double t = ahora_ms();
        if (ult_present > 0) { double d = t - ult_present; if (d > per * 0.5 && d < per * 1.5) per = per * 0.98 + d * 0.02; }
        ult_present = t;
        /* instante de JUEGO que corresponde a lo que se vera. La linea de tiempo del juego es cuadro x 33,367 ms (no
           la hora de cierre: asi el temblor de +-3 ms no entra). 'desfase' absorbe los tirones: tras uno el juego
           queda atrasado para siempre; si no hay estado para t_vis, se congela lo minimo y se corre el desfase. */
        static double desfase;
        static unsigned congelados;
        double t_vis = t + per - retraso - desfase;
        LONG n = g_n;
        double x = x_ant < 0 ? 0 : x_ant;
        if (n >= 2) {
            double ult_t = g_est[(n - 1) % 64].t;
            if (t_vis > ult_t) { desfase += t_vis - ult_t; t_vis = ult_t; congelados++; }
            else if (ult_t - t_vis > CUADRO_MS * 1.5) desfase -= 0.05;   /* sobra margen: recuperar latencia de a poco */
        }
        if (n_pres % 1152 == 1151) fprintf(stderr, "[prueba-hilo] desfase %.1f ms, refrescos congelados por falta de estado %u\n", desfase, congelados);
        if (n >= 2) {
            int j = n - 1;
            while (j > 0 && j > n - 63 && g_est[j % 64].t > t_vis) j--;
            Estado a = g_est[j % 64], b = g_est[(j + 1 < n ? j + 1 : j) % 64];
            double p = b.t > a.t ? (t_vis - a.t) / (b.t - a.t) : 1.0;
            if (p < 0) p = 0;
            if (p > 1) p = 1;
            if (sabotaje) p = floor(p * 5.0) / 5.0;   /* lo viejo: t = k/5 */
            x = a.x + (b.x - a.x) * p;
        }
        float fondo[4] = { 0.05f, 0.05f, 0.08f, 1 }, barra[4] = { 1, 0.8f, 0.1f, 1 };
        ID3D12GraphicsCommandList_ClearRenderTargetView(l, d3d_rtv_atras(), fondo, 0, NULL);
        D3D12_RECT rc = { (LONG)fmod(x, 760.0), 40, (LONG)fmod(x, 760.0) + 40, 160 };
        ID3D12GraphicsCommandList_ClearRenderTargetView(l, d3d_rtv_atras(), barra, 1, &rc);
        if (!d3d_terminar_cuadro(1)) break;
        n_pres++;
        if (x_ant >= 0 && t - t_ini > 1000.0) {   /* sin el arranque */
            double paso = x - x_ant, ideal = VEL * per;
            pasos++;
            err += fabs(paso - ideal) / ideal;
            rep += paso < 0.25 * ideal;
            dobles += paso > 1.5 * ideal;
        }
        x_ant = x;
        t_ult = t;
    }
fin:;
    (void)t_ult;
    g_fin = 1;
    WaitForSingleObject(hj, 1000);
    fprintf(stderr, "[prueba-hilo] %s%s: %u presentaciones (periodo medido %.3f ms = %.1f Hz), %u estados del juego; paso de la barra: "
            "error medio %.1f %%, repetidas %u, dobles %u (de %u); DXGI: %u refrescos sin imagen nueva\n",
            sabotaje ? "SABOTAJE t=k/5" : "interpolado al refresco", getenv("SM3DL_D3D_SIN_TEMBLOR") ? ", juego SIN temblor" : ", juego con temblor y tirones",
            n_pres, per, 1000.0 / per, (unsigned)g_n, pasos ? 100.0 * err / pasos : 0, rep, dobles, pasos, g_d3d.perdidos);
    d3d_cerrar();
    DestroyWindow(hw);
    timeEndPeriod(1);
    return 0;
}
