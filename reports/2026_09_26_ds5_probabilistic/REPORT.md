# DS5: probabilistic satellite timing evaluation

## Conclusion

Completed all **42 DS5 scans / 1,739 tracks**, with **zero failures**. SOL implemented and ran the batch evaluation; the parent independently audited input membership, evidence digests, aggregation and development-case parity.

The prototype does **not demonstrate a broad improvement in location discrimination**. Shared satellite timing helps discriminate several large Reno errors compared with independent per-track timing, but the historical age prior contributes almost nothing beyond that sharing on the 41 non-development scans. The optional scan clock also has little effect. Zero timing has larger average reference-versus-estimate score separation, despite considerably worse residual fits.

These are retrospective comparisons at fixed coordinates, **not new localization searches**. There are no new location-error statistics to claim. No candidates, geographic proposals or fitted corrections were shared between Sacramento and Reno; the reference location was diagnostic only.

## Dataset and frozen protocol

- Manifest: `/home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_26_ds5_since_local_midnight/manifest.json`.
- Manifest SHA256: `6c7cfbe0e91f6eb2d5f041295d453f44ab99910cd17ff63b0fb1f3096655fa35`.
- 42 admitted captures, 2026-09-26 07:00–13:50 UTC. All have **120 ms visit dwells**; DS5 does not contain 240/360 ms dwell settings. Its low/middle/high strata refer to total valid exposure, not different visit dwell settings.
- Sample rates: 2.5 MS/s (14 scans), 5 MS/s (10), 7.5 MS/s (9), 10 MS/s (9).
- Evaluate three fixed sites per scan: known reference, persisted Sacramento winner, persisted Reno winner.
- At each site independently, select satellite IDs by full-catalogue **training-only zero-timing RMS**, then freeze them across timing arms. Do not reuse production IDs selected by evaluation RMS.
- Reuse original training/evaluation masks. Published winning coordinates were themselves evaluation-selected; overlapping tracks also create dependence across masks. This is not a fresh independent/randomized radio holdout, and no confidence level for geographic correctness is claimed.
- Historical prior frozen from the preceding prototype. Its latest calibration snapshot is **2026-09-24 12:03:43.771974 UTC**, about 43 hours before DS5 starts. No DS5 RF observations train the prior.
- Main residual scale 100 Hz, normalized Student-t(4), no RMS cap. Additional 50/200 Hz checks for age-shared models. CFO is training-profiled per track rather than integrated. No frequency-drift fit.
- Satellite timing support +/-60 seconds at **0.1-second spacing**. Optional scan clock: normal prior, sigma 1 second, support +/-3 seconds. All these settings were fixed before DS5 results.
- Five main arms: zero timing, flat independent per-track timing, flat shared-satellite timing, age-conditioned shared-satellite timing, and age-conditioned shared-satellite plus scan clock. Nine model/noise combinations per scan, 378 total scan/model combinations, each at three sites.
- The developmental scan `scan-fw-d86e8f23c0624bac` is included in DS5; report both all 42 and the other 41. This exclusion removes the original worked example, but does not turn the remaining data into an untouched prospective validation set.

Runtime: approximately **817 seconds (13.6 minutes)** summed across scan analyses, single-threaded numerical libraries. No new RF collection or production changes.

## Main results: 41 scans excluding the development example

Score gap is **reference NLL minus prior-estimate NLL**, in nats per evaluation observation, averaged with equal weight per scan. Negative favors the known reference. A “reference win” is only a fixed-site score comparison, not a localization success.

| Timing model | Reference wins vs Sacramento | Mean gap vs Sacramento | Reference wins vs Reno | Mean gap vs Reno |
|---|---:|---:|---:|---:|
| Zero timing | 27/41 | -0.2742 | 29/41 | -0.4820 |
| Flat independent per-track | 27/41 | -0.0556 | 29/41 | -0.0954 |
| Flat shared-satellite | 25/41 | -0.0524 | 28/41 | -0.1231 |
| **Age shared-satellite** | **25/41** | **-0.0541** | **28/41** | **-0.1231** |
| Age shared-satellite + scan clock | 25/41 | -0.0543 | 28/41 | -0.1238 |

The age prior changes the mean gap relative to flat satellite sharing by **-0.001725** for Sacramento and **+0.00000216** for Reno: negligible for Reno, small for Sacramento. It changes neither comparison's win count. Scan-clock freedom changes no win count either.

Mean uncapped posterior-expected weighted RMS across these 41 scans:

| Model | Reference (Hz) | Sacramento (Hz) | Reno (Hz) |
|---|---:|---:|---:|
| Zero timing | 463.7 | 474.2 | 502.0 |
| Flat independent per-track | 278.6 | 277.2 | 281.5 |
| Age shared-satellite | 296.7 | 289.9 | 304.4 |

Thus nuisance flexibility reduces residual error substantially without necessarily improving location discrimination. The robust predictive score and uncapped RMS can still disagree; replacing the cap does not remove model ambiguity.

## Full 42-scan results

| Timing model | Reference wins vs Sacramento | Mean gap vs Sacramento | Reference wins vs Reno | Mean gap vs Reno |
|---|---:|---:|---:|---:|
| Zero timing | 28/42 | -0.2734 | 29/42 | -0.4663 |
| Flat independent per-track | 27/42 | -0.0517 | 30/42 | -0.0968 |
| Flat shared-satellite | 25/42 | -0.0491 | 29/42 | -0.1286 |
| Age shared-satellite | 25/42 | -0.0508 | 29/42 | -0.1288 |
| Age shared-satellite + scan clock | 25/42 | -0.0510 | 29/42 | -0.1295 |

Most persisted estimates are already close to the reference: Sacramento 39/42 and Reno 35/42 are within 25 km. Original median errors are 6.53 km and 9.41 km respectively. These are **unchanged baseline errors**, not results of the new scoring model.

## Large-error cases

For the six Reno estimates at least 100 km from the reference, zero timing favors the reference in **3/6**, while shared age timing favors it in **5/6**. Flat shared timing and free per-track timing also reach **5/6**, so this improvement in count cannot be attributed specifically to the age prior. Excluding the development scan gives **3/5 versus 4/5**.

| Scan start UTC | Original Reno error (km) | Zero-timing score gap | Age-shared score gap |
|---|---:|---:|---:|
| 07:50 | 428.0 | -1.5176 | -0.8352 |
| 08:10 | 675.8 | -0.9847 | -0.8032 |
| **08:50** | **123.5** | **+0.1569** | **+1.0363** |
| 10:10 | 214.8 | -2.1195 | -0.8306 |
| 10:30 | 688.0 | +1.3700 | -0.6250 |
| 12:50, development | 706.8 | +0.1767 | -0.3612 |

The **08:50 scan, `scan-fw-dc1153010e57ac76`, is the main counterexample**. The model strongly prefers both wrong estimates: Sacramento is 128.9 km wrong with gap +1.1370; Reno is 123.5 km wrong with gap +1.0363. The reference posterior-expected RMS is about 1,271 Hz versus 390 Hz at Sacramento. Timing boundary mass is negligible, so expanding the timing range is not an indicated fix. Candidate identity remains frozen in this test; investigate its associations/track construction/model mismatch before adding more nuisance freedom.

## Sample-rate stratification

Age-shared model, 100 Hz residual scale, all 42 scans:

| Rate (MS/s) | Scans | Reference wins vs Sacramento | Mean gap vs Sacramento | Reference wins vs Reno | Mean gap vs Reno |
|---|---:|---:|---:|---:|---:|
| 2.5 | 14 | 8 | -0.0727 | 12 | -0.1783 |
| 5.0 | 10 | 5 | -0.0598 | 7 | -0.1923 |
| 7.5 | 9 | 5 | -0.0331 | 5 | -0.1000 |
| 10.0 | 9 | 7 | -0.0244 | 5 | -0.0101 |

Small, observational strata; these differences do not establish a causal sample-rate effect. All captures use the same visit dwell setting.

## Noise sensitivity and numerical checks

Age-shared model, 41 non-development scans:

| Residual scale (Hz) | Reference wins vs Sacramento | Mean gap vs Sacramento | Reference wins vs Reno | Mean gap vs Reno |
|---|---:|---:|---:|---:|
| 50 | 28/41 | -0.1371 | 30/41 | -0.2482 |
| 100 | 25/41 | -0.0541 | 28/41 | -0.1231 |
| 200 | 24/41 | -0.0125 | 28/41 | -0.0453 |

No main age-shared fit has more than 1% posterior point mass at the +/-60-second satellite endpoints at the 100 Hz setting. Some flat-prior/free-per-track arms do; details are retained in the audit. Small endpoint mass is not proof against disconnected modes beyond support.

The original developmental scan reproduces the earlier +/-60-second prototype **exactly** for all nine matching experiments at reference and Reno: maximum predictive-NLL difference **0.0**.

Combined verification: **20 tests passed** across DS5 runner/aggregation, probabilistic timing, and the existing nuisance/clock diagnostics. Every admitted session is accounted for; no scan was silently skipped.

## Limitations and recommendation

- Historical priors measure old/new TLE consistency, not absolute orbital truth. Their earlier nominal 90% intervals had only 85.3% validation coverage.
- The historical sample lacks enough <12-hour TLE examples. DS5 uses the conservative pooled fallback, not an asserted calibrated tight-young prior. The earlier uncalibrated 0.25-second young-prior sensitivity was not rerun across DS5.
- Frozen zero-timing identities do not test probabilistic reassociation. The prior concerns orbit-space equivalent timing, not a fully calibrated receiver-specific Doppler correction.
- CFO uncertainty and observation correlation are not fully integrated. Score differences are not calibrated location probabilities.
- Existing location winners and masks make this retrospective. No model settings were tuned on DS5, but that does not remove prior selection effects.
- Full-dataset summaries aggregate independent per-scan analyses. This is not a joint multi-scan or eight-scan localization evaluation.

**Recommendation:** keep shared satellite timing as a candidate model, but do not promote the age-prior addition as an established accuracy improvement. First audit the 08:50 counterexample, then evaluate independently selected identity alternatives and better-calibrated residual/correlation models. A subsequent fresh, independent-prior geographic search is required to measure any location-error improvement.

## Artifacts

- `run_ds5.py`: SOL batch runner and metadata guards.
- `results.json`: all 42 scans, all three sites, frozen identities, timing summaries and scores.
- `input_audit.json`: independent persisted-input inventory and original location errors.
- `aggregate_audit.py`, `aggregate_audit.json`: independent equal-scan and observation-weighted summaries, development exclusion, rate/error strata and accounting.
- `test_run_ds5.py`, `test_aggregate_audit.py`: DS5 selection/isolation/inventory and aggregation tests; numerical prototype tests live in the preceding report directory.

Result SHA256: `fb1c7f69ce2469c3727c35bcc652abf382a02996d079730d3096fe9f1bb78635`.

Reproduction uses the installed API Python environment, with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`:

```sh
python reports/2026_09_26_ds5_probabilistic/run_ds5.py
python reports/2026_09_26_ds5_probabilistic/aggregate_audit.py reports/2026_09_26_ds5_probabilistic/results.json
```

The runner reads existing data and writes only local generated report artifacts; the output directory must be writable by its execution user.
