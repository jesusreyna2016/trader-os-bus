# Contexto, meta revision semanal 2026-11-23 a 2026-11-27

Primera semana weekly completa de esta lente desde la migracion de calibracion (2026-11-22): no
existe una `reviews/contexto/<sabado>-semana.md` inmediata anterior para comparar (la unica previa,
2026-11-14, viene del Session Analyst migrado, dos semanas atras y en otro formato). Los marcadores
de abajo se comparan contra el rolling de 46 dias a 2026-11-26, no semana a semana. Viernes
(2026-11-27) corrio normal (pre-asia/pre-london/pre-ny con plan), pero su calificacion de cierre la
escribe la pre-asia del lunes, que todavia no corrio: sin review, marcado como "sin review: la
pre-asia del viernes no corrio (ver watchdog)".

## Marcador de la semana por instrumento

(De `grades/2026-11-23..26.json`, 4 dias calificados de 5; "/\" contra el rolling `hitLog` 46 dias
a 2026-11-26. EM = % de sesion x dia dentro de banda, de las mismas 4 fechas.)

- **NQ**: sesgo 50% (4/8) baja leve vs 52% rolling (n=103) · escenario A 67% (4/6) sube vs 56%
  rolling (n=85) · zona 0% (0/5) se desploma vs 23% rolling (n=65) · EM dentro 33% (3/9).
- **ES**: sesgo 43% (3/7) baja vs 49% rolling (n=99) · escenario A 50% (3/6) sube vs 48% rolling
  (n=83) · zona 0% (0/6) se desploma vs 28% rolling (n=54) · EM dentro 33% (3/9).
- **GC**: sesgo 43% (3/7) baja vs 55% rolling (n=96) · escenario A 50% (4/8) igual vs 52% rolling
  (n=88) · zona 0% (0/7) se desploma vs 25% rolling (n=56) · EM dentro 33% (3/9).
- **YM**: sesgo 29% (2/7) se desploma vs 49% rolling (n=83), el peor sesgo de la semana · escenario
  A 60% (3/5) sube vs 57% rolling (n=97) · zona 25% (1/4) baja vs 17% rolling (n=52), la unica zona
  que pago entre los 5 (`retest_break` NY). EM dentro 67% (6/9), el mejor de los 5.
- **CL**: sesgo 43% (3/7) baja vs 52% rolling (n=99) · escenario A 86% (6/7) sube fuerte vs 59%
  rolling (n=103) · zona 0% (0/5) se desploma vs 24% rolling (n=63). EM dentro 43% (3/7).
- **Global**: `predictionScore` ponderado 57.5% (n=2670, rolling 46d, sin cambio semanal medible
  todavia). Zona global 1/27 = 4% esta semana, muy por debajo del 17-28% rolling por simbolo: el
  dato mas duro de la semana.

## Donde fallo y lo que mejor paga

`scorecard.blindSpots` llego vacio esta semana (la muestra fresca por dimension aun no alcanza el
umbral tras la migracion). Por causa declarada en las reviews diarias, lo que mas pesó fue
`zona_sin_confluencia_real` (zonas de reversion tocaron y rompieron 26 de 27 veces, lunes a jueves,
en dias de tendencia/expansion que el metodo leyo como rango) y `EM_mal_calibrado` (Asia corta en 3
de 4 dias calificados, el ajuste de -10% por feriado del jueves fue insuficiente en NQ/GC). De
`scorecard.strengths`: escenario A los martes 75% (n=12) vs 62% promedio, confirmado otra vez esta
semana (CL 86%, NQ 67% el martes-jueves de la ventana).

## Expectativa en R

`python3 method/weekly_r.py`: plan -0.84R (n=16, 6% ganan), la peor lectura de plan puro de las
semanas vistas por esta lente. Ejecucion sin datos: `live/journal.json` no existe en el bus esta
semana (ningun dia de los 5 lo tuvo), sincroniza el journal desde mywhyjournal.com; sin ese dato no
hay brecha plan-vs-tu que medir. Aparte, plan cripto +0.26R (n=5, 100% ganan).

## Plan vs ejecucion

Sin datos: `scorecard.execution.planFit` solo tiene posiciones acumuladas hasta 2026-11-18 (144 en
total, todas previas a esta ventana), nada nuevo que atribuir a 2026-11-23..27. No se puede decir si
in-plan gano mas que off-zone esta semana especifica.

## Contexto fuera del grafico

Semana de un solo catalizador real: miercoles el Core PCE/PIB preliminar (07:30 CT) giro el dia con
fuerza de bajista a rally en NQ/ES/GC/YM, rompiendo el EM de las 3 sesiones por amplios margenes; el
resto de dias no tuvo dato de ese peso (martes solo comentarios de la Fed de fondo, viernes sin
driver nuevo, solo tension residual de VIX). Jueves fue feriado de Accion de Gracias, volumen bajo
pero con breakout real en NQ/GC que el metodo trato como dia recortado. El tono cruzado (VIX
subiendo, risk-off de fondo) fue mayormente en contra del resultado neto alcista de miercoles y
jueves: la macro de fondo no explico el rally, lo contradijo.

## Ejecucion de la semana

`live/journal.json` ausente los 5 dias (no es solo que no se clasifique: el archivo no existe en el
bus esta semana). Sin dato no hay disciplina, contra-sesgo ni fuga que medir esta ventana. El
rollup acumulado en `scorecard.execution.ALL` sigue fechado al 2026-11-18 (45 dias, disciplinado 0%,
341 de 341 trades fuera de edge clasificados, 42 de 45 dias con overtrade, 38 con revenge): numeros
viejos, no una lectura fresca de esta semana.

## Que se repitio

1. Las zonas de reversion a favor del sesgo mecanico de 24h (`bounce_val`, `fade_vah`,
   `poc_reversion`, `sweep_pdh/onh`) siguieron rompiendo por el lado malo en dias de tendencia, el
   mismo patron de `zona_sin_confluencia_real` visto lunes, martes, miercoles y jueves: 4 de 4 dias
   calificados con la misma causa.
2. El sesgo mecanico de Asia (fade 24h, regla 8e) fallo en la mayoria de las llamadas de la semana
   (NQ, ES, GC, YM, CL todos bajo su rolling), confirmando otra vez que dos sesiones seguidas
   confirmando tendencia sin pullback bajan la confianza de ese default.
3. El EM se quedo corto en la mayoria de celdas index/metal (NQ, ES, GC con solo 33% dentro de
   banda), repitiendo la leccion de `EM_mal_calibrado` ya anotada en 3 de las 4 reviews diarias.

## Cambios de la semana

Sin cambios aplicados: ninguna condicion nueva de `predictionSkip` cruzo el umbral esta semana
(`GC|range` ya estaba activo desde 2026-09-12, rate 38.4% n=56, sigue bajo 0.40, sin cambio),
`method/zone_type_rates.py` no marco ningun arquetipo `actionable` (todos con `winN<30` o
divergencia dentro de +-0.10), y no hay `blindSpots` con muestra para evaluar `convictionCap`
nuevo o su retiro. Sin cambios, muestra corta.

## Propuestas de metodo

1. Bajar un escalon adicional el `winRate` de confianza de zonas de reversion (`bounce_val`,
   `fade_vah`, `poc_reversion`, `golden_zone`, `sweep_onh/onl/pdh/pdl`) cuando `whipsawRisk>=0.6` Y
   el dia ya rompio su EM en la sesion previa: esta semana 26 de 27 zonas de reversion fallaron o
   rompieron bajo esa combinacion exacta. Campo: `method/instructions.md` seccion 4 (score de
   confluencia de zonas).
2. Revisar el ajuste de EM por feriado (-10%) para dias donde ya hay un breakout en marcha antes de
   la apertura: jueves NQ/GC necesitaron mas rango, no menos, repitiendo la misma leccion anotada en
   el review del 2026-11-26.

## Leccion de la semana

El bus entero sigue ciego para ejecucion real (`live/journal.json` ausente los 5 dias) justo en una
semana donde el plan puro ya perdio -0.84R y las zonas de reversion fallaron 26 de 27 veces: sin
ese dato no se puede saber si Jesus evito el dano del plan o lo agravo.

## Regimen

- **NQ**: entra la semana en el dia 7-8 de un corto estructural (invalida sobre 27424.50) con
  frameConflict activo (semanal LONG vs sesion SHORT) y sale igual, sin romperse, tras dos
  round-trips extremos (132-139% del ADR) jueves y viernes. thesisAlign EVOLVING, whipsawRisk 0.60.
- **ES**: mismo corto estructural que NQ, sin su conflicto de marcos, el mas limpio del grupo toda
  la semana; sale en dia 8 todavia sin romper, tras el mismo patron de round-trips extremos.
- **GC**: la tesis reinicio 3 veces en la semana (largo, corto, largo otra vez el viernes), la mas
  inestable de los 5; sale el viernes en dia 1 de un largo reinstalado con autoridad pero ya con un
  CISD bajista de 5m probandolo.
- **YM**: entra y sale la semana ALIGN con la tesis alcista confirmada el 2026-11-25, el regimen
  mas estable de los 5 a pesar del peor sesgo mecanico (29%); dia 3 de tendencia al cierre.
- **CL**: tesis de largo de 3 dias sin invalidarse, pero con COT crowded-short extremo y conflicto
  de marcos persistente (semanal largo vs sesion fade corto); sale la semana en AVOID, sin perseguir
  ningun lado.

## Perfil del trader

`state/trader-profile.json` bloque `observed` reescrito con la ventana 2026-11-23..27: sin dato real
(`live/journal.json` ausente los 5 dias), `disciplinedPct`/`againstBiasRate`/`outsideEdgeRate`/
`exitQuality` en null. `exitBaseline` se deja igual: este bus no tiene clonado `../scalp-cc-bus`
(solo `trader-os-bus` esta presente en este contenedor), no hay `exit-baseline.json` que leer.
