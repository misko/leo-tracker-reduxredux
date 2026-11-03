# Receiver height materially affects horizontal localization

**The fixed zero-height assumption is a material part of the geographic error budget.** Raising modeled WGS84 ellipsoidal receiver height by 100 m moves the locally refitted horizontal position by 73–300 m; a 300 m change moves it by 201–852 m on the three balanced-N8 panels. These sensitivity offsets are not measurements of the antenna height, and none should be selected from agreement with the roof reference.

The existing `site()` function in `tools/ds7_baseline_adapter.py` returns the WGS84 ellipsoid surface position. The geographic baseline uses it without a receiver-height term. This report introduces a research-only fixed-height model; production code and the baseline are unchanged.

## Results

| Dataset | Tested ellipsoidal height | Horizontal shift from zero-height fit | Horizontal reference distance | Training log-score change | Held log-score change |
|---|---:|---:|---:|---:|---:|
| DS7 | 0 m, baseline | 0 m | 1,688 m | 0 | 0 |
| DS7 | 100 m | 237 m | 1,922 m | −128.55 | −66.40 |
| DS7 | 300 m | 774 m | 2,453 m | −414.39 | −223.63 |
| DS8 | 0 m, baseline | 0 m | 722 m | 0 | 0 |
| DS8 | 100 m | 73 m | 794 m | +14.24 | +9.57 |
| DS8 | 300 m | 201 m | 920 m | +1.53 | +6.30 |
| DS9 | 0 m, baseline | 0 m | 2,042 m | 0 | 0 |
| DS9 | 100 m | 300 m | 2,204 m | +11.92 | +23.80 |
| DS9 | 300 m | 852 m | 2,450 m | −17.19 | +26.49 |

Positive score change favors the elevated model on the same observations. All six elevated fits increase horizontal reference distance; DS8 and DS9 nevertheless improve held prediction. This again demonstrates that better waveform/track likelihood does not automatically mean a better horizontal reference distance. It does not justify setting an incorrect physical height because zero happens to agree better with the reference.

The largest movement per 100 m height change is about 300 m on DS9. These are finite local sensitivities, not calibrated bounds or a linear rule valid at all heights. The response varies between datasets and is somewhat nonlinear. The offsets do not establish the actual height bias, nor prove that height explains the observed disagreement between scan sets.

## Frozen method

The [protocol](PROTOCOL.md) preceded execution. Reuse the same balanced_0 eight-scan sets, original observations, timing grids and candidate banks as the prior source-consistency experiments. Use the original all-track likelihood with background probability 0.2.

Modify receiver ECEF position only: `receiver = ellipsoid_surface + height_km * geodetic_up`. Retain the geodetic up direction, satellite positions/velocities, visibility rule, canonical RF convention and all likelihood terms. The height is fixed, not fitted from radio measurements. At each height independently warm-start one local E/N/per-scan-time optimization from the saved zero-height optimum. No reference coordinate enters optimization.

Zero-height training scores reproduce the selected baseline within 1e-7. At the original endpoint, the 100 m and 300 m models retain identical candidate visibility support. All six refits qualify under the inherited convergence, boundary and finite-difference gradient checks. Maximum projected gradient is 0.00284 and maximum gradient-audit discrepancy is 7.2e-6. Each dataset completes both refits in approximately 10–12 seconds.

These are local refits from the previous selected solution, not a fresh multistart search or a proof of global optimality. Candidate visibility is checked at the starting endpoint; no global support-invariance claim is made. The experiment covers these three N8 panels, not the pooled N24 fits or every dataset scan.

## What to do with this evidence

Obtain the receiver antenna's independently supported elevation and datum, then repeat the geographic comparison with that fixed physical input. WGS84 ellipsoidal height is the model input. Elevation above sea level, terrain elevation and antenna mounting height need their definitions recorded before being substituted. An elevation/reference-source question is pending; no supplied physical height is assumed here.

Before interpreting pooled subkm agreement, extend this sensitivity check to the N24 baseline. Do not freely fit height to horizontal ground truth or claim a correction from these arbitrary offsets. Height may couple with timing, candidate association and horizontal position, so a reference-distance improvement alone is insufficient to identify it.

The horizontal reference is the existing operator coordinate; its independent uncertainty remains unspecified. Reported distances use the same spherical horizontal convention as prior panels, not 3D antenna error. Search-center and candidate-bank conditioning remain. Reliable absolute subkm accuracy is not established.

## Validation and evidence

The component-owned synthetic test verifies exact zero-height prediction replay and agreement with an independently constructed 300 m ECEF displacement. Input artifacts are SHA-256 verified. [DS7.json](DS7.json), [DS8.json](DS8.json) and [DS9.json](DS9.json) retain full optimizer outputs, scores, coordinates, shifts, timing parameters and source hashes.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_height_sensitivity -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 180 uv run --no-project --with numpy --with scipy python reports/2026_09_29_height_sensitivity/run.py DS7
```

Repeat the second command for DS8/DS9 in a fresh output context; writers use exclusive creation. `evidence.sha256` seals the local report, protocol, implementation, test and results. No new RF, archive export, production edit or remote publication occurred.
