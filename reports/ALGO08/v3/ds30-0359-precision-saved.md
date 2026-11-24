# Guarded coefficient-space grid publication on DS30-0359

The guarded option used the original predictor at **356 of 356** evaluations.
It reproduced both calibrated fixes, the full grid and all eight PNGs.
The complete saved process took **19.239 s elapsed / 19.163 s CPU**, compared
with **15.558 / 15.553 s** for the clean composed worker and **29.703 /
29.677 s** for fresh installed ALGO08v3. The guarded coefficient-space path
did not qualify.
[Frozen protocol](ds30-0359-precision-saved-protocol.md) ·
[Machine receipt](measurements/ds30-0359-precision-saved.json.gz)

| Same signed saved input | Fresh installed | Clean composed | Guarded coefficient-space option |
| --- | ---: | ---: | ---: |
| Numerical solve including full grid, elapsed / CPU s | 24.984 / 24.960 | 12.260 / 12.257 | 15.371 / 15.338 |
| Official publication inside worker, elapsed / CPU s | 28.069 / 28.044 | 14.243 / 14.240 | 17.797 / 17.725 |
| Child through verified exit, elapsed / CPU s | **29.703 / 29.677** | **15.558 / 15.553** | **19.239 / 19.163** |
| Separate admission and isolated smoke, elapsed / CPU s | 0.588 / 0.540 | 0.600 / 0.553 | 0.547 / 0.499 |
| Exit with corresponding admission, elapsed / CPU s | 30.291 / 30.217 | 16.159 / 16.106 | 19.786 / 19.662 |

The 32-call diagnostic had exercised the unguarded coefficient-space
arithmetic and found numerical agreement on those exact operands. The
full option kept the checked original posterior, required a supported
residual layout, then checked the bias downdate's diagonal margin,
the Cholesky condition estimate and the final result. No candidate score
passed that combined guard. Telemetry groups failures at these checks, so
the record does not identify which specific check rejected each call. The
original reduced predictor succeeded on all 356 attempts. No dense fallback
or incomplete grid occurred.
[Earlier paired kernel slice](ds30-0359-preparation-and-precision.md) ·
[Guard implementation](grid_predictive_precision.py)

The predictive kernel spent **1.812 CPU s** including the unused candidate
preparation, guard and original calculation, compared with **1.212 s** in
the clean worker in a separate launch. Both runs paid the same 134 original
authenticated catalogue reads. The fresh optional process also recorded
9,968 input blocks and 66 major faults versus zero of each in the controls.
The whole-process **+3.681 s elapsed / +3.610 s CPU** difference includes
work outside prediction and resources without file-level attribution.
The optional process was **1.544×** the fresh installed speed through exit
and **1.531×** when charging each admission. No additional solver launch
was made after this comparison.
[Clean composed control](ds30-0359-composed-saved.md) ·
[Fresh installed control](ds30-0359-installed-control.md)

Both arm endpoints and RF metrics, all **3,640 ordered owners per arm**,
the terminal, graph, numerical path, every score at all **179 locations**,
and both sampled minima matched the clean control exactly. Fixed-zero
and fitted horizontal error remain **592.489 / 666.751 m**, and RF RMS
remains **115.604323 / 115.588647 Hz**, as scored on the existing sealed
control. The ordinary-qualified image verifier compared all eight encoded
SHA-256s and decoded RGBA SHA-256s. All matched. The match validates the
fallback's published result.

The first isolated launch stopped before solver or intake work in
**0.339 s elapsed / 0.170 s CPU** because the new protocol pin occupied the
field used by the composed worker's own protocol. The corrected launcher
binds both. The read-only score was retried with the checkout's read-only
storage API after an installed API argument mismatch. The timed child and
prediction seal stayed untouched. All science used one low-priority
Gauss CPU 2 lease, one numerical thread and the original resident saved
packet and catalogue. No waveform or backing archive inputs were opened.
Three focused tests passed, including normal condition, supported numeric
parity, and safe fallbacks for ill-conditioned and compact residuals.
[Entry and scorer](ds30_0359_precision_saved.py) ·
[Component tests](../../../tests/pipeline_eval/test_grid_predictive_precision.py)
