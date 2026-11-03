# Candidate-specific residual structure transfers across receivers

**Same-candidate cross-RX slopes improve held residual prediction in all nine
panels.** This contrasts with the failed other-candidate receiver-clock models.
It supports investigating shared candidate-specific errors, but it does not
identify an orbit correction or establish improved geographic accuracy.

| Dataset | Supported / eligible targets | Better held predictions | Median paired reduction, Hz |
|---|---:|---:|---:|
| DS7 | 635 / 1,346 | 386 / 635 | +6.44 |
| DS8 | 617 / 1,311 | 400 / 617 | +13.10 |
| DS9 | 595 / 1,326 | 385 / 595 | +10.65 |
| Total | 1,847 / 3,983 | 1,171 / 1,847 | +9.89 |

Each target contributes its median absolute held residual. Positive paired
reduction means lower error than a zero residual slope. All 72 scans contribute
supported targets. RX0-target and RX1-target median gains are +10.10 and +9.17 Hz.
These directed transfers include reciprocal pairs and are not independent trials.
The remaining 2,136 targets retain zero-slope fallback: all-population median
gain is zero and mean gain is +17.13 Hz. No unsupported target is counted as
improved. Original bank membership was 4,328 tracks; 3,983 passed the inherited
conditional residual export before this experiment.

## Matched other-candidate control

Only 257 targets have both same-candidate and other-candidate opposite-RX support.
The following comparisons keep that population identical across arms.

| Dataset | Matched targets | Same-candidate median gain, Hz | Other-candidate median gain, Hz | Same candidate beats other |
|---|---:|---:|---:|---:|
| DS7 | 95 | +11.67 | −27.85 | 69 / 95 |
| DS8 | 85 | +26.57 | −26.63 | 67 / 85 |
| DS9 | 77 | +13.48 | −61.73 | 60 / 77 |
| Total | 257 | +16.09 | −36.91 | 196 / 257 |

![Matched held-residual gains](matched.png)

Same-candidate transfer beats zero slope on 172/257 matched targets; the other
candidate control does so on 92/257. This distinguishes the conditional
predictors, not verified same-satellite versus different-satellite signals.
Candidate assignments derive from the original training model.

The target's own training slope is stronger: on the 1,847 supported targets,
it improves 1,393 cases with median gain +17.95 Hz. That comparator is not an
independent calibration. Adding another free slope to the position model is
not warranted by either result.

## Frozen method and all panel results

The [protocol](PROTOCOL.md) was written before execution. Donors must be on the
opposite receiver in the same scan and exact RF, with at least 50% overlap of
the target training span and at least five training points spanning five seconds
within that span. Fit donor slopes only on those points. Same-candidate transfer
uses the median slope of available tracks assigned to that number. The control
uses median slopes within each other number and then across numbers. One donor
is sufficient for this candidate-specific hypothesis; unlike a population-clock
estimate, requiring three distinct same-candidate numbers would be incoherent.
Every donor track and candidate number is retained in `results.json`.

All arms use the target training-only mean time and residual, then predict held
points. Masks are inherited interleaved partitions, not causal forecasting.
No held sample estimates a slope or selects a donor. Residuals are normalized
to canonical 11.2-GHz Hz and inherit the existing fitted geographic location,
recording time, and candidate assignments.

| Eight-scan panel | Supported targets | Median paired gain, Hz |
|---|---:|---:|
| DS7 early | 214 | +5.18 |
| DS7 middle | 201 | +7.23 |
| DS7 late | 220 | +6.46 |
| DS8 early | 223 | +12.14 |
| DS8 middle | 202 | +14.14 |
| DS8 late | 192 | +13.51 |
| DS9 early | 199 | +5.30 |
| DS9 middle | 207 | +11.47 |
| DS9 late | 189 | +16.90 |

## Implication for sub-km work

This is consistent with shared candidate-specific residual structure. It cannot
distinguish orbit errors from fitted-location errors, shared timing errors,
transmitter behavior, common processing artifacts or incorrect associations.
In particular, subtracting the shared residual may erase the position information
we are trying to recover. It must not be treated as an independent orbit or
receiver calibration.

The next discriminating analysis should compare the shared residual directions
with position, recording-time and candidate-orbit sensitivities. Quantify how
much position information a candidate-specific nuisance term would remove before
attempting geographic fitting. An independently anchored orbit correction would
be preferable to a free candidate slope if suitable evidence exists. Historical
candidate transfer already failed to generalize reliably; within-scan cross-RX
agreement does not override that result. No sub-km accuracy gain is claimed here.

## Verification and reproduction

Three tests pass: slope recovery with correct candidate/receiver separation,
held mutation isolation, and RF/time support exclusions. The runner verifies the
prior export's input/source bindings. Result hashes bind all nine input exports,
protocol, runner and reused scoring helper. Plot generation verifies hashes,
3,983 unique case keys, support counts, candidate exclusions and fallback identity.
Ruff lint/format pass. No collection, production edit or geographic fit occurred.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s reports/2026_09_29_candidate_rx_transfer -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 90 .venv/bin/python reports/2026_09_29_candidate_rx_transfer/transfer.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_candidate_rx_transfer/plot.py
```
