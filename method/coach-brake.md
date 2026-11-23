# Coach · freno en vivo (ejecutor MFP)

Spec para evaluar y construir. Escrito el 2026-11-22 a partir de la nota de revision (seccion 8) y el
analisis de paridad/conducta. **Nada de esto esta construido aun.** Antes de escribir codigo hay que
cerrar las 3 decisiones del final.

## Por que

La palanca mayor medida del Trader OS es la conducta, no la precision del plan. `reviews/2026-11-22.md`
registra un solo trade de revancha de -200R (R1_REVENGE, 7.5x el tamano, 99 s despues de un SL): una
fuga asi borra cientos de trades del mejor edge. Hoy el Coach marca el LOCKOUT en `live/trader.json`
**despues** del trade. El freno actua **durante**: no impide abrir (la API no deja), pero cierra o
corrige en segundos lo que rompe una regla.

## Que permite la API de MFP (y que no)

Fuente: `https://docs.myfundedperpetuals.com/openapi.yaml` (beta, puede cambiar) y el cliente actual
`tradedadlog/netlify/functions/_mfp.mjs` (hoy **solo lectura**).

Permite (requiere una key con permiso de **trading**; la actual es Read Only):
- `POST /v1/positions/{id}/close` (parcial o total) y `POST /v1/accounts/{id}/close-all-positions`.
- `DELETE /v1/orders/{id}` y `POST /v1/accounts/{id}/cancel-all-orders`.
- `PUT /v1/positions/{id}/exit-orders` (poner o mover TP/SL de una posicion abierta).
- Lectura de posiciones, ordenes y fills (lo que ya usa el Coach).

NO permite: no hay endpoint para **pausar o bloquear** trading en una cuenta, ni para fijar limites de
perdida o de tamano por cuenta (`/trading-policy` es solo lectura). Por eso el freno es un **ejecutor**,
no un portero.

## Reglas de actuacion

Del registro vivo de reglas de `method/coach-review.md` (misma fuente que usa la review nocturna):

| Regla | Disparo | Accion del freno |
|---|---|---|
| R1 (pausa post-SL) | entrada nueva dentro de la pausa tras un SL | **cerrar** la posicion (close total) |
| DAY_STOP_HIT | se toco el stop del dia (perdida diaria por cuenta) | **cerrar todo** + cancelar ordenes |
| Tamano | tamano > N veces la mediana propia del trader | **reducir** al tamano normal (close parcial) o cerrar |
| NO_STOP | posicion abierta > 30 s sin stop | **poner** el stop del plan con `exit-orders` (no cerrar) |

Umbrales (pausa, N de tamano, segundos) salen de `state/trader-profile.json` y del registro del Coach,
no hardcodeados. Con esto, el trade R1_REVENGE del 2026-11-22 (99 s tras el SL, 7.5x, -200R) se habria
cerrado en ~3 s.

## Arquitectura

- **Vigilante** que consulta posiciones y ordenes de las cuentas cada 2-3 s (limite documentado en
  `_mfp.mjs`: ~300 req/min por IP; 3-4 cuentas caben de sobra). Si MFP documenta su WebSocket de cuenta
  (lo menciona sin documentar), reemplaza el sondeo.
- Lee las reglas y umbrales del bus (`live/trader.json`, `state/trader-profile.json`, reglas del Coach).
- Cada accion se registra con su motivo, la regla y la cuenta, y notifica a Jesus.
- **Interruptor de apagado manual** siempre accesible (un flag que el vigilante lee cada ciclo).

### Infra

- **No cabe en Netlify** (el minimo de las funciones programadas es 1 min; el freno necesita 2-3 s).
  Necesita un proceso siempre encendido.
- Opciones: un servicio chico (**Fly.io o Railway, ~5 USD/mes**) o la PC de Jesus encendida.
  **Recomendacion: el servicio en la nube.** La PC es fragil justo para esto: el incidente del copiador
  (wifi caido) ya tumbo cuentas por trailing DD. Un freno de seguridad no puede depender de que la PC
  y el wifi sigan en pie.
- La **key de trading** la crea Jesus en MFP y vive **solo como secreto del servidor**: nunca en un
  repo, un archivo del bus ni un chat. El vigilante la lee de su entorno.

## Encendido por etapas (innegociable)

1. **Sombra** (1-2 semanas): solo registra y notifica lo que **habria** cerrado; se miden falsos
   positivos. No toca ninguna cuenta.
2. **Suave**: pone stops (NO_STOP) y notifica, pero **no cierra**.
3. **Duro**: cierra segun las reglas.

Siempre con el interruptor de apagado manual y el log de cada accion. Nunca saltar de sombra a duro.

## Medicion

Violaciones R1 por semana y R por semana, antes y despues de cada etapa. En sombra, tasa de falsos
positivos (cierres que no debieron dispararse). El objetivo es bajar las violaciones R1 sin cerrar
trades buenos.

## Conexion con el pronostico de tilt (nota seccion 7)

Cuando exista el modelo de probabilidad de romper una regla en los proximos 30 min, su salida **ajusta
los umbrales del vigilante en vivo**: pausa mas larga y tamano maximo menor cuando sube el riesgo. El
freno es el actuador; el pronostico es el termostato. El freno se construye primero.

## Las 3 decisiones de Jesus (antes de escribir codigo)

1. **Terminos de MFP**: confirmar que sus reglas permiten cierres/cancelaciones automaticas via API
   para estas cuentas (la API es oficial, pero hay que verificarlo en los terminos; algunas prop
   firms restringen la automatizacion). **Esto va primero**: si no se permite, no hay freno.
2. **Host**: Fly.io / Railway (~5 USD/mes, recomendado) o su PC.
3. **Key de trading**: crearla en MFP con permiso de trading y guardarla como secreto del host
   (Jesus la crea y la pega en el panel del host; Claude nunca la ve).

Ademas, aceptar que cada cierre forzado cuesta comision y spread.

## Lo que haria yo al construir (cuando esten las 3)

- Un servicio Node pequeno (reusa la logica de `_mfp.mjs`, ampliada a los endpoints de escritura).
- Arranca en **modo sombra** por defecto; el modo (shadow/soft/hard) es un flag de entorno.
- Loop de 2-3 s: lee posiciones/ordenes, evalua las 4 reglas, en shadow solo loguea/notifica.
- Log append-only de cada evaluacion y accion, y un endpoint/flag de apagado.
- Metricas semanales al bus para la review del Coach.
