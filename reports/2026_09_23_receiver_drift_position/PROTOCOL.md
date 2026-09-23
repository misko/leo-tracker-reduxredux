# Receiver drift with shared host-bracket timing: frozen protocol

This experiment continues the seed-20260923 random-group split. The 23
retrospective-test scans and all prospective evidence remain excluded. Position
truth is unavailable during inference and hyperparameter selection.

## Training-only model selection

Use the first twelve sessions in the frozen TRAIN partition order, matching the
previous receiver-drift diagnostic. Reconstruct every cached observation ID from
the public `ScannerTrackingInputStore`, projected scanner candidates, and
persistent-hop trajectory graph. Fail the experiment on any missing or conflicting
stream/path assignment. The earlier all-RX1 example is not generalized to another
scan without this exact join.

At each TRAIN scan's previously published coordinate, compare a
zero-drift control with receiver-drift ridge strengths
`[0, 100, 1000, 10000] s^2`. For each scan, select one saved-host-bracket timing
offset on the same 17-point inclusive grid as the shared-timing experiment. Each
track retains a separately profiled constant frequency offset. For every exact
receiver stream identity (`stream_id`, RX0 or RX1), fit one frequency slope in
Hz/s against within-track elapsed time centered at that track's training-row mean.
The exact path ID remains part of the join audit but does not create a separate
oscillator parameter.
Apply the ridge penalty once per receiver coefficient, not once per track.
The coefficient fit minimizes observation-level squared error plus this ridge;
the outer scan and location comparison uses duration-weighted capped track RMS
plus the same once-per-receiver penalty. This is a declared alternating nuisance
fit and capped outer-score heuristic, not an exact joint capped-loss optimizer.

Candidate identity, shared scan timing, track intercepts, and receiver slopes use
training frequency rows only. Rank ridge strengths by pooled complementary-row
frequency RMS over these twelve TRAIN scans after freezing each fitted scan. This
is training-only inner validation, not independent leave-group-out validation.
Break ties toward stronger regularization. Do not use coordinates or geographic
errors in this choice. Hash and save the training evidence and selected strength
before reading validation evidence.

The published coordinates, validation seeds, and candidate pools remain
historically response-conditioned. This experiment preserves that known
limitation and does not claim blind full-catalogue acquisition.

## Frozen validation

Compare exactly two arms: the zero-drift shared-bracket capped-800-Hz control and
the selected receiver-drift shared-bracket capped-800-Hz model. Retain the same
two complete validation groups and each group's first-scan sensitivity view, own-
window published seeds, prior intersection, duration weighting, 17 timing points,
and 150 evaluations per seed used by the shared-timing experiment. Preserve all
attempts, selected timings, receiver slopes, timing-boundary flags, mapping
coverage, and runtime.

Seal inference before scoring complementary frequency rows or comparing to the
reference coordinate. Report capped and uncapped complementary-row RMS and
geographic error for all four views. Lower frequency residual alone does not
establish position accuracy. Receiver slope remains confounded with orbit,
identity, timing, and track-shape error.

No production deployment, new RF collection, persisted-contract change, test
partition access, or prospective evidence is authorized.
