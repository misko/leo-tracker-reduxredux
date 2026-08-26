# Frozen POST-FIX long-arc research cohort

Date: 2026-08-26 UTC

Status: **opened development cohort; exact-input registry frozen; no new
experiment run**

The machine-readable authority is
[`post-fix-long-arc-research-cohort-v1.json`](../config/analysis/post-fix-long-arc-research-cohort-v1.json).
It admits exactly two already-opened, device-counter-authoritative arcs for
future long-trajectory Doppler and satellite-association research. It is not a
holdout, it grants no secure satellite identity, and it does not authorize any
newer, dynamically discovered, PRE-FIX, or replacement input.

## Exact cohort

| Arc | Capture and path | Half-open span | POST-FIX continuity | Bound source | Present result |
|---|---|---:|---|---|---|
| `long-arc-9981-r19f2-s1-rx1-upper-0-30s` | `cap-20260824T192252-9981b9c27853`; `radio_pluto_19f2 / stream-1 / RX1 / upper` | samples `[0, 75,000,000)`; `[0, 30.000) s` | full capture: 150,000,000 stored = 150,000,000 device-span samples, 1 segment, 0 missing/gaps/overflows/enqueue failures; 573 full-capture refills | selected alias `-1`; five exact branch/trajectory digest pairs | strong receiver-relative cubic CFO curvature; NORAD 67930 conditional only |
| `long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s` | `cap-20260825T150802-473cb5bbcbd6`; `radio_pluto_19f2 / stream-1 / RX1 / upper` | samples `[93,937,500, 128,500,000)`; `[37.575, 51.400) s` | same full-capture equality and zero-loss gates; 573 full-capture refills; **132 refill handoffs inside this arc** | scope `7f564a…`, alias `0`, branch `f6d13e…`, trajectory `92955a…` | strong quadratic CFO/timing curvature; cubic CFO only a sensitivity; NORAD 59748 conditional only |

The `573` value is the refill count for each complete 60-second recording. It
must not be read as the number of handoffs in either selected span. The
`150802` evidence explicitly binds 132 in-arc handoffs. The `9981` report did
not persist an equivalent in-arc handoff count, so the registry records that
field as null rather than deriving and presenting a new result.

## Why both are after the refill fix

Both recordings use committed `RecordingManifestV2` manifests whose selected
`stream-1` records are complete. They retain device sample counters and report
`sample_loss_observable=true`. On the selected path, observed sample count
equals device-counter span, there is one continuity segment, and missing
samples, gaps, overflow evidence, clipping, enqueue failures, and terminal
rejected loss are all zero. Their first-sample times are explicitly
`device_counter_anchored`.

That is the repository's POST-FIX definition. It is stronger than a recording
date or a contiguous-looking stored array. Accepted refill handoffs are audit
markers in these captures, not omitted RF time and not automatic trajectory
resets. The original evidence says this directly for
[`9981`](2026_08_24_9981b9c27853_cubic_cfo_tle_comparison.md) and demonstrates
it across 132 handoffs for
[`150802`](2026_08_25_counter_continuous_frame_timing_and_delay.md).

## Immutable bindings

The registry freezes, for each arc:

- capture, radio serial, stream, receiver, edge, sample rate, IF, and exact
  half-open sample span;
- recording-manifest and sealed Standard-analysis run/digests;
- device-counter continuity, validated stream generation, gap-map digest, and
  timeline digest;
- exact selected alias, scope where available, branch IDs, and trajectory IDs;
  and
- the committed evidence artifacts, including compressed and decompressed
  frame-row digests for `150802`.

The validator
[`long_arc_dataset.py`](../src/leo/analysis/research/long_arc_dataset.py) checks
the registry against the immutable parent dataset policy, verifies every
committed artifact byte-for-byte, checks the primary evidence semantics, and
authorizes only an exact capture/path/span request. External manifest
verification reads manifest metadata only; it neither opens IQ nor discovers
alternative captures.

## Permitted and forbidden interpretation

These are good **development** inputs for comparing long-arc polynomial and
physics-informed trajectory models, testing blocked or rolling prediction,
separating constant CFO/rate nuisance from orbital curvature, and designing
matched catalogue/time nulls. They are particularly valuable because the
30-second `9981` arc requires a cubic radio description while the 13.825-second
`150802` arc clearly requires quadratic curvature but does not robustly require
CFO jerk.

They cannot provide a fresh confirmation because both have already been
examined extensively. Results must remain receiver-relative unless separate
clock/LNB/transmitter terms are measured. A low-RMS TLE overlay remains a
conditional candidate unless it also survives runner, wrong-time, rolling,
catalogue, site, and recurrence controls. The distinction between a physically
bounded orbital time nuisance and the deliberately broad wrong-time catalogue
null is recorded in the
[time-shift addendum](2026_08_26_wrong_time_specificity_and_orbital_time_shift.md).

Any additional arc, subspan, widened span, different receiver, alternate
branch, or new evidence product requires a reviewed v2 registry. PRE-FIX data
remain excluded rather than being repaired or pooled.
