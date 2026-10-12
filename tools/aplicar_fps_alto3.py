"""Modo monitor, 3a version (8 oct): el dueno lo abrio a pantalla completa y se vio a ~2 FPS con el juego a velocidad
completa por dentro. Causa: el presentador esperaba que qpcVBlank de DWM cambiara; a pantalla completa (flip
independiente) DWM no compone y ese valor se congela -> casi nunca presentaba. Ahora el refresco en curso se CALCULA
con el reloj (QPC) y el periodo del monitor, usando qpcVBlank solo como fase."""
import os
B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp")
ruta = os.path.join(B, "render", "ventana_gpu.c")
t = open(ruta, encoding="utf-8").read()
a = """    long long vb = 0;
    if (DwmGetCompositionTimingInfo(NULL, &ti) == S_OK && ti.qpcRefreshPeriod) vb = (long long)ti.qpcVBlank;
    else {   /* sin DWM: por reloj */
        LARGE_INTEGER q, f;
        QueryPerformanceCounter(&q);
        QueryPerformanceFrequency(&f);
        vb = q.QuadPart / (f.QuadPart / (long long)gpu_hz());
    }
"""
b = """    /* el refresco EN CURSO = (ahora - fase) / periodo. qpcVBlank de DWM solo da la fase: a pantalla completa (flip
       independiente) DWM no compone y qpcVBlank se queda quieto (8 oct: se veia a ~2 FPS esperando que cambiara) */
    static long long fase, periodo;
    static ULONGLONG fase_cuando;
    LARGE_INTEGER q, f;
    QueryPerformanceCounter(&q);
    QueryPerformanceFrequency(&f);
    if (!periodo || GetTickCount64() - fase_cuando > 1000) {
        periodo = (long long)((double)f.QuadPart / gpu_hz());
        if (DwmGetCompositionTimingInfo(NULL, &ti) == S_OK && ti.qpcVBlank) fase = (long long)(ti.qpcVBlank % (unsigned long long)periodo);
        fase_cuando = GetTickCount64();
    }
    if (periodo <= 0) return;
    long long vb = (q.QuadPart - fase) / periodo;
"""
assert t.count(a) == 1
t = b.join(t.split(a))
open(ruta + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
os.replace(ruta + ".tmp", ruta)
print("ok")
