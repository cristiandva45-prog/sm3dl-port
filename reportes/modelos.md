# Modelos CGFX a glTF 2.0

Conversor: `tools\cgfx_gltf.py`. Las salidas quedan en `extraido\modelos_gltf\` (con la misma estructura de carpetas del romfs) y las previas en `extraido\modelos_gltf\_previas\`.

```
py -I tools\cgfx_gltf.py <archivo.szs|.bcmdl> <carpeta_salida> [--previa]
py -I tools\cgfx_gltf.py --todo extraido\romfs extraido\modelos_gltf [--previa]
py -I tools\cgfx_gltf.py --previa-de <archivo.gltf> <salida.png>
```

## Estructura CGFX verificada contra los bytes

Todos los punteros son relativos a la posición donde están escritos (`cgfx.rel`). Una "tabla-ptr" es un par `(cuenta, offset rel)` que apunta a un arreglo de offsets relativos.

| Objeto | Offset | Contenido (confirmado) |
|---|---|---|
| **CMDL** (tipo 0x40000092) | +0x0C | nombre |
| | +0x30 / +0x3C / +0x48 | escala, rotación y traslación del modelo; matrices local/world en +0x54 y +0x84 |
| | +0xB4 | tabla-ptr de **mallas** |
| | +0xBC | (n, DICT) de **materiales** |
| | +0xC4 | tabla-ptr de **shapes** |
| | +0xCC | (n, DICT) de nodos de malla (visibilidad) |
| | +0xE0 | ptr al **esqueleto**; solo existe si `flags & 0x80` |
| **Malla** SOBJ 0x01000000 | +0x18 / +0x1C | índice de shape / índice de material |
| | +0x20 | ptr al modelo dueño (offset negativo, comprobado que cae en el CMDL) |
| | +0x24 | visible (u8), prioridad, índice de nodo de malla (s16) |
| **Shape** SOBJ 0x10000001 | +0x1C | ptr al bounding box |
| | +0x20 | position offset (3 floats) |
| | +0x2C | tabla-ptr de face groups |
| | +0x38 | tabla-ptr de vertex buffers |
| | +0x40 | ptr a blend shape |
| **Face group** | +0 / +4 | n huesos y ptr a la paleta (`u32[]`) |
| | +8 | modo de skinning: 0 ninguno, 1 rígido, 2 suave |
| | +0xC | tabla-ptr de primitivas |
| **Primitiva** | +0 | tabla-ptr de index streams |
| **Index stream** | +0 | formato: 0x1401 u8, 0x1403 u16 |
| | +4 | modo (u8: 0 triángulos, 1 tira, 2 abanico) y visible (u8) |
| | +8 / +0xC | largo en bytes / ptr a los datos |
| **VB entrelazado** 0x40000002 | +0x14 / +0x18 | largo / ptr a los datos |
| | +0x24 | stride |
| | +0x28 | tabla-ptr de atributos |
| **Atributo** 0x40000001 (0x34 bytes) | +4 | uso: 0 Pos, 1 Nrm, 2 Tan, 3 Color, 4-6 UV0-2, 7 BoneIdx, 8 BoneWgt |
| | +0x24 | formato GL (0x1400-0x1403, 0x1406) |
| | +0x28 | elementos |
| | +0x2C | escala (float; p. ej. color 1/255, pesos 0,01) |
| | +0x30 | offset dentro del vértice |
| | (si no va entrelazado) | +0x14/+0x18 = largo/ptr del flujo propio |
| **Atributo fijo** 0x80000000 | +0xC / +0x10 | formato / elementos |
| | +0x18 / +0x1C | n floats / ptr a los floats. Ej.: hueso fijo 0 y peso fijo 1,0 en las mallas de los ojos de Mario |
| **Esqueleto** SOBJ 0x02000000 | +0x18 / +0x1C | (n, DICT) de huesos |
| | +0x20 | hueso raíz |
| | +0x24 | regla de escalado |
| **Hueso** (0xE0 bytes) | +0 | nombre |
| | +4 / +8 / +0xC | flags / id / id del padre (s32, −1 = raíz) |
| | +0x20 / +0x2C / +0x38 | escala, rotación euler XYZ en radianes, traslación |
| | +0x44 | local 3x4 por filas |
| | +0x74 | world: en el archivo viene en **identidad**, porque se rellena en tiempo de ejecución |
| | +0xA4 | **inverse bind**, que coincide con la que calculamos (error < 7e-6) |
| **MTOB** | +0x168 | n de coordinadores de textura |
| | +0x16C | 3 coordinadores de 0x58 bytes: fuente, mapeo (0 UV, 2 = mapa de entorno, p. ej. la moneda), cámara, tipo, escala, rot, trasl., matriz 3x4 en +0x28 |
| | +0x274..+0x280 | ptrs a los texture mappers |
| | +0x284 | ptr al shader (SHDR) |
| **Texture mapper** 0x80000000 | +8 | ptr a la textura: TXOB-referencia 0x20000004, con el nombre de la textura enlazada en +0x18 |
| | +0x1C | cabecera de comando PICA 0x809F0081 |
| | +0x24 | TEXUNIT0_PARAM: wrap S en los bits 12-14 y wrap T en los bits 8-10 (0 clamp, 2 repeat, 3 espejo) |

**Verificaciones hechas:**
- `T * Rz * Ry * Rx * S` reproduce la matriz local guardada (error 1e-8).
- Las mallas en modo **ninguno o rígido** traen los vértices en el espacio del hueso: las manos de Mario y el cuerpo del Goomba quedan en su sitio solo después de multiplicarlos por la world del hueso.
- Las mallas en modo **suave** ya vienen en espacio de modelo.
- **V de las UV: NO se invierte.** Con `1-v` Mario salía con la panza color piel y el bigote azul. Los PNG de `texturas.py` ya vienen volteados (`FLIP_TOP_BOTTOM`), así que la V del 3DS coincide con la de glTF. Si algún día cambia `texturas.py`, esto se rompe.

## Qué soporta el conversor
- **Geometría:** posición (con escala del atributo y position offset), normal, UV0 (con la matriz del coordinador 0) y color de vértice.
  - Índices u8/u16 en triángulos, tiras y abanicos.
  - Una primitiva glTF por face group, con los vértices compactados por grupo, porque cada grupo tiene su propia paleta de huesos.
- **Materiales:** textura base (`texturas_png\<szs>\<tex>.png` por ruta relativa, con respaldo a un índice global por nombre), wrap del sampler y `alphaMode MASK` si el PNG tiene transparencia.
  - Si el mapeo es de entorno (esfera o cubo), el material va sin textura y con el color medio de esa textura.
- **Esqueleto:** nodos con jerarquía y TRS (cuaternión a partir del euler XYZ), skin con inverse bind matrices y JOINTS_0/WEIGHTS_0 (hasta 4 pesos, normalizados).
  - Rígido y ninguno: 1 hueso con peso 1, y el vértice se lleva a la bind pose.
- **Validación** (`validar`): byteLength, rangos de bufferViews, min/max de POSITION (calculados sobre float32), count iguales, índices múltiplo de 3 y menores que el count, joints dentro de la skin, pesos que suman 1, material e imagen existentes.
- **Previa:** rasterizador propio con z-buffer (solo Pillow) que muestra frente (+Z) y lado (+X). El color es textura con su wrap × color de vértice × Lambert.

## Previas revisadas a ojo
- **Mario:** en pose T, con la gorra con la M, los ojos, el bigote, el overol azul con botones y los zapatos café.
- **Bloque ?:** el cubo con el signo de interrogación en todas las caras.
- **Moneda:** el disco con la ranura; dorado plano porque su textura es un mapa de entorno.
- **Goomba:** con la cara, las cejas, los colmillos y las patas.
- **Toad** (prueba extra): la forma está bien, pero la gorra y el chaleco salen en gris.

## Pendiente
1. **Combinadores TEV / colores constantes del material.** Muchas texturas son en escala de grises y el color lo pone el TEV (constantes en el MTOB +0x28..+0x100 y vertex color). Por eso Toad sale gris en vez de con manchas rojas y chaleco azul. Hay que leer los 6 stages del fragment shader del MTOB.
2. Mapas de entorno (`_spc`, mapeo 2) y texturas en los mappers 1 y 2 (especular, máscaras): hoy solo se exporta el mapper 0.
3. **Animaciones:** esqueléticas (`MarioAnimation.szs`, 174), de material (`.cmtpa`, `.cmcla`, p. ej. el parpadeo) y de visibilidad. Los nodos ya están en TRS, así que se pueden añadir canales glTF sin tocar la jerarquía.
4. Patrón de texturas de los ojos: hoy se usa siempre `.0`.
5. Blend shapes (ptr en shape +0x40, no se leen), UV1/UV2, tangentes, billboards de huesos, el modo de blending y cull del material (todo sale `doubleSided: false`), nodos de visibilidad de malla (hoy se exportan todas las mallas), el transform del modelo (identidad en las pruebas) y el `.glb`.
6. Unidades: se dejan las del juego (Mario mide unas 120 unidades de alto). Sin reescalar.

## Resultado del lote (`--todo extraido\romfs extraido\modelos_gltf`, 49 s)
- **1.066 modelos convertidos** y 1.896.077 triángulos en total.
- **0 szs con error** y **0 modelos con avisos** de validación.
  - Hubo 4 avisos de min/max por redondeo a float32 en modelos grandes de `BalanceTruck*`; se arreglaron calculando el min/max sobre los valores ya empaquetados.
- 600 szs no traen ningún CMDL (son solo config o colisión).
- **0 texturas referenciadas sin PNG** (contra el volcado de `texturas_png` a la hora de correr el lote).
- El detalle está en `extraido\modelos_gltf\_lote.txt`. El censo contaba 1.078 `.bcmdl`; la diferencia son archivos CGFX sin CMDL (solo texturas o animaciones).
