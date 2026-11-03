# Tracking after removal of the GLRT coarse cutoff

Frozen algorithms were rerun on all 16,191 passing candidates from the same
300-second DS9 scan. Coarse-seeded curvature tracking is the strongest candidate
for trajectory coverage: it represents 55/62 reviewed server segments in 5.72 s
on PLUTO+. Rolling-backfill remains better at reproducing separate server
segments under one-to-one matching (50 versus 45). No algorithm was retuned.

## Full-scan comparison

Strict representation requires both >=80% reference source coverage and >=80%
in-span output source purity, with the existing 2,500 Hz circular CFO tolerance.
Only the previously approved reference #10 exception is excluded. Several
references may be represented by one output; one-to-one matching forbids this.
Short is <15 s, medium is 15–<30 s, and long is >=30 s.

| Frozen method | Strict represented /62 | Short /9 | Medium /25 | Long /28 | One-to-one /62 | ARM tracking seconds |
|---|---:|---:|---:|---:|---:|---:|
| Rolling, 8 s | 43 | 7 | 15 | 21 | 43 | 1.84 |
| Kalman v2 | 24 | 2 | 8 | 14 | 23 | 39.86 |
| Local tracklet linking v2 | 44 | 4 | 19 | 21 | 40 | 23.27 |
| Coarse-seeded curvature | **55** | **7** | **23** | **25** | 45 | **5.72** |
| Rolling-backfill | 50 | 7 | 19 | 24 | **50** | 4.57 |

Physical timings are medians of three sequential runs on 192.168.1.15, firmware
0.59. All outputs were byte-identical to host outputs; physical component tests
passed. Coarse-seeded timing includes seed generation and curvature extension.
Rolling-backfill reuses the already qualified run on exactly this input.
These are batch tracking times, excluding GLRT, acquisition and transport.
Coarse-seeded whole-process median is 7.41 s. This does not qualify continuous
live scanning or streaming latency.

## What changed with denser GLRT input?

| Method | Previous strict /62 | New strict /62 | Previous ARM seconds | New ARM seconds |
|---|---:|---:|---:|---:|
| Rolling | 39 | 43 | 1.12 | 1.84 |
| Kalman v2 | 33 | 24 | 11.74 | 39.86 |
| Linking v2 | 40 | 44 | 14.96 | 23.27 |
| Coarse-seeded | 49 | 55 | 3.54 | 5.72 |
| Rolling-backfill | 47 | 50 | 2.56 | 4.57 |

More detections do not automatically improve association. The frozen Kalman
configuration loses substantial agreement, whereas coarse-seeded gains six
segments. Determining the Kalman failure mechanism requires a separate audit;
these results alone do not establish its cause.

Coarse-seeded recovers the three coverage regressions seen in rolling-backfill:
#9 (39/39 sources, 90.7% purity), #33 (29/30, 82.9%), and #37 (71/71, 97.3%).
#19 remains a source-purity failure (22/23, 61.1%).

## Remaining disagreement and merge caveat

Ignoring purity, coarse-seeded reaches >=80% coverage for 61/62 references,
including all 28 long references. This is a coverage diagnostic, not 61 correct
tracks. Its seven strict misses are #8, #11, #19, #30, #35, #47, and #60.
For each, its selected output contains all available reference-matching sources
in this GLRT input. Six fail only purity; #11 also has only 23/29 matching
sources available (79.3%, below the required 24/29).

Ten coarse-seeded outputs qualify against multiple reference segments. The
12 eligible reference pairs include five overlapping in time and seven disjoint.
These associations explain why 55 represented segments become only 45 under
one-to-one scoring. They may include fragmented server trajectories, but physical
identity and correct merging have not been established. See merge-audit.json.

Coarse-seeded emits 80 hypotheses versus rolling-backfill's 542; 26 versus 139
have no matching source/CFO support in any of the 63 server references. Those
counts are not false-positive rates: the server is not exhaustive ground truth.
Likewise, extra detections outside a server assignment are not proven noise.

## Recommended next iteration

Use coarse-seeded curvature as the coverage baseline, retaining rolling-backfill
as the segment-separation control. Audit the five overlapping reference pairs
first, then test a local split/conflict-resolution pass that preserves the
recovered #9/#33/#37 evidence. Evaluate both segment representation and one-to-one
agreement with unchanged thresholds. Do not discard new GLRT points merely to
raise source purity; use local continuity and competing trajectory evidence.

This comparison does not yet justify replacing the deployed tracker. It identifies
a promising recovery path at only 1.15 s more batch tracking time per 300 s scan.

## Additional outputs and plausibility audit

Here an additional output is an output left unmatched by the frozen strict
one-to-one assignment. This includes duplicates, fragments, merged or impure
tracks, and potentially new trajectories. It does not mean a distinct new
satellite. For clarity, the simple numerical excess over 62 references is also
shown; it is a different quantity.

| Method | Total outputs | Numerical excess over 62 | Additional unmatched outputs | >=80% sources corroborated by server tracks | Pass local continuity screen |
|---|---:|---:|---:|---:|---:|
| Rolling | 542 | 480 | 499 | 191/499 (38.3%) | 432/499 (86.6%) |
| Kalman v2 | 128 | 66 | 105 | 66/105 (62.9%) | 105/105 (100%) |
| Linking v2 | 128 | 66 | 88 | 53/88 (60.2%) | 77/88 (87.5%) |
| Coarse-seeded | 80 | 18 | 35 | 0/35 (0%) | 33/35 (94.3%) |
| Rolling-backfill | 542 | 480 | 492 | 196/492 (39.8%) | 471/492 (95.7%) |

Corroboration counts same-source, same-lane CFO agreement within 2,500 Hz
against the union of points assigned to all 63 server references (including #10
as descriptive evidence only). It does not require a complete reference match,
and therefore can support fragments or duplicates. Neither column is an
estimated real-track fraction; the two columns overlap and must not be added.

The continuity screen uses the existing causal local linear diagnostic: predict
each point from the previous 8 seconds with at least five prior points spanning
two seconds. Require at least five predictions covering at least half the
output points, a 95th-percentile circular prediction error <=2,500 Hz, and no
adjacent gap >4 seconds. These descriptive thresholds were set before computing
this audit. They are not calibrated on labeled real and false tracks. Smoothness
is partly selected by the trackers themselves and can accept smooth false
associations; failing or lacking evidence does not prove a false track.

Among outputs with **zero** server-track source/CFO support, the screen passes
106/147 rolling outputs (72.1%), 12/14 linking outputs (85.7%), 24/26
coarse-seeded outputs (92.3%), and 125/139 rolling-backfill outputs (89.9%).
Kalman has no zero-support outputs. These are plausible candidates for review,
not verified new tracks. Coarse-seeded's 0/35 strongly corroborated extras is
compatible with many extras being outside the server's assigned points; it does
not establish that those extras are noise.

The available evidence cannot give a defensible true-real fraction. That needs
independent validation, such as orbital/Doppler consistency or confirmation in
held-out detections, plus duplicate-family resolution. `additional_tracks.py`
reproduces the audit; `additional-summary.json` and per-method
`additional-tracks.json` retain the counts and individual diagnostics.

## Reproduction and evidence

### Extra-duration and missed-long visualizations

The 33 continuity-screen-passing extras span 11.25–65.53 seconds (median
25.84 seconds): 13 are <15 seconds, eight are 15–<30 seconds, and 12 are
>=30 seconds. Duration here is first-to-last measured point, not summed RF
exposure. These are output hypotheses, not distinct verified satellites.

![Extra duration distribution](extra-duration-distribution.png)

Six examples are selected at evenly spaced ranks in sorted duration order,
including the shortest and longest, without selection by visual appearance.
Dots are measured CFO with tracker alias choices, not fitted curves. Each
panel has its own axis scales. ARM output IDs and server reference IDs belong
to different namespaces. Output #51, for example, also partly represents
server reference #8, so an additional output need not be an entirely new track.

![Extra measured trajectories](extra-track-examples.png)

The three long strict misses are server #8, #30 and #47. Their coverage is
85.7%, 90.0% and 83.3%, respectively; their source purity is 64.3%, 59.0%
and 54.1%. Thus all three fail purity rather than the coverage threshold.
The additional ARM points visually follow the same trajectories, but this alone
does not establish physical identity. Left and right plots use identical axes
within each row. ARM output is clipped to the reference time span and aligned
to its CFO alias for display; scoring is unchanged.

![Long server reference comparisons](missed-long-tracks.png)

`plot_extra_tracks.py` regenerates PNG and PDF versions of all three figures;
`plot-summary.json` records duration counts and selected output/reference IDs.

Run `benchmark.py host`, then `benchmark.py score`, then `benchmark.py device`
using the scientific Python environment and frozen binaries referenced in the
script. Host output directories must be fresh. Device execution requires the
existing authorized PLUTO+ SSH configuration. No RF collection is performed.

- `protocol.md`: frozen comparison protocol.
- `science-summary.json`: duration buckets and regression targets.
- Each method's `evaluation.json`: full membership and one-to-one scoring.
- Each newly run method's `device/receipt.json`: timing and byte agreement.
- `coarse-seeded/merge-audit.json`: multi-reference associations.
- Prior input and rolling-backfill receipts: `../2026_10_01_arm_ungated_full_scan/`.
- Original comparisons: `../2026_09_30_arm_streaming_tracks/`.
