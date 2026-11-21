# trader-os-bus

Bus de datos del cerebro **Trader OS**. Lo escriben funciones de Netlify del repo
`tradedadlog`; lo leen las lentes (Contexto, Edge, Coach) y el watchdog.

## Estructura

```
live/
  feeds.json      Último estado crudo por fuente+símbolo (lo escribe tos-bus-snapshot).
                  Claves "<src>:<SYM>": feed (FEED1, geometría), command (sesgo fusionado),
                  orb, regime, trendcl, tdl_kl (heartbeat STATE).
  market.json     Estado compuesto por símbolo (lo escribe la lente Contexto, tos-market):
                  { verdict, bias, dir, conviction, dayType, newsRisk, geo{...}, struct{...} }.
events/
  <YYYY-MM-DD>.jsonl   Log append-only de eventos semánticos Tier B (tos-bus-snapshot):
                  tdl_kl (TOUCH/REJECT/SWEEP/ACCEPT/FAILED_BREAK/RETEST/CISD/ALIGN),
                  tdl_rev (entrada + RESOLUTION con R), tdl_po3 (PHASE_CHANGE).
```

## Flujo

TradingView (webhook) → `tos-ingest` → Netlify Blobs (store `tos`) →
`tos-bus-snapshot` (espeja crudo aquí) → `tos-market` (compone `live/market.json`).

Mirror cada 15 min (`tos-bus-cron`). Todo merge-only con guard anti-borrado.

El diseño completo vive en `tradedadlog`/`trader-os/DESIGN.md` y `TRADER-STATE.md`.
