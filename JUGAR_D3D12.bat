@echo off
rem Super Mario 3D Land (port nativo) - PRIMERA PRUEBA DEL BACKEND DIRECT3D 12 (9 oct 2026), con la partida del dueno.
rem Igual que JUGAR.bat pero con SM3DL_BACKEND=d3d12 y el exe integrado de la tanda de 15 agentes.
rem La 1a vez tarda ~16 s extra al arrancar (el driver compila los PSO); despues ~2 s.
rem Antes de jugar se copia la partida a sesion_juego\jugar\guardado_antes_d3d12 (por si acaso).
rem (S2, 9 oct) Al CERRAR el juego: si la partida dejo efectos (PS) sin DXIL en extraido\shaders\desconocidos_d3d12\
rem (iban por el uber, lento), tools\shaders_nuevos_al_cerrar.py los convierte e instala solo (precompilar_d3d12.py
rem desconocidos, prioridad baja, log en sesion_juego\jugar\shaders_nuevos.txt). Si falla, la cache queda igual.
rem Prueba sin juego: set SM3DL_PRUEBA_SIN_JUEGO=1 y SM3DL_SHADERS_PRUEBA=<carpeta> (ver agentes_dx12\S2.md).
setlocal
cd /d "%~dp0"
if defined SM3DL_PRUEBA_SIN_JUEGO goto al_cerrar
if not exist "sesion_juego\jugar\guardado" (
    xcopy /e /i /q "sesion_juego\j8\guardado" "sesion_juego\jugar\guardado" >nul
)
if not exist "sesion_juego\jugar\guardado_antes_d3d12" (
    xcopy /e /i /q "sesion_juego\jugar\guardado" "sesion_juego\jugar\guardado_antes_d3d12" >nul
)
set SM3DL_SIN_TRAZA=1
set SM3DL_GUARDADO=sesion_juego\jugar\guardado
set SM3DL_BACKEND=d3d12
rem 10 oct: intermedios del modo Monitor por la "cinta" de H1 (medido: 3,0 -> 1,8 ms por intermedio). Para volver: =0
set SM3DL_D3D12_REPETIR_RAPIDO=1
echo Jugando con Direct3D 12... (cierra la ventana para terminar; log en sesion_juego\jugar\log_d3d12.txt)
agentes_dx12\principal\sm3dl_d3d12_todo.exe 2> "sesion_juego\jugar\log_d3d12.txt"

:al_cerrar
rem Sin efectos nuevos no se hace nada (ni se busca Python).
set "S2_DESC=extraido\shaders\desconocidos_d3d12"
if defined SM3DL_SHADERS_PRUEBA set "S2_DESC=%SM3DL_SHADERS_PRUEBA%\desconocidos"
if not exist "%S2_DESC%\F_*.glsl" goto fin
rem py puede no estar en el PATH de un cmd abierto con doble clic: PATH, luego el lanzador por usuario, luego el global.
set "S2_PY="
for /f "delims=" %%P in ('where py 2^>nul') do if not defined S2_PY set "S2_PY=%%P"
if not defined S2_PY if exist "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" set "S2_PY=%LOCALAPPDATA%\Programs\Python\Launcher\py.exe"
if not defined S2_PY if exist "%SystemRoot%\py.exe" set "S2_PY=%SystemRoot%\py.exe"
if not defined S2_PY goto sin_py
"%S2_PY%" -I "tools\shaders_nuevos_al_cerrar.py"
goto pausa

:sin_py
echo Hay efectos nuevos para preparar pero no encontre Python (py). Quedan guardados para la proxima vez.

:pausa
rem Unos segundos para leer el mensaje antes de que la ventana se cierre (en prueba, no).
if not defined SM3DL_PRUEBA_SIN_JUEGO timeout /t 8 /nobreak >nul 2>&1
:fin
endlocal
