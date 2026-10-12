@echo off
rem Super Mario 3D Land (port nativo) - abre el juego con la partida del dueno.
rem Ajustes: la tuerca o Esc dentro del juego (se guardan en sm3dl_ajustes.ini).
rem   "Cuadros por segundo": 30 (original) / 60 (interpolados)
rem   "Resolucion interna": 1x a 4x
cd /d "%~dp0"
if not exist "sesion_juego\jugar\guardado" (
    xcopy /e /i /q "sesion_juego\j8\guardado" "sesion_juego\jugar\guardado" >nul
)
set SM3DL_SIN_TRAZA=1
set SM3DL_GUARDADO=sesion_juego\jugar\guardado
echo Jugando... (cierra la ventana del juego para terminar; el log queda en sesion_juego\jugar\log.txt)
recomp\arranque\sm3dl.exe 2> "sesion_juego\jugar\log.txt"
