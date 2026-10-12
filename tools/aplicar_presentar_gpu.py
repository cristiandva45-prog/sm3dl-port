"""Presentacion por GPU (8 oct): conecta recomp/render/ventana_gpu.c con ventana.c, ventana_hud.c y ventana_ui.c."""
import os
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recomp", "render")

def parchear(nombre, pares):
    ruta = os.path.join(R, nombre)
    t = open(ruta, encoding="utf-8").read()
    for a, b in pares:
        assert t.count(a) == 1, (nombre, a[:80])
        t = b.join(t.split(a))
    open(ruta + ".tmp", "w", encoding="utf-8", newline="\n").write(t)
    os.replace(ruta + ".tmp", ruta)

# --- HUD: sobre una capa transparente, acumula alfa (premultiplicado) y anota la zona que toco
parchear("ventana_hud.c", [
    ("/* mezcla src sobre dst con alfa a (0..256) */\nstatic void mezclar(uint8_t *d, const uint8_t *s, int a)\n{\n"
     "    for (int c = 0; c < 3; c++) d[c] = (uint8_t)((s[c] * a + d[c] * (256 - a)) >> 8);\n}",
     "/* PRESENTACION POR GPU (ventana_gpu.c): con g_capa_hud el HUD se compone sobre TRANSPARENTE y se anota la zona */\n"
     "static int g_capa_hud;\nstatic RECT g_hud_sucio;\nstatic void gpu_hud_limpiar(void);\n"
     "/* mezcla src sobre dst con alfa a (0..256); el alfa de dst acumula (sobre transparente queda premultiplicado) */\n"
     "static void mezclar(uint8_t *d, const uint8_t *s, int a)\n{\n"
     "    for (int c = 0; c < 3; c++) d[c] = (uint8_t)((s[c] * a + d[c] * (256 - a)) >> 8);\n"
     "    d[3] = (uint8_t)((255 * a + d[3] * (256 - a)) >> 8);\n"
     "    if (g_capa_hud) {\n"
     "        size_t i = (size_t)(d - g_unica_bgra) / 4;\n"
     "        RECT p = { (LONG)(i % (size_t)g_u_w), (LONG)(i / (size_t)g_u_w), 0, 0 };\n"
     "        p.right = p.left + 1; p.bottom = p.top + 1;\n"
     "        if (g_hud_sucio.right <= g_hud_sucio.left) g_hud_sucio = p;\n"
     "        else {\n"
     "            if (p.left < g_hud_sucio.left) g_hud_sucio.left = p.left;\n"
     "            if (p.top < g_hud_sucio.top) g_hud_sucio.top = p.top;\n"
     "            if (p.right > g_hud_sucio.right) g_hud_sucio.right = p.right;\n"
     "            if (p.bottom > g_hud_sucio.bottom) g_hud_sucio.bottom = p.bottom;\n"
     "        }\n"
     "    }\n}"),
    ("    memcpy(g_unica_bgra, g_u_s > 1 ? g_alta_bgra : g_bgra, (size_t)g_u_w * g_u_h * 4);\n    if (!g_hud_visible) return;",
     "    if (g_capa_hud) gpu_hud_limpiar();   /* GPU: la imagen va aparte; aqui solo el HUD */\n"
     "    else memcpy(g_unica_bgra, g_u_s > 1 ? g_alta_bgra : g_bgra, (size_t)g_u_w * g_u_h * 4);\n"
     "    if (!g_hud_visible) return;"),
])

# --- interfaz: idem
parchear("ventana_ui.c", [
    ("static uint8_t *ui_px;   /* destino BGRA de arriba a abajo */",
     "static uint8_t *ui_px;   /* destino BGRA de arriba a abajo */\n"
     "static int g_ui_seguir;   /* GPU: anotar en g_ui_sucio la zona que se toca (capa transparente) */\nstatic RECT g_ui_sucio;"),
    ("    d[2] = (uint8_t)((((rgb >> 16) & 0xFF) * a + d[2] * (256 - a)) >> 8);\n}",
     "    d[2] = (uint8_t)((((rgb >> 16) & 0xFF) * a + d[2] * (256 - a)) >> 8);\n"
     "    d[3] = (uint8_t)((255 * a + d[3] * (256 - a)) >> 8);   /* sobre transparente: premultiplicado */\n"
     "    if (g_ui_seguir) {\n"
     "        if (g_ui_sucio.right <= g_ui_sucio.left) SetRect(&g_ui_sucio, x, y, x + 1, y + 1);\n"
     "        else {\n"
     "            if (x < g_ui_sucio.left) g_ui_sucio.left = x;\n"
     "            if (y < g_ui_sucio.top) g_ui_sucio.top = y;\n"
     "            if (x + 1 > g_ui_sucio.right) g_ui_sucio.right = x + 1;\n"
     "            if (y + 1 > g_ui_sucio.bottom) g_ui_sucio.bottom = y + 1;\n"
     "        }\n"
     "    }\n}"),
])

parchear("ventana.c", [
    # ajuste nuevo: presentar=gpu
    ("static int g_menu, g_sel, g_titulo;", "static int aj_presentar_gpu;   /* presentar=gpu en el .ini (ventana_gpu.c) */\nstatic int g_menu, g_sel, g_titulo;"),
    ("        else if (!strncmp(l, \"resolucion=\", 11) && atoi(l + 11) >= 1 && atoi(l + 11) <= 4) aj.resol = atoi(l + 11);\n",
     "        else if (!strncmp(l, \"resolucion=\", 11) && atoi(l + 11) >= 1 && atoi(l + 11) <= 4) aj.resol = atoi(l + 11);\n"
     "        else if (!strncmp(l, \"presentar=\", 10)) aj_presentar_gpu = !strncmp(l + 10, \"gpu\", 3);\n"),
    ("aj.fps30 ? 30 : 60, aj.resol);\n    fclose(f);",
     "aj.fps30 ? 30 : 60, aj.resol);\n    if (aj_presentar_gpu) fprintf(f, \"presentar=gpu\\n\");\n    fclose(f);"),
    # pintar(NULL): solo componer en g_px (verificacion de la GPU)
    ("    BitBlt(dc, 0, 0, w, h, g_mem, 0, 0, SRCCOPY);\n", "    if (!dc) return;   /* verificacion de la presentacion por GPU: solo componer en g_px */\n    BitBlt(dc, 0, 0, w, h, g_mem, 0, 0, SRCCOPY);\n"),
    # el DC de la ventana para GL
    ("    wc.lpfnWndProc = proc;\n", "    wc.style = CS_OWNDC;   /* presentacion por GPU: el contexto GL queda sobre este DC */\n    wc.lpfnWndProc = proc;\n"),
    # WM_PAINT
    ("        HDC dc = BeginPaint(h, &ps);\n        pintar(dc);\n        EndPaint(h, &ps);",
     "        HDC dc = BeginPaint(h, &ps);\n        if (g_gpu == 1 && aj.unica) gpu_pintar(); else pintar(dc);\n        EndPaint(h, &ps);"),
    # incluir el modulo antes de ventana_presentar
    ("void ventana_presentar(const GspPresentacion *p)\n{", "#include \"ventana_gpu.c\"\n\nvoid ventana_presentar(const GspPresentacion *p)\n{"),
    # pantalla de arriba: en GPU, la textura (sin bajar 6 MB)
    ("            int s = (!p->negro && p->rgba) ? raster_alta(p->dir_fisica, p->formato & 7u, p->stride, 400, 240, &hi) : 0;\n",
     "            g_arr_dir = p->dir_fisica; g_arr_fmt = p->formato & 7u; g_arr_stride = p->stride; g_arr_ok = !p->negro && p->rgba;\n"
     "            int gpu = aj.unica && gpu_activo() == 1;\n"
     "            unsigned tex = 0, gen = 0;\n"
     "            int s = !g_arr_ok ? 0 : gpu ? raster_alta_textura(g_arr_dir, g_arr_fmt, g_arr_stride, 400, 240, &tex, NULL, &gen)\n"
     "                                       : raster_alta(p->dir_fisica, p->formato & 7u, p->stride, 400, 240, &hi);\n"
     "            if (gpu) {   /* la imagen no pasa por la CPU: solo marcar que hay una nueva */\n"
     "                static unsigned gen_antes;\n"
     "                int capa = s > 1;\n"
     "                if (capa != g_capa_hud) { g_capa_hud = capa; g_sucio_comp = 1; g_hud_base_sucia = 1; g_hud_subido_w = 0; }\n"
     "                if (gen != gen_antes) { gen_antes = gen; g_sucio_pint = 1; }\n"
     "                hi = NULL;\n"
     "            } else if (g_capa_hud) { g_capa_hud = 0; g_sucio_comp = 1; }\n"),
    ("            if (g_alta_s) {   /* ya viene girada en la GPU y en BGRA con A = 255 */",
     "            if (g_alta_s && hi) {   /* ya viene girada en la GPU y en BGRA con A = 255 */"),
    # despues de componer: la base (1x) cambio
    ("                    componer_unica_imagen();\n                    g_sucio_comp = 0;\n                    g_sucio_pint = 1;",
     "                    componer_unica_imagen();\n                    g_sucio_comp = 0;\n                    g_sucio_pint = 1;\n                    g_hud_base_sucia = 1;"),
    # pintar del flujo normal y del menu
    ("                if (pintar_ya) {\n                    HDC dc = GetDC(g_v);\n                    pintar(dc);\n                    ReleaseDC(g_v, dc);",
     "                if (pintar_ya && g_gpu == 1 && aj.unica) { gpu_pintar(); g_cr_pint++; }\n"
     "                else if (pintar_ya) {\n                    HDC dc = GetDC(g_v);\n                    pintar(dc);\n                    ReleaseDC(g_v, dc);"),
    ("            HDC dc = GetDC(g_v);   /* pintar directo (una ventana oculta de prueba no recibe WM_PAINT) */\n            pintar(dc);\n            ReleaseDC(g_v, dc);",
     "            if (g_gpu == 1 && aj.unica) gpu_pintar();\n"
     "            else {\n"
     "                HDC dc = GetDC(g_v);   /* pintar directo (una ventana oculta de prueba no recibe WM_PAINT) */\n"
     "                pintar(dc);\n"
     "                ReleaseDC(g_v, dc);\n"
     "            }"),
])
print("ok")
