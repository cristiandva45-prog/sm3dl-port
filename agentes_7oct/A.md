# Bitácora agente A — raster GPU a 4x (7 oct noche)

Dueño de `recomp\render\raster_gl.c` + `raster_gl.h` (respaldos `.antes_A`). Exe `recomp\arranque\sm3dl_A.exe`.
Corredor: `powershell -File agentes_7oct\A\correr.ps1 <etiqueta> <res> [VAR=valor ...]` → `agentes_7oct\A\<etiqueta>\log.txt`.

## Paso 1 — cronómetros (hecho)
- `SM3DL_A_CRONO=1`: línea `[raster] crono xS vA-B:` cada 300 vblanks con ms POR VBLANK (CPU, pared del hilo) de:
  bajar / bajar.leer (glReadPixels síncrono) / ligar_nativo / dif.emitir / dif.espera (ClientWaitSync) / dif.resto /
  subir / subir.expandir / copiar_alta / alta / alta.leer / escala, y GPU ms/vblank por GL_TIME_ELAPSED asíncrono
  (anillo de 512 queries, se cosechan sin esperar; dibujos muestreados 1 de 8 y x8).

### Medido ANTES (exe A sin cambios de comportamiento, 45 s, guion j8, ventana oculta, régimen v1500+)
- ⚠️ En MIS corridas (ventana oculta) 4x NO está asfixiado: swaps/vblank 4x ≈ **1,87-1,90** (v2193→2671: 902 swaps / 478 vbl), 1x ≈ **2,00**. Pared del hilo: 4x ~11,6-12,2 ms/vblank, 1x 10,44 ms/vblank (TURBO=3 tope 5,6 ms: los dos van limitados por CPU). El 0,83 debe venir de la presentación (lado B) con ventana visible.
- 4x, ms POR VBLANK (CPU pared): alta 1,25-1,59 (de eso **alta.leer = glReadPixels síncrono 1,22-1,55**, 0,48 cuadros nuevos/vblank → ~2,6-3,2 ms por cuadro), dif.resto 1,16-1,26 (codificar el transfer a memoria; igual a 1x: 1,23-1,27), dif.emitir 0,2-0,36 (1x 0,16-0,19), dif.espera 0,003, ligar_nativo 0,000, copiar_alta 0,000, bajar 0,01, subir 0 (no hubo RT nuevos en régimen), escala 0.
- GPU (GL_TIME_ELAPSED): dibujos 0,9-2,9 ms/vblank a 4x vs 1,9-2,3 a 1x (ruido de escena; la GPU NO es el cuello: <25 % de un vblank), blits ligar/copiar/giro ~0,02-0,05 c/u.
- Conclusión: lo único de raster_gl que crece con 4x es el **glReadPixels síncrono del giro** (≈ la diferencia de pared 1x vs 4x).

## Paso 2 — raster_alta asíncrona (hecho)
- `raster_alta` nueva: giro (`alta_girar`) → glReadPixels a PBO (anillo 3) + fence; entrega lo que la GPU YA terminó (map+memcpy). 1 vblank de retraso como mucho. Primer cuadro o cambio de tamaño: espera (una vez). `SM3DL_ALTA_ASINC=0` = camino viejo (`raster_alta_sinc`, intacto). `SM3DL_ALTA_CPU=1` sigue igual.
- Verificación `SM3DL_ALTA_VERIFICAR=1`: al EMITIR se calcula el giro de CPU del MISMO cuadro (lee a->fbo) y al ENTREGAR se compara bit a bit. =2 sabotea 1 byte de lo entregado. Corrida verif4: **0 bytes distintos en 420 cuadros**.

## Paso 3 — API PARA B (hecho, en raster_gl.h)
- Prueba en proceso (con SM3DL_ALTA_VERIFICAR): al emitir llama `raster_alta_textura`, lee la textura con glGetTexImage(BGRA) y compara con la referencia CPU. =3 sabotea esa prueba. verif4: **0 distintos en 420 cuadros**.
- Sabotajes vistos FALLAR: `=2` (sab2) → "1 bytes distintos ... 360 de 360" (82 % de canales con color: no es negro); `=3` (sab3) → API "1 bytes distintos ... 343 de 343", mientras ASINC en la misma corrida da 0 de 300.

### Medido DESPUÉS (corridas seguidas: sinc4 = SM3DL_ALTA_ASINC=0, desp4 = nuevo; B corriendo a la vez → la pared es ruidosa)
| 4x, ms por vblank | base4 (antes) | sinc4 (viejo, misma tanda) | desp4 (asíncrono) |
|---|---|---|---|
| alta (total en el hilo) | 1,25-1,59 | 1,13-1,37 | **0,44** (0 ms de espera; queda el map+memcpy de 6 MB) |
| alta.leer (espera a la GPU) | 1,22-1,55 | ~igual | **0** (nunca tuvo que esperar) |
| swaps/vblank (v≥1500) | 1,91 | 1,80 | 1,80 |
- swaps/vblank no separa nada en mis corridas (oculta + B robando CPU: 1,8-1,9 con los dos caminos). La ganancia real se ve en el cronómetro: **~1 ms por vblank (~2 ms por cuadro del juego) devueltos al hilo**.
- 1x (base1): 2,00 swaps/vblank, pared 10,44 ms/vblank; raster_alta no corre a 1x (no cambia nada ahí).

## API PARA B (contrato; declarado en raster_gl.h, implementado y probado en raster_gl.c)
```c
int raster_alta_textura(unsigned dir_fisica, unsigned fmt, unsigned stride, unsigned ancho, unsigned alto,
                        unsigned *tex_gl, int *s, unsigned *gen);   /* mismos args que raster_alta */
int raster_gl_hacer_actual(void *hdc);                               /* HDC de la ventana visible */
int raster_alta_a_ventana(int x0, int y0, int x1, int y1, int lineal); /* blit al framebuffer 0 */
```
- `raster_alta_textura`: devuelve s (>1) o 0 (= no hay alta, usar la nativa como hoy). `*tex_gl` = `g_giro_tex`, GL_RGBA8 de (ancho*s)x(alto*s) YA GIRADA, **fila 0 abajo** (dibujada tal cual en el framebuffer 0 queda derecha). `*gen` cambia solo con cuadro nuevo (si no cambió, no hace falta re-presentar). Sin glReadPixels: solo hace el giro (1 triángulo) si el cuadro es nuevo. La textura es del raster: no borrarla ni tocarle parámetros; vale hasta la próxima llamada a raster_alta/raster_alta_textura.
- `raster_gl_hacer_actual(hdc)`: copia el pixel format del DC interno del raster al `hdc` (si aún no tiene; SetPixelFormat solo se puede UNA vez por ventana → si la ventana ya tiene otro pixel format, falla y devuelve 0) y hace `wglMakeCurrent(hdc, ctx_del_raster)`. Se puede dejar así: el raster dibuja en sus FBO y solo comprueba que el contexto sea el suyo. **Todo en el MISMO hilo** (el de las fibras).
- Presentar: `raster_gl_hacer_actual(hdc)` (una vez) → por cuadro: `raster_alta_textura(...)`; si devuelve >0: `raster_alta_a_ventana(x0,y0,x1,y1,lineal)` (coordenadas GL, origen ABAJO-izquierda: la pantalla de arriba en una ventana de alto H va en y0 = H - dy - dh) y lo demás (pantalla de abajo, HUD) dibujarlo también por GL (subir su BGRA a una textura y otro blit / quad); luego `SwapBuffers(hdc)`. ⚠️ Mezclar GDI (StretchDIBits/BitBlt) y GL en la MISMA ventana con doble búfer parpadea/se pisa: o todo por GL o una ventana hija para GL.
- vsync: `SwapBuffers` con vsync del driver BLOQUEA el hilo hasta el vblank del monitor (como `DwmFlush` hoy). Para no robarle tiempo al juego: `wglSwapIntervalEXT(0)` (WGL_EXT_swap_control; B lo carga con wglGetProcAddress con el contexto ya actual) y que el ritmo lo ponga el vblank emulado.
- Prueba: con `SM3DL_ALTA_VERIFICAR=1` cada cuadro emitido llama a `raster_alta_textura`, baja la textura con glGetTexImage y la compara con el giro de la CPU: 0 distintos en 420 cuadros (verif4); `=3` la sabotea y falla en 343/343 (sab3).

## Qué falta / propuestas (no aplicadas)
- Con la ventana por GL (B + API) desaparece también el map+memcpy de 0,44 ms/vblank y toda la conversión/StretchDIBits de B.
- `dif.resto` ~1,1-1,2 ms/vblank (igual a 1x y 4x): codificar en morton + gsp_display_transfer en CPU de lo que el juego "lee". Candidato siguiente para todo el raster (no es de 4x): codificar en la GPU (compute/shader que escriba ya en el formato y orden de la PICA) y bajar solo bytes finales.
- GPU de los dibujos a 4x: 1,5-3,8 ms/vblank (<25 % de un vblank) → la GPU NO es el cuello; MSAA/menos resolución en RT chicos no hace falta por ahora.
- `subir_color` (expandir en CPU) no aparece en régimen (0 llamadas); solo pega al crear RT/cambiar escala.

## Paso 2b — cero copia (hecho)
- PBOs con `glBufferStorage` + mapeo PERSISTENTE y COHERENTE (anillo 4, máx 2 pendientes al emitir → el último entregado nunca se reusa mientras la ventana lo lee). `raster_alta` devuelve el puntero al mapeo: sin map/unmap ni memcpy de 6 MB. `SM3DL_ALTA_CERO_COPIA=0` = map + memcpy (paso 2). Si el mapeo falla, cae solo a memcpy.
- Verificación: verif4c (=1) **0 distintos en 840 cuadros** (68-70 % de canales con color), API 0 en 840; sab2c (=2) **792 de 792** cuadros fallan.

## Números finales (corridas seguidas, sistema más quieto; el exe incluye lo que B tenga hoy en ventana.c)
| 4x, ms por vblank | sinc4b (SM3DL_ALTA_ASINC=0) | cero4 (final) |
|---|---|---|
| alta en el hilo | 0,68-1,26 (espera GPU 0,66-1,24) | **0,16** (0 esperas) |
| pared del hilo | 7,67-8,32 | 7,37-7,98 |
| swaps/vblank (v≥1500) | 1,992 | **1,994** |
| vblanks en 45 s | 5711 | 5949 (+4 %) |
- 1x final (cero1): 1,997 swaps/vblank, pared 5,57 ms/vblank (= tope de TURBO 3: sobra CPU).
- % libre a 4x (estimado): el hilo ocupa ~7,4-8,0 ms por vblank → ~45-48 % de 16,67 ms; **~52-55 % libre** (~15-16 ms ocupados por cuadro del juego de 33,3 ms). Medido con turbo (CPU sin dormir) y ventana oculta.
- Lo que queda del raster por vblank a 4x: dif.resto 1,19-1,27 + dif.emitir ~0,2 + dibujar 1,6-1,7 (CPU) — todo IGUAL que a 1x. GPU dibujos ~2,3 ms/vblank.
