# Grafo de acciones de Mario (PlayerActionGraph_build)

Generado por `tools\grafo_legible.py` desde la emulacion (`tools\emular_grafo.py`). Las aristas van en el orden en que el juego las registra (se evalúan en ese orden y gana la primera que se cumple — CONFIRMADO en PlayerActionExecutor_selectNext 0x0018144C).

## Correr  (nodo 0x100000D0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si pulsó A/B (≤5f)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Caer** si NO en suelo
- → **EmpujarPared?** si durante 15 frames: (pared al frente encarada (normal·frente ≥ K) Y flag9c Y NO pared al frente con código 1 Y stick hacia adelante)
- → **Deslizar agachado** si (stick hacia adelante (N frames) Y mantiene L/R Y en suelo)
- → **Deslizar agachado** si (mantiene L/R Y en suelo)
- → **Frenar** si stick contrario a la velocidad (frenar)
- → **Esperar** si velocidad ≈ 0

## Esperar  (nodo 0x10000100)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Caer** si NO en suelo
- → **Agachado** si mantiene L/R
- → **Giro(TurnPoint)** si stick hacia atrás
- → **Correr** si stick movido

## Giro(TurnPoint)  (nodo 0x10000140)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si pulsó A/B (≤5f)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Caer** si NO en suelo
- → **Agachado** si mantiene L/R
- → **Correr** si (Giro(TurnPoint)+4.vf0 Y stick movido)
- → **Esperar** si Giro(TurnPoint)+4.vf0

## Salto  (nodo 0x100001D0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## Caer  (nodo 0x10000250)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## CaerInicio?  (nodo 0x100005E0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## CaerInicio2?  (nodo 0x10000660)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## SaltoPared  (nodo 0x10000330)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## RebotePisotón  (nodo 0x10000E20)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## LuigiMove(flotar)  (nodo 0x100006E0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Caer** si Hélice.vf4
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## FinAgachado  (nodo 0x10000560)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Esperar** si anim "SquatEnd" terminó
- → **Salto** si pulsó A/B (≤5f)

## Deslizar agachado  (nodo 0x100003E0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **RebotePisotón** si (ctx1a.vf0 Y pisó a un enemigo (ctx8.bit1))
- → **SaltoAtras** si (NO ctx1a.vf0 Y pulsó A/B (≤5f))
- → **SaltoLargo** si (recuerda(…) Y ((NO ctx1a.vf0 O mantiene L/R) Y (pulsó A/B (≤5f) Y en suelo)))
- → **SaltoLargo** si ((NO ctx1a.vf0 O mantiene L/R) Y (pulsó A/B (≤5f) Y en suelo))
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo)
- → **Caer** si (NO mantiene L/R Y NO en suelo Y ctx1a.vf0)
- → **FinAgachado** si (NO mantiene L/R Y en suelo Y ctx1a.vf0)
- → **Agachado** si (velocidad² < umbral Y anim "TailAttackSquatGround" terminó Y anim "TailAttackSquatAir" terminó)
- → **AtaqueColaSuelo** si ((forma == X O forma == X O forma == X) Y (valor previo de … Y (pulsó X/Y (≤5f) Y en suelo)))
- → **AtaqueColaSuelo** si ((forma == X O forma == X O forma == X) Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si (valor previo de … Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si (pulsó X/Y (≤5f) Y en suelo)

## Deslizar agachado  (nodo 0x10000410)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **RebotePisotón** si (ctx1a.vf0 Y pisó a un enemigo (ctx8.bit1))
- → **SaltoAtras** si (NO ctx1a.vf0 Y pulsó A/B (≤5f))
- → **SaltoLargo** si ((NO ctx1a.vf0 O mantiene L/R) Y (pulsó A/B (≤5f) Y en suelo))
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo)
- → **Caer** si (NO mantiene L/R Y NO en suelo Y ctx1a.vf0)
- → **FinAgachado** si (NO mantiene L/R Y en suelo Y ctx1a.vf0)
- → **Agachado** si (velocidad² < umbral Y anim "TailAttackSquatGround" terminó Y anim "TailAttackSquatAir" terminó)
- → **AtaqueColaSuelo** si ((forma == X O forma == X O forma == X) Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si (pulsó X/Y (≤5f) Y en suelo)

## Deslizar agachado  (nodo 0x10000440)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **SaltoAtras** si (NO ctx1a.vf0 Y pulsó A/B (≤5f))
- → **SaltoAtras** si ((NO ctx1a.vf0 O mantiene L/R) Y (pulsó A/B (≤5f) Y en suelo))
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo)
- → **Caer** si (NO mantiene L/R Y NO en suelo Y ctx1a.vf0)
- → **FinAgachado** si (NO mantiene L/R Y en suelo Y ctx1a.vf0)
- → **Agachado** si (velocidad² < umbral Y anim "TailAttackSquatGround" terminó Y anim "TailAttackSquatAir" terminó)
- → **AtaqueColaSuelo** si ((forma == X O forma == X O forma == X) Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si (pulsó X/Y (≤5f) Y en suelo)

## Agachado  (nodo 0x100004A0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **RebotePisotón** si (ctx1a.vf0 Y pisó a un enemigo (ctx8.bit1))
- → **SaltoAtras** si ((NO ctx1a.vf0 O mantiene L/R) Y (pulsó A/B (≤5f) Y en suelo))
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo)
- → **AtaqueColaSuelo** si ((forma == X O forma == X O forma == X) Y velocidad² < umbral Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si ((forma == X O forma == X O forma == X) Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si ((Agachado+4 anim al 100% O NO velocidad² < umbral) Y (pulsó X/Y (≤5f) Y en suelo))
- → **AtaqueColaSuelo** si (pulsó X/Y (≤5f) Y en suelo)
- → **FinAgachado** si (NO (NO ctx1a.vf0 O mantiene L/R) Y en suelo)
- → **Caer** si NO (NO ctx1a.vf0 O mantiene L/R)

## SaltoAtras  (nodo 0x10000530)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **Sentón(HipDrop)** si (ctx1a.vf0 Y NO col[28] (¿techo?) Y (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo)))
- → **AgarrePared** si (ctx1a.vf0 Y (pared enfrente (agarrable) Y ctx35 ≥ parámetro))
- → **LuigiMove(flotar)** si (ctx1a.vf0 Y ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0))
- → **Salto** si (ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo Y NO subiendo))
- → **AterrizarChoque** si (en suelo Y NO subiendo Y NO stick movido)
- → **AterrizarChoque** si (en suelo Y NO subiendo)
- → **RebotePisotón** si (ctx1a.vf0 Y pisó a un enemigo (ctx8.bit1))
- → **CaídaLenta(tanuki)** si (ctx1a.vf0 Y (forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y durante 3 frames)

## Sentón(HipDrop)  (nodo 0x10000730)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Bucear** si Zona.vf4(Fís)
- → **LuigiMove(flotar)** si (anim HipDropLand terminó Y ... Y ctx15.vf0)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Salto** si anim HipDropLand terminó Y ...
- → **Correr** si (Sentón(HipDrop)+8.vf0 Y stick movido Y en suelo)
- → **Caer** si (Sentón(HipDrop)+4.vf0 Y NO en suelo)
- → **Esperar** si (Sentón(HipDrop)+4.vf0 Y en suelo)

## AgarrePared  (nodo 0x100002A0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Aterrizar** si en suelo
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **CaerDesdePared** si soltó la pared (4f sin contacto o stick hacia afuera)
- → **SaltoPared** si (pulsó A/B (≤5f) Y tocando pared)

## AtaqueColaAire  (nodo 0x10000C20)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)

## AtaqueColaAire  (nodo 0x10000C70)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)

## AtaqueColaAire  (nodo 0x10000CC0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)

## AtaqueColaAire  (nodo 0x10000D10)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)

## AtaqueColaAire  (nodo 0x10000D60)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)

## ChoquePared  (nodo 0x10000DA0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **AterrizarChoque** si (en suelo Y NO subiendo)
- → **Agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **Caer** si anim (actual) terminó

## AterrizarChoque  (nodo 0x10000EA0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si NO en suelo
- → **SaltoAtras** si ((NO ctx1a.vf0 O mantiene L/R) Y (AterrizarChoque+8.vf0 Y pulsó A/B (≤5f)))
- → **Agachado** si ((NO ctx1a.vf0 O mantiene L/R) Y (anim (actual) terminó O (AterrizarChoque+8.vf0 Y stick movido)))
- → **LuigiMove(flotar)** si (ctx15.vf0 Y (AterrizarChoque+8.vf0 Y pulsó A/B (≤5f)))
- → **Salto** si (AterrizarChoque+8.vf0 Y pulsó A/B (≤5f))
- → **Correr** si (AterrizarChoque+8.vf0 Y stick movido)
- → **Esperar** si anim (actual) terminó

## Daño  (nodo 0x100007B0)
- → **Morir** si toca Floor_code 2?
- → **Morir** si toca Floor_code 3?
- → **DeslizarPared** si Zona.vf0(Fís)
- → **Morir** si sin vida (ctx14.vf8)
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Correr** si (en suelo Y pasaron N frames Y stick fuerte)
- → **Caer** si Daño+4.vf0

## InicioDeEscena?  (nodo 0x10000060)
- → **Morir2** si sin vida (ctx14.vf8)
- → **Morir2** si Entrada.vf8
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **NadarInicio?** si ((InicioDeEscena?+4.vf0 O Entrada.vf0c ≠ 0) Y Zona.vf4(Fís))
- → **Correr** si (stick movido Y Entrada.vf0)
- → **Esperar** si Entrada.vf0
- → **CaerInicio2?** si Entrada.vf0c ≠ 0
- → **Agachado** si Entrada.vf4
- → **CaerInicio?** si InicioDeEscena?+4.vf0

## Frenar  (nodo 0x10000770)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Caer** si NO en suelo
- → **SaltoGiro** si ((pulsó A/B (≤5f) Y stick fuerte no hacia atrás) Y NO ctx16.vf14)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si pulsó A/B (≤5f)
- → **GiroTrasFrenar** si (stick fuerte no hacia atrás (si Frenar+4.vf0) Y NO ctx16.vf14)
- → **Correr** si Frenar+4.vf0

## GiroTrasFrenar  (nodo 0x10000ED0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Caer** si NO en suelo
- → **Correr** si anim (actual) terminó
- → **SaltoGiro** si pulsó A/B (≤5f)

## SaltoLargo  (nodo 0x10000890)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **Correr** si ((cayendo (vel·grav>0) Y en suelo) Y stick movido)
- → **Aterrizar** si (cayendo (vel·grav>0) Y en suelo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **CaídaLenta(tanuki)** si (((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4) Y durante PARAM frames)

## SaltoLargo  (nodo 0x100008D0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **Deslizar agachado** si (en suelo Y NO subiendo Y pulsó A/B (≤5f) ...)
- → **Correr** si ((cayendo (vel·grav>0) Y en suelo) Y stick movido)
- → **Aterrizar** si (cayendo (vel·grav>0) Y en suelo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **CaídaLenta(tanuki)** si (((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4) Y durante PARAM frames)

## SaltoGiro  (nodo 0x10000900)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## AtaqueColaSuelo  (nodo 0x100009A0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Caer** si (AtaqueColaSuelo+4.vf0 Y NO en suelo)
- → **Deslizar agachado** si (AtaqueColaSuelo+4.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))
- → **Correr** si (AtaqueColaSuelo+4.vf0 Y en suelo Y ctx1a.vf0)
- → **LuigiMove(flotar)** si ((NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo)) Y ctx15.vf0)
- → **AtaqueAéreo** si (NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo))
- → **AtaqueColaAire** si ((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4)

## AtaqueColaSuelo  (nodo 0x10000A10)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Caer** si (AtaqueColaSuelo+4.vf0 Y NO en suelo)
- → **Deslizar agachado** si (AtaqueColaSuelo+4.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))
- → **Correr** si (AtaqueColaSuelo+4.vf0 Y en suelo Y ctx1a.vf0)
- → **LuigiMove(flotar)** si ((NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo)) Y ctx15.vf0)
- → **AtaqueAéreo** si (NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo))
- → **AtaqueColaAire** si ((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4)

## AtaqueColaSuelo  (nodo 0x10000A80)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Caer** si (AtaqueColaSuelo+4.vf0 Y NO en suelo)
- → **Deslizar agachado** si (AtaqueColaSuelo+4.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))
- → **Correr** si (AtaqueColaSuelo+4.vf0 Y en suelo Y ctx1a.vf0)
- → **LuigiMove(flotar)** si ((NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo)) Y ctx15.vf0)
- → **AtaqueAéreo** si (NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo))
- → **AtaqueColaAire** si ((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4)

## AtaqueColaSuelo  (nodo 0x10000AF0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Caer** si (AtaqueColaSuelo+4.vf0 Y NO en suelo)
- → **Deslizar agachado** si (AtaqueColaSuelo+4.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))
- → **Correr** si (AtaqueColaSuelo+4.vf0 Y en suelo Y ctx1a.vf0)
- → **LuigiMove(flotar)** si ((NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo)) Y ctx15.vf0)
- → **AtaqueAéreo** si (NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo))
- → **AtaqueColaAire** si (((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4) Y (Agachado+4 anim al 100% O NO velocidad² < umbral))
- → **AtaqueColaAire** si ((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4)

## AtaqueColaSuelo  (nodo 0x10000B60)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Caer** si (AtaqueColaSuelo+4.vf0 Y NO en suelo)
- → **Deslizar agachado** si (AtaqueColaSuelo+4.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))
- → **Correr** si (AtaqueColaSuelo+4.vf0 Y en suelo Y ctx1a.vf0)
- → **LuigiMove(flotar)** si ((NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo)) Y ctx15.vf0)
- → **AtaqueAéreo** si (NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo))
- → **AtaqueColaAire** si ((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4)

## AtaqueColaSuelo  (nodo 0x10000BD0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **ChoquePared** si (pared al frente Y NO petición externa bit0 Y NO pisó a un enemigo (ctx8.bit1))
- → **Caer** si (AtaqueColaSuelo+4.vf0 Y NO en suelo)
- → **Deslizar agachado** si (AtaqueColaSuelo+4.vf0 Y en suelo Y (mantiene L/R O NO ctx1a.vf0))
- → **Correr** si (AtaqueColaSuelo+4.vf0 Y en suelo Y ctx1a.vf0)
- → **LuigiMove(flotar)** si ((NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo)) Y ctx15.vf0)
- → **AtaqueAéreo** si (NO mantiene L/R Y ctx1a.vf0 Y (pulsó A/B (≤5f) Y en suelo))
- → **AtaqueColaAire** si ((pulsó A/B (≤5f) Y en suelo) Y NO Hélice.vf4)

## Aterrizar  (nodo 0x10000E60)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Caer** si NO en suelo
- → **LuigiMove(flotar)** si (((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4) Y Aterrizar+8.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y Aterrizar+8.vf0)
- → **Agachado** si (mantiene L/R Y Aterrizar+8.vf0)
- → **Correr** si (Aterrizar+8.vf0 Y stick movido Y en suelo)
- → **Esperar** si anim (actual) terminó

## Nadar(parado)  (nodo 0x10000F30)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **NadarAgachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si ((forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4) Y NO en suelo)
- → **Salto** si NO Zona.vf4(Fís)
- → **SentónAcuático** si (NO en suelo Y (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo)))
- → **NadarAgachado** si (en suelo Y mantiene L/R Y NO *ctx38 ≠ 0 Y NO ctx24.vf0 ≠ 0)
- → **NadarSuperficie** si (SupAgua.vf0 Y SupAgua.vf4 > umbral según forma)
- → **Caer** si (NO Zona.vf4(Fís) Y NO SupAgua.vf0)

## NadarInicio?  (nodo 0x10001090)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Estatua** si ((forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4) Y NO en suelo)
- → **Salto** si NO Zona.vf4(Fís)
- → **SentónAcuático** si (NO en suelo Y (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo)))
- → **NadarAgachado** si (en suelo Y mantiene L/R Y NO *ctx38 ≠ 0 Y NO ctx24.vf0 ≠ 0)
- → **NadarSuperficie** si (SupAgua.vf0 Y SupAgua.vf4 > umbral según forma)
- → **Caer** si (NO Zona.vf4(Fís) Y NO SupAgua.vf0)

## SentónAcuático  (nodo 0x10001120)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **NadarPisotón** si pisó a un enemigo (ctx8.bit1)
- → **Nadar(parado)** si ((Ctrl.vf4c O stick movido) Y SentónAcuático+8.vf0)
- → **Nadar(parado)** si SentónAcuático+4.vf0

## Bucear  (nodo 0x10001150)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **NadarPisotón** si pisó a un enemigo (ctx8.bit1)
- → **Nadar(parado)** si Bucear+4.vf0

## NadarPisotón  (nodo 0x10001190)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **SentónAcuático** si (NadarPisotón+4.vf0 Y (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo)))
- → **Nadar(parado)** si (NadarPisotón+4.vf0 Y (stick movido O Ctrl.vf4c))
- → **Nadar(parado)** si NadarPisotón+8.vf0
- → **NadarSuperficie** si (SupAgua.vf0 Y SupAgua.vf4 > umbral según forma)

## NadarAgachado  (nodo 0x100011D0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si NO (NO ctx1a.vf0 O mantiene L/R)
- → **Nadar(parado)** si (ctx1a.vf0 Y NO en suelo)
- → **Nadar(parado)** si (ctx1a.vf0 Y ctx24.vf0 ≠ 0)

## NadarSuperficie  (nodo 0x100010D0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Estatua** si ((forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4) Y NO en suelo)
- → **SaltoFueraDelAgua** si (cerca de la superficie (SupAgua.vf4 < 200) Y (pulsó A/B (≤5f) O pisó a un enemigo (ctx8.bit1)))
- → **SaltoFueraDelAgua** si pisó a un enemigo (ctx8.bit1)
- → **SentónAcuático** si (NO en suelo Y (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo)))
- → **Nadar(parado)** si (Zona.vf4(Fís) Y profundidad vs umbral según forma)
- → **Caer** si (NO Zona.vf4(Fís) Y NO SupAgua.vf0)

## SaltoFueraDelAgua  (nodo 0x10001250)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si (volvió a tocar agua (flanco) Y NO SupAgua.vf0)
- → **SaltoFueraDelAgua** si pisó a un enemigo (ctx8.bit1)
- → **NadarSuperficie** si volvió a tocar agua (flanco)
- → **Nadar(parado)** si (cayendo (vel·grav>0) Y Zona.vf4(Fís))
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## EmpujarPared?  (nodo 0x10001280)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Caer** si NO en suelo
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo) Y ctx15.vf0 Y NO Hélice.vf4)
- → **Salto** si pulsó A/B (≤5f)
- → **Agachado** si mantiene L/R
- → **Esperar** si NO stick movido
- → **Correr** si NO stick hacia adelante
- → **Correr** si NO pared al frente

## CaídaLenta(tanuki)  (nodo 0x10001300)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **Caer** si (NO (forma == X O forma == X O forma == X) O NO mantiene A/B)

## AtaqueAéreo  (nodo 0x10001390)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## CaerDesdePared  (nodo 0x100003B0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Estatua** si (forma == 5 Y pulsó L/R'' Y ctx1a.vf0 Y NO Hélice.vf4)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **AterrizajeRígido** si (ctx30.vf0 Y en suelo)
- → **LuigiMove(flotar)** si ((pulsó A/B (≤5f) Y en suelo Y NO subiendo) Y ctx15.vf0)
- → **Salto** si (pulsó A/B (≤5f) Y en suelo Y NO subiendo)
- → **Aterrizar** si (en suelo Y NO subiendo Y NO stick movido)
- → **Correr** si (en suelo Y NO subiendo)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **PlanearHélice** si (Hélice.vf0(0) Y cayendo (vel·grav>0) Y mantiene A/B Y NO ctx34.vf4)
- → **CaídaLenta(tanuki)** si ((forma == X O forma == X O forma == X) Y NO ctxeff+ffc.vf0 Y cayendo (vel·grav>0) Y NO en suelo Y mantiene A/B Y NO ctx34.vf4)

## PlanearHélice  (nodo 0x10001430)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Sentón(HipDrop)** si (NO ctx16.vf14 Y (pulsó L/R' Y hay espacio abajo))
- → **AgarrePared** si (pared enfrente (agarrable) Y ctx35 ≥ parámetro)
- → **Aterrizar** si ((en suelo Y NO subiendo Y NO stick movido) Y PlanearHélice+58.vf0)
- → **Correr** si ((en suelo Y NO subiendo) Y PlanearHélice+58.vf0)
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Caer** si NO Hélice.vf0(0)

## Estatua  (nodo 0x10001490)
- → **Morir** si toca Floor_code 2?
- → **Morir** si toca Floor_code 3?
- → **DeslizarPared** si Zona.vf0(Fís)
- → **Nadar(parado)** si ((en suelo Y NO mantiene L/R'' Y Estatua+8.vf0) Y Zona.vf4(Fís))
- → **Nadar(parado)** si (Estatua+4.vf0 Y Zona.vf4(Fís))
- → **Esperar** si (en suelo Y NO mantiene L/R'' Y Estatua+8.vf0)
- → **Esperar** si Estatua+4.vf0
- → **RebotePisotón** si pisó a un enemigo (ctx8.bit1)
- → **Esperar** si NO forma == X

## AterrizajeRígido  (nodo 0x100014C0)
- → **Morir** si [Morir quiere entrar]
- → **DeslizarPared** si [DeslizarPared quiere entrar]
- → **Nadar(parado)** si [Nadar(parado) quiere entrar]
- → **NadarSuperficie** si [NadarSuperficie quiere entrar]
- → **Agachado** si (ctx2a.vf0 Y NO ctx1a.vf0)
- → **Caer** si NO en suelo
- → **Esperar** si anim (actual) terminó
