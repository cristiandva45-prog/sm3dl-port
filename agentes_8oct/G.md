# G — verificador diferencial de los fragment shaders TEV (8 oct 2026) — TERMINADO

## Resultado
- **332/332 recetas iguales** a la referencia: 679.936 casos (8 dibujos x 256 fragmentos por receta, entradas
  aleatorias u8 + bordes 0,1,2,126-129,253-255; tev_update aleatorio/0/0xFF00), **diferencia 0 LSB en todos**
  (GPU Intel UHD 770, FBO RGBA32F, tolerancia 1/255). Siguen compilando y enlazando 332/332 (`tev_glsl.py --validar`).
- Antes de los arreglos: **59/332** (generador viejo; reproducible con `--generador <copia vieja>`).

## Archivos
- `tools/tev_ref.py` (nuevo): modelo entero u8 del combinador, escrito desde Azahar `renderer_software/sw_texturing.cpp`
  (GetColorModifier/GetAlphaModifier/ColorCombine/AlphaCombine) + `sw_rasterizer.cpp` WriteTevConfig + regs_texturing.h.
  Modo 'real' (sin truncar) y `variante=` (hipotesis alternativas) SOLO para diagnosticar.
- `tools/probar_tev.py` (nuevo): `tools\.venv_gl\Scripts\python.exe tools\probar_tev.py [-d 8] [--sabotaje 1|2|3]
  [--solo R12,..] [--generador ruta] [-v]`. Puntos de 1 px, tex0-2 = texturas RGBA8 256x1 NEAREST (texel i = fragmento i).
  Clasifica cada caso que falla por la hipotesis que lo explica. ~90 s con -d 8.
- `tools/tev_glsl.py` (arreglado) + escribe `extraido/shaders/frag/recetas.json` (firmas, para no repetir el censo).
- `extraido/shaders/frag/R*.frag` regenerados.

## Diferencias encontradas en el generador viejo (por tipo, -d 2: casos / recetas)
1. Precision: float sin cuantizar vs u8 truncado por etapa (acumula hasta 10 LSB): 80.032 / 272.
   Arreglo: q8() = floor(clamp(x)*255+1e-3)/255 tras cada operacion (antes de la escala).
2. ADDS con 0.5 en vez de 128/255 y DOT3 en float en vez de la formula entera por canal: ~2.036 casos de 1-4 LSB / ~40.
   Arreglo: medio = 128/255; dot3_u8() con ((2a-255)(2b-255)+128)/256 truncado hacia 0.
3. Etapa 0 con fuente de color "previo" (Azahar: pasa a ser la fuente 3) y etapa 0 tipo "paso" con fuente 3 != previo
   (no es paso): 512 / 1 (R106, ShadowVolumeMat00: salia 0 en vez de tev_const[0].rgb).
4. Etapa "paso" que no actualizaba el buffer del combinador (y que ignoraba escala x2/x4): 97 / 1.
5. Etapa 0 leia tev_buffer_color por la fuente 0xD; en Azahar lee 0 (el color entra desde la etapa 1). Arreglado;
   ninguna receta lo ejercita de verdad (0 casos).

## Sabotajes (copia en memoria del generador; deben FALLAR) — -d 2
- 1 LERP con pesos cruzados: 232/332, exit 1.  2 escala x4 -> x2: 310/332, exit 1.  3 operando alfa 1-a lee a: 331/332, exit 1.
- Ademas el generador viejo completo: 59/332.

## Pendientes / preguntas abiertas
- Azahar no es consistente consigo mismo: el rasterizador software TRUNCA cada etapa y aplica la peculiaridad
  "previo->fuente 3" solo a las fuentes de color 1-2 de la etapa 0; el generador GLSL de Azahar REDONDEA (byteround),
  la aplica tambien al alfa y salta la etapa 0 "paso" sin la peculiaridad. Se siguio el software (referencia del
  brief). Diferencia esperable vs hardware: <=1 LSB por etapa. Si un dia hay capturas de hw, esto se ajusta en q8.
- No cubierto: fragment lighting (frag_primario/secundario son uniforms), tex3 procedural, DOT3 en el combinador de
  alfa (ninguna receta), alpha test/niebla/blend.

## Pedidos de integracion
- Ninguno obligatorio. Quien consuma los .frag: los uniforms no cambiaron; `buf_prev` de la etapa 0 ahora es 0.
