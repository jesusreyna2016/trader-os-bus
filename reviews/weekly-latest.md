# Review semanal - 2026-W47 (primera semana de seguimiento)

## Marcador de disciplina

Solo hay dato confiable para **2 días** de la semana: viernes 21 ("sin operar", limpio) y
domingo 22 (roto). Lunes a jueves no tienen review ni histórico de `live/trader.json` -
**brecha de dato**, no se asume que esos días fueron limpios.

- Días limpios: 1 de 2 días con dato (50%, muestra insuficiente para sacar conclusión).
- Violaciones por regla (domingo): R1 revancha x2 incidentes, stop del día ignorado tras
  romperse x2 entradas posteriores, NO_STOP x1 posición abierta.
- maxLossStreak: 3.
- pnlR con dato: -208.97R (domingo), 0 (viernes).

## Patrón recurrente

La fuga es inequívoca y se repitió **dos veces el mismo día**: cerrar en pérdida y reabrir
de inmediato sin pausa, una vez con 7.5x el tamaño normal y en contra, otra vez sin stop.
Es exactamente R1/R2, persecución de pérdidas, la fuga que el método marca como la que más
cuentas le ha costado.

## ¿Mejora o empeora?

No se puede decir: no existe semana previa en `coach-state.json`, esta es la línea base.

## Ajuste propuesto (1)

Pausa dura y cronometrada tras cualquier SL o salida con pérdida antes de permitir una
nueva entrada en la misma sesión, y ninguna entrada sin stop colocado, sin excepción.
