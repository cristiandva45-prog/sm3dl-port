# Agente I — fragment lighting PICA200 (8 oct)
Estado: arrancado. Leyendo pica_registros.md y pica_materiales.tsv.

## Paso 1 (hecho): layout MTOB de fragment lighting + censo
- `tools\luz_frag_mtob.py` decodifica: MTOB+0x18 flags (bit0 = luz frag), +0x288 -> fragment shader
  (+0x10 flags clamp/D0/D1/geo0/geo1/refl, +0x14 capa, +0x18 fresnel, +0x1C/20/24 bump), +0x28 -> 6 ptr LUT
  (RR,RG,RB,D0,D1,FR) {entrada, escala, ->sampler{tipo,tabla,sampler}}. El ABS no esta en el material:
  vive en la seccion LUTS (sampler +8). 237 (tabla,sampler) definidas, 51 contenidos, 10 nombres ambiguos, 0 sin resolver.
- Censo: 4.579 mats, 0 errores, 4.146 con luz frag, 105 configuraciones de codigo.
- Salidas: extraido\shaders\luz\censo_luz.{txt,tsv}, luts.json
- Decodificado de LUT (valor 12b/4095, |dif| 11b/2047, signo bit23) verificado por continuidad v[i]+d[i]=v[i+1]: 13.005/13.005 pares.
- 10 nombres de LUT con versiones distintas entre archivos (StageBasicTableSet/StageLight 4 versiones...): se resuelve local primero; la global es la 1a ordenada (PENDIENTE: saber cual carga el runtime).
- configs.json: 105 configuraciones con ejemplo real (archivo/material/tablas/escalas).
## Paso 2: generador GLSL (en curso)
- (retomado tras corte de API) archivos revisados: compilan; salida ajustada a u8 truncado (convencion TEV de G).
## Paso 2-3 (hecho)
- tools\luz_frag_glsl.py -> extraido\shaders\luz\L0..L104.glsl + flip_quat.geom. Salida u8 truncado (luz_q8, convencion q8 de G).
- tools\luz_frag_ref.py: referencia escalar independiente (sw_lighting de Azahar), decodifica LUT cruda por su cuenta.
- tools\probar_luz_frag.py (venv_gl): 105/105 configs (4.146 mats), 430.080 canales, 99,97 % exactos, max 1 LSB; flip GS OK.
  12/12 sabotajes FALLAN (ver reportes\luz_fragmentos.md). El 8 (redondear vs truncar) solo lo pesca el criterio >=99,5 % exactos.
- Cruce con TEV: 489 pares (receta, luz), 382 con luz.
## Archivos tocados
tools\luz_frag_mtob.py, luz_frag_glsl.py, luz_frag_ref.py, probar_luz_frag.py; extraido\shaders\luz\*; reportes\luz_fragmentos.md
## Pendientes / pedidos de integracion
- G: reemplazar uniforms frag_primario/secundario por luz_frag(pica_o1, pica_o2.xyz, t0,t1,t2, ...) + pegar L<id>.glsl.
- Pipeline: flip_quat.geom entre VSH y FS (salidas del VSH como g_pica_oN).
- Runtime: luces de escena (CFLT) + DA/spot, colores luz*material, LUTs a textura; cual de las 10 LUT ambiguas carga el runtime.
