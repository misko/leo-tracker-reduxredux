# DS22 native C satellite-density qualification

The pure native satellite-propensity density passed actual-data qualification at the original full-training C winners on DS22-019 and DS22-075. The original objective and NLL replayed exactly. At zero logits the raw density matched original native likelihood, posteriors and dense prediction derivatives to numerical precision. This is a qualified likelihood component, not a fitted model or localization improvement.

| Case | Candidates | Windows | Pure-density evaluations | Elapsed seconds | All-logit finite-difference maximum error |
|---|---:|---:|---:|---:|---:|
| 019 | 36 | 3144 | 75 | 33.726 | 1.1822e-7 |
| 075 | 43 | 3155 | 89 | 33.609 | 1.2821e-7 |

Each case additionally used exactly one original objective, one explicit native orbit prediction and one explicit source-likelihood call. The original objective itself includes one source-likelihood call; that is recorded separately. There were zero optimizer calls and no held/reference reads. Both stayed within the frozen 120-second internal, 135-second TERM and 140-second KILL bounds.

The dense predictions used each original bank, native branch timestamps, physical calibration, recorded receiver lifts and group calibration exactly once. Maximum raw NLL difference was 7.28e-12, satellite posterior difference 1.78e-15 and dense prediction-gradient difference 3.13e-17. Conditional-minus-raw NLL matched the integrated log-mass sum within 7.01e-13. Zero-logit integrated mass matched the independent existing `model_c_visibility_mass.support_mass` port within 4.45e-16.

At both actual states every available branch/candidate entry was visible. Integrated mass was one within 2.3e-16, so this normalization makes no substantive score change there. There were 11,520 and 11,802 unavailable padded branch slots, respectively; their posterior mass was verified exactly zero. The component tests separately cover partial visibility and no visible support, so the actual lack of invisible available entries is disclosed rather than treated as testing those cases.

At logits `0.1*cos(index)`, all 36/43 coefficient derivatives passed centered finite differences with step 0.0001. The summed logit gradient was within 2.14e-13 of zero, and the satellite softmax probabilities summed to one. This parameterization is a normalized satellite mixture and differs from B's fixed-budget logistic detection probabilities. Branch evidence remains conditioned; this is not a generative peak-selection model, and no temporal or physical hardware interpretation follows.

Driver source `b9d1c92a8` uses pure density source `9cebf6a1e`. Twelve tests passed: three owned pipeline/accounting/replay guards and nine density tests, plus Ruff. Frozen namespaces are `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c-propensity-qualification-v1/DS22-019` and `DS22-075`.

| Case | Protocol SHA256 | Report SHA256 |
|---|---|---|
| 019 | `45a8985d197be498c9876b7fb965da6eadf024166e706a84857093f29b15d532` | `c277d7a6fcac471ebb0541422a0ef4164e90613c25817af0ad5fd8e54ac390a9` |
| 075 | `029f985ea0944c5e493f724c15da90118d7084e5c6ffd27edb932786c3614301` | `cda2a84492b6fc6f1a2d0aae33f5f75f9ac27fb7ec9129071097a94ad0e1175b` |
