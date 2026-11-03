# Extraction checkpoint repair

The initial bounded extraction stopped with an empty final inventory and 14
saved arrays. Its process handle is no longer available, so the exact exit code
was not recovered. These arrays alone do not establish completed extraction.

Before numerical evaluation, extraction was amended to atomically checkpoint
each completed selection and resume only hash-verified inventory entries.
Uninventoried arrays are re-read through the public read-only port. The same
18 frozen selections and numerical protocol remain in force. Each extraction
invocation retains its 120-second cap; at most two repair invocations are planned.
This is an execution amendment, not a scientific selection change.

The first repair invocation exited 124 at its 120-second cap, retaining 12
completed entries. The second resumed the remaining six and exited zero.
All 18 extractions succeeded.

## Deterministic phase convention correction

The initial numerical run returned all 18 excerpts, but short/long fits hit their
bounds in 8/5 excerpts. Code inspection identified an omitted deterministic
phase rotation: the narrowband pilot reference resets within each OFDM symbol,
while the helper upconverts continuously to the native FFT grid. The resulting
rotation is `exp(2j*pi*pilot_center_hz*symbol_index*4.4e-6)`. Independent
frame/carrier gains absorb the constant phase. Removing this known rotation
requires no estimated parameter or held symbols.

A synthetic raw waveform with injected +137 Hz recovered 137.034 Hz at the
upper edge and 136.978 Hz at the lower edge after the correction. This motivated
a corrected replay of exactly the same selections, search bounds and splits.
The frozen protocol predates this implementation correction; no outcome-based
selection or search expansion was introduced. The initial run and results are
preserved as `initial_run.py` and `initial_results.json`; its recorded `run.py`
digest identifies the preserved `initial_run.py` bytes. Those initial numerical
outcomes are invalid for comparing carrier-frequency estimators.
