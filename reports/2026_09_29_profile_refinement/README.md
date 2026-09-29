# Joint profile refinement does not rescue short-set accuracy

**All 36 joint location/timing refinements pass their numerical audits.**
Thirty-four return within 1 m of their original fitted location. One finds a
better training solution, but its nominal geographic error worsens. The
training-selected result still has only **3/18 panels below 1 km**; the worst
remains **3,680.9 m**. This is not promoted as a geographic improvement.

The study follows the [spatial-profile diagnostic](../2026_09_29_spatial_profile/README.md).
For every DS7/DS8/DS9 early/middle/late four/eight panel, the highest training
score probe at 250 m and at 1 km initializes a joint location/timing fit. The
model and all observations remain unchanged. This isolates search effects
from changes to the statistical model. Held scores and geographic reference
errors never select starts or endpoints.

| Outcome | Count |
|---|---:|
| Completed panels | 18/18 |
| Qualified endpoints | 36/36 |
| Endpoints within 1 m of original location | 34/36 |
| Panels with training improvement above 1e-6 nats | 1/18 |
| Training-selected sub-km panels | 3/18 |

## The DS7 alternative

DS7 middle-four's 1 km probe converges to a point **496.75 m** from the
original location. Training improves **15.0912 nats** and held prediction
improves **41.8811 nats**, while nominal error increases from **2,196.1 m to
2,568.5 m**. Ten of 231 tracks change their conditional candidate MAP; mean
conditional candidate-weight total variation is 0.03846. The largest scan
timing change is 0.74407 s. Those are model-assignment changes, not verified
satellite identities or measured clock corrections.

This explains why the earlier local quadratic badly predicted that probe's
loss. The original fit was not the best training solution among these starts.
However, the better likelihood and held prediction do not bring the location
closer to the exposed reference. Neither local sharpness nor predictive gain
alone establishes sub-km geographic accuracy.

DS7 late-eight has a second exceptional endpoint, 34.70 m from baseline,
with training change -0.13428 nats and held change +7.70930 nats. It is not
selected because its training score is lower. Every other endpoint is within
1 m of baseline. These finite starts do not prove global uniqueness.

## Matched median errors

Metres; medians of three early/middle/late sets for each dataset and size.
Baseline is retained unless a numerically qualified refinement improves
training by more than 1e-6 nats. Nested four/eight sets are dependent.

| Dataset | Scans per set | Original | Training-selected refinement |
|---|---:|---:|---:|
| DS7 | 4 | 2,196.1 | 2,568.5 |
| DS7 | 8 | 2,023.6 | 2,023.6 |
| DS8 | 4 | 2,473.8 | 2,473.8 |
| DS8 | 8 | 1,721.1 | 1,721.1 |
| DS9 | 4 | 1,173.9 | 1,173.9 |
| DS9 | 8 | 876.1 | 876.1 |

![Joint refinement outcomes](refinement.png)

[All 36 endpoint results](RESULTS.md) retain failures/ties and descriptive
outcomes. The [machine-readable summary](summary.json) includes assignment
changes, timing changes and both candidate starts per panel. Full per-track
scores and weights are retained under runs/. No failed start was retried.

## Verification and interpretation

Five synthetic tests passed before freezing the inputs and execution sources.
All eighteen child processes exited zero. Independent result auditing
reconstructed probe selection, numerical qualifications, derivative arithmetic,
score sums, track correspondence and weight normalization, then verified the
source/input/process hashes. It is not an independent radio-likelihood
implementation. The reported coordinates use the inherited coordinate model.

Summed child wall time is **174.69 s**, longest child **15.24 s**, peak RSS
**666,312 KiB**. Execution was sequential, BLAS1/nice19, with a 90 s timeout,
4 GiB address-space cap and at least 5 GiB available memory. No RF collection,
raw-waveform analysis, propagation, provider fetches or production changes.

This result rules out these particular extra starts as a geographic rescue;
it does not rule out all search improvements or identify the source of error.
These are previously explored single-site panels with an exposed unsurveyed
reference. They are not blind validation or calibrated sub-km resolution.
The full-dataset results use more observations and should not be substituted
for these four/eight-scan performance requirements.

[Frozen protocol](PROTOCOL.md), [tests](tests.log), [input seal](input-seal.json),
[complete evidence hashes](evidence-sha256.json), [next model work](NEXT.md).
