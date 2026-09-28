# Frozen 24-document resource-readiness measurement

This specification precedes execution. The experiment loads exactly 24 `ready` captures from one sealed DS7 input contract through `ds7_fast_baseline_adapter.load_documents`, constructs the optional Wave 4 `BatchedJointObjective`, and evaluates it exactly once at east/north zero with every recording-time offset zero.

It is a resource experiment, not a fit. It must not invoke an optimizer, score a position, read reference or pose data, read raw IQ, export sources, or modify any Wave 4 file.

## Bounds

- one process and one CPU/BLAS thread at nice 19;
- 120 seconds total wall time, enforced both internally and by a root-side timeout;
- 4 GiB address-space limit;
- exactly one objective/gradient call after one document load;
- output written exclusively under this directory.

## Measurements

The receipt must bind the input contract, every observation/candidate artifact by declared and actual SHA-256, the optional arm, current objective/loader sources, and `reports/2026_09_27_ds7_wave4/closeout.json`. It must report ready-document count, tracks, candidate rows, training observations, retained NumPy array bytes, current and peak RSS before/load/objective, load wall/CPU time, objective wall/CPU time, and the finite objective/gradient norm.

The report may linearly extrapolate retained bytes, tracks, candidates, and objective time from 24 to 88. RSS extrapolation must show both a proportional upper estimate and an incremental estimate based on measured post-import/load growth. These are planning estimates under heterogeneous captures and changing host load, not a full-88 execution guarantee.

The readiness question is whether a future, separately authorized 8--10 GiB process envelope appears sufficient without adding streaming infrastructure. This run may allocate no more than 4 GiB and may not launch a full-88 objective or fit.
