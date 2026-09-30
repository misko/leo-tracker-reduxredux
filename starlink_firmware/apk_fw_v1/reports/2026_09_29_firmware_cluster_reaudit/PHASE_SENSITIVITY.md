# Upper-edge lead depends on absolute phase and marginal-quality coverage

The frozen eight-group upper-edge result does not reproduce using either of two
phase-invariant feature sets. A higher pilot threshold also removes the entire
small group that contributed most of the lead. These findings limit its value
as a field-decoding lead; they do not prove the original measurements are noise.

## Frozen sensitivity test

Retain exactly the original discovery-frame group labels. Fit discovery centroids
for three fixed representations of the same symbols 2–7 and four nonpilot carriers:

1. Original absolute unit phase.
2. Products of adjacent carrier phases within each of the two pilot flanks:
   `u[0] conj(u[1])` and `u[2] conj(u[3])` per symbol. These cancel an arbitrary
   common rotation independently for each symbol.
3. Products of consecutive symbol phases on each carrier. These cancel a common
   frame-wide rotation, but not different per-symbol rotations.

Evaluate only the second reserved frame. All raw artifact hashes are checked.
Use 499 shuffles and 499 chronological circular rotations within the same exact
session/channel/rate/receiver strata as before. Center each complete reference
set symmetrically and use family maxima across these three representations.
This is a post-selection sensitivity test on reused data. Its correction does
not encompass the entire history of exploratory research.

| Representation | Discovery balanced accuracy | Held balanced accuracy | Mean shuffle | Family shuffle p | Family circular p |
|---|---:|---:|---:|---:|---:|
| Absolute phase | 0.951 | 0.192 | 0.155 | 0.030 | 0.014 |
| Within-symbol carrier products | 0.613 | 0.104 | 0.109 | 0.988 | 0.972 |
| Between-symbol products | 0.710 | 0.109 | 0.108 | 0.762 | 0.732 |

The original result is reproduced descriptively; its new p-values are not an
independent confirmation. The invariant models neither preserve the discovery
groups well nor generalize above the conditional controls. Because these groups
were discovered using absolute phase, this loss is partly expected when removing
information that defined them. It cannot distinguish a true absolute-phase
modulation pattern from residual calibration or other common-phase structure.
It does show that the current association is not a demonstrated invariant relation
among neighboring symbols that could be mapped directly to a code or interleaver.

## Pilot-quality coverage

The recorded `pilot` value is a proxy based on held-pilot coherence, not SNR or
BER. Apply higher thresholds only as a coverage audit, without reclustering or
dropping missing classes from the target definition:

| Required coherence | Remaining entries in groups 0…7 | Missing groups |
|---|---|---|
| >0.52 | 210, 15, 23, 7, 12, 9, 6, 0 | 7 |
| >0.55 | 75, 6, 12, 4, 6, 1, 4, 0 | 7 |
| >0.60 | 12, 2, 1, 0, 1, 0, 0, 0 | 3, 5, 6, 7 |

All stricter eight-group comparisons abstain. This is a loss of coverage, not
a negative held-out accuracy result. No new quality cut was selected to obtain
a favorable p-value or to rescue the lead.

## Firmware implications and remaining scope

The firmware prefix has mode-dependent fields, while the observed association
is phase-sensitive and heavily supported by near-threshold observations. These
facts provide no defensible assignment to a type flag, sequence value, length,
SATAddr or satellite identity. The lead remains recorded as limited reproducible
absolute-phase structure with concentrated support. More arbitrary scans around
it are not justified by this result.

This closes the immediate robustness questions raised by the frame-transfer lead.
Other symbol-pair/group associations, complete initialization/coding paths and
the cross-association firmware ledger remain part of the active investigation.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_firmware_cluster_reaudit/phase_sensitivity.py
uv run --no-project --with numpy --with scipy --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit/test_phase_sensitivity.py
```

The ignored JSON records the frozen-source and method hashes, all reported
metrics and quality coverage. The component test verifies the intended rotation
invariances; it and Ruff pass. No new RF, source-data alteration, fixture update
or data commit occurred.
