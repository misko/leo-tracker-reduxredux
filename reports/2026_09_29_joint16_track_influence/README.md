# Track influence does not isolate the two joint16 failures

The two joint fits above 1 km reference distance do not show unusually concentrated local track influence. Their top-ten shares of summed influence magnitudes are **7.57% and 8.00%**, within the **6.15–10.01%** range across all nine fits. Removing the most influential tracks is not supported as a failure-identification rule by this diagnostic.

| Fit | Reference distance | Largest track response | Top-ten vector response |
|---|---:|---:|---:|
| DS7 middle+late (above 1 km) | 1,727.7 m | 112.1 m | 203.8 m |
| DS8 early+middle (above 1 km) | 1,091.7 m | 164.7 m | 407.5 m |
| DS7 early+late (largest top-ten response) | 176.2 m | 161.2 m | 664.8 m |

[All nine fits](table.md) · [Full-precision summary](summary.json) · [Protocol](PROTOCOL.md)

The most sensitive top-ten set occurs in a near-reference fit. High influence can mean useful geographic information, not bad data. Conversely, the DS7 failure has a smaller projected top-ten response than several successful fits. No tracks were removed, reweighted or labelled corrupt.

## What the response means

At each selected joint16 fit, compute each scan's observed training Hessian and profile its timing nuisance. Transform each track's gradient using that full scan's timing-profile operator, then solve against the pooled geographic curvature. The negative solution is the local derivative of location when that track's likelihood weight decreases.

The reported metre values extrapolate that derivative to a unit weight change. They are not fitted leave-one-out displacements, geographic errors or uncertainty bounds. The top-ten vector response sums signed response vectors for the ten largest individual norms; the norm share instead sums magnitudes and ignores cancellation. No removal direction was selected using the reference.

The largest single-track response across all nine fits is about 210 m. This does not exclude a large nonlinear change after deleting a track: curvature and candidate responsibilities could change. The audit specifically finds no exceptional **local concentration** in the two failing fits. It cannot prove that errors are uniformly distributed or establish a physical cause.

## Implication

Deprioritize automatic trimming based only on local influence magnitude. Keep these derivatives as diagnostics, and require signal-quality or physical-consistency evidence before rejecting tracks. The remaining failures warrant tests of shared measurement-model error and dependence across tracks, rather than treating every influential track as an outlier. Ordinary pooling remains the geographic baseline from the preceding matched comparison.

## Validation

All nine profiled pooled Hessians are positive definite and all 144 scan derivative audits pass. Each scan's independently evaluated track scores and gradients replay its aggregate evaluation within 1e-7; scan scores also replay the saved joint fit within 1e-7. Each fit contains 948–976 tracks. The same scans and tracks recur across pairs, so totals are not independent trial counts.

A synthetic quadratic test verifies the downweighting sign and equality of the profiled response with the full location-plus-timing response, including a small finite perturbation that changes curvature. Dataset subprocesses finished in 19–20 seconds under 300-second caps. No numerical retries occurred.

[run.py](run.py), [launch.py](launch.py), [input/code hashes](manifest.json), per-track gradients and response vectors, receiver/window group responses, receipts, [test_response.py](test_response.py), and [summarize.py](summarize.py) are retained. Reference distance is added only during summary generation. Existing source conditioning, prior research exposure and unquantified reference uncertainty remain.

No new RF, production changes or remote publication occurred.
