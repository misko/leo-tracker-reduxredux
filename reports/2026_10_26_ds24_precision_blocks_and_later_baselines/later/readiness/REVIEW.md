# Transfer and precision: the remaining decision

The complete-owner study moved beyond rejected-source recovery toys: it replayed
all 159 points from four accepted owners, preserved exact historical parity,
and tested the same native CFO intervention in both c arms. It produced useful
two-scan development evidence, with stricter research qualification preserved
only for 0010; 0011 lost 57 postfit-only IDs. This is progress, but neither the
number of refined windows nor a higher pilot score is a new cohort replication.
Source: `ds24-complete-owner-refinement-r01/measurement/FINDINGS.md` and
`position/execution.json`.

The factorial study sharpens the mechanism. The saved Hδ prediction matches
the CFO effect at the original fixed precision packet within 0.354–2.323 m
across both scans and c arms. The earlier roughly 92–95 m discrepancy in 0011
largely belongs to the precision-packet intervention and its interaction, within
this conditional model. The packet includes both noise and prior precisions,
learned at different endpoints. This does not prove a physical noise error or
license replacing the inferred scatter with a smaller number. Source:
`ds24-cfo-precision-factorial-r01/linearization/FINDINGS.md` and
`solver/rf_report/contrasts.json`.

The later four now remove the immediate input-availability ambiguity: complete
contracts, acquisition clock brackets and ordered raw-authority metadata pass.
They do not remove exposure or truth ambiguity. Their next legitimate role is
a fixed four-case transfer with exact runtime/measurement parity, complete-owner
coverage, matched baseline/correction fits, unchanged gates and separate raw
versus fallback results. Without applicable evaluation-site authority the
geographic part remains unavailable; the RF/retention test is still useful.
No preparation or correction test has started during this review pause.

## What the cached pilot correlations can support

The existing cache is sufficient for a small **conditional precision diagnostic
without IQ or detector calls**. The 159-window replay files preserve, per window,
frame-by-64 exact/control complex correlations and their times. The refiner
already exports the local score curvature, original cell, numerical reference
and boundary flags. Fixed frame or symbol partitions could therefore measure
repeatability and held-partition score behavior at a training-only frequency.
Current acquisition/epoch/rank selection used the full window, so such a result
would remain conditional on that selection, not end-to-end independent
validation. No such calculation was run here.

Persistence was checked locally, not merely inferred from return statements:
all 64 synthetic NPZ files contain exact/control complex arrays and time arrays,
with frame-by-64 headers. The two complete-owner worker JSON files preserve
76 and 75 new recorded correlation matrices, with 14 or 15 frames by 64 symbols;
the eight reused rows remain in the prior recorded result. The check inspected
headers/schema only, not scores. [cached_schema_check.json](cached_schema_check.json)
records exact cache files and hashes.

The saved exact/control arrays also exist for the prior known-frequency
synthetic controls, with truth and correlation-file hashes. They could test
whether a proposed correlation-based interval actually covers those known
frequencies before affecting real-data weights. Paired receivers/shared
synthetic windows must not be counted as independent repetitions.

There is an important gap: the score is a normalized sum of coherent squared
correlations, **not a calibrated log likelihood**. Its curvature alone cannot
be inverted into an honest Hz variance. Current caches do not provide a
validated complex noise/interference covariance or arbitrary unselected
pilot/symbol data. Odd/even disagreement or bootstrap scatter is a precision
proxy until a declared noise law and known-truth coverage test justify more.
The control sequence need not be pure noise. Shared deterministic bias,
interference and rank/epoch errors can survive an apparently stable split.

This is not entirely new prior art: `tools/ds23_refined_noise.py` already combines
odd/even-frame disagreement with polynomial predictive scatter, and
`tools/report_470384_continuous_glrt_refinement.py` already checks held-out Qin
symbols after continuous refinement. A useful next control would validate a
specific uncertainty law on the **current saved known-truth correlations**,
then ask whether its scale remains consistent on the fixed accepted-owner
cache. It should stop short of new weighting or accuracy claims if calibration
fails. No new broad precision sweep or detector campaign is needed to answer
that initial feasibility question.

Concrete cache/source authorities:

- `/srv/bulk/leo/research/ds24-complete-owner-refinement-r01/measurement/worker0.json`
  and `worker1.json`, hash-bound by its `RF_seal.json`.
- `/srv/bulk/leo/research/ds24-detector-response-r01/measurement/refiner.py`,
  especially `direct_score`, `refine_correlations` and the returned workspace.
- The same study's `measurement/execution.json` and `measurement/correlations/*.npz`,
  created by `measurement/run.py` with generated truth and per-file hashes.

This is source/schema review only. No pilot split, variance estimate, coverage
calculation, new draw, IQ access, position fit or GPS read was performed.
