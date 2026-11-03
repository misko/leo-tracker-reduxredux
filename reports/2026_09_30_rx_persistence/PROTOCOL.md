# Frozen coefficient persistence test

Test whether the previous paired-state model's persistence ceiling explains its failed signed-geometry transfer. Use the same six leave-record-out calibration folds and original dataset. Freeze all coefficients, occupancy, preprocessing and candidate priors. Read no new panel. This is development on reused evidence.

For each P/U/O arm and fold, score persistence times 1, 10, 30, 100 and 300 seconds on the original five-record training reception data. Choose highest training score, breaking exact ties toward shorter persistence. Coefficient penalties are constant across this comparison. Apply that chosen time to the omitted record, scoring sequentially before update through reception and later windows. Also replay the original fitted time. Do not select from held scores.

Report all grid training scores, selection, per-record role scores, P/U/O differences and signed swap/reversal/permutation controls. A useful direction result requires positive equal-record later O-minus-U and O-minus-P, each positive by more than 1e-6 nats/window in at least four of six records, plus positive mean O-minus-each-control with the same recording criterion. No geometry promotion, new confirmation evaluation or geographic fit follows automatically.

Numerical replay must match the original role scores within 1e-8 nats/window. Preserve original fits and sources. One serialized worker, one BLAS thread, at most 120 seconds for execution. No new RF or IQ reads. This isolates persistence conditional on existing coefficients; it is not a full refit of a new model family.
