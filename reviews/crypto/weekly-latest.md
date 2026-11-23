# Revision semanal cripto · semana que cierra el 2026-11-22 (domingo CT)

**Aviso de datos (lo mas importante de esta revision):** la semana lunes 16 a lunes 23 de
noviembre UTC solo tiene `grades/crypto/` para 3 de los 7 dias en este bus (16, 17 y 18 de
noviembre). Los dias 19, 20, 21 y 22 de noviembre no tienen `plans/crypto/*.json` en
`trader-os-bus` (la migracion de calificacion se cerro el 2026-11-22 y hoy, 2026-11-23, es la
primera corrida de `crypto-close` en el bus unificado). No hay como calificar esos 4 dias a
posteriori: el feed en vivo de entonces no quedo guardado aqui. Los numeros de abajo son solo
de los 3 dias disponibles, muestra muy corta (no confundir con una semana completa).

## Marcador (solo 16, 17 y 18 de noviembre; n chico)

- Zonas: ETH 3/6 tocadas-ganadoras (50%), BTC 5/5 (100%, n=5). Combinado 8/11 (73%).
- Sesgo de sesion (bias): ETH 2/5 (40%), BTC 2/5 (40%). Combinado 4/10 (40%).
- Close contra ny: no se puede comparar, `grades/crypto` no separa por slot y no hay
  `plans/crypto/*-ny.json` de esos dias en este bus para cruzar a mano.

## Fin de semana contra entre semana

Sin dato: los 3 dias disponibles (16, 17, 18 nov) son todos entre semana (lunes a miercoles);
no hay un solo dia de fin de semana calificable esta semana en este bus.

## Donde fallo

Con n=11 zonas y n=10 llamadas de sesgo no se puede sacar una lectura real por tipo de zona o
por contexto (todas las claves de `byContext` del `scorecard` de `state/crypto-state.json`
pertenecen al historial sembrado del SA viejo, no a esta semana). Lo unico medido esta semana:
BTC gano todas sus zonas tocadas (5/5, n chico) y ETH se quedo en 50%.

## Contexto fuera del grafico

No hay dato fresco de `cryptoContext` por dia de esta semana en este bus (no quedaron los
planes). El contexto de HOY (apertura de la semana que entra): miedo extremo (11), fondeo de
ETH cargado de cortos, DVOL bajando, dos hackeos de puentes menores en 24h (Chainflip $12M,
CYBER) y el hueco del CME de ETH (viernes 1,597.50, 7.28% abajo del spot) todavia sin llenar.

## Semana que entra

Evento USD de alto impacto: Core PCE Price Index m/m y Prelim GDP q/q el miercoles 25 de
noviembre 13:30 UTC (07:30 CT) — la semana de Accion de Gracias adelanta el dato. Sin earnings
de megacaps listados esta semana en `news.json`.

## Propuestas de método

Sin propuestas, muestra corta (n=11 zonas, n=10 sesgos, y 4 de los 7 dias de la semana sin
dato en este bus). La unica propuesta operativa es de proceso, no de método: asegurar que
`crypto-close` escriba `plans/crypto/<fecha>-close.json` y `plans/crypto/<fecha>-ny.json`
todos los dias para que la proxima revision semanal (30 de noviembre) tenga los 7 dias
completos en este bus.
