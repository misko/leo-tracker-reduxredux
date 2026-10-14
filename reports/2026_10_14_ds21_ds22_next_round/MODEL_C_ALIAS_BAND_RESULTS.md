# C029: band scores after receiver ambiguity refinement

The ambiguity correction changes the disagreement: CH5–8 now slightly prefers
the 3.691118 km endpoint, while CH1–4 still prefers the selected 83.390154 km
endpoint. The selected position therefore remains unchanged. These errors are
retrospective development diagnostics from the previously sealed paired experiment;
neither reference coordinates nor position errors enter this audit or selection.

| Sealed endpoint | CH1–4 NLL | CH5–8 NLL | Prior penalty | Total objective |
|---|---:|---:|---:|---:|
| Original incumbent, 83.390154 km | 18665.864810 | 14097.779451 | 271.223664 | 33034.867925 |
| Ordinal 1 unshifted, 5.202842 km | 21979.036557 | 16137.255059 | 241.466317 | 38357.757934 |
| Ordinal 1 shifted, 3.691118 km | 18888.370656 | 14085.601164 | 226.746740 | 33200.718561 |
| Ordinal 10 unshifted | 22313.569627 | 16941.009017 | 566.815716 | 39821.394359 |
| Ordinal 10 shifted | 21843.525908 | 16884.250808 | 545.800265 | 39273.576981 |

Lower scores are better. Relative to the incumbent, the corrected ordinal 1 has
CH1–4 NLL **222.505846 worse**, CH5–8 NLL **12.178286 better**, and prior penalty
**44.476924 better**. Their sum leaves its total objective **165.850636 worse**.
The remaining selection failure is driven by the lower-band likelihood, rather
than the prior or both bands preferring the distant endpoint. This does not
justify reweighting the bands using known position errors.

Posterior signal mass changes from 960.995 to 929.158 of 1500 low-band windows,
and from 796.491 to 831.120 of 1172 high-band windows. Mass is fractional model
responsibility, not a count of independently verified satellite detections.
The next useful diagnostic is the low-band likelihood and assignment breakdown
at these two endpoints, to distinguish satellite support, residual penalties,
and clutter rejection before proposing another fit experiment.

## Reproducibility

- Source `caa7f5abf`; new wrapper `tools/ds21_model_c_alias_band_audit.py`.
- Two tests passed, including actual native band/objective probability closure;
  Ruff passed. The new input guard rejects incomplete or duplicate paired outcomes.
- Frozen output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-alias-band-audit-029-v1`.
- All four paired endpoints and the source incumbent were included; no new
  endpoint selection, optimizer calls, reference access, or held-data access.
- Five objective calls, five explicit orbit predictions, ten band likelihood
  evaluations; complete in 14.015 seconds under 120/135/140-second limits.
- Original objective/NLL and additive band decomposition close within 1e-7.
- Result SHA256 `fe63dc06091557a5702a3f02f9c75f4703b84ea9e4fcb37a21981f8bf301d5b2`.
- Seal SHA256 `cf74689585fa6905e83113c8396372510bb7c0b7144c5fbf2d2dfcfec7a69f7d`.

This is a fitted-c diagnostic on a repeatedly inspected development case, not an
independent validation result or a promoted estimator.
