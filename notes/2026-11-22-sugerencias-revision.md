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

## 6. Visión: cómo hacerlo más eficiente, inteligente, independiente, único y preciso

Pedido por Jesus el mismo día. Igual que arriba: evaluar, no aplicar a ciegas.

**Más eficiente**
- Un solo método y un solo bus; nada de copias que se desfasan.
- Scripts deterministas para todo cálculo; la IA solo donde un script no llega (interpretar, explicar,
  detectar anomalías). Hoy varias corridas recalculan con la IA cosas que un script hace en segundos.
- Corridas por evento, no por reloj: el plan sale cuando `feeds.json` trae datos posteriores a la
  reapertura, no a una hora fija (evita planes vacíos como el pre-asia de las 12:43 CT del 22 nov).

**Más inteligente**
- Un registro único de decisiones: cada veredicto, zona y trade con sus features y su resultado, en una
  sola tabla. Hoy está repartido en session-analyst-bus, scalp-cc-bus y trader-os-bus con formatos distintos.
- Un simulador como juez: toda regla nueva corre primero en sombra sobre velas reales (como
  `session-analyst-bus/method/entry_study.py`) y solo se activa si gana neta con su IC.
- Probabilidades calibradas además de GO/WAIT ("58 % con este gatillo"), para dimensionar el riesgo.

**Más independiente**
- Segunda fuente para cada dato crítico (las velas de Yahoo de `tos-bus-bars` van en ese camino);
  menos dependencia de los webhooks de TradingView.
- Contrato de salud por pieza: cada lente declara cómo se ve "sana" y el watchdog lo verifica. La falla
  del digest de Mi Mesa (6 nov) habría saltado el primer día y no tres semanas después.
- Reglas que se retiran solas cuando sus números las desmienten (como las hipótesis `trial-*` con
  `refuteWhen`), extendido a todas las reglas.

**Más único**
- El edge personal: no "qué setup paga en el mercado" sino "qué setup paga **cuando Jesus lo opera**".
  Cruzar el edge medido (lente Edge) con su ejecución real (trader.json, fills de Mi Mesa) deja una lista
  corta de setups suyos; el sistema lo empuja solo hacia esos.

**Más preciso**
- Todo neto de costes, con IC, y un solo calificador para los tres sistemas (hoy Mi Mesa mide en bruto,
  Scalp CC neto y el Session Analyst con su propio criterio).
- Predicciones escritas antes y calificadas después, con su calibración (Brier) visible.

## 7. La cereza: pronóstico de tilt

Idea de la sesión revisora, la que más diferenciaría al sistema. El Coach no solo marca la fuga después:
**la predice minutos antes**. Con el historial de trades y flags se entrena un modelo simple
(regresión logística, sin dependencias) de la probabilidad de romper una regla en los próximos 30 min,
con señales como: minutos desde el último SL, racha de pérdidas, salto de tamaño vs la mediana,
velocidad de re-entrada, hora del día, P&L del día en R, día de la semana y si ya se tocó el stop del
día. Cuando la probabilidad cruza un umbral, Mi Mesa baja el tamaño máximo, alarga la pausa o bloquea,
y le muestra a Jesus una tarjeta corta: "esto es lo que tu yo de otros días hizo en esta situación, y
cuánto costó". Medir: violaciones R1 y R por semana antes y después, y la calibración del pronóstico.

## 8. Factibilidad del freno anti-tilt con la API de MFP (revisado el 2026-11-22)

Fuente: la especificación oficial `https://docs.myfundedperpetuals.com/openapi.yaml` (API en beta, puede
cambiar) y el cliente actual `tradedadlog/netlify/functions/_mfp.mjs` (solo lectura).

**Lo que la API permite** (requiere una key con permiso de trading; la actual es "Read Only")
- `POST /v1/positions/{id}/close` (parcial o total) y `POST /v1/accounts/{id}/close-all-positions`.
- `DELETE /v1/orders/{id}` y `POST /v1/accounts/{id}/cancel-all-orders`.
- `PUT /v1/positions/{id}/exit-orders` (poner o mover TP/SL de una posición abierta).
- Lectura de posiciones, órdenes y fills (lo que ya usa `tos-coach`).

**Lo que NO permite**: no hay endpoint para pausar o bloquear trading en una cuenta, ni para fijar
límites de pérdida o de tamaño por cuenta (`/trading-policy` es solo lectura). Por eso el freno es un
**ejecutor**: no impide abrir, pero cierra o corrige en segundos lo que rompe una regla.

**Diseño propuesto**
- Vigilante que consulta posiciones y órdenes de las cuentas cada 2-3 s (límite documentado en el
  cliente: ~300 req/min por IP; 3-4 cuentas caben de sobra). La spec menciona un WebSocket de cuenta
  sin documentar; si se documenta, reemplaza el sondeo.
- Reglas de actuación (las del registro vivo de `method/coach-review.md`):
  - R1 (entrada dentro de la pausa post-SL): cerrar la posición.
  - DAY_STOP_HIT: cerrar todo y cancelar órdenes.
  - Tamaño > N veces la mediana propia: cerrar o reducir al tamaño normal.
  - NO_STOP pasados 30 s: poner el stop del plan con `exit-orders` en vez de cerrar.
- Con esto, el trade R1_REVENGE del 2026-11-22 (99 s después del SL, 7.5x el tamaño, −200R) se habría
  cerrado en ~3 s.

**Infraestructura**
- No cabe en Netlify (el mínimo de las funciones programadas es 1 min). Necesita un proceso siempre
  encendido: un servicio chico (Fly.io o Railway, ~5 USD/mes) o la PC de Jesus encendida.
- La key de trading la crea Jesus en MFP y vive solo como secreto del servidor; nunca en un repo, un
  archivo del bus ni un chat.

**Encendido por etapas**
1. Sombra (1-2 semanas): solo registra y notifica lo que habría cerrado; medir falsos positivos.
2. Suave: pone stops y notifica, no cierra.
3. Duro: cierra según las reglas.
Siempre con un interruptor de apagado manual y un log de cada acción con su motivo y la regla.

**A confirmar antes de construir**
- Que las reglas de MFP permitan cierres automáticos vía API para estas cuentas (la API es oficial,
  pero hay que verificarlo en sus términos).
- Que Jesus acepte que cada cierre forzado cuesta comisión y spread.

**Conexión con la sección 7**: el pronóstico de tilt ajusta los umbrales del vigilante en vivo (pausa
más larga y tamaño máximo menor cuando sube el riesgo).
