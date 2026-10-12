# Bitácora agente D (controles) — 8 oct 2026
Hecho: (1) cadena estática del pad documentada en `reportes/hid.md` (sección "Cadena completa" y "Servicio HLE"): 0x1F3890 -> estado 0x424FC8 -> 0x297690 ReadPad -> 0x1F52E8 -> 0x2DA4FC -> 0x2DB000 -> isPadHold/getPadLeftStick -> PlayerInput_update. (2) `recomp/hid/servicio_hid.c/.h` + `prueba_servicio_hid.c`: OK; sabotajes detectados (3 y 1 fallas).
Archivos: recomp/hid/servicio_hid.{c,h}, prueba_servicio_hid.{c,exe}, reportes/hid.md (sección añadida), esta bitácora.
Pendiente: llamador por fotograma de 0x2DB000 y derivación +0x110 -> +0x10C; confirmar con el primer arranque que el juego no espera los eventos; supuesto accel z=-512.
Pedido de integración: ver reportes/hid.md sección 5 (5 puntos).
