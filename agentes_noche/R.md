# Bitácora agente R (rasterizador) — tanda nocturna

## Estado
- Inicio: leído BRIEF_COMUN y ESTADO (160-213). Leyendo raster_gl.c, tev_glsl.py, G/I/F.
- Respaldos: recomp/render/{raster_gl.c,raster_gl.h,pica.c,pica.h,pica_dibujar.c,texturas.c,texturas.h}.antes_R
- Diseño decidido (leído en Azahar sw_rasterizer/sw_lighting/glsl_fs_shader_gen, sin copiar):
  * TEV en ENTEROS u8 en el shader (ivec, divisiones enteras truncadas = tev_ref por construcción), no float+q8.
  * OUTMAP real (0x04F-0x056 + OUTMAP_MASK): el .vert se envuelve (main -> pica_vmain) y un main nuevo remapea o[] a
    semánticas; color abs+saturado POR VÉRTICE (Azahar output_vertex.cpp); sin mapear = 1.0.
  * Luz por fragmento leída de los registros 0x140-0x1D9 (habilitada por 0x1C6 bit0 == 0, NO por 0x08F), LUTs 24x256
    en textura RG32F; geometry shader de flip de cuaternión solo con luz (como Azahar GL).
  * Profundidad: z = -gl_FragCoord.z*escala + offset (el raster viejo usaba +, BUG); w-buffer si 0x06D bit0 == 0.
- Hito 1 (compila, corre): uber-shader 100% por uniforms -> CORRECTO en estructura pero LENTO en la Intel UHD 770:
  bajar_color (glReadPixels = espera a la GPU) 9,4 s de 12 s; el juego hace 1.788 listas/25 s (antes 4.445) y no
  pasa del logo (el viejo llega a "Press A to Start!" en ~4 s). Causa: shader enorme (luz + 6 etapas con switch y
  divisiones enteras). Arreglo: especializar por clave (estructura TEV/luz = constantes de compilación, valores =
  uniforms; el compilador pliega los switch) + div255 por multiplicación-desplazamiento ((x+1+(x>>8))>>8, exacta
  en 0..65534 verificado).
- Hito 2 (especialización): 60.000 dibujos/25 s, 4.098 listas (viejo 4.445), bajar_color 3,6 s/25 s, 0 errores GL.
  Capturas (agentes_noche/R/mos02.png, izq viejo / der nuevo): el juego llega igual a "Press A to Start!" y ahora
  se ve como el juego real: texto naranja/amarillo, icono verde, "Return to HOME Menu" legible, "© 2011 Nintendo"
  negro (el raster viejo ignoraba el TEV: color×tex0 dejaba el texto crema y el pie casi invisible). 6 fragment
  shaders distintos en la pantalla de título.
- Hito 3 (arnés propio, GPU real, raster_gl.c REAL + pica.c + gsp.c sobre VRAM falsa): agentes_noche/R/prueba_raster.c
  + herr/probar_raster.py. TEV especializado: 332/332 recetas reales iguales a tools/tev_ref.py, 0 LSB
  (2 dibujos x 256 frag. c/u). Las 300 al azar: 247/300 en esa corrida; las 53 restantes fallaban porque la caché de
  fragment shaders se llenó (1.024: tev_upd iba en la clave) -> arreglado (tev_upd ahora es uniform + vaciar la caché
  al llenarse), recompilado pero SIN volver a correr. Sabotajes 1-10 preparados en prueba_raster.c, SIN correr.
- Topología 3 (shader sin GS) = lista: integrado (pedido de P).
- Guion g3 (P) con guardado propio agentes_noche/R/g: la pantalla de abajo YA NO sale blanca (título correcto con
  TEV, mos02.png), pero con luz (3D) el juego se arrastra: 'tiempo dibujar' 56 s en 75 s y solo 2 capturas.
  Sospecha: preparar_luts re-sube la textura 24x256 RG32F en cada dibujo (luz_lut_ver cambia con cada escritura de LUT)
  y/o compilación de shaders por clave de luz. PENDIENTE URGENTE antes de usar en 3D.
  Programa desconocido visto: fnv512 9FCCAA64 (no está en programas.tsv).

## Estado al cierre (sano / no sano)
- Compila (sm3dl_R.exe). 2D/título: SANO y mejor que antes. 3D con luz: CORRECTO pero MUY LENTO -> para avanzar
  en niveles usar los .antes_R (cp *.antes_R) hasta arreglar el rendimiento de la luz.
- Sin verificar aún: luz contra luz_frag_ref (falta herr/probar_raster_luz.py), stencil/culling/tijera/niebla/mipmaps,
  modo inmediato (implementado en pica.c, sin prueba).
## Archivos tocados
recomp/render/raster_gl.c (reescrito), raster_uber.c (nuevo, incluido), pica.c (f20, versiones de LUT, modo
inmediato), pica.h (campos nuevos de PicaEstado). Respaldos *.antes_R. Arnés y herramientas en agentes_noche/R/.
## Pedidos de integración: ninguno (raster_uber.c va por #include, no toca compilar.py).
