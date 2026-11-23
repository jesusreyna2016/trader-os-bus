# Contrato de salud del Trader OS

La idea, en simple: el sistema tiene varias piezas que escriben archivos cada cierto tiempo (los datos
del mercado, el plan del dia, la paridad...). Si una se calla, hoy nos enterabamos tarde (el 22-nov un
plan no se publico y lo vimos horas despues). El **watchdog** revisa cada 15 minutos que cada pieza
este "viva" y deja el resultado en `live/health.json`. Una pagina lo muestra en verde / amarillo / rojo.

Lo escribe la funcion `tradedadlog/netlify/functions/tos-health.mjs`.

## Que es estar "sana" (cada pieza declara su ritmo)

Cada pieza tiene un ritmo esperado. El watchdog la marca:
- **al dia** (verde): llego a tiempo.
- **viejo** (amarillo): se esta retrasando, conviene mirar.
- **caido** (rojo): lleva demasiado sin aparecer, algo se rompio.
- **cerrado** (gris): el mercado esta cerrado, es normal que no llegue (no es alarma).

| Pieza | Que es | Quien la escribe | Ritmo | Viejo | Caido |
|---|---|---|---|---|---|
| Datos crudos (feeds) | precios y niveles que manda TradingView | tos-bus-snapshot | continuo (mercado abierto) | 45 min | 150 min |
| Estado del mercado | resumen por simbolo | tos-market | continuo | 45 min | 150 min |
| Edge medido | si los setups pagan | lente Edge | continuo | 90 min | 300 min |
| Velas 5m del dia | velas para calificar | tos-bus-bars (cada hora) | por hora | 120 min | 240 min |
| Estado del trader | trades y bloqueos (Coach) | tos-coach | cuando opera (puede estar quieto) | 3 dias | 7 dias |
| Plan de futuros | el plan de la sesion de Asia | lente Contexto | 1 al dia, 17:20 CT | no corrio hoy | no corrio en 2 dias |
| Plan de cripto | el plan de ETH/BTC | lente Contexto | 1 al dia, 00:15Z | no corrio hoy | no corrio en 2 dias |
| Paridad (Paso 4) | acuerdo Contexto vs Session Analyst | parity.py | 1 al dia (con el plan) | no corrio hoy | no corrio en 2+ dias |

**Diferencia clave entre "continuo" y "1 al dia":**
- Las continuas (feeds, mercado, edge, velas) se miden por antiguedad en minutos, y solo cuando el
  mercado de futuros esta abierto (fin de semana y el corte diario 16:00-17:00 CT salen "cerrado", no
  disparan alarma).
- Las de "1 al dia" no se miden por minutos: lo que importa es **si ya corrio hoy cerca de su hora**.
  Un plan de hoy pero de mucho antes de su hora (p.ej. un pre-asia de mediodia, antes de la reapertura)
  NO cuenta como "al dia": si ya paso la hora esperada y no hay un latido nuevo, sale "no corrio hoy".
  Esto es justo lo que fallaba el 22-nov.

Ademas, si el latido del plan trae `ok:false` (la corrida termino con error aunque sea reciente), sale
amarillo con "ultima corrida con error".

## El archivo `live/health.json`

```json
{ "schema": "health-1", "checkedAt": "<ISO>", "status": "ok|warn|bad",
  "marketOpen": true, "issues": ["Plan de futuros: no corrio hoy ...", ...],
  "items": [ { "key", "label", "writer", "status", "ageMin", "at", "note" }, ... ] }
```

`status` global = el peor de las piezas (rojo si hay alguna roja, amarillo si hay amarilla, verde si
todo bien; "cerrado" no cuenta como problema).

## Como anadir una pieza nueva

Regla del Trader OS (nota del 22-nov, punto 4): cada lente/pieza nueva trae su metrica de exito **y** su
chequeo de salud. Para sumar una pieza al watchdog, anade una fila al array `CONTRACT` de
`tos-health.mjs` con su archivo, su ritmo (`kind`) y sus umbrales. Preferir reemplazar piezas a
duplicarlas.
