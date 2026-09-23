# TRAIN edge/reference convention audit

## Result

The production GLRT and persistent-hop projection contain no lower/upper CFO
sign reversal. Both edges use the same residual-frequency estimator and define
`tracking_cfo_hz` as acquired CFO plus residual CFO. Edge selection changes the
QIN pilot bins and reference template. The persisted RF projection subtracts
the measured IF offset for both edges, and trajectory normalization multiplies
CFO by the positive ratio `canonical_rf_hz / actual_rf_hz`.

A report-owned IQ injection independently confirms the convention. With an
acquisition seed deliberately displaced by 1.5 kHz, injected +42 kHz and
-42 kHz CFO were recovered within 200 Hz with the correct residual direction
on both lower and upper templates. Two probes separated by one second with the
same -1.8 kHz/s injected chirp recovered -1.776 kHz/s on both edges. Five
focused tests pass. The finite error reflects the GLRT frequency grid. This
evidence weighs against a simple template or canonical projection sign bug as
the cause of the sealed lane pattern; it is not a full end-to-end acquisition
or hardware calibration test.

The corpus does not isolate an edge effect. The sealed diagnostic contains 313
lower-edge and 173 upper-edge pairs. Their absolute-time standardized mean
difference is -0.34, and the lower/upper counts across absolute-time quartiles
are 88/34, 84/37, 63/58, and 78/44. Only five sessions contain passing pairs
from both edges. Within those five sessions the mean lower-minus-upper
differential slope is -9.41 Hz/s, but this tiny, selected subset spans -17.86
to +2.43 Hz/s and is not a randomized edge comparison.

The organized lower/upper lane signs therefore remain a real diagnostic clue,
but current evidence supports neither an estimator artifact nor edge causality.
RF channel, edge, receiver-pair support, satellite association, and observation
time remain coupled. A shared receiver-drift correction is not supported by
this evidence.

## Scope and provenance

The audit reads only the sealed TRAIN pair result and strict recovered TRAIN
metadata. It does not use VAL, TEST, geographic truth, a position refit, or new
RF data. `results/audit.json` binds the audit source, sealed pair result,
metadata artifact, and the four inspected production source files. Existing
production code was not changed.

Reproduce from the repository root with:

```bash
uv run pytest -q tests/tools/test_train_edge_convention_audit.py
uv run ruff check reports/2026_09_23_train_edge_convention_audit/audit.py tests/tools/test_train_edge_convention_audit.py
uv run python reports/2026_09_23_train_edge_convention_audit/audit.py
sha256sum reports/2026_09_23_train_edge_convention_audit/audit.py reports/2026_09_23_train_edge_convention_audit/results/audit.json
cat reports/2026_09_23_train_edge_convention_audit/results/audit.sha256
```
