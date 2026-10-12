# Fragment lighting del PICA200: censo, GLSL y verificador (agente I, 8 oct 2026)

## Herramientas
- `tools\luz_frag_mtob.py`: decodifica la luz por fragmento de cada material (MTOB) y de las LUTs (sección LUTS).
  - `censo` genera `extraido\shaders\luz\censo_luz.{txt,tsv}`, `configs.json` y `luts.json`. Tarda unos 10 s.
- `tools\luz_frag_glsl.py`: genera `extraido\shaders\luz\L0..L104.glsl`, uno por configuración, y `flip_quat.geom`.
- `tools\luz_frag_ref.py`: referencia escalar en Python, reimplementada desde `sw_lighting.cpp` de Azahar. No comparte código con el generador y decodifica las LUTs crudas por su cuenta.
- `tools\probar_luz_frag.py`: verificador diferencial en GPU. Se corre con `tools\.venv_gl\Scripts\python.exe`.

## Layout (no es comando PICA; el `LIGHTING_CONFIG0` del material es solo una plantilla)
- **MTOB +0x18:** flags. El bit 0 indica luz por fragmento.
- **MTOB +0x24:** colores float (emisión, ambiente, difuso, especular 0 y 1, constantes).
- **MTOB +0x288 → fragment shader:**
  - `+0x10` flags: clamp, D0, D1, geo0, geo1, reflexión
  - `+0x14` capa: 0..7, que pasa a config PICA 0..6 y 8
  - `+0x18` Fresnel: 0 = no, 1 = primaria, 2 = secundaria, 3 = ambas
  - `+0x1C` textura de bump · `+0x20` modo de bump · `+0x24` renormalización
  - `+0x28` → 6 punteros de LUT (RR, RG, RB, D0, D1, FR). Cada LUT tiene entrada, código de escala y un sampler con el nombre de su tabla.
- **El "absoluto" de cada LUT NO está en el material.** Está en el sampler de la sección LUTS, en `+8`. Los datos son 256 palabras `LIGHTING_LUT_DATA` en 2 ráfagas:
  - bits 0-11: valor/4095
  - bits 12-22: |dif|/2047
  - bit 23: signo de la diferencia

  Este decodificado se verificó por continuidad, `v[i]+d[i] = v[i+1]`, en **13.005/13.005** pares.

## Censo (4.579 materiales, 0 errores)
- **4.146 con luz por fragmento** (90,5 %) y 433 sin luz. Los tienen 105 configuraciones de código distintas.
- **Config PICA:**
  - 3 (D0/D1/Fresnel): 3.774
  - 0: 355
  - 2: 10
  - 6: 7

  Ningún material usa las configs 1, 4, 5 ni 7(8). Con eso, la reflexión RR/RG/RB casi no existe: solo 8 materiales la piden.
- **LUT activas:**
  - D0:NH, D1:NV, FR:LN (todas con signo): 2.501
  - D0:NV, D1:NV, FR:LN: 768
  - sin ninguna LUT: 346
  - 38 combinaciones en total
- **Entradas usadas:** NH, NV, LN, VH y SP. CP aparece en 5 materiales con config ≠ 7, donde vale 0.
- **Valor absoluto:** casi todo usa entrada con signo. Solo 13 materiales usan entrada absoluta.
- **Escalas:** de ×0,25 a ×8.
- **Fresnel:** secundaria 3.508, ninguno 527, ambas 111. Nunca solo primaria.
- **Factor geométrico:** geo0 en 1.508, geo0+geo1 en 55, solo geo1 en 12.
- **Clamp highlights:** 0 materiales.
- **Bump (siempre normal map, nunca tangent map):** 1.421 materiales, en las texturas 0, 1 o 2. Casi todos renormalizan.
- **Sombras:** el material no tiene campos de sombra, así que no hay sombras de material.
- **Luz por vértice y hemisférica:** 1 material.
- **Número de luces, spot y atenuación por distancia:** NO son del material. Los pone el runtime desde la escena; aquí son uniforms.
- **LUTs:** 237 nombres (tabla/sampler) con 51 contenidos distintos. Hay 10 nombres con versiones distintas entre archivos, por ejemplo `StageBasicTableSet/StageLight` con 4. Se resuelve primero la tabla del propio archivo y, si no está, la global (la primera ordenada). **PENDIENTE: cuál carga el runtime.**
- **Cruce con el TEV:** 489 pares (receta TEV, config de luz) distintos. Los materiales con luz están en 382 de esos pares.

## GLSL
Cada `L<id>.glsl` es autocontenido: uniforms, helpers y `void luz_frag(vec4 normquat, vec3 vista, vec4 t0, vec4 t1, vec4 t2, out vec4 primario, out vec4 secundario)`.

**Qué es código fijo por configuración:**
- config y LUTs activas
- entrada de cada LUT y si es absoluta o con signo
- clamp, geo0 y geo1
- selector de Fresnel (se aplica solo en la última luz)
- bump: modo, textura y renormalización

**Qué es dato (uniforms):**
- `luz_fuente[8]`: color ya multiplicado por el material, posición, dirección, dos caras, atenuación por distancia y spot
- `luz_num` y `luz_ambiente_global`
- `luz_luts`: textura RG32F de 256×N (valor, diferencia), leída con `texelFetch`
- `luz_lut_fila[6]` y `luz_lut_escala[6]`
- la entrada, el absoluto y la escala del spot

**Salida:** u8 **truncado** (`luz_q8`), con la misma convención que el `q8` del TEV del agente G.

`flip_quat.geom` alinea el signo de los cuaterniones de los 3 vértices con el del primero antes de interpolar (`FlipQuaternionIfOpposite`). Sin él, q y -q se promedian a ~0.

## Verificación (Intel UHD 770, GL 3.3)
- **Resultado:** **105/105 configuraciones (4.146/4.146 materiales)**. Se usan las LUT reales del material de ejemplo, de 0 a 4 luces al azar, y la atenuación por distancia y el spot con LUTs al azar.
- **Precisión:** 430.080 canales comparados, 99,97 % exactos. Ningún canal difiere más de 1 LSB; los de 1 LSB son floors que caen a lados distintos entre la GPU y Python.
- **Geometry shader de flip:** OK.
- **12/12 sabotajes se ven fallar:**

| # | Sabotaje | Resultado |
|---|---|---|
| 1 | LUT con signo sin interpolar | 8/105 |
| 2 | Fresnel en la primera luz | 42/105 |
| 3 | cuaternión con w negado | 0/105 |
| 4 | factor geométrico sin min | 69/105 |
| 5 | índice con signo sin envolver | 33/105 |
| 6 | vector medio sin normalizar | 33/105 |
| 7 | bump sin renormalizar | 63/105 |
| 8 | redondear en vez de truncar | 74 % exactos, por debajo del 99,5 % exigido |
| 9 | spot ignorado | 98/105 |
| 10 | decodificar sin el signo de la diferencia | 2/105 |
| 11 | sin el geometry shader de flip | flip FALLA, máx. 48 LSB |
| 12 | atenuación por distancia con la distancia a la mitad | 10/105 |

## Pedidos de integración
1. **TEV (agente G, `tev_glsl.py`):** por cada par (receta, L) del material, cambiar los `uniform vec4 frag_primario/frag_secundario` por variables locales que se llenan con `luz_frag(pica_o1, pica_o2.xyz, t0, t1, t2, frag_primario, frag_secundario)` antes de las etapas, y pegar `L<id>.glsl` arriba. Son 382 pares con luz. Los 433 materiales sin luz siguen recibiendo primaria y secundaria constantes (en el PICA, con la luz apagada valen 0).
2. **Pipeline:** poner `flip_quat.geom` entre el vertex shader y el fragment shader. Para eso las salidas del VSH se renombran a `g_pica_oN`.
3. **Runtime:** cargar los colores de luz multiplicados por el material (especular, difuso y ambiente del MTOB+0x24). También subir las LUTs a `luz_luts` desde `luts.json` y las luces de la escena (CFLT) con su atenuación por distancia y spot. Falta decodificar las luces de escena y la escritura en `0x1C0–0x1D9` del código.
