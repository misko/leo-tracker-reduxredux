# DS21 and DS22: combined-band failure investigation

The updated objective is sub-kilometre fast-scan localization on DS21 and DS22,
with a median below 0.5 km and CH1–8 improving on separate-band estimates.
This target remains unmet. No algorithm will be chosen separately for each
recording using reference error.

Three model investigations run in parallel. The original five-recording,
shared-six-proposal comparison gives the following worst two cases per model;
these ranks must not be mixed with later coverage-policy results.

| Model | Worst original case | Second worst original case | Investigation |
|---|---|---|---|
| A, sequential | 039: 6.229 km | 005: 5.436 km | Separate upper-band timing changes from learned band offsets before the final fit |
| B, free group contrasts | 039: 8.600 km | 023: 5.600 km | Profile geographic information against calibration and timing, including satellite-assignment covariance |
| C, native candidates | 023: 4.899 km | 039: 4.291 km | Distinguish relative satellite phase from receive-epoch retiming; audit optimization and identifiability |

Additional combination regressions are explicit targets: expansion-v2 B on
025 is 8.315 km combined versus 0.588 km on CH5–8; coverage-policy A on 009
regresses from 0.658 to 3.155 km. The 013 discovery failure was substantially
reduced by coverage, but its corrected estimates still miss the target.
Existing half-band estimates share discovery/proposal provenance. They are
useful paired fitting controls, but final claims against bands used alone
require independent band-only discovery and initialization as well.

The matched 34-recording DS21 development comparison remains useful as a
baseline and is running in bounded, monitored parallel jobs. Original frozen
scientific sources and fit budgets stay unchanged. Twenty DS21 locked fast
recordings remain reserved for a fixed algorithm and selection rule.

DS22's sealed authority contains 69 fast CH1–8 recordings. Sixty-eight have
pinned tracking inputs; DS22-137 has no tracking input or session identity in
that snapshot and remains explicitly unavailable, not excluded. Its manifest
SHA-256 is `705380facbea54e6a1142eab07f1114f7ae99d3066e4f8bd9210cb55014768f3`.
Before inspecting DS22 localization errors, the planned allocation randomizes
whole UTC-hour acquisition groups across all 137 members using seed 20261014:
45 fast development recordings (44 ready plus 137 unavailable), and 24 locked
fast recordings. This allocation requires its own verified frozen inventory.

Each next prototype must state a falsifiable mechanism, preserve fitted c,
record all failures, and compare the same observations and search budgets.
Reference errors enter only after training selections are sealed. Report
per-case CH1–8 minus each half-band error, median, p90, maximum, availability,
and failure counts separately for each dataset and algorithm version.
Frequency-fit improvements alone do not establish localization improvement.

No new RF collection is part of this work. Reports are published separately
from research code and local scientific receipts.
