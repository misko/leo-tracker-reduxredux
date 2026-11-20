# Fresh supplied-tile acceptance on simulated sites

Both receivers published all four correct-tile fixes in both calibration
arms. Joint pass identification published on zero of four omitted tiles
with zero calibration and one with fitted calibration. Pass geometry
published on two omitted tiles in each arm. Both receivers withheld
the shuffled input. All 18 method-and-query workers completed.

| Receiver and calibration | Correct-tile fixes / attempts | Within 5 km / attempts | Correct-tile median / P95 / max (km) | Omitted false fixes / attempts | Shuffle false fixes / attempts |
|---|---:|---:|---:|---:|---:|
| Joint pass, zero | 4 / 4 | 4 / 4 | 0.830 / 1.115 / 1.120 | 0 / 4 | 0 / 1 |
| Joint pass, fitted | 4 / 4 | 4 / 4 | 0.316 / 0.535 / 0.566 | 1 / 4 | 0 / 1 |
| Pass geometry, zero | 4 / 4 | 4 / 4 | 1.656 / 2.614 / 2.634 | 2 / 4 | 0 / 1 |
| Pass geometry, fitted | 4 / 4 | 4 / 4 | 0.197 / 0.304 / 0.313 | 2 / 4 | 0 / 1 |

Supplied correct centers missed by 8.476–9.892 km. Joint pass's fitted
arm published one wrong-tile fix at 48.625 km. Pass geometry's
omitted-region publications ranged from 43.093 to 58.721 km across
both arms. The joint gate reduced false publications on this draw and
preserved the correct-tile fix count. Its fitted median position error
was higher than pass geometry's on the four correct-tile cases.
[Per-query errors and scores](scores.json) · [Prediction seal](prediction-lock.json)

## Satellite and frequency evidence

On correct tiles, joint pass identification matched 91 of its 95
reported lane assignments to the planted emitter in the same channel
and activity interval. It found 46 of the 48 distinct planted
emitters in that comparison. Pass geometry's selected-ID sets
contained all 48 planted emitters. Its saved output does not resolve
lane-by-lane identity accuracy. On the fitted joint arm's false fix,
11 of 20 lane assignments matched, representing six distinct planted
emitters. Both methods found zero qualifying tracklets on the shuffle.
[Post-seal identity audit](identity-audit.json)

Conditional CFO RMS medians on the four correct tiles were 31.8 Hz
with zero calibration and 29.1 Hz with fitted calibration for joint
pass identification. Its median held frame residual was 0.0192 and
0.0156 µs in the same order. The pass-geometry CFO medians were
194.0 and 72.9 Hz. Each method's calibration comparison preserves its
own chosen observations and hypotheses. The joint fitted omission
false fix had 447.5 Hz conditional CFO RMS and 0.375 µs held frame RMS.
Median correct-tile sandbox wall times were 5.35 s for joint pass and
9.22 s for pass geometry under the locked three-worker replay.

## Panel and seal

This independent draw reuses the corrected synthetic native GLRT
generator with a new seed. Four new captures contain 12 independently
planted transmitters per receiver site. A fifth capture shuffles its
candidate lists within receiver and channel lanes. Every positive
has a matched pair of supplied single-tile trials, one 25 km square
containing the true receiver and one omitting it. The correct tile
centers are 8–10 km from the sites. The shuffle receives a single tile
and has no geographic truth. [Predeclared protocol](PROTOCOL.md)

Joint pass identification and the unchanged pass-geometry control
receive the same native probes, causal catalogue, cutoff, and tile
on each query. Their programs and shared dependencies were locked
before the new capture and tile seeds were drawn. Workers ran inside
Bubblewrap with package source and dependencies mounted read-only.
The only per-query data was the public NativeCapture envelope and
one offered tile on standard input. The score process opened the
labels after both methods completed and their joint predictions
were sealed. [Source lock](source-lock.json) · [Input lock](input-lock.json) ·
[Public offers](offers.json) · [Sealed predictions](predictions.jsonl.gz)

All comparisons here are supplied-tile results. The study begins
with synthetic GLRT peaks. It does not test IQ detection, an
independent TLE prediction error, or performance at physical
receiver sites. The tile-center distance is the no-estimation
geographic baseline. A publication in an omitted-region trial or
on the shuffle is a false fix. The centered CFO, shared absolute
CFO, and frame residual diagnostics are frequency and timing
evidence, separate from position-error measurements.

## Rebuild

Run the corrected generator from the archived setup with the
source releases listed in the source lock. Running generation
again draws new seeds. The finalized receipts retain the exact
evaluated seed and the offer seed for reproduction.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
fresh_root="$(mktemp -d /tmp/leo-fresh-supplied-tiles.XXXXXXXX)/panel"
taskset -c 17 .venv/bin/python -m tools.pipeline_eval.qualification.fresh_scenes prepare "$fresh_root" \
  --release joint_pass_id=a3e8960fcdae75662ce6be07eab44d37936a8f3e5120db44e31aa4c02ffa7e35 \
  --release pass_geometry=f5f52f43ef201f57e484992042c90c2f3270c2bb43a18b7108f2ce077d2f924f
taskset -c 17-19 .venv/bin/python -m tools.pipeline_eval.qualification.fresh_scenes predict "$fresh_root"
.venv/bin/python -m tools.pipeline_eval.qualification.fresh_scenes score "$fresh_root" --out "$fresh_root/report"
```
