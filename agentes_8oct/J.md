# Bitacora agente J (censo IPC, 8 oct 2026)
- Hecho: tools\censo_ipc.py -> extraido\ipc_comandos.tsv (139/139 svc 0x32 con cabecera, servicio, nombre azahar, llamadores, profundidad) y extraido\ipc_servicios.tsv; reportes\ipc_censo.md.
- Primera version dejaba 14 sin cabecera (str con writeback, strd, stm, registros sl/sb); corregido.
- Verificacion: 10 filas leidas a mano 10/10; sabotaje (2 parches en copia de code.bin via CENSO_CODE_BIN/CENSO_SALIDA) detectado.
- Hallazgos: no hay cadenas cam/ptm/ac/frd/boss/news/y2r/nim/ir...; handle 0x3E3190 nunca se escribe, forma = cam:u (hipotesis); hid/dsp/mic/cecd no alcanzables estaticamente (vtables/fabrica).
- Pedidos de integracion: ninguno obligatorio. Opcional: renombrar en simbolos.txt SvcX3E3190_* a CAMU_* (hipotesis) y nombrar 0x1056E8/0x105798 SRV_GetServiceHandle(cuerpo).
