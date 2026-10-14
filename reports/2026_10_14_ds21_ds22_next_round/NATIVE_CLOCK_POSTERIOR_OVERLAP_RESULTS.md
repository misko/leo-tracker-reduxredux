# Native-clock full versus half posterior correspondence

The original matched DS22-001 full-band winner loses substantial low-band likelihood through windows it treats as clutter but the low-only winner treats as signal. This is a correspondence result on the same observations, not evidence that the half-only satellite labels are correct. The diagnostic uses no reference, held data or optimizer fits.

The three states are the original native-clock matched-view training selections: full `B-profile-release`, low `low-anchor`, high `B-profile-release`. Every state is reconstructed against the same full frame, bank and original clock precision. Comparisons use only the relevant half's observations. These are conditional shared-discovery comparisons, not independent half-only discovery.

| Quantity | CH1–4 | CH5–8 |
| --- | ---: | ---: |
| Windows | 1811 | 1418 |
| Full minus own-half NLL | +911.735371 | +205.680071 |
| Full / own-half effective signal windows | 1227.964 / 1361.834 | 965.490 / 979.920 |
| Mean joint satellite/branch/clutter posterior overlap | 0.765695 | 0.920331 |
| Signal-conditioned satellite overlap | 0.797373 | 0.915370 |
| Signal-conditioned Jensen–Shannon divergence (nats) | 0.119414 | 0.039282 |
| Both-state confident MAP switches / confident windows | 304 / 1519 | 51 / 1258 |

Confidence is a prespecified posterior probability of at least 0.8, including clutter as a state. Signal-conditioned statistics exclude windows with either state's total signal mass at most `1e-12` (1286 low and 1014 high windows remain). Mean joint branch overlap and satellite-marginal overlap agree to approximately `1e-19`; alias-branch redistribution contributes negligibly to the disagreement in these particular states.

Positive NLL differences below mean the full state predicts worse. MAP transition groups partition every window; their likelihood contributions sum to each band's total.

| Transition group | Low windows | Low NLL difference | High windows | High NLL difference |
| --- | ---: | ---: | ---: | ---: |
| Same signal satellite | 964 | +90.534831 | 887 | +115.887054 |
| Different signal satellite | 233 | +96.590741 | 76 | +27.143892 |
| Full clutter, half signal | 171 | +908.211087 | 23 | +95.509955 |
| Full signal, half clutter | 41 | −183.362109 | 7 | −32.638407 |
| Both clutter | 402 | −0.239179 | 425 | −0.222423 |

The low-band deficit is dominated by lost signal support, partially offset by the reverse transitions. The high-band deficit is smaller and includes a larger stable-assignment residual component. This distinguishes assignment/clutter changes from a simple common widening of residuals, but cannot establish which state generalizes or localizes better. It does not justify changing clutter odds or treating the native likelihood normalization as erroneous. The expanded-calibration trial remains unpromoted; this diagnostic introduces no new fit.

Implementation source `f15e37e58` preserves the original source `1ee0b16f7`. The first six-evaluation diagnostic passed exact likelihood/posterior checks but failed report serialization because ratio-based Jensen–Shannon arithmetic produced infinity for subnormal probabilities. Its failed receipt is retained. The second namespace binds that failure and uses log-space arithmetic; a subnormal/disjoint-support JSON regression was added. Five tests passed, including a genuine nonzero-clock model reconstruction, identity, transition accounting and bound-state mutation rejection; Ruff passed.

The completed diagnostic took 33.655 seconds, six objective evaluations and zero fits under the prespecified 120-second internal cap. Per-window likelihood and satellite/clutter posterior reconstruction replay the original objective, and transition accounting closes. Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-overlap-audit-v2/report.json`, SHA-256 `93c6ab01e4651f2dfab3a26101cda0a890f63784fc365a8e82575070fbab10b3`. The preserved failed first diagnostic adds six evaluations to the total work; neither diagnostic uses references or held prediction.
