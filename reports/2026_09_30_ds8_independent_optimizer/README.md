# Independent optimizer validates a second nearby DS8 solution

SLSQP completes the forty-scan DS8 fit in **162.85 seconds** and passes the unchanged scientific qualification gates. It produces a location **422.683 m from the supplied reference**, **67.683 m from the previously qualified corrected fit**. It validates a nearby alternative after the earlier L-BFGS attempts failed qualification; it does not establish a global optimum or reliable physical accuracy.

## Results

| Quantity | Independent SLSQP fit |
|---|---:|
| Training log score | −423353.883935181 |
| Held log score | −279778.266410416 |
| Maximum absolute gradient | 0.0013811 |
| Finite-difference gradient discrepancy | 0.00002907 |
| Absolute score replay error | 0 |
| Iterations / evaluations | 44 / 183 |
| Runtime | 162.850 s |
| Boundary hit | No |
| Qualification | Pass |

| Qualified comparison | Position separation | Training gain of new fit | Held gain of new fit |
|---|---:|---:|---:|
| Original rank-start N40 endpoint | 177.754 m | +8.159843 | +43.761621 |
| Previously corrected endpoint | 67.683 m | −0.681997 | +5.591251 |

The original two N40 endpoints were 273.484 m apart. After timing-mode diagnosis and independent optimization, the new rank-derived fit and the corrected fit are 67.683 m apart. They still differ and prefer different training/held tradeoffs. **The corrected fit remains selected by highest qualified training score**, at 424.581 m from the reference; neither held score nor reference distance changes that selection.

The SLSQP absolute training score agrees with the unqualified centered L-BFGS output to roughly 5.4e−9. Agreement in score does not itself imply identical vectors, but successful independent optimization supports the existence of a valid local solution near the previously failed optimization result. The old failures remain unchanged in the [prior report](../2026_09_30_ds8_validated_timing_refit/README.md).

## Method and controls

The [protocol](PROTOCOL.md) freezes the same model, forty recordings and initial vector as the previous validated-timing experiment. It starts at the original rank location, replacing three ambiguous timings with independently validated scalar choices. It does not start from either failed joint endpoint.

Only the optimizer changes: SLSQP with maxiter=100, ftol=1e−10, and initial-score centering. E/N bounds remain ±12 km and per-scan timing bounds ±5 seconds. Qualification requires optimizer success, no parameter within 0.001 of a bound, maximum gradient <=0.01 and central finite-difference discrepancy <=0.02. Held observations do not enter optimization or qualification. The process completes before the declared 180-second cap with no retry.

Three component-owned synthetic tests pass before radio execution: coupled interior recovery with a large likelihood offset, boundary-optimum rejection, and rejection of deliberately incorrect zero derivatives. The last test prevents optimizer success and a reported zero gradient from bypassing the independent numerical audit. Cached input/source hashes, exact scan order and absolute score replay verify.

## Consequence for sub-km work

Timing alternatives and optimizer termination explain part of the local DS8 disagreement. This is useful numerical progress, but the extra optimizer costs substantially more than the preceding 40–71 second fits and does not beat the strongest qualified training score. Do not replace the main optimizer on this evidence alone.

Stop expanding solver variants on this same example. The next useful transfer test is to profile and independently validate timing alternatives on a fixed DS10 panel that previously missed sub-km reference distance, then run a bounded joint fit only if training data identify a material timing improvement. Report failures and resource costs, and do not select panels using their reference distances. A successful DS8 numerical diagnosis must not conceal DS10 or DS8 scan-selection failures.

The roof reference has no supplied uncertainty. This remains an exposed-data, zero-height, site-conditioned candidate analysis; within-recording held prediction and agreement of local fits do not certify geographic accuracy. No new RF, export, propagation, production change or remote publication occurred.

## Reproduce verification

[result.json](result.json) retains the full vector, initial state and qualification evidence. [summary.json](summary.json) records comparisons. [solver.py](solver.py) is research-local and has no production effect. The inventory `evidence.sha256` binds all artifacts.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_ds8_independent_optimizer -p 'test_*.py'
python3 reports/2026_09_30_ds8_independent_optimizer/summarize.py
cd reports/2026_09_30_ds8_independent_optimizer
sha256sum -c evidence.sha256
```
