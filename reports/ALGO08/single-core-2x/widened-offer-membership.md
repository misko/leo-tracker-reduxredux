# Testing original-offer membership after a wider positional search

**The wider-fit membership rule withheld both omitted offers and rejected the valid northern offer.** The unchanged covariance solver kept both containing offers and gave false fixes for both omissions. The new rule kept one of the two containing offers. Its valid-fix failure occurred with the same satellite owners as the unchanged solver. [Scored per-arm receipt](measurements/widened-offer-membership.json)

The frozen covariance solver `375895c3afda…` ran once at 50 km width on each of four saved public offers. Every solve kept its original 25 km offer center, sky-screen center, detector file and causal archive. The proposed policy publishes the expanded estimates only when both calibration arms fall within the original square. The archived covariance solves at 25 km supply the controls. [Prespecified protocol](widened-offer-protocol.md) · [Exact input and offer pins](measurements/widened-offer-plan.json)

The widened prior covers four times the area. The stock corner nominations and box constraints act over the wider range. Width-dependent gates, including the frozen exterior guard's face trigger and distance criterion, now refer to the expanded solve. The final paired membership check uses the original square. A fixed screening center preserves the preparation reference but still allows candidate associations and aliases to change in the expanded search. A diagnostic grid produced by the solver describes the expanded domain. The research runner records this policy's output and does not change the publication contract. [Original search frame](../../../src/leo/analysis/localization_v3/region.py) · [Frozen exterior guard](../../../tools/pipeline_eval/variants/experimental/regional_bound_guard.py)

## Results

Every expanded solve returned both estimates, and the public reference lay within its expanded square. The frozen far-exterior guard's boundary trigger fired on none of the widened fits. The paired membership check produced all three proposed withholds. Positive clearance means inside the **original** square. Horizontal error and RF RMS below describe the returned estimates even when the proposed policy withholds them. All paired numbers are fixed-zero / fitted `c`. [Full endpoints and coverage](measurements/widened-offer-membership.json)

| Original offer | Reference clearance | Expanded estimate clearance | Original decision → wider-fit rule |
|---|---:|---:|---|
| India, containing | +3.576 km | +4.319 / +4.047 km | Valid fix → valid fix |
| India, omitted | −1.500 km | −0.758 / −1.029 km | False fix → correct withhold |
| North, inside | +0.100 km | −0.641 / −0.583 km | Valid fix → false withhold |
| North, omitted | −0.100 km | −0.841 / −0.783 km | False fix → correct withhold |

| Original offer | Horizontal error, original → expanded | RF RMS, original → expanded |
|---|---:|---:|
| India, containing | 1.017 / 0.751 → 1.017 / 0.751 km | 15.53635 / 15.30584 → 15.53635 / 15.30584 Hz |
| India, omitted | 1.580 / 1.534 → 1.017 / 0.751 km | 15.63058 / 15.45128 → 15.53634 / 15.30584 Hz |
| North, inside | 0.106 / 0.141 → 0.745 / 0.711 km | 5.40643 / 5.16663 → 5.37969 / 5.17265 Hz |
| North, omitted | 0.123 / 0.118 → 0.745 / 0.711 km | 5.41806 / 5.16725 → 5.37969 / 5.17265 Hz |

Both arms of each widened fit retained the exact original owner maps, with 517 points per arm on India and 302 on north. The India containing endpoints and RMS matched exactly. In the India omission the widened estimates fell north of the original face, toward the reference, and the rule withheld. On the northern pair both widened solutions sat west of both original faces. Their two fixed-zero estimates were about 11 cm apart across the 200 m offer shift, and their fitted estimates about 9 mm apart. The original positions had been on the offered west faces. Widening removed both constraints and the membership rule rejected both offers, including the valid one. In the valid northern offer, fixed-zero RF RMS fell while horizontal error rose from 106 m to 745 m. [Original India results](covariance-geographic-transfer.md) · [Original northern results](measurements/covariance-north-bound-replays.json)

## Reproduction

Use the four saved public inputs pinned in the plan and a fresh output directory. The worker receives a single expanded region and the pinned frozen specification per solve. Scoring opens the public references after all predictions are available. Seven component cases passed, including the exact original corner, one arm just outside and an unavailable estimate. [Component tests](../../../tests/pipeline_eval/test_widened_offer_trial.py)

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
plan=reports/ALGO08/single-core-2x/measurements/widened-offer-plan.json
out="$bench/widened-offer-375895-repeat"
export PYTHONPATH="$PWD:$PWD/src:$release"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$release/venv/bin/python" -B -m reports.ALGO08.single-core-2x.widened_offer_trial \
  run "$plan" "$bench/integration-covariance-posterior" "$out"
"$release/venv/bin/python" -B -m reports.ALGO08.single-core-2x.widened_offer_trial \
  score "$plan" "$out" "$out/scored.json"
```
