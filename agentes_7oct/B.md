# Bitácora del agente B — presentación/ventana a 4x (7 oct noche)

Archivos míos: `recomp\render\ventana.c`, `ventana_hud.c`, `ventana.h` (respaldos `*.antes_B`). Exe: `recomp\arranque\sm3dl_B.exe`.
Corridas: `agentes_7oct\B\correr.ps1 -Res 1|4 -Nombre X [-Extra "VAR=v;VAR2=v"]` (guion j8, oculta, turbo 3, 45 s, guardado fresco, crono ON). Logs en `agentes_7oct\B\log_*.txt`.
Ajustes del dueño en `sm3dl_ajustes.ini` (unica, escala 3, completa, nitido, vsync, 60, resol 4): NO se tocó el .ini.

## Paso 1 — cronómetros (`SM3DL_VENTANA_CRONO=1`)
`[ventana-crono]` cada 600 cuadros de la de abajo: ms por vblank de conv (RGBA→BGRA nativo), raster_alta, copia_alta (memcpy 6 MB),
titulo, unica (componer_unica), oscuro, stretch (StretchDIBits+GdiFlush), ui, bitblt, dwmflush, bombear, TOTAL.

**¿Con `SM3DL_VENTANA_OCULTA=1` corre pintar()? SÍ.** `ventana_presentar` llama `pintar(GetDC(g_v))` directo: StretchDIBits a la DIB en
memoria, BitBlt y DwmFlush corren igual. PERO: (a) oculta NO aplica pantalla completa → la ventana mide 1200x720 (escala 3), no el monitor;
(b) BitBlt a una ventana oculta cuesta 0,01 ms (recortado) = no representa el BitBlt real a pantalla completa; (c) DwmFlush sí espera la composición.

### Línea base (exe B solo con cronómetros, misma tanda, oculta)
| | swaps/vblank (régimen, vb ~1800→3000) | conv | raster_alta | copia_alta | unica | stretch | ui | dwmflush | TOTAL |
|---|---|---|---|---|---|---|---|---|---|
| 1x | (5762-3348)/(3019-1796) = **1,97** | 0,10 | 0 | 0 | 0,03-0,14 | 0,43 | 0-0,2 | **4,5-4,9** | 5,2-5,7 |
| 4x | (7872-5718)/(4034-2957) = **2,00** | 0,10 | 0,66-1,29 | 0,55 | 0,5-1,45 | 0,50 | 0-0,2 | **2,2-4,2** | 5,6-7,2 |

Hallazgos:
- En ESTA corrida 4x ya va a velocidad completa (2,0 swaps/vblank) con la ventana oculta: la presentación cuesta ~6-7 ms/vblank, la mitad
  es ESPERA en DwmFlush (no CPU). El 0,83 del brief no se reproduce aquí (¿build anterior, o carga del otro agente, o ventana visible a pantalla completa?).
- El juego produce 1 cuadro cada 2 vblanks (nota del coordinador): la mitad de los pintar/componer/DwmFlush rehace una imagen idéntica.
- Lo caro de verdad, en orden: DwmFlush (espera) > componer_unica a 4x (1,4 ms) > raster_alta (0,7-1,3, de A) > copia_alta (0,55) > stretch (0,5).
- HALFTONE no aplica (filtro=nitido → COLORONCOLOR). Oscuro: 0 (menú cerrado).

## Paso 2 — cambios (interruptor `SM3DL_VENTANA_SALTAR`, por defecto 1; `=0` = camino viejo completo)
- `ventana.c:ventana_presentar` — detección de imagen nueva SIN tocar raster_gl.c: la conversión RGBA→BGRA compara cada píxel con lo
  que ya había (xor, gratis en el mismo bucle); la copia en alta solo se hace si `memcmp` dice que cambió (o cambió la escala).
  En UNICA con alta, la nativa de arriba NO ensucia (no se usa; y como raster_alta de A entrega con 1 vblank de retraso, si ensuciaba
  se repintaba CADA vblank: medido cambios arriba=300/alta=300 desfasados → 0 saltados).
- `ventana_hud.c` — `componer_unica` partida en `hud_histeresis()` (corre SIEMPRE, cuenta vblanks igual que antes) +
  `componer_unica_imagen()` (solo si hubo cambio o cambió la visibilidad del HUD). `componer_unica()` = las dos (camino viejo / menú).
- `pintar` solo si hay imagen nueva, interfaz animada (título, tuerca, o el último pintado llevaba tuerca), o cambió el tamaño.
- `pintar` — oscurecido del menú UNA vez por apertura (se invalida en `abrir_menu` y en cada `cambiar`).
- `cambiar(OP_RESOL)` — `raster_escala` se aplica UNA vez al cerrar el menú (`g_resol_pend`).
- `pintar` — **DwmFlush fuera** con SALTAR (`SM3DL_VENTANA_DWMFLUSH=1` lo devuelve). Es pura espera del único hilo: 2-10 ms/vblank
  según la carga; al pintar solo cuadros nuevos pierde la fase y espera MÁS (7-10 ms). Con DWM (siempre activo en Win10/11) lo pintado por
  GDI no se rasga; el ritmo ya lo pone el vblank emulado. ⚠️ Decisión para el coordinador/dueño: el ajuste "vsync" queda sin efecto en GDI
  hasta que exista la presentación GL (ahí vsync = SwapInterval).
- No hecho: doble estirado en modo DOBLE con alta (el dueño usa UNICA; recortar la fuente de StretchDIBits con DIB top-down puede cambiar el
  redondeo de COLORONCOLOR → no se puede garantizar igualdad sin verificarlo aparte).

## Verificación (en el MISMO proceso) — `SM3DL_VENTANA_VERIFICAR=1|2`
En cada vblank que se SALTA, se recompone por el camino viejo (`componer_unica_imagen` sobre los mismos datos) y se comparan los bytes con
lo retenido. Cubre detección, histeresis e interfaz (el pintado solo depende de la composición + UI, y con UI se pinta siempre).
- `verif4x_b` (4x, + menú de prueba en vb 2500): **1800 saltados verificados, 0 con diferencias**.
- Sabotaje `=2` (`sabot4x`: la detección ignora los cambios de la pantalla de abajo): **lo caza** en cuanto aparece el HUD
  (vb 1912: 28.264 bytes distintos; 109 de 600 saltados con diferencias).

## Números antes/después (corridas seguidas, oculta, turbo 3, 45 s; con el agente A corriendo a la vez)
| | swaps/vblank | vblanks en 45 s | ms/vblank presentación (TOTAL) | dwmflush | unica | stretch | pintados/600 |
|---|---|---|---|---|---|---|---|
| 4x viejo (`viejo4x_b`) | (4536-3500)/(2748-2110) = **1,62** | 2.748 | 11,8 | 9,1 | 1,13 | 0,53 | 600 |
| 4x nuevo (`nuevo4x_d`) | (11556-9880)/(5832-4994) = **2,00** | 5.832 | **2,97** | 0 | 0,91 | 0,38 | 353 |
| 1x viejo (`viejo1x`) | (5910-4944)/(3350-2825) = **1,84** | 3.350 | 9,8 | 9,0 | 0,13 | 0,42 | 600 |
| 1x nuevo (`nuevo1x`) | (15634-14438)/(7864-7264) ≈ **2,00** | 7.864 | **0,48** | 0 | 0,08 | 0,24 | 300 |
(La línea base del paso 1, sin A corriendo, daba 4x viejo 2,00 con dwmflush 2-4 ms: el costo de DwmFlush depende de la carga/fase.)
Lo que queda a 4x (ms/vblank): copia_alta 1,0 (memcmp+memcpy de 6 MB), unica 0,9, raster_alta 0,46 (A), stretch 0,38, conv 0,13.
⚠️ No medible oculto: BitBlt real y StretchDIBits al tamaño del MONITOR (oculta no aplica pantalla completa: 1200x720).

## Paso 3 — presentación por GL (DISEÑO; la API de A llegó en raster_gl.h pero no alcanzó el tiempo para hacerla con verificación)
API de A: `raster_alta_textura(...,&tex,&s,&gen)`, `raster_gl_hacer_actual(hdc)`, `raster_alta_a_ventana(x0,y0,x1,y1,lineal)`.
Diseño (archivo nuevo `recomp\render\presentar_gl.c`, interruptor `SM3DL_PRESENTAR_GL=1`, respaldo GDI = lo de hoy):
1. Ventana: clase con `CS_OWNDC`; `raster_gl_hacer_actual(GetDC(g_v))` una vez (A copia el pixel format). `wglSwapIntervalEXT(aj.vsync)`
   = vsync real (y entonces sí tiene sentido; SwapBuffers bloquea igual que DwmFlush → para "N presentaciones por cuadro con ritmo propio"
   usar SwapInterval 0 + un temporizador propio, o un hilo de presentación con contexto compartido que haga SwapBuffers).
2. Por presentación: `raster_alta_a_ventana(dx,dy,dx+dw,dy+dh, aj.suave)` — sin bajar 6 MB, sin memcmp, sin StretchDIBits.
3. HUD integrado + interfaz (título/tuerca/menú): se componen en CPU en una capa BGRA con alfa SOLO del tamaño de sus rectángulos
   (barra ~260x30, círculo 64x64 a escala s, UI) y se suben con glTexSubImage2D solo cuando `gen` o la UI cambian; se dibujan con
   blending encima. Necesita un programa GL mínimo (quad + textura + blend) → o lo agrega A como `raster_capa_a_ventana(tex_bgra,...)`
   (PEDIDO a A), o presentar_gl.c carga sus propios punteros con wglGetProcAddress.
4. Igualdad: el blending GL (float, /255) NO da los mismos bytes que `mezclar` (entero, >>8). Para igualdad bit a bit, la capa del HUD
   se compone YA mezclada en CPU sobre el recorte de la imagen de ARRIBA en alta (los rectángulos donde va el HUD) (glReadPixels solo de esos rectángulos pequeños, asíncrono por PBO)
   y se dibuja opaca. Verificador: `glReadPixels` del framebuffer 0 tras dibujar vs `g_px` del camino GDI del mismo cuadro (con filtro
   nítido y destino de tamaño entero la imagen debe coincidir; con escalado no entero comparar contra el mismo muestreo NEAREST).
   Sabotaje: desplazar la capa 1 px.
5. Pedido al coordinador: agregar `presentar_gl.c` a `compilar.py` (o incluirlo desde ventana.c como ventana_hud.c para no tocar compilar.py).
