# Laboratorio Edgeful · lente Edge de Trader OS

Mide qué combinación de **estrategia + entrada + stop + salida + confluencia** funciona mejor,
solo con data propia (TradingView vía tus indicadores, Trader OS). Nada de velas de Yahoo.

## De dónde sale la data

| Fuente | Qué aporta | Desde |
|---|---|---|
| `tvbars/<día>.json` | Velas de 5m del **TDL Feed (FEED1)** con su contexto por vela: VWAP, EMA 20/50/200, EMA 20/50 1h, PDH/PDL/PDC, ON, IB, Asia, Londres, VA, chop, estiramiento ATR, dPos, SMT | cuando FEED1 mande `o/h/l/vol` (tdl-indicators, rama `feed-ohlcv`) |
| `events/*.jsonl` · TDL KL | Régimen y alineación cada 5m; toques y desenlaces de niveles (histórico desde 2026-11-22) | ya |
| `plans/` | Sesgo del plan pre-NY por símbolo | ya |
| `events/*.jsonl` · EDG_* | SUMMARY de los indicadores de estrategia (paridad) | al conectar sus alertas |

Ruta: FEED1 → `tos-ingest` (blob `tvbar:<día>:<SYM>`) → `tos-bus-snapshot` (cada 15 min) → `tvbars/`
→ GitHub Action `edgeful` (cada hora a :25) → `live/edgeful.json`.

## Qué se prueba (rejilla en `config.json`)

| Familia | Señal | Entradas | Stops | Salidas |
|---|---|---|---|---|
| **ORB** | primer cierre fuera del rango, ventanas **5 / 15 / 30 min** | al cierre · retest del borde (6 velas) | lado opuesto · medio · borde − 0.25 rango | 1R · 2R · 3R · 1x rango · cierre del día |
| **IBB** | primer cierre fuera del IB (60 min) | al cierre · retest | opuesto · medio · borde | 1R · 2R · +0.5x · +1x · cierre |
| **IBL** | primer toque de niveles **-50 / 0 / 25 / 50 / 75 / 100 / 150 %** del IB | límite en el nivel | 0.1 · 0.25 IB | 1R · 2R · siguiente nivel (25 %) |
| **IBR** | mismo toque: ¿respeta (rebota 0.25 IB) o lo atraviesa (cierre 0.1 IB al otro lado)? | | | |
| **SWR** | barrida de Asia, Londres, ON, PDH/PDL en NY + cierre de vuelta en 3 velas → reversa | al cierre del reclaim | extremo · extremo + 0.25 ATR | 1R · 2R · otro lado del rango · cierre |
| **SWC** | barrida aceptada (2 cierres fuera) → continuación | al 2º cierre | nivel ∓ 1 ATR5 | 1R · 2R · cierre |
| **VA80** | regla del 80 %: abre fuera del value area de ayer y vuelve a entrar con 2 cierres de 5m | al 2º cierre · retest del borde | borde ∓ 0.25 ATR5 · extremo de la sesión | POC · otro borde del VA · 1R · 2R |
| **PB** | retroceso a **EMA20** o **VWAP** de 5m (venía ≥ 0.5 ATR5 del mismo lado; nivel de la vela anterior) | límite en la referencia · cierre de rechazo (vela del toque o la siguiente) | swing del toque · 0.5 ATR5 | 1R · 2R · máximo / mínimo del día |

**Base de control:** IBL/IBR incluyen niveles a 12.5 / 37.5 / 62.5 / 87.5 % del IB. Si 25/50/75
no superan al control, el nivel no aporta (mismo criterio que la medición de TDL KL del 11-nov).
VA80: `va80.control` da el % de días que tocan los dos bordes del VA sin la regla (días que abren dentro
y todos los días); la regla solo vale si `afterReentry.reachedFarPct` queda claramente arriba.
PB: la dirección la da el lado de llegada, no la tendencia, así que los toques con la tendencia 1h en
contra son el control; `lab.PB.trendTest` compara cada variante a favor frente a en contra.

**Confluencias** (en la vela de la señal, relativas a la dirección: favor / contra): VWAP, EMA 20/50,
EMA200, HTF 1h, régimen y alineación de TDL KL, plan pre-NY, chop, estiramiento, premium/discount,
SMT, gap vs cierre previo, hora desde la apertura, día de la semana, y en barridas si ya se tomó pre-NY.

**Reglas de simulación:** R neto con `costTicks` (2 ticks) por operación; stop y target en la misma vela
= stop; en la vela del llenado de un límite solo cuenta el stop; lo que sigue abierto se cierra a las 16:00.
El ranking ordena por `lb` = expR − 1 error típico, con mínimo `minN` (10) por variante y `comboMinN`
(20) por combinación, para no premiar rachas de pocos casos.

## Qué tan confiable es cada número

| Campo | Qué dice | Para qué |
|---|---|---|
| `days`, `se`, `lb` | días distintos, error típico **agrupado por día**, expR − 1 error | NQ y ES el mismo día, o 90 variantes de una ruptura, no son pruebas independientes |
| `ctrlExpR`, `edgeVsCtrl` | misma fecha, mismo riesgo y recompensa, pero vela y dirección **al azar** | si `edgeVsCtrl` ≈ 0 la señal no aporta: el resultado es del horario o del tamaño del stop |
| `walkForward` | elige con el 60 % más viejo de los días y mide en el 40 % nuevo; `survivors` = lo que siguió positivo | la defensa principal contra elegir por suerte entre cientos de combinaciones (desde 20 días) |
| `mfe`, `mae` (p50, p75) | cuánto fue a favor / en contra, en R, antes de salir | dónde poner stop y target sin multiplicar variantes |
| `ambPct`, `expROpt` | % de operaciones con stop y target en la misma vela de 5m; expR si todas esas hubieran ganado | el resultado real está entre `expR` y `expROpt`; si la brecha es grande, hace falta 1m |
| `nMore95` | operaciones que faltan para que la ventaja sea significativa al 95 % si se mantiene | no actuar antes |

Confluencias nuevas: `news` (high / medium / none, días con noticias USD de 07:00 a 16:00 ET; se acumulan en
`state/edgeful-news.json` porque `live/news.json` solo trae la semana), `pdClose` (dónde cerró ayer, relativo a
la dirección). Por estrategia, en terciles low / mid / high de la familia: `rangeAtr` (OR / IB contra el ATR
diario), `depth` (barrida en ATR5), `openDist` y `vaWidth` (VA80), `trendStr` (EMA20 − EMA50 en ATR5);
y `ibVsVA` (IB dentro / fuera / cruzando el VA de ayer), `nth` (1º, 2º o 3º pullback del día).

## Qué hay en `live/edgeful.json`

- `lab.<familia>.variants`: cada variante con n, % ganadoras, expR, pf, lb (y % de llenado en retest).
- `lab.<familia>.best` / `worst`: variante + 1 o 2 confluencias, las mejores y peores.
- `lab.<familia>.confluence`: efecto de cada confluencia sobre toda la familia.
- `ibLevels`: % de respeto por nivel del IB frente al promedio de los niveles de control.
- `klLevels`: histórico propio de TDL KL: % que aguanta por nivel, por papel (soporte/resistencia),
  régimen y alineación relativos, y sesión.
- `parity`: ORB del indicador EDG frente al motor.

## Indicadores (`pine/`, gráfico de 5m)

Visual y alertas en vivo de cada estrategia. Alerta "Cualquier llamada a la función alert()" →
`https://tradedadlog.com/api/tos-ingest?key=<TOS_INGEST_SECRET>`.

- `edg_orb.pine`: 3 ventanas a la vez (5/15/30), dibuja la elegida; BREAK_n, FAILED_n, SUMMARY.
- `edg_ib.pine`: IB con niveles 25/50/75 y extensiones; IB_SET, BREAK_H/L, SUMMARY.
- `edg_sweep.pine`: Asia/Londres; SWEEP, SUMMARY.

## Correr a mano

```
python3 edgeful/edge_stats.py --dry
```
