# All-observation single-scan IID screen

Using all available observations does not pass the declared advancement gate.
All eight fits qualify, but only three positions improve. Median error falls
1.90%, while mean and P90 error increase. No remaining-panel fits are launched.

| Eight fixed screen scans | Original training only | All observations |
|---|---:|---:|
| Qualified |8/8|8/8|
| Median error |3108.16m|3048.99m|
| Mean error |3481.54m|3499.48m|
| P90 error |6046.04m|6344.54m|
| Below 1km |1/8|1/8|

The model retains original Student-t4/100Hz observations, the profiled 1MHz
CFO prior, full catalogue divisor, original shortlists and training-mask
visibility. Only the fitting mask changes, using formerly held observations
from the same recording. Nothing is pooled across recordings. The first scan
uses 3162 observations rather than 1940; its error improves 765m to 318m, but
that favorable example does not represent the panel result.

Formerly held data now fit position, timing, CFO and candidate evidence.
Consequently the harness's common-IID held-score fields are in-sample
diagnostics and provide no independent prediction claim. Bank admission is
still conditional on the original training export. These limitations are
declared before fitting in [PROTOCOL.md](PROTOCOL.md).

Three component tests pass: exact original parity and input-mask isolation,
direct full-data density with unchanged visibility, and gradient agreement
with intentional dependence on formerly held measurements. The index0
original-mask control qualifies and reproduces the original score within
2.55e-11 and fitted coordinates within 8.88e-9. Every screen fit exits zero
under its 90second cap; runtimes are approximately 25–37seconds.

[assessment.json](assessment.json) verifies source/input hashes, preserves all
attempts, and checks maximum qualified score selection before computing the
declared stricter screen gate. [assess.py](assess.py) reproduces the assessment
with exclusive output creation. No default, production or golden fixture
changes occurred. This negative screen does not prove that reserving data is
always harmless; it says this full-data estimator did not produce a dependable
gain on the frozen DS11 screen.
