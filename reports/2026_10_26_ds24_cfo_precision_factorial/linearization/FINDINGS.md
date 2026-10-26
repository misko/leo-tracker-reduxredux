# The earlier local-response discrepancy follows the precision intervention

The saved local Hδ vectors agree closely with the factorial **CFO contrast at the original fixed precision packet**, including DS24-0011. Their earlier disagreement with the full VI refit was therefore not evidence that local linearization missed the isolated CFO effect by about 90 m. That comparison also contained precision feedback and its interaction with the CFO change.

| Case / arm | Saved Hδ east / north (m) | CFO contrast at original packet east / north (m) | Difference norm (m) | Earlier H versus full VI difference (m) |
|---|---:|---:|---:|---:|
| 0010 c0 | −76.006 / +109.927 | −76.069 / +110.275 | 0.354 | 25.708 |
| 0010 fitted c | −75.783 / +110.623 | −73.496 / +110.216 | 2.323 | 18.608 |
| 0011 c0 | −21.662 / +6.042 | −21.087 / +6.458 | 0.710 | 91.526 |
| 0011 fitted c | −22.913 / +6.717 | −22.448 / +6.688 | 0.467 | 94.513 |

![Equal-aspect signed displacement comparison](isolated_CFO_response02.png)

[comparison.csv](comparison.csv) retains all signed east/north vectors: Hδ, isolated CFO contrast, new full conditional movement, previous actual VI movement, their differences, and the factorial interaction. The full conditional movement agrees with the previous VI movement within 3.040/2.788 m for 0010 c0/fitted-c and 0.00277/0.00855 m for 0011. These are endpoint-displacement comparisons, not distances from geographic truth.

This sharpens the earlier interpretation: in 0011, the original-packet CFO effect is about 22–23 m, while the full movement is about 102–105 m. The controlled precision-packet change and interaction account for the additional movement within this conditional model. The packet contains both fragment noise and coefficient-prior precisions; this does **not** isolate measurement-noise Gamma alone or establish a physical noise defect. The packets themselves were learned at different endpoints on the same exposed observations.

Residual nonlinear effects remain: H differs from the isolated nonlinear solve by 0.35–2.32 m. The factorial interaction norms are 13.9–25.0 m, so factor effects depend on the other factor's level; displacement norms and causal percentages must not be added. The full conditional and original VI models also have different objective constructions, with small endpoint-difference residuals noted above. None of these comparisons changes qualification, policy or an accuracy conclusion.

This was a saved-only posthoc readback. Exactly four unique case/arm pairs were joined; saved vector norms independently checked kilometre-to-metre conversion and row matching. Both source evidence seals and their exact CSV/JSON bindings were verified. [summary.json](summary.json) records source hashes; [seal.json](seal.json) binds the original readback, and [plot02_seal.json](plot02_seal.json) binds the layout-only final figure revision. The first figure version is preserved as provenance. Total processing including the reporting revision and metadata allowance was **2.475 seconds**, below the five-second cap. No fitting, RF-sample access, geometry evaluation or GPS read occurred; validation/ and all earlier sealed studies remain unchanged.
