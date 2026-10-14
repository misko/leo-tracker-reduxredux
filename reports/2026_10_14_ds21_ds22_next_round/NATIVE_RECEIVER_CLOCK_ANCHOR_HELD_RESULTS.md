# Training-selected lower anchor also predicts held observations better

The selected native-clock lower-anchor C001 solution improves held prediction in both bands compared with the native-clock full-anchor state. Training and held likelihood therefore agree on this comparison, unlike the earlier original-C anchor experiment. This supports the improvement beyond its training score, but does not establish the requested localization accuracy.

| Frozen released state | Held CH1–8 NLL/window | Held CH1–4 NLL/window | Held CH5–8 NLL/window |
|---|---:|---:|---:|
| Full anchor | 13.650782096 | 12.766972790 | 14.983379306 |
| Lower anchor, training-selected | 13.281089418 | 12.646494921 | 14.237923487 |
| Upper anchor | 14.553032641 | 14.297051101 | 14.938998578 |

Lower is better. All three states use the same 805 held windows (484 lower, 321 upper), disjoint from the original training partition. Position, fitted c, receiver clock/calibration functions, satellite timing and candidate bank are frozen before projection at native branch timestamps. The training state objectives replay within 1e-7 and band NLLs sum to full NLL within 1e-7. This evaluates full-band fitted states, not independently fitted half-band models.

Previously sealed configured-reference distances are 19.428852, 6.928778 and 5.411226 km respectively. The nearer upper-anchor state remains worse on both training and held aggregate likelihood, so likelihood is still not a demonstrated position selector. DS22 reference is configured-unconfirmed. No reference was read by this diagnostic, no held selection occurred, and the training-selected state was not changed.

This is a repeated diagnostic on the development sample's existing held partition, not a fresh untouched validation cohort. The locked evaluation cohort remains separate. The result must not be generalized into a full-dataset accuracy claim.

Source `bbb815e31`; the six existing transport/disjoint-inventory tests and Ruff pass. The run completed in 44.474258 seconds with nine predictions and zero fits. Receipts: `local/ds22-native-clock-anchor-held-v1`; report SHA256 `d058255d040bb76506b9520bd663227a6097a559491d2abdc8f7adad52c4b2e0`.
