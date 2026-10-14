# B relative orbital phase: matched warm result

Relative orbital phase does not repair the original B worst-case pair. Full
CH1–8 worsens on039 and improves only slightly on023. Do not promote this
intervention or claim the0.5km target achieved.

|Case|View|Original epoch km|Relative phase km|
|---|---|---:|---:|
|DS21-039|CH1–8|8.599847|9.321383|
|DS21-039|CH1–4|2.917469|1.222063|
|DS21-039|CH5–8|20.117621|Unavailable: nonstationary|
|DS21-023|CH1–8|5.599817|5.451883|
|DS21-023|CH1–4|29.635673|30.294240|
|DS21-023|CH5–8|10.458750|9.901805|

These are original B shared-discovery half views, not independent four-channel
pipelines. Each condition uses one identical per-view original training winner
and matching new25km search disk,20-second/600-iteration cap, fitted c and
unchanged common-clock/calibration priors. This is an additional warm control,
not a complete six-start refit. Both case outcomes sealed before reference
evaluation. No held data or reference was used for fitting or selection.

All12 calls returned;11 passed independent stationarity checks. The039 high
phase solver reported success after1.687s/386 evaluations but projected
stationarity.001304546 exceeds.001, so its position is not reported as an
accepted estimate. This was not a timeout and was not retried. Whole-case
times were33.803s and23.644s, including preparation. Epoch controls reproduce
the original selected solution within floating-point precision.

Full-band phase likelihood NLL rises573.412 on039 and42.671 on023. RMS rises
98.245→103.506Hz on039 and falls94.674→89.476Hz on023. Meanwhile039 low-band
position improves substantially while RMS worsens82.308→83.548Hz;023 low-band
NLL improves79.459 while position worsens. Score, residual RMS and position
accuracy remain distinct outcomes.

Actual-data zero-relative nulls, all-coordinate finite differences and
Python/native objective/gradient/posterior equivalence passed before fitting;
see MODEL_B_PHASE_PROTOCOL.md. This rules out the tested implementation error
as an explanation for these adverse results. A single warm branch does not
exclude other stationary basins or combinations of physics changes.

Receipts: local/model-b-phase-control-039-v1 and
local/model-b-phase-control-023-v1, including call launches/results/terminations,
sealed training outcomes and development-errors.json. Terminal hashes:
039700acec11f8434c716bae94a39ae5122f2017e907eb638efd66df4bd9980fd10;
023e6bfada5af844110fae0286b594260353dd97e5b0f989a79123fc37aabd15c37.
Source commits81411c4ed (control) and6e475579d (post-seal evaluation).
