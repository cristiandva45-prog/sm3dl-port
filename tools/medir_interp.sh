#!/bin/sh
# Mide la interpolacion con el detector de laboratorio (8 oct): misma partida por guion hasta el 1-1, y en N cuadros
# compara el intermedio mezcla(A,C) con el cuadro REAL B. Uso: sh tools/medir_interp.sh <exe> <etiqueta> [vblank] [cuadros] [entorno extra...]
cd "$(dirname "$0")/.." || exit 1
EXE=$1; ET=$2; VB=${3:-5600}; N=${4:-300}; shift 4 2>/dev/null
D=sesion_juego/medir_$ET
rm -rf "$D"; mkdir -p "$D/volcado"
cp -r agentes_noche/P/guardado_w1_base "$D/guardado"
env "$@" SM3DL_SIN_AUDIO=1 SM3DL_VENTANA_OCULTA=1 SM3DL_SIN_TRAZA=1 SM3DL_TURBO=3 SM3DL_GUARDADO="$D/guardado" \
    SM3DL_GUION=sesion_vel/guiones/g7_jugar_1_1.txt SM3DL_INTERP=1 SM3DL_REPETIR=$VB SM3DL_REPETIR_CADA=$N \
    SM3DL_REPETIR_VOLCAR="$D/volcado" SM3DL_HASTA_VBLANK=$((VB + 2 * N + 200)) \
    nice -n 10 "recomp/arranque/$EXE" 2> "$D/log.txt"
grep -E "^\[destello\] [0-9]+ cuadros|\[interp\] re-ejecucion" "$D/log.txt" | tail -4
