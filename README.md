# sm3dl-port — Super Mario 3D Land nativo en PC

Port nativo a Windows de **Super Mario 3D Land** (Nintendo 3DS) por **recompilación estática ARM11 → C**, con un runtime propio que reemplaza los servicios del 3DS y la GPU PICA200 por OpenGL / Direct3D 12.

Ya corre el bucle principal y se juega: niveles a color, hasta 4x de resolución interna, 60 FPS interpolados, una sola pantalla y backend Direct3D 12 (el lanzador `JUGAR_D3D12.bat`). Es un **proyecto en curso**: no está terminado.

## ⚠️ Necesitas tu propio juego

Este repositorio **no trae nada de Nintendo**: ni la ROM, ni el ejecutable del juego, ni texturas, modelos, sonidos, textos o niveles, ni el código C que se genera a partir del binario. Solo están las **herramientas** y el **runtime** escritos para el port.

Para usarlo necesitas **un volcado propio y descifrado** de tu cartucho de *Super Mario 3D Land* (USA, `CTR-P-AREE`, title ID `0004000000054000`). Todo lo demás se genera a partir de ese archivo con los scripts de `tools/` y `recomp/`. No pidas ni compartas ROMs aquí.

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `tools/` | Extracción y conversión: ExeFS/RomFS, SZS/SARC, BYML, CGFX → glTF, shaders PICA → GLSL/HLSL, texturas |
| `recomp/` | Traductor ARM → C (`recomp.py`), verificadores contra Unicorn y el runtime: `runtime`, `gpu`, `render` (OpenGL y D3D12), `audio`, `hid`, `sistema`; el arranque está en `recomp/arranque/` (`main.c`, `compilar.py`) |
| `decomp/` | Primer intento de decompilación a mano, con verificador |
| `extraido/` | Solo el **mapa de símbolos** (`simbolos.txt`) y las tablas de análisis (funciones, actores, vtables). El resto se regenera |
| `reportes/`, `agentes_*/` | Notas de investigación y bitácoras |
| `ESTADO.md` | La bitácora completa del proyecto: qué se sabe, qué funciona y el próximo paso. **Empieza por aquí** |

## Por dónde empezar

```
py -I tools\extraer_code.py "<tu_juego>.3ds" extraido
py -I tools\listar_romfs.py "<tu_juego>.3ds" extraido\romfs_lista.txt extraido\romfs
```

Luego sigue `recomp/README.md` (traducción y compilación con `zig cc`) y `ESTADO.md`. Los `.bat` de la raíz lanzan el juego ya compilado: esperan encontrar en `recomp/arranque/` o `agentes_dx12/principal/` el `.exe` que hayas compilado tú, y una partida en `sesion_juego/`.

Requisitos: Windows 10/11 x64, Python 3 (`py`), `ziglang` (pip) como compilador, y `capstone`/`unicorn` para los verificadores.

## Contribuir

Cualquiera puede modificar, arreglar y mejorar el port: abre un *issue* o manda un *pull request*. Antes de empezar, lee `ESTADO.md` para ver qué se sabe y qué falta. Una sola regla: **nunca subas nada sacado del juego** (ROM, texturas, modelos, sonidos, textos ni el C generado).

## Licencia

El código de este repositorio es **MIT** (ver `LICENSE`). La licencia no cubre el juego ni su contenido.

## Aviso legal

Proyecto de investigación y preservación hecho por fans, sin relación con Nintendo. *Super Mario 3D Land* y todo su contenido son propiedad de Nintendo. Para usarlo debes tener una copia legítima del juego.
