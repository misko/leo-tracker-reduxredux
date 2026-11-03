# Invalid preliminary alias-gauge diagnostics

These files preserve the first integration attempt, before the new tracks'
integer aliases were aligned with the existing receiver frequency gauge.
In scan 0342, roughly 200 kHz residuals and near-zero robust precision exposed
the error. They are not valid algorithm comparison results and are excluded
from the parent report's tables, plots and evaluation CSV.

The corrected adapter chooses aliases using other tracks' RF-derived receiver
gauge at the predeclared regional center. It preserves measured CFO modulo
integer aliases and does not consult GPS.
