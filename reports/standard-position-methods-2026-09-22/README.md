# Additional automatic position diagnostics

Saved-data qualification on `scan-fw-e3bc0741ecf02704`, 2026-09-22.
Three additional PNGs and a machine-readable JSON sidecar are implemented for
standard tracking analysis. The existing positioning diagnostic is preserved.

| Method | Latitude | Longitude | Horizontal error against supplied reference |
| --- | ---: | ---: | ---: |
| Expanded, pass-balanced Doppler | 37.84072987 | -122.36323034 | 10,789.4 m |
| Position with constrained orbital corrections | 37.84176890 | -122.46707481 | 1,820.4 m |
| Soft satellite identity mixture | 37.85375442 | -122.43725480 | 4,281.8 m |

Reference: **37.84903264307456, -122.4856541910174**, supplied previously by the
user. It is used only after inference for horizontal great-circle error, never
as an optimization target, initializer, or fitting prior. Coordinates are
conditional position estimates in geographic latitude/longitude, not GPS sensor
readings. Altitude is fixed at zero; no vertical accuracy is inferred.

The expanded method uses 37 reviewed tracks, 16 candidate satellite identities,
780 fitting and 547 evaluation observations from this scan. The rolling methods
use 128 tracks from 17 sessions (the target plus 16 earlier completed scans within
eight hours), 82 fixed-leader identities, 3,745 fitting and 2,589 evaluation
observations. Selection uses saved track reviews rather than the small final
association table. The older sparse diagnostic used three tracks and 30 points,
with approximately 11.02 km reference error.

| Method | Fit RMS (Hz) | Evaluation RMS (Hz) |
| --- | ---: | ---: |
| Expanded Doppler | 300.59 | 308.47 |
| Orbit corrected | 751.03 | 691.68 |
| Identity mixture | 777.84 | 776.70 |

These RMS values are not an apples-to-apples ranking: the expanded model uses
only the target scan, whereas the rolling models admit a larger and noisier
cohort. Large residual outliers remain. Robust objectives reduce their influence
but do not turn them into valid satellite evidence. Several orbital rate
corrections hit their constraints. The result does not establish that all saved
identities are correct, nor that a formal local covariance is calibrated.

The orbital fit is checked against exact shifted SGP4 propagation at the fitted
corrections, retaining Earth rotation at observation time. Maximum Doppler
approximation error is **0.0009328534 Hz**, below the unchanged **0.2 Hz** gate.
Five propagated states with quartic interpolation replace the insufficient
three-state approximation for this new analysis. The older research path remains
available. Failed verification withholds coordinates rather than loosening the
gate.

The soft model recomputes fitting-conditioned candidate weights at each trial
location, includes an unassigned component, and profiles track frequency offsets.
Its saved, site-assisted top-five candidate lists are **not** certified full-sky
identity support; weights are model-dependent, not calibrated probabilities.
All methods assume a stationary receiver over their stated window. Repeated
receiver copies and neighboring samples are not independent satellite passes.

## Artifacts and reproduction

- [Expanded Doppler PNG](expanded-doppler.png)
- [Orbit-corrected PNG](orbit-corrected.png)
- [Identity-mixture PNG](identity-mixture.png)
- [Complete numerical results, configuration and source provenance](document.json)

The document digest is
`sha256:6fb5ba01a42dfcce54c48d25e2f3716121934f9421b6388d8548be286799914e`.
It contains source digests, observation IDs, train/evaluation membership,
candidate weights, residuals, bounds, exclusions and numerical diagnostics.

From this repository with the scientific dependencies installed, as a user with
read access to the saved corpus and TLE archive:

```bash
mkdir -p /tmp/position-replay
OPENBLAS_NUM_THREADS=1 python -m leo.cli.scan_position_methods \
  --bulk-root /srv/bulk/leo --tle-root /var/lib/leo/tle \
  --session-id scan-fw-e3bc0741ecf02704 --output-root /tmp/position-replay
```

History selection is bounded and frozen at first publication. If other old
tracking products become available later, a fresh replay can select a different
cohort; use the recorded source manifest to identify such differences. No new
radio recordings were made for this qualification.

## Automatic publication

The tracking worker publishes three PNGs and a JSON document in the additive
`scanner-position-methods-v1` namespace. The Web UI exposes these below the
existing tracking analysis, including coordinate/error summaries and JSON download.
Queue completion requires verified artifacts; completed tracking without these
sidecars is eligible for recent bounded backfill. Unsupported data produces
explicit insufficient/failed panels and null coordinates, never invented fixes.

Tests cover known-position recovery, injected orbital rate recovery, held-out
mutation isolation, ambiguous identity handling, finite JSON, source selection
and provenance, artifact integrity, queue completion, API and Web UI rendering.
The saved-data replay exercises the full input-to-publication path. It exposed a
tuple-to-JSON configuration bug, now covered by a regression test.

A separate queue compatibility repair adds a new binding major for sparse
native-10M receipt V5 while preserving published V2 contracts and numerical
products. This is required for the automatic queue to progress past those captures.
See the operational documentation for policy and endpoint details.
