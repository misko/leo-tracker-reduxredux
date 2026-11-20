# Geographic transfer with measured frequency disturbances

Lean support published all four correct-tile fixes within 5 km in both calibration arms. Exact orbit fit published two. Both receivers withheld all eight omitted tiles and the shuffled control in both arms. Exact orbit fit's four forced correct-tile solutions were all within 2.734 km. The extra fixes therefore show a publication advantage for lean support on this draw. [Scores](scores.json) · [Sealed predictions](predictions.jsonl.gz)

| Receiver | Calibration | Correct fixes within 5 km / attempts | Published median / P95 / max (km) | Near omitted false fixes / attempts | Far omitted false fixes / attempts | Shuffle false fixes / attempts |
|---|---|---:|---:|---:|---:|---:|
| Exact orbit fit | Zero | 2 / 4 | 1.718 / 2.096 / 2.138 | 0 / 4 | 0 / 4 | 0 / 1 |
| Exact orbit fit | Fitted | 2 / 4 | 1.469 / 1.941 / 1.993 | 0 / 4 | 0 / 4 | 0 / 1 |
| Lean support | Zero | 4 / 4 | 2.151 / 3.252 / 3.443 | 0 / 4 | 0 / 4 | 0 / 1 |
| Lean support | Fitted | 4 / 4 | 2.267 / 3.913 / 4.150 | 0 / 4 | 0 / 4 | 0 / 1 |

The four supplied correct tile centers missed truth by 8.329–9.753 km. Near and far omitted centers missed by 23.251–26.359 km and 58.884–97.357 km respectively. Both receivers produced forced coordinates on all twelve labeled queries in each arm. The two additional correct-tile fixes from lean support corresponded to weak held track support and weak position geometry in exact orbit fit. Among the two common published sites, lean support's fitted errors were 4.150 and 1.961 km, compared with 0.945 and 1.993 km for exact orbit fit. The shuffle produced zero qualifying anonymous tracks. All 26 workers completed under the 100 s deadline. Median worker CPU time across the full 13-query roster was 1.30 s for exact orbit fit and 1.44 s for lean support on this host. These timings start at the common prepared-track input boundary. [Per-case scores](scores.json) · [Worker records](predictions.jsonl.gz)

## What the archive supplies

The donor archive contained 15,134 candidate samples where an earlier lean fit and an authenticated v5 receipt agreed on the satellite. It provided 85 eligible donor tracks across six roof recordings. Their median span was 54.61 s. The median separation of consecutive retained samples was 0.355 s and their 95th-percentile separation was 2.126 s. The residual used here is measured CFO minus the previous fit's radio terms and exact orbital range rate, centered within each drawn interval. The residual includes any remaining clock, emitter, orbit, geometry and detector effects. The observation gaps come from joined track support and include both acquisition and association effects. [Donor receipt](donor-receipt.json) · [Earlier ownership audit](../../2026_11_19_receiver_convergence/track-fit/README.md)

On the donor tracks, pooled residual correlation was 0.69 at a 0.35 s lag, 0.50 at 4.25 s and 0.36 at 8.50 s. These are Pearson correlations of pairs within 0.06 s of each lag after median centering and RMS scaling on each donor track, over 3,006, 3,183 and 1,917 pairs respectively. On the fresh draw, 96 independently sampled 40 s windows had a median centered residual RMS of 98.4 Hz and a median next-sample correlation of 0.575. The replay retained 4,334 of 4,455 donor visits on the synthetic probe grid. Median retained lane span was 38.40 s and median maximum gap was 2.11 s. [Realized disturbance receipt](realized-disturbances.json)

The nearest of the four new simulated sites was 1,699 km from a site in the three earlier synthetic panels. Fixed orbital propagation, the original causal TLE and frame epoch still come from the simulator. The replay uses measured frequency residuals and selected-track support within a simple, single-peak-per-lane model. Its independently sampled lanes and selected donor tracks capture only part of the radio environment. No physical-site measurements were collected for this panel. [Frozen protocol](PROTOCOL.md) · [Committed trial labels](labels.json)

## Frequency fit and evidence boundary

Both receivers received identical anonymous, unwrapped GLRT CFO tracks, the same causal catalogue and one 25 km offer. The projection grouped observations from their time and frequency metadata and did not reference TLE, site, orbit assignments or fresh labels. It supplied 24–25 tracks and 1,014–1,109 points per labeled capture. These comparisons start from prepared CFO tracks and carry no raw I/Q inference claim. They contain no synthetic v5 comparator.

| Receiver | Correct-tile conditional CFO RMS, zero / fitted (Hz) | Near omitted, zero / fitted (Hz) | Far omitted, zero / fitted (Hz) |
|---|---:|---:|---:|
| Exact orbit fit | 109.48 / 107.09 | 226.29 / 213.08 | 499.23 / 465.78 |
| Lean support | 125.09 / 118.89 | 205.20 / 189.41 | 614.79 / 582.76 |

These are medians of the four fit RMS values per stratum, including forced outcomes and each method's own fitted associations. Compared with zero calibration, fitted calibration reduced lean support's median correct-tile CFO RMS while raising its median position error. [Per-arm RMS and positions](scores.json)

## Audit and replay

The source lock froze both released solvers, the protocol, the generator and donor evidence before any new seed was drawn. The input lock binds the public manifest, offers, TLE and private truth, donor choices and seeds. Each worker received only the serialized observation, tile and catalogue in a namespace without the fresh labels or network access. The prediction lock commits the complete 26 records and their paired input hashes before score access. [Source lock](source-lock.json) · [Input lock](input-lock.json) · [Prediction lock](prediction-lock.json) · [Figure input bindings](figure-lock.json)

Run the same prospective protocol with an untouched private folder and the original archived catalogue available.

```bash
panel_root="$(mktemp -d)/panel"
taskset -c 8 .venv/bin/python -m tools.pipeline_eval.qualification.site_transfer prepare "$panel_root" \
  --release robust_orbit_fit=934221dd9747bc984ad15b6a0a537a534584db24a6f73e0815aac1f37a199125 \
  --release robust_support=d86784a8415f115784cc2783cc7034641c31ec6cdbedb17f6327dd6d2aa74614
taskset -c 8,9 .venv/bin/python -m tools.pipeline_eval.qualification.site_transfer predict "$panel_root"
taskset -c 8 .venv/bin/python -m tools.pipeline_eval.qualification.site_transfer score "$panel_root" --out "$panel_root/report"
```

The three now-public seeds reproduce the same native capture hashes, offers, labels, realized disturbance summary and donor receipt byte-for-byte in a temporary directory.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.pipeline_eval.qualification import site_transfer as trial
from tools.pipeline_eval.qualification import site_transfer_samples as samples

seeds = [
    bytes.fromhex((trial.REPORT / f"seed-{purpose}.hex").read_text())
    for purpose in trial.SEEDS
]
with TemporaryDirectory() as directory:
    replay = Path(directory)
    with patch.object(samples.secrets, "token_bytes", side_effect=seeds):
        samples.generate(replay)
    for path, report_name in (
        ("public/manifest.json", "capture-manifest.json"),
        ("public/offers.json", "offers.json"),
        ("private/labels.json", "labels.json"),
        ("private/realized-disturbances.json", "realized-disturbances.json"),
        ("donor-receipt.json", "donor-receipt.json"),
    ):
        assert (replay / path).read_bytes() == (trial.REPORT / report_name).read_bytes()
```
