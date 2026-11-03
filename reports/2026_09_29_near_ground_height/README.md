# N24 height sensitivity near the public terrain estimate

**Fixed 20 m and 40 m ellipsoidal-height scenarios move N24 horizontal estimates by 19–84 m.** Their horizontal reference distances remain 147–413 m. Height matters to the fine error budget, but these scenarios do not provide a kilometre-scale correction or establish the actual antenna elevation.

| Dataset | Fixed model height | Horizontal movement from zero-height fit | Horizontal reference distance | Training log-score change | Held log-score change |
|---|---:|---:|---:|---:|---:|
| DS7 | 0 m, baseline | 0 m | 388 m | 0 | 0 |
| DS7 | 20 m | 38 m | 383 m | −50.07 | −29.36 |
| DS7 | 40 m | 75 m | 382 m | −102.42 | −60.21 |
| DS8 | 0 m, baseline | 0 m | 390 m | 0 | 0 |
| DS8 | 20 m | 19 m | 401 m | −13.98 | −9.74 |
| DS8 | 40 m | 38 m | 413 m | −29.46 | −20.40 |
| DS9 | 0 m, baseline | 0 m | 107 m | 0 | 0 |
| DS9 | 20 m | 41 m | 147 m | +0.29 | −0.06 |
| DS9 | 40 m | 84 m | 190 m | −0.78 | −0.93 |

The radio likelihood does not consistently favor these corrections, and all held scores decline. DS7's reference distance improves slightly while its held score worsens substantially. Neither metric should select physical height. No scenario is promoted into the baseline.

## Why these heights were tested

The [public elevation lookup](../2026_09_29_public_elevation/README.md) inferred approximately 22.1 m NAD83-related ellipsoidal bare-ground height at the nominal site from independent terrain/geoid services. Mounting height and the precise WGS84 frame conversion remain unknown. The [protocol](PROTOCOL.md) fixed 20 m and 40 m as illustrative WGS84 model-height scenarios before these fits, not as measurements or an asserted confidence interval. They bracket a useful scale for testing, not a verified bound on antenna elevation.

This follows the much larger [100 m and 300 m N24 stress tests](../2026_09_29_height_n24/README.md). It avoids treating those large stress offsets as the best available physical estimate. No new elevation lookup or inferred mounting height was used in this run.

## Method and checks

Reuse the N24 observation membership, masks, candidate banks, likelihood, zero-height selected endpoints and [tested fixed-height model](../2026_09_29_height_sensitivity/height_model.py). At each fixed height independently warm-start one local horizontal-position/per-scan-timing refit from the baseline. Source hashes include the terrain summary motivating the experiment; actual WGS84 antenna height remains explicitly unknown there.

All six refits qualify. Maximum projected gradient is 0.00747 and maximum finite-difference gradient discrepancy is 1.48e-5, within the unchanged qualification rules. Original scores replay within 1e-7, exact session order verifies, and candidate visibility remains unchanged at initial and final endpoints. All original observations remain. Dataset runs complete in 33–37 seconds with no retries or numerical failures.

The runner is a mechanical copy of the N24 height-sensitivity runner with only scenario heights and terrain-provenance binding changed. It uses the same component-owned height tests previously passed; no new geometry implementation was introduced. This is local sensitivity, not a fresh multistart global search.

## Decision for subkm work

Include receiver height as a documented physical input when the mounting elevation/datum is available. The modeled displacement here is tens of metres and does not account for the previously observed kilometre-scale short-window disagreement. That conclusion is scoped to these N24 scenarios; it is not an upper bound for all panels or all possible heights.

The pooled subkm reference agreement survives these illustrative heights. Absolute accuracy remains unverified because antenna elevation, reference uncertainty, site-conditioned candidate banks and previously exposed data remain unresolved. The [position-injection test](../2026_09_29_position_injection/README.md) supports local model response but does not independently validate those physical assumptions.

Keep the original baseline and the height scenarios as separate evidence. Do not continue selecting height from reference distance or likelihood. Further progress on the dominant short-window discrepancy should focus on discriminating association/model error while awaiting the physical elevation information.

## Evidence and reproduction

[DS7.json](DS7.json), [DS8.json](DS8.json), and [DS9.json](DS9.json) preserve optimizer outputs, coordinates, timing parameters, scores, visibility checks and source hashes. `evidence.sha256` seals the local protocol, runner, report and outputs.

```sh
OPENBLAS_NUM_THREADS=1 timeout 180 uv run --no-project --with numpy --with scipy python reports/2026_09_29_near_ground_height/run.py DS7
```

Repeat for DS8/DS9 in a fresh output context; writers use exclusive creation. No RF collection, archive export, production change or remote publication occurred.
