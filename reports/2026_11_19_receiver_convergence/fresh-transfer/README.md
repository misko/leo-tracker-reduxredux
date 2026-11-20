# Fresh supplied-tile comparison

The challenger improved correct-tile accuracy on the exact synthetic draw. Under the declared orbit and receiver perturbations, it withheld three of four correct tiles and accepted one omitted tile in both calibration arms. The frozen joint-pass baseline published all four correct tiles and withheld all four omitted tiles in that cohort.

Two prospective synthetic cohorts compare `joint_pass_id` and `region_challenge` from native time, frequency and frame-epoch hypotheses plus a causal TLE catalogue. Each cohort contains four independently drawn receiver locations and one time-shuffled control. Each location contributes one containing tile and one omitted tile. Both methods receive the same serialized native candidate packet, catalogue and offer for each query. The supplied tiles are 25 km squares. Their centers are deliberately offset from truth by 8–10 km with an independent bearing for the containing tiles, and by 45–115 km for the omitted tiles.

The exact cohort uses the corrected 300 s GLRT candidate generator unchanged. The perturbed cohort independently shifts simulated emitters along their orbits and introduces a correlated oscillator term, independent fractional-epoch readout noise and randomly missing visits. It retains the same native ambiguity and timing format and exposes the original causal TLE. The native candidates follow a simplified schedule with sparse, low-margin clutter. Results apply to supplied-tile performance for these two simulated models. [Frozen protocol](PROTOCOL.md)

## Position and publication

| Cohort | Receiver | Calibration | Correct fixes / attempts | Within 5 km / attempts | Published median / P95 / max (km) | Omitted false fixes / attempts | Shuffle false fixes / attempts |
|---|---|---|---:|---:|---:|---:|---:|
| Exact | Joint pass | Zero | 4 / 4 | 4 / 4 | 1.143 / 2.459 / 2.642 | 0 / 4 | 0 / 1 |
| Exact | Joint pass | Fitted | 4 / 4 | 4 / 4 | 0.448 / 2.301 / 2.622 | 0 / 4 | 0 / 1 |
| Exact | Regional challenge | Zero | 4 / 4 | 4 / 4 | 0.073 / 0.131 / 0.140 | 0 / 4 | 0 / 1 |
| Exact | Regional challenge | Fitted | 4 / 4 | 4 / 4 | 0.046 / 0.075 / 0.077 | 0 / 4 | 0 / 1 |
| Perturbed | Joint pass | Zero | 4 / 4 | 4 / 4 | 0.602 / 1.522 / 1.678 | 0 / 4 | 0 / 1 |
| Perturbed | Joint pass | Fitted | 4 / 4 | 4 / 4 | 1.138 / 1.500 / 1.513 | 0 / 4 | 0 / 1 |
| Perturbed | Regional challenge | Zero | 1 / 4 | 1 / 4 | 1.205 / 1.205 / 1.205 | 1 / 4 | 0 / 1 |
| Perturbed | Regional challenge | Fitted | 1 / 4 | 1 / 4 | 1.204 / 1.204 / 1.204 | 1 / 4 | 0 / 1 |

The offered correct centers were 8.018–9.886 km from truth across the two cohorts. Forced estimates were available for all labeled attempts. In the perturbed cohort, the challenger's median forced error on correct tiles was 4.769 km in both arms. Each of its three correct-tile withholds had a higher-scoring outside hypothesis in both arms. The omitted-tile false publications came from the same query, whose center was 79.844 km from truth. The two fixes were 75.531 km and 75.495 km from truth. The simulated receiver fell outside the entire nine-tile neighborhood tested for that offer. Every shuffled control was withheld by both methods and both arms. [Per-case scores](scores.json) · [Held-out regional comparisons](predictions.jsonl.gz)

## Conditional RF fit

The medians below include all four correct-tile attempts per method and cohort, including forced estimates that were withheld. Each method uses its own selected held-out support. All 36 workers completed within the 100 s deadline. Median execution was 5.0 s for joint pass and 14.5 s for the regional challenger across the 18 attempts per method under this run's host load.

| Cohort | Receiver | Conditional carrier RMS, zero / fitted (Hz) | Held frame RMS, zero / fitted (µs) |
|---|---|---:|---:|
| Exact | Joint pass | 33.86 / 28.81 | 0.0200 / 0.0161 |
| Exact | Regional challenge | 25.41 / 25.33 | 0.0126 / 0.0126 |
| Perturbed | Joint pass | 125.07 / 122.80 | 0.0592 / 0.0570 |
| Perturbed | Regional challenge | 255.33 / 255.61 | 0.0803 / 0.0803 |

On the perturbed draw, the 48 emitters had a median absolute phase displacement of 0.496 s and a maximum of 2.144 s. Across 96 receiver/pass lanes, median oscillator RMS was 70.45 Hz and median epoch jitter RMS was 0.443 sample. The independent gaps removed 1,476 of 21,350 planted candidate visits across 48 lanes. [Realized perturbations](perturbations-perturbed.json)

## Verification

- [Source lock](source-lock.json) binds both release versions, the executable protocol and generator dependencies before either draw. [Input lock](input-lock.json) binds both cohort locks. Exact and perturbed capture IDs and native hashes are disjoint from one another and the preceding corrected and fresh synthetic evidence.
- The workers receive only the public `NativeCapture` and supplied tile under an isolated filesystem and network namespace. The two methods' prediction rows contain matching `worker_input_sha256` values for all offers. The [prediction lock](prediction-lock.json) commits the exact compressed prediction bytes and complete roster. Scoring validates that lock before opening labels or exposing seeds. Published location error requires both a published fix and a labeled location.
- [Exact offers](offers-exact.json), [perturbed offers](offers-perturbed.json), [exact labels](labels-exact.json), [perturbed labels](labels-perturbed.json), and [realized perturbations](perturbations-perturbed.json) provide the post-seal audit. [Raw predictions](predictions.jsonl.gz) retain the published and forced outcomes independently. [Scores](scores.json) contain all per-arm decisions, geodesic errors and conditional RF metrics.

Run the same prospective protocol with new secrets from the repository root.

```bash
panel_root="$(mktemp -d)/panel"
taskset -c 8 .venv/bin/python -m tools.pipeline_eval.qualification.challenge_scenes prepare "$panel_root" \
  --release joint_pass_id=a3e8960fcdae75662ce6be07eab44d37936a8f3e5120db44e31aa4c02ffa7e35 \
  --release region_challenge=8ba08cce4a267c76f7bbf94b871b8090fd53356ae2ec481fb8d7fcf4aa64228d
taskset -c 8,9 .venv/bin/python -m tools.pipeline_eval.qualification.challenge_scenes predict "$panel_root"
taskset -c 8 .venv/bin/python -m tools.pipeline_eval.qualification.challenge_scenes score "$panel_root" --out "$panel_root/report"
```

The full native packets stay in the local scratch run. The seed recipe regenerated both published native manifests, offer files and cohort locks byte-for-byte after scoring.

Regenerate with the published seeds and original archived TLE to verify this draw's public bytes.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.pipeline_eval.qualification import challenge_scenes_generator as generator

report = Path("reports/2026_11_19_receiver_convergence/fresh-transfer")
with TemporaryDirectory() as folder:
    for cohort in generator.COHORTS:
        purposes = ("capture", "offer")
        if cohort == "perturbed":
            purposes = ("capture", "perturbation", "offer")
        seeds = [
            bytes.fromhex((report / f"seed-{cohort}-{purpose}.hex").read_text())
            for purpose in purposes
        ]
        target = Path(folder) / cohort
        with patch.object(generator.secrets, "token_bytes", side_effect=seeds):
            generator.generate(target, cohort)
        for actual, released in (
            ("public/manifest.json", f"capture-manifest-{cohort}.json"),
            ("public/offers.json", f"offers-{cohort}.json"),
            ("cohort-lock.json", f"cohort-lock-{cohort}.json"),
        ):
            assert (target / actual).read_bytes() == (report / released).read_bytes()
```
