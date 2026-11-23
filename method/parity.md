# Paso 4 · Registro de paridad Contexto vs Session Analyst

Contexto (este bus) corre EN PARALELO al Session Analyst viejo. Antes de apagar uno hay que
probar que dan lo mismo. `method/parity.py` es el termometro.

## Que mide

Por cada ciclo pre-asia, compara `live/plan.json` (Contexto) con `plans/latest.json` del
`session-analyst-bus` (publico). Para NQ, ES, GC, YM, CL mira si el `verdict.signal`
(GO / WAIT / AVOID) coincide. Escribe:

- `state/parity-log.jsonl`: una linea por ciclo (idempotente por date+runType), con el
  veredicto de cada lente por instrumento y si coincide.
- `live/parity.json`: el acumulado de la ventana movil de 14 dias (agreePct total y por
  instrumento), el dia de hoy, y la evaluacion del criterio.

## Criterio de corte (de la nota de revision del 2026-11-22)

Apagar uno de los dos cuando, sobre 2 semanas:

1. **>= 90 % mismo verdict** por instrumento-sesion (lo mide `criterion.verdictAgreeMet`,
   con >= 10 dias en la ventana), **y**
2. **E[R] calificado igual o mejor** (fase 2: aun no automatizado; necesita cruzar las
   calificaciones de `grades/` de ambos buses).

`readyToCut` se deja en `false` y se decide a mano: el acuerdo de veredicto por si solo no
basta, dos lentes pueden coincidir en WAIT y ninguna ganar dinero. La divergencia util es la
que el Paso 4 quiere entender: hoy Contexto marca WAIT en NQ/ES por FEED1 caido mientras el
SA da GO; cual acierta lo dice la calificacion del dia siguiente, no el acuerdo.

## Como corre

Ultimo paso (best-effort) del pre-asia de Contexto, tras generar y pushear el plan:
`python3 method/parity.py`. Nunca rompe el pipeline: si el SA no responde o algo falla,
imprime el motivo y sale 0. La Mesa (tradedadlog.com/la-mesa.html) lee `live/parity.json`.
