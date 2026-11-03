# Fast ARM track comparison

This directory compares independently reconstructed track sets without using
candidate IDs, ranks, or equal track counts as proof of recovery.  The fixed
thresholds in `thresholds.json` were written before any fast-track result was
inspected.

Eligibility always requires an identical receiver/channel/edge/RF lane.  The
strict view uses the deployed 250 Hz/s cross-lane rate gate and 2500 Hz tracking
residual gate, plus close time-support agreement.  The relaxed view uses twice
those numerical gates and permits fragmented support.  Both views use a global
one-to-one assignment within each lane.  Candidate/source overlap is reported
independently so a curve-only association cannot be mistaken for shared GLRT
evidence.

A reference track with fewer than the configured six canonical recording
source identities represented in the native observations is reported as
unsupported. Candidate timestamps are deliberately not used as source identity
because integer and fractional detector epochs can differ within one dwell. Supported unmatched
reference tracks are misses; unmatched native tracks are extras.  Multiple
eligible native tracks for one reference are split evidence, and multiple
eligible reference tracks for one native are merge evidence.  These labels are
diagnostics around the one-to-one assignment, not extra matches.

The report also measures how much of each reference time interval is covered by
the union of all individually eligible native fragments. This continuity metric
does not add matches and cannot turn a split into one recovered track.

Run the comparator with the maintained server oracle and ARM observations:

```sh
python3 compare_tracks.py \
  --reference-observations ../server-baseline/output/server-observations.tsv \
  --reference-tracks ../server-baseline/output/server-tracks.tsv \
  --reference-source-map ../server-baseline/output/server-candidate-map.tsv \
  --native-observations ../server-baseline/output/arm-observations.tsv \
  --native-tracks ../grid/arm-3601-64-512.tsv \
  --native-source-map ../server-baseline/output/arm-candidate-map.tsv \
  --output comparison.json
```

The source maps bind candidates to `(original visit, receiver, probe)` and are
required. Candidate timestamps are never substituted for that authority. The
parser also checks every point against its observation lane, normalized CFO,
alias conversion, and support interval. Research profiles may lack published
config and tracklet identities; the report records those omissions explicitly.

## Frozen grid diagnostic

`grid-summary.json` applies the thresholds above to the maintained 63-track
Python server oracle. The ordinary 3601/64/512 ARM-input result has 43 strict
and 54 relaxed one-to-one associations. None of the reduced grids improves the
strict count: 1801/32, 601/32, and 901/32 each have 42; 301/32 has 41. Every
grid leaves one oracle track unsupported by the ARM observation input, while
the other unmatched oracle tracks are supported misses. These are diagnostic
associations between different detector outputs. They do not establish equal
track recovery, and the server oracle's standard 4-second/8-point policy is
different from the native default 3-second/6-point policy.
