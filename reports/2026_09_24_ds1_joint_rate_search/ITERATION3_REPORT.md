# DS1 iteration 3: joint global-tau and causal-rate geographic screening

## Result

Iteration 3 completed all four prefix-6 TRAIN tasks in 793.0 seconds using two
workers: the two independent causal cache groups, each with the sealed Reno
and Sacramento global-time seeds.  Every task screened 144 geographic/tau
points using all qualified observations and a fresh hard association.  The
four deterministic rate-selected finalists passed exact SGP4 replay, with
maximum Doppler discrepancies from 0.0000549 to 0.0000582 Hz.

The post-seal comparison improves the iteration-2 global-time error in three
of four overlapping development views.  The fourth (`20260921_16`, Sacramento)
worsens by 1.260 km.  These are paired development views of the same corpus,
so the result is evidence for continued testing rather than an independent
accuracy claim.

## Inference contract

The inference driver accepts only four sealed, TRAIN-only one-hour global-time
artifacts.  They supply the prefix-6 session memberships, prior, RF-selected
centre, and global tau.  No reference coordinate, error value, truth label, or
observation mask is present in the driver or its result.

Each seed searches a fixed local hierarchy with a 6.25 km initial half-width,
then 3.125, 1.5625, and 0.78125 km steps, beam width two, and a symmetric
three-point tau stencil around the sealed source tau (`tau ± 0.25 s`).  At
every point it:

1. re-associates every full-observation track against the causal catalogue;
2. forms a Doppler phase derivative from cache predictions at `tau - 1` and
   `tau + 1` seconds;
3. jointly profiles a per-track CFO and one bounded per-NORAD causal rate;
4. ranks with capped full-observation loss plus the predeclared Normal-rate
   prior penalty; and
5. sends the deterministic winner to the existing exact SGP4 rate fit and
   replay gate.

The cache derivative advances Earth rotation as well as orbit phase, so it is
only a geographic-screening surrogate.  Exact SGP4 continues to hold Earth
rotation at receive time plus tau and is the qualification gate.

## TRAIN inference and exact audit

| Group / seed | Screen points | Screen time | Selected tau | Surrogate score | Exact capped loss | Surrogate-to-exact capped-loss difference | Exact gate max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `20260921_00` / Reno | 144 | 357.8 s | -1.25 s | 0.059962 | 0.039699 | 0.004344 | 0.0000556 Hz |
| `20260921_00` / Sacramento | 144 | 355.8 s | -1.25 s | 0.060021 | 0.039190 | 0.004639 | 0.0000549 Hz |
| `20260921_16` / Reno | 144 | 409.5 s | -0.75 s | 0.100707 | 0.077410 | 0.002249 | 0.0000582 Hz |
| `20260921_16` / Sacramento | 144 | 419.9 s | -1.25 s | 0.103875 | 0.078373 | 0.002423 | 0.0000549 Hz |

The cached rate score and exact loss have different objectives, so their
numeric difference is an approximation diagnostic rather than a selection
criterion.  All final rate fits passed the 0.2 Hz exact replay threshold.

## Post-seal comparison

Only after the inference artifact was complete and validated as
reference-free, `evaluate_iteration3_postseal.py` introduced the external
Sausalito coordinate and read the sealed iteration-2 global-time evaluation.

| Group / seed | Iteration-2 global-time error | Iteration-3 joint-rate error | Delta |
|---|---:|---:|---:|
| `20260921_00` / Reno | 6.048 km | 4.260 km | -1.788 km |
| `20260921_00` / Sacramento | 6.055 km | 4.204 km | -1.852 km |
| `20260921_16` / Reno | 1.775 km | 0.635 km | -1.140 km |
| `20260921_16` / Sacramento | 1.689 km | 2.949 km | +1.260 km |

The mean paired error changed from 3.892 km to 3.012 km (-0.880 km), but the
four results are not independent validation observations.  The Reno and
Sacramento seeds from each group overlap, and the source corpus was used for
all geographic/rate selection.

## Artifacts and reproduction

- `iteration3-results.json` is the complete reference-free machine-readable
  inference result, including screen traces, causal-cache bindings, full
  finalist associations, rate fits, and exact gates.
- `iteration3-postseal/iteration3-postseal.json` and CSV contain the external
  evaluation only.
- `iteration3-postseal/iteration3-postseal.png` is the paired error plot.

```bash
.venv/bin/python -m pytest -q \
  reports/2026_09_24_ds1_joint_rate_search/test_joint_rate_search.py \
  reports/2026_09_24_ds1_joint_rate_search/test_iteration3_prefix6.py \
  reports/2026_09_24_ds1_joint_rate_search/test_evaluate_iteration3_postseal.py

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_24_ds1_joint_rate_search/iteration3_prefix6.py \
  --workers 2 \
  --output reports/2026_09_24_ds1_joint_rate_search/iteration3-results.json

.venv/bin/python reports/2026_09_24_ds1_joint_rate_search/evaluate_iteration3_postseal.py \
  --results reports/2026_09_24_ds1_joint_rate_search/iteration3-results.json \
  --output-dir reports/2026_09_24_ds1_joint_rate_search/iteration3-postseal
```
