# Height sensitivity persists in the pooled N24 location estimates

**Pooling 24 scans does not remove receiver-height sensitivity.** A hypothetical +100 m WGS84 ellipsoidal height moves the locally refitted horizontal estimates by 94–225 m; +300 m moves them by 287–769 m. All six elevated estimates remain within 1 km of the operator reference, but the reference agreement is conditional on height and is not independently certified absolute accuracy.

| Dataset | Fixed height | Horizontal movement from zero-height fit | Horizontal reference distance | Training log-score change | Held log-score change |
|---|---:|---:|---:|---:|---:|
| DS7 | 0 m, baseline | 0 m | 388 m | 0 | 0 |
| DS7 | 100 m | 190 m | 401 m | −272.69 | −161.49 |
| DS7 | 300 m | 617 m | 652 m | −963.80 | −579.76 |
| DS8 | 0 m, baseline | 0 m | 390 m | 0 | 0 |
| DS8 | 100 m | 94 m | 451 m | −84.92 | −57.94 |
| DS8 | 300 m | 287 m | 584 m | −364.45 | −241.14 |
| DS9 | 0 m, baseline | 0 m | 107 m | 0 | 0 |
| DS9 | 100 m | 225 m | 330 m | −11.92 | −8.51 |
| DS9 | 300 m | 769 m | 875 m | −130.76 | −90.13 |

Unlike the mixed N8 likelihood response, all elevated N24 fits have worse training and held log scores. This does not identify the true height or prove zero is optimal: negative heights and other heights were not searched, only two positive offsets were tested, and other model errors may be absorbed into position/timing. The strongest apparent horizontal agreement, DS9's original 107 m, changes to 330 m at +100 m height and 875 m at +300 m height.

## Comparison with N8

| Dataset | N8 movement at +100 m | N24 movement at +100 m | N8 movement at +300 m | N24 movement at +300 m |
|---|---:|---:|---:|---:|
| DS7 | 237 m | 190 m | 774 m | 617 m |
| DS8 | 73 m | 94 m | 201 m | 287 m |
| DS9 | 300 m | 225 m | 852 m | 769 m |

More scans reduce sensitivity on DS7/DS9 but increase it on DS8. Height is a shared geometric assumption rather than independent measurement noise expected to average away. These are finite sensitivity changes on particular panels, not a calibrated error bound or a universal derivative.

## Frozen experiment and checks

The [protocol](PROTOCOL.md) preceded execution. Reuse the saved N24 observation sets, candidate banks, masks, RF convention and background-mixture likelihood. Use the tested [fixed-height implementation](../2026_09_29_height_sensitivity/height_model.py), which adds `height_km * geodetic_up` to the WGS84 ellipsoid surface ECEF position. Each fixed-height fit independently starts at the saved zero-height optimum and optimizes only horizontal position and the 24 per-scan timing parameters.

Exact session order and input hashes verify. Zero-height scores reproduce the original selected fits within 1e-7. All six elevated refits qualify; maximum projected gradient is 0.00483 and maximum finite-difference audit discrepancy is 9.45e-6. Candidate visibility is unchanged both at the original endpoint and at every final endpoint, relative to the baseline. All original observations remain. Per-dataset runs complete in 41–48 seconds with no retries or failures.

The inherited component test passes again: exact zero-height prediction replay and agreement with an independently constructed 300 m ECEF displacement. The new runner performs the session, hash, score and visibility checks during execution. These are local refits, not a new multistart search or globally certified height profile.

## Consequence for the subkm goal

The working N24 baseline remains encouraging, but its uncertainty budget must include the height assumption. Obtain an independently supported antenna elevation and vertical datum before treating the 107–390 m reference agreement as established positioning accuracy. Do not select height to improve reference distance or likelihood on this already exposed corpus.

The repository already defines `ObserverSiteV1.altitude_m` as WGS84 ellipsoidal height in [ADR 0007](../../docs/adr/0007-sky-prediction-geometry.md). That contract convention does not provide the actual installed antenna value, and the research Stationary baseline does not consume it. No physical elevation has been supplied in response to the pending question; none is inferred from these offsets.

Horizontal reference uncertainty, site-conditioned candidate banks and the 809 m distance from configured center to reference remain separate limitations. The test does not show that height causes all scan-set disagreement or that correcting it improves accuracy. No new RF, archive export, production changes or remote publication occurred.

## Evidence and reproduction

[DS7.json](DS7.json), [DS8.json](DS8.json), and [DS9.json](DS9.json) preserve full optimizer outputs, coordinates, timing parameters, visibility counts, scores and dependency hashes. `evidence.sha256` seals the report, protocol, runner and outputs.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_height_sensitivity -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 180 uv run --no-project --with numpy --with scipy python reports/2026_09_29_height_n24/run.py DS7
```

Repeat the second command for DS8/DS9 in a fresh output context; writers use exclusive creation. Reliable absolute subkm accuracy remains unverified.
