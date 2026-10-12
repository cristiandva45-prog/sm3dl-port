# Agente B — arranque SM3DL (8 oct)

- Inicio: punto de parada rt_externo 0x001ED5B4 (lr=0x0028EAE0).
- Obstaculo 4: 0x1ED5B4 = puntero a funcion en el literal pool del constructor 0x38A188 (pasado a __aeabi_vec_ctor 0x28EAB4). Los constructores (arreglo 4) no existian cuando corrio descubrir_funciones -> sus literales nunca se sembraron. Arreglo 5 en generar.py (cierre de literales/saltos sobre las funciones nuevas): +28 funciones (17.652 -> 17.680).
- El sm3dl.exe NUEVO lo bloquea Smart App Control (Start-Process: "Una directiva de Control de aplicaciones bloqueo este archivo"). No se esquiva -> verificacion en Unicorn.
- Obstaculos 4-8 resueltos (detalle en recomp\arranque\BITACORA.md). PRIMER IPC: srv: RegisterClient 0x00010002 en 0x102B1C (traducidas 00000020 00000000). Exe llega a 417 IPC (srv, APT, ndm, fs+RomFS 202, cfg, gsp 138, hid, dsp 40). Parada actual: rt_externo 0x2DDC24 (blx r1 0x2F226C).
- Archivos: generar.py (arreglos 5-8), parchear.py (ldr pc,[sp],#k), compilar.py (servicios de C), unicorn_arranque.py (nuevo), BITACORA.md, log4-6.txt.
- Sabotajes: --quitar 1ED5B4 -> aviso; todo.c sin parche ldr pc -> aviso 0x380444 = fallo real del exe.
- No se cambio de base a recomp.py: no tiene arreglos 5-8 ni ldr pc,[sp],#k; seguir con la copia hasta integrarlos.
- PEDIDOS DE INTEGRACION (recomp.py / descubrir_funciones.py): (a) ldr pc,[sp],#k = retorno; (b) sembrar literales de los constructores (o correr descubrir con ellos); (c) punteros PC-relativos ldr+add pc; (d) destinos de salto directo rechazados "no termina" -> aceptar como funcion (los resuelve rt_llamar(fin)); (e) punteros de vtable dentro de rangos de Ghidra tras final incondicional; (f) mov{cc} pc, lr ya lo tiene A.
