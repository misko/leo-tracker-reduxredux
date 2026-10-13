# DS21-007 fitted shape initialization

The shape stage completed all nine prescribed fits in **17.446 seconds**.
Every fit was stationary. This supplies three training-selected shape parents
for subsequent initialization; it is not a final position-accuracy result.
No reference position or held observation projection was used.

| View | Fits / stationary | Selected objective | Supported observations | Shape degrees of freedom |
| --- | ---: | ---: | ---: | ---: |
| CH1–8 | 3 / 3 | 649.683709 | 1,045 | 1,016 |
| CH1–4 | 3 / 3 | 803.428045 | 865 | 838 |
| CH5–8 | 3 / 3 | 97.652185 | 617 | 597 |

Objectives across views use different evidence and must not be compared as
position-accuracy scores. The original supported-sequence construction and shape
math were retained. Each view used the same three discovery locations, with a
20-second/600-iteration limit per fit. The 28-satellite subset came from the
completed discovery's 970-satellite bank. All nine calls used the fitted-c arm;
the constant-RF sequence projection removes information about c, so this stage
does not establish a learned RF calibration. Absolute hybrid fits estimate that
coefficient later.

The fitted-only parent selector replaces the historical selector's zero-c arm.
It exports the low-, high- and all-band winners without substituting discovery
states. Their local east/north coordinates in kilometres are respectively
(-90.260206, -79.996104), (-84.371197, -77.171234) and
(-86.841844, -79.232767). These are proposal coordinates, not position errors.

All ten component-owned tests passed independently in the worker and integration
runs; the integration run took 47.79 seconds. Tests include an actual tiny shape
fit, original-core routing, fitted-only selection, parent and source tampering,
failed/orphan slice rejection, cached reuse and budgets. A post-run cached
validation passed without additional fitting and confirmed all nine attempts,
selected parents and immutable source bindings.

Receipt bindings:

- Implementation commit: `855b32f04`.
- Protocol: `sha256:153cba2ca5bc33785ff2c2a0165164dc49801222aa01a09340686eab91c047b9`.
- Terminal: `sha256:140f2fcff9ca92c32d46d825b7388e92392631443108ea7e759d96f57a4e9cc9`.
- Source archive: 314 files.
- Local namespace: `local/shape-007-v1` within this report directory.

The remaining original initialization chain is fresh bootstrap, absolute hybrid
fits, cold bootstrap and six physical proposal exports. Those stages are being
implemented in a separate adapter to preserve this successful stage's frozen
sources. Twenty-eight of the 34 fast development recordings still lack discovery;
29, including DS21-007, still lack completed downstream proposal caches. No new
full-DS21 accuracy claim follows from this milestone.
