# A two-receiver veto for far omitted regions

The frozen rule would have withheld both far-omission fixes and retained all four valid fixes. It would also have retained every near-omission fix, including both 100 m and both 1.5 km omissions. These ten offers reuse two public simulated captures. The test identifies a useful distinction within these captures and leaves wrong-offer decisions near a face unresolved. [Frozen protocol at `f10bf43b4`](regional-exterior-veto-protocol.md) · [Measurements](measurements/regional-exterior-veto.json)

## Saved two-receiver evidence

The earlier fixed-owner likelihood could improve just outside a valid boundary. The subsequent causal all-track mixture reassigned satellites at every probe, and its pooled sign would still have withheld a valid southern fix. A separate orbit-split halo rule used fitted radii and agreement across assigned satellites. The present audit uses each physical receiver's own maximum from the saved all-track score, the original matched inside and exterior grids, and one width-scaled geometric rule. Both receivers must improve over their own inside maximum, prefer a unique exterior location at least one offer width beyond a face, and agree within one offer width. [Fixed-owner profile](exterior-profile.md) · [All-track score](regional-reassignment.md) · [Orbit-split halo](../../../tools/pipeline_eval/variants/region_halo.py)

| Public offer | RX1 gain | RX2 gain | Both exterior maxima past face | Veto outcome |
|---|---:|---:|---:|---|
| North, centered | −0.065298 | −0.060224 | 0.098 km | Keeps valid fix |
| North, 100 m inside | −0.000638 | −0.000451 | 0.098 km | Keeps valid fix |
| North, 100 m outside | −0.000536 | −0.000347 | 0.098 km | Misses omission |
| North, 1.5 km outside | +0.000171 | +0.000372 | 0.098 km | Misses omission |
| North, far omitted | +1.421316 | +1.132595 | 50.000 km | Vetoes omission |
| South, centered | −0.064240 | −0.071451 | 0.098 km | Keeps valid fix |
| South, 100 m inside | −0.000067 | +0.000160 | 0.098 km | Keeps valid fix |
| South, 100 m outside | +0.000074 | +0.000300 | 0.098 km | Misses omission |
| South, 1.5 km outside | +0.001047 | +0.000815 | 0.098 km | Misses omission |
| South, far omitted | +0.808568 | +0.817415 | 50.000 km | Vetoes omission |

Both receiver groups selected the exact same exterior coordinate on every offer, so their separation was zero throughout. Each far maximum was two offer widths beyond the face. The other eight maxima were on the first exterior shell, 97.656 m outside. Three of the four near omissions favored an exterior point in both receivers, and all three gains failed the clearance requirement. The northern 100 m omission already favored the inside in both groups. The two mirrored inside packets matched their corresponding original edge packets and were counted once. [Mirrored offers](mirrored-regions.md) · [Pointwise input archives and digests](regional-exterior-veto-protocol.md#receiver-agreement-beyond-the-offered-square)

Per calibration arm, the earlier pooled-score sign retained 3 of 4 valid fixes and would have vetoed 5 of 6 omitted offers. This rule retains 4 of 4 and would veto 2 of 6. The veto calculation shares its verdict across arms because within-track contrasts cancel the constant fitted calibration term. It changes no likelihood, assigned position, or publication. The receivers share a waveform and causal sky. Agreement at two simulated locations gives no independent physical site count, and all ten observed maxima already coincide across receivers. This panel therefore leaves the agreement requirement's contribution untested. The component tests exercise deliberately conflicting maxima. [Earlier decision totals](mirrored-regions.md) · [Component tests](../../../tests/pipeline_eval/test_regional_exterior_veto.py)

## Cost and reproduction

Evaluating the rule on saved scores took **44.7 μs of CPU per offer**, using the median of 101 ten-offer batches. The original Graph preparation, catalogue lookup, and orbit scoring used **2.84–3.05 CPU seconds per offer**, with **1.31–1.45 seconds** in the probe calculation after preparation. A new offer would need those scores or equivalent evidence. The audit reads only the digest-checked public score packets. It makes no new orbit probes and runs no localization solver. Eighteen component tests passed across the rule and original scorer suites. [Trial runner](regional_exterior_veto_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/regional_exterior_veto_trial.py
```
