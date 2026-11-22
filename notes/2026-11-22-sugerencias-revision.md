# Sugerencias para Trader OS · revisión externa del 2026-11-22

Escrito por otra sesión de Claude que revisó el bus del Session Analyst, Mi Mesa, Scalp CC y Trader OS
con Jesus el 21 y 22 nov. **Son sugerencias para evaluar, no instrucciones.** Compáralas con el diseño
(`tradedadlog` / `trader-os/DESIGN.md`, `TRADER-STATE.md`) y con los datos; adopta lo que convenga,
descarta lo que no, y deja escrito por qué.

## 1. Prioridad: el Coach con freno en vivo, antes que más lentes de análisis

**Evidencia.** `method/entry_study.py` (session-analyst-bus) mide sobre velas reales: el mejor setup del
plan (A+ del método con gatillo de 5 m) paga **+0.50R por trade** (n=35 desde la regla 8e, 31 oct).
Mi Mesa con orden límite paga +0.35R (n=199). `reviews/2026-11-22.md` de este bus registra **un solo
trade de revancha de −200R** (R1_REVENGE, 7.5x el tamaño, 99 s después de un SL). Una fuga así borra
cientos de trades del mejor edge medido. La palanca más grande disponible es la conducta, no la
precisión del plan.

**Sugerencia.** Que el Coach actúe **antes** del trade, no solo en la revisión de la noche. Hoy el
LOCKOUT se marca en `live/trader.json`, pero el trade ya ocurrió. Ideas a evaluar dentro de Mi Mesa
(`src/lib/engine.js` ya detecta revenge, orphan y gate): pausa forzada tras un SL (R1) con cuenta
regresiva visible, tamaño máximo por trade que bloquea o pide confirmación escrita, y bloqueo tras
el stop del día (`DAY_STOP_HIT`). Medir: violaciones R1 por semana antes y después.

## 2. Contexto vs Session Analyst: definir paridad y fecha de corte

**Evidencia.** `method/contexto-plan.md` lleva dentro una copia del método del SA. El 22 nov ya se
había desfasado (no tenía los cambios del 21 nov: tope de ES en calendario mayor, GO al gatillo en
Asia/NY, guarda del journal). Se sincronizó a mano en el commit `3f1883c`. Dos planes en paralelo
pueden dar veredictos distintos el mismo día.

**Sugerencia.** (a) Fijar un criterio de paridad medible, p. ej. 2 semanas con el mismo `verdict`
en ≥ 90 % de los instrumentos-sesión y E[R] calificado igual o mejor, y una fecha de corte para
apagar uno. (b) Mientras convivan, que Contexto lea el método desde una sola fuente
(`session-analyst-bus/method/instructions.md` + su §0 adaptador) en vez de mantener una copia, o
añadir un chequeo que falle si las secciones del método divergen.

## 3. Horario de la corrida de Contexto

**Evidencia.** `live/plan-heartbeat.json`: pre-asia del domingo a las 12:43 CT, antes de la
reapertura de las 17:00 CT. Resultado: "FEED1 caído en los 5 futuros", todo WAIT. El pre-asia del SA
(16:24 CT) salió con datos buenos y dio GO en NQ y ES.

**Sugerencia.** Correr Contexto después de las 16:05 CT (domingo y entre semana), o que espere a que
`feeds.json` tenga datos posteriores a la reapertura.

## 4. Complejidad vs edge

**Evidencia.** Hoy hay 5 repos de datos y ~10 agentes/rutinas; el edge medido es delgado (Scalp CC
neto −0.06R global; solo 15m/29m RETEST positivos; ver `session-analyst-bus/zones/scoreboard.json`).
Varias fallas silenciosas se detectaron tarde: el digest de Mi Mesa contaba todo trade sin ficha como
"fuera de zona" desde el 6 nov (arreglado en mi-mesa#41), el script de pushes tenía el horario de
cripto mal tras el cambio de horario, y los pre-* de futuros corren duplicados desde el 11 nov
(probablemente tareas locales de la app de escritorio, sin confirmar).

**Sugerencia.** Antes de sumar piezas, que cada lente nueva traiga (a) su métrica de éxito y (b) un
chequeo automático de salud que el watchdog lea. Preferir reemplazar a duplicar.

## 5. Orden propuesto

1. Coach con freno en vivo (punto 1).
2. La lente Edge como filtro obligatorio del plan (que no salga GO en un setup con E[R] neto ≤ 0).
3. Unificar Contexto y Session Analyst en uno solo (punto 2).

## Referencias

- `session-analyst-bus/reviews/2026-11-21-estudio-entradas.md` · estudio de entradas y salidas.
- `session-analyst-bus/zones/scoreboard.json` · E[R] por setup de los tres sistemas (lo regenera el
  agente de zonas cada noche). Tablero: "Qué paga · setups del bus" (artifact de claude.ai).
- `session-analyst-bus/method/instructions.md` sección 8e y 9 · reglas nuevas del 21 nov.
- `mi-mesa` PR #41 · digest sin ficha ya no cuenta como fuera de zona; manda fills.
