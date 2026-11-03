# DSX01 research checkpoint — 2026-10-17

Research only. No production deployment or promotion is implied. The active objective remains generalizable recovery of the 15 frozen GLRT windows, without using reference coordinates to seed or select models.

## Age-dependent timing prior

The independently sampled historical TLE-update consistency investigation and controlled S03 tests are complete in [iteration5/age_timing](../2026_10_17_dsx01_iteration5/age_timing/README.md). Element age is measured from each object's entry epoch, not archive download time. Provider-specific supported bins set relative-timing widths; unsupported bins retain the 2 s baseline. The common clock prior remains 3 s. This is a conservative sensitivity, not a calibrated orbit-error distribution.

In the fitted-c blocked comparison, the age policy changed held assignments from 788 to 791 out of 1,909, requested-window assignments from 68 to 67 out of 80, and configured-reference distance from 7.346 to 7.934 km. The matched research domain is the broad regional prior; it does not retain the production endpoint's additional 25 km local disk. Both arms pass strict convergence. The conditional c=0 comparison is also saved. These results do not support promoting this prior or expanding it into an all-five campaign.

## Current calibration experiment

[full_joint_band/PROTOCOL.md](full_joint_band/PROTOCOL.md) and its versioned errata/addendum specify the all-five comparison: fixed versus jointly fitted receiver/band contrasts, fitted c and conditional c=0, 20 endpoints. Ordered original candidate banks, ephemerides, observations and regional domain remain matched. Both policies have 1,000-objective / 120 s inference allowances, including profile and qualification calls for the joint policy. Two source-family workers reuse only immutable source preparation, with fresh complete parameter copies and fingerprint checks.

All ten actual-data qualifications passed before fitting. All 20 endpoints froze in `full_joint_band/outcomes_seal.json` (SHA256 `29ae2084f41741b07ef629eeb125c66384daf1c84f4f8b21a03953fc94a3448a`), before evaluation against requested windows or configured reference positions. Charged inference used 7,944 objective/density calls. Strict selected endpoints are fixed fitted-c 4/5, joint fitted-c 3/5, fixed c=0 5/5, joint c=0 1/5. Lower-J nonstrict outcomes remain visible.

The sealed full-cohort evaluation is negative for the recovery/location objective: fitted-c fixed to joint increases full assignments from 13,784 to 14,144 /20,084, but requested support falls from 422 to 420 /693. Joint versus matched fixed adds 587 and loses 227 full observations; retained-pair frequency RMS improves from 153.37 to 151.13 Hz. Summed data NLL improves by 2,337.81, without a geographic fix. Configured-reference distances S01–S05 change from 132.472/135.377/3.282/260.094/4.709 km to 132.415/135.113/3.276/259.787/2.354 km. Conditional c=0 full support increases 12,180 to 13,412, requested support falls 417 to 399, and only one joint endpoint is strict. No promotion or sub-kilometer claim follows.

The preceding training-only blocked pilot improved held support from 788 to 815/1,909 and requested support from 68 to 70/80, with lower held data NLL. Configured-reference distance slightly worsened, 7.346 to 7.481 km. That is evidence for improved prediction, not improved location or verified identities.

## Other completed evidence

- [provider_disagreement](provider_disagreement/README.md): causal HF/ST element sets yield more than 10 s of local along-track displacement disagreement for 7/211 jointly valid selected pairs. Neither provider is truth. Perpendicular differences remain separate; scalar time shifts cannot repair arbitrary orbit errors.
- [recovery_identity_audit](recovery_identity_audit/README.md): most strongly restored windows have a dominant model identity. Identity concentration does not establish a correct satellite assignment.
- [physical_bias_review.md](physical_bias_review.md): scaling the previously unsuccessful satellite frequency-bias correction by actual RF does not repair its held-data failure. No additional fractional-bias fitting campaign is justified.
- [frame_phase_audit](frame_phase_audit/README.md): original positive-arrival phase convention and saved cross-band arrays reproduce exactly. The observed sign disagreement is not explained by a global sign error; no phase-geolocation model is promoted.
- [frame_phase_inventory](frame_phase_inventory/README.md): all-15 metadata inventory is sealed. All 693 observations have bound arrival anchors; all 4,251 candidate alternatives remain retained. Three tests pass. Raw ambiguity counts do not identify distinct emitters.
- [joint_timing_profiles](joint_timing_profiles/README.md): an exact complete-calibration timing-profile adapter is qualified against direct objectives. No additional timing-profile fit campaign has started.
- [paired_blocks](paired_blocks/README.md): temporal block comparisons keep complete denominators and paired gains/losses. The 80 requested held observations occupy only two temporal blocks.

## Interpretation and next decision

More associations, better frequency likelihood, and better location are separate outcomes. Existing full-data restoration gains have not established sub-kilometer accuracy, and the configured station location is a diagnostic with unknown survey uncertainty.

The all-five calibration gate does not justify another timing-profile fitting matrix as the next primary experiment. The exact adapter remains available as a qualified fallback; its mathematical closure is not evidence that a better physical solution exists in the current candidate/timing basin. Prioritize an independent audit of generic cold candidate discovery and initialization, with causal ephemeris provenance and unchanged evaluation rules. Candidate omissions observed in an earlier half-recording forecast motivate that audit, but do not prove missing candidates in the full-recording banks. No new fitting campaign has started. No per-window winner mixing, satellite-ID exceptions, reference-position selection, new RF collection, or sealed-evidence rewrites are authorized by this checkpoint.
