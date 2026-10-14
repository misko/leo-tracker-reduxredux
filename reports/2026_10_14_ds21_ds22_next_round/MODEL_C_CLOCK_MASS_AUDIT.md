# Native-clock C integrated-density audit

The visibility-dependent emission mass does not explain the tested C053 ordering or the C081 donor rejection. This is a fixed-state diagnostic with fitted c, no optimizer calls, no reference reads, and no held-data use.

| Case | Frozen state | Training NLL | Sum log integrated mass | Conditional NLL |
| --- | --- | ---: | ---: | ---: |
| 053 | Incumbent | 22083.543077 | -9.503479 | 22074.039599 |
| 053 | High-band position, full nuisance profile | 22065.031881 | -9.503479 | 22055.528403 |
| 053 | Selected release | 22064.556982 | -9.503479 | 22055.053504 |
| 081 | B-derived donor after native fit | 26669.227653 | -1.925053 | 26667.302600 |
| 081 | Repeated native incumbent | 25638.756309 | -2.064550 | 25636.691760 |

C053 has 1,870 windows; integrated mass ranges from 0.961259 to 1. All three states have exactly the same total log-mass correction. C081 has 2,054 windows; mass ranges from 0.986147 to 1. Normalization increases the donor-minus-incumbent NLL gap by only 0.139497, from 1030.471344 to 1030.610841. Priors are unchanged. Neither comparison reverses.

The calculation conditions on the existing detector branch evidence and singleton families. It integrates the original satellite/branch emission density under its existing visibility support. It is not a generative model of peak selection and does not establish that other observation-model assumptions are correct. It also does not justify applying B's event-model normalization formula to C.

Five exact objective and per-window NLL replays and five explicit native-orbit calls completed in 20.790 seconds. Source endpoint replay tolerance was 1e-7. The component test uses nonzero receiver-clock coefficients, checks band partition closure, and rejects corrupted endpoint scores; 1 test passed and Ruff passed. Implementation commit: `0baf126d5`.

Frozen experiment: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-mass-audit-v1`.

- Result SHA256: `47d77abe0e31c7e37b29136ca1978ae4c0fa0af72f96085dcfd44c9725250b55`
- Seal SHA256: `adb8e7b79feb673053696227b0fe40fa86d0c66d4e94a54d02540d91210b6aea`

Original cohort results remain unchanged. This audit does not promote a new estimator.
