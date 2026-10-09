# Iteration 51: uniform additive region policy, 29/148 completed

This is a descriptive completion checkpoint at 2026-10-09T00:16:51.527521+00:00.
All 63 DS16, 51 DS17 and 34 DS18 members remain in the denominator. Pending,
unstarted and failed members are listed explicitly; subset means are not
full-dataset results. No new independent validation claim is made.

![Paired baseline, previous research and uniform-policy distributions](comparison.png)

## Position error on the matched completed subset

| Dataset evaluated/full | Arm | Model | Mean km | Median km | p95 km | Worst km |
|---|---|---|---:|---:|---:|---:|
| DS16 10/63 | fitted-c | baseline | 1.138 | 0.897 | 2.749 | 3.926 |
| DS16 10/63 | fitted-c | previous | 0.864 | 0.882 | 1.822 | 2.266 |
| DS16 10/63 | fitted-c | candidate | 0.864 | 0.882 | 1.822 | 2.266 |
| DS16 10/63 | zero-c | baseline | 1.538 | 1.235 | 3.659 | 4.079 |
| DS16 10/63 | zero-c | previous | 1.501 | 1.232 | 2.871 | 2.877 |
| DS16 10/63 | zero-c | candidate | 1.501 | 1.232 | 2.871 | 2.877 |
| DS17 9/51 | fitted-c | baseline | 18.073 | 1.295 | 92.896 | 152.840 |
| DS17 9/51 | fitted-c | previous | 1.043 | 0.877 | 2.295 | 2.616 |
| DS17 9/51 | fitted-c | candidate | 1.043 | 0.877 | 2.295 | 2.616 |
| DS17 9/51 | zero-c | baseline | 17.953 | 1.333 | 92.182 | 151.707 |
| DS17 9/51 | zero-c | previous | 1.051 | 0.853 | 2.057 | 2.256 |
| DS17 9/51 | zero-c | candidate | 1.051 | 0.853 | 2.057 | 2.256 |
| DS18 10/34 | fitted-c | baseline | 2.110 | 1.952 | 4.686 | 5.912 |
| DS18 10/34 | fitted-c | previous | 0.982 | 1.223 | 1.502 | 1.523 |
| DS18 10/34 | fitted-c | candidate | 0.982 | 1.223 | 1.502 | 1.523 |
| DS18 10/34 | zero-c | baseline | 2.649 | 1.993 | 5.276 | 6.549 |
| DS18 10/34 | zero-c | previous | 1.325 | 1.300 | 2.742 | 3.518 |
| DS18 10/34 | zero-c | candidate | 1.325 | 1.300 | 2.742 | 3.518 |

Baseline is deployed bounded-recovery hard60 (including qualified historical
replays). Previous is the frozen joint-clock/RF-time/satellite-slope research
candidate. Candidate retains baseline, sep25 and sep50 regions and selects each
arm by eligible regional score, then runs the same downstream model. Original
choices are never discarded because of their reference error.

## Paired changes and frequency fit

| Dataset | Arm | Better/worse/tied | Failed/not reached | Fallbacks | RMS base/previous/new Hz |
|---|---|---:|---:|---:|---:|
| DS16 | fitted-c | 0/0/10 | 0/0 | 0 | 81.19/65.54/65.54 |
| DS16 | zero-c | 0/0/10 | 0/0 | 0 | 132.65/120.66/120.66 |
| DS17 | fitted-c | 0/0/9 | 0/0 | 0 | 92.08/75.88/75.88 |
| DS17 | zero-c | 0/0/9 | 0/0 | 0 | 129.44/119.68/119.68 |
| DS18 | fitted-c | 0/0/10 | 0/0 | 0 | 101.93/74.49/74.49 |
| DS18 | zero-c | 0/0/10 | 0/0 | 0 | 134.10/115.27/115.27 |

Position ties use 1 m tolerance. Frequency RMS is separate from localization;
objectives from different models/banks are not treated as position accuracy.
c=0 and fitted-c retain matched observations, candidate sets, priors, seeds and
budgets within each stage; c=0 also locks RF-time terms. Failed final fits use
only the frozen convergence fallbacks, whose exact receipts remain in results/.

The policy adds computation: the identical ordered 400-point grid is reused,
but new regional calibrations/fits are required. Some older scans had no sep25
replay, so this uniform policy computes missing sep25 as well as sep50. This is
not an equal-total-compute comparison. Each result records archived/new replay
status, borrowed stages and elapsed time. DS16-046 reuses its already consumed
sep50 diagnostic; its success is not relabeled independent validation.

The protocol includes every frozen member, authority/exposure metadata, source
hashes and bindings. DS18 authority and seal remain unchanged. No readiness or
quality filter changes membership. Production, public contracts, golden fixtures,
QNAP data and RF collection are unchanged. Results do not promote a new default.

## Full membership and outcomes

| Member | Session | Outcome | Fitted-c new km | Zero-c new km | Exposure |
|---|---|---|---:|---:|---|
| DS16-001 | scan-fw-ba4cd19379329520 | complete  | 0.154 | 0.908 | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-002 | scan-fw-a326fb07c0e9b6e2 | complete  | 0.885 | 1.389 | previously_evaluated_consumed |
| DS16-003 | scan-fw-1ad7f3926e9a03e5 | complete  | 0.082 | 0.623 | previously_evaluated_consumed |
| DS16-004 | scan-fw-3ad2719629e7c60d | complete  | 0.884 | 2.036 | previously_evaluated_consumed |
| DS16-005 | scan-fw-194e6f064a898b85 | complete  | 1.071 | 1.774 | previously_evaluated_consumed |
| DS16-006 | scan-fw-e90e71153f3be029 | complete  | 0.522 | 0.640 | previously_evaluated_consumed |
| DS16-007 | scan-fw-0b8d0887b97b192b | complete  | 1.278 | 0.821 | previously_evaluated_consumed |
| DS16-008 | scan-fw-59521cec45054a41 | complete  | 0.880 | 1.075 | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-009 | scan-fw-99f3c2befba57d44 | complete  | 0.623 | 2.877 | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-010 | scan-fw-aa77506012889211 | not_run  | — | — | previously_evaluated_consumed |
| DS16-011 | scan-fw-8e8033677042ba97 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-012 | scan-fw-9284d4f6ce040d80 | not_run  | — | — | previously_evaluated_consumed |
| DS16-013 | scan-fw-330829d1e597d288 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-014 | scan-fw-dbf401c02543f194 | not_run  | — | — | previously_evaluated_consumed |
| DS16-015 | scan-fw-392b4f493b7c3c0e | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-016 | scan-fw-3b61d64df77251ca | not_run  | — | — | previously_evaluated_consumed |
| DS16-017 | scan-fw-5fab2b5974ce6bfb | not_run  | — | — | previously_evaluated_consumed |
| DS16-018 | scan-fw-13998828c952f265 | not_run  | — | — | previously_evaluated_consumed |
| DS16-019 | scan-fw-96d70bdc5aef38ed | not_run  | — | — | previously_evaluated_consumed |
| DS16-020 | scan-fw-151ee2be70b82235 | not_run  | — | — | previously_evaluated_consumed |
| DS16-021 | scan-fw-389713be72cd8450 | not_run  | — | — | previously_evaluated_consumed |
| DS16-022 | scan-fw-79f5280d20dd9e65 | not_run  | — | — | previously_evaluated_consumed |
| DS16-023 | scan-fw-356acff46cd12764 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-024 | scan-fw-0e40d0535caa0b16 | not_run  | — | — | previously_evaluated_consumed |
| DS16-025 | scan-fw-6ad6175fa731231e | not_run  | — | — | previously_evaluated_consumed |
| DS16-026 | scan-fw-320fa74020b04d85 | not_run  | — | — | previously_evaluated_consumed |
| DS16-027 | scan-fw-84eb24f335b96c64 | not_run  | — | — | previously_evaluated_consumed |
| DS16-028 | scan-fw-6cfa779ffd41637a | not_run  | — | — | previously_evaluated_consumed |
| DS16-029 | scan-fw-d3b1edc33cb8210d | not_run  | — | — | previously_evaluated_consumed |
| DS16-030 | scan-fw-de9320ef0602bad8 | not_run  | — | — | previously_evaluated_consumed |
| DS16-031 | scan-fw-9f4e8b72d567c0bb | not_run  | — | — | previously_evaluated_consumed |
| DS16-032 | scan-fw-eb9ba03847cd10fb | not_run  | — | — | previously_evaluated_consumed |
| DS16-033 | scan-fw-0ffe1eede92820a9 | not_run  | — | — | previously_evaluated_consumed |
| DS16-034 | scan-fw-90722ab71ea4e7bd | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-035 | scan-fw-2917f7344e48ba39 | not_run  | — | — | previously_evaluated_consumed |
| DS16-036 | scan-fw-a8fbd8c43834a765 | not_run  | — | — | previously_evaluated_consumed |
| DS16-037 | scan-fw-9061ae11d2702df3 | not_run  | — | — | previously_evaluated_consumed |
| DS16-038 | scan-fw-d6e344d47603fb34 | not_run  | — | — | previously_evaluated_consumed |
| DS16-039 | scan-fw-6f9e553db123bebd | not_run  | — | — | previously_evaluated_consumed |
| DS16-040 | scan-fw-fedf239661900a5a | not_run  | — | — | previously_evaluated_consumed |
| DS16-041 | scan-fw-85f7398f9b9461ec | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-042 | scan-fw-a52fc8f717bd9f76 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-043 | scan-fw-c937db2e26dad0aa | not_run  | — | — | previously_evaluated_consumed |
| DS16-044 | scan-fw-64163dfbcc531a50 | not_run  | — | — | previously_evaluated_consumed |
| DS16-045 | scan-fw-58975d3328a47507 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-046 | scan-fw-c6c51bfeb6a7c3d9 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-047 | scan-fw-98990902df445215 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-048 | scan-fw-7e51f48fa65d6f81 | not_run  | — | — | previously_evaluated_consumed |
| DS16-049 | scan-fw-3bf66f35e3a07685 | not_run  | — | — | previously_evaluated_consumed |
| DS16-050 | scan-fw-7e6fe9f57ae2562c | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-051 | scan-fw-899e83e995c96cdf | not_run  | — | — | previously_evaluated_consumed |
| DS16-052 | scan-fw-7b796c5b898df6bf | not_run  | — | — | previously_evaluated_consumed |
| DS16-053 | scan-fw-a88b75d9a4cad4ff | not_run  | — | — | previously_evaluated_consumed |
| DS16-054 | scan-fw-4dbadefb5dadb59d | not_run  | — | — | previously_evaluated_consumed |
| DS16-055 | scan-fw-5e190e43f0c8c9e2 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS16-056 | scan-fw-8d94198baa058d67 | complete  | 2.266 | 2.864 | previously_evaluated_consumed |
| DS16-057 | scan-fw-6aa645776351507d | not_run  | — | — | previously_evaluated_consumed |
| DS16-058 | scan-fw-4099ab8ea46fad71 | not_run  | — | — | previously_evaluated_consumed |
| DS16-059 | scan-fw-aeea3ef6d81d637f | not_run  | — | — | previously_evaluated_consumed |
| DS16-060 | scan-fw-19a8822932068f7a | not_run  | — | — | previously_evaluated_consumed |
| DS16-061 | scan-fw-f8a93156e16bf663 | not_run  | — | — | previously_evaluated_consumed |
| DS16-062 | scan-fw-ecb0b93df67421a9 | not_run  | — | — | previously_evaluated_consumed |
| DS16-063 | scan-fw-82df8e587b0af01b | not_run  | — | — | previously_evaluated_consumed |
| DS17-001 | scan-fw-94a135be557220a2 | complete  | 0.522 | 0.668 | previously_evaluated_consumed |
| DS17-002 | scan-fw-d52ab5a4255e6b69 | complete  | 1.048 | 0.638 | previously_evaluated_consumed |
| DS17-003 | scan-fw-0b7f58e4a4c5f248 | complete  | 0.605 | 0.626 | previously_evaluated_consumed |
| DS17-004 | scan-fw-489095a9b5fac6fa | complete  | 0.281 | 0.828 | previously_evaluated_consumed |
| DS17-005 | scan-fw-3556024e5a9aca59 | complete  | 1.814 | 1.758 | previously_evaluated_consumed |
| DS17-006 | scan-fw-ede4e78d97eba2b8 | complete  | 0.877 | 0.875 | previously_evaluated_consumed |
| DS17-007 | scan-fw-489c6a2a9c099f1f | complete  | 0.521 | 0.853 | previously_evaluated_consumed |
| DS17-008 | scan-fw-f6399482c82aa4ae | complete  | 2.616 | 2.256 | previously_evaluated_consumed |
| DS17-009 | scan-fw-3aeb80c956be3aa4 | complete  | 1.098 | 0.954 | previously_evaluated_consumed |
| DS17-010 | scan-fw-a8c6131bf5668000 | not_run  | — | — | previously_evaluated_consumed |
| DS17-011 | scan-fw-b730e91a3bc15f50 | not_run  | — | — | previously_evaluated_consumed |
| DS17-012 | scan-fw-90cf9bd2e3bdf17a | not_run  | — | — | previously_evaluated_consumed |
| DS17-013 | scan-fw-3998f1ce91552465 | not_run  | — | — | previously_evaluated_consumed |
| DS17-014 | scan-fw-80e0b5ff0c2281bd | not_run  | — | — | previously_evaluated_consumed |
| DS17-015 | scan-fw-02fa8ae90161a54e | not_run  | — | — | previously_evaluated_consumed |
| DS17-016 | scan-fw-cd431e86366d1a4c | not_run  | — | — | previously_evaluated_consumed |
| DS17-017 | scan-fw-edfd1d12c2197eb2 | not_run  | — | — | previously_evaluated_consumed |
| DS17-018 | scan-fw-9cc717ef20e35ab4 | not_run  | — | — | previously_evaluated_consumed |
| DS17-019 | scan-fw-311f43e4ce6623c9 | not_run  | — | — | previously_evaluated_consumed |
| DS17-020 | scan-fw-70960ed5154a66f4 | not_run  | — | — | previously_evaluated_consumed |
| DS17-021 | scan-fw-9842f56a548dce0a | not_run  | — | — | previously_evaluated_consumed |
| DS17-022 | scan-fw-e8dab4957e0fa180 | not_run  | — | — | previously_evaluated_consumed |
| DS17-023 | scan-fw-ae430bd782cebf78 | not_run  | — | — | previously_evaluated_consumed |
| DS17-024 | scan-fw-56d44c8114c78a9e | not_run  | — | — | previously_evaluated_consumed |
| DS17-025 | scan-fw-69d773d8350f9180 | not_run  | — | — | previously_evaluated_consumed |
| DS17-026 | scan-fw-ba074a45b06c3191 | not_run  | — | — | previously_evaluated_consumed |
| DS17-027 | scan-fw-2c2cda36cd4299ab | not_run  | — | — | previously_evaluated_consumed |
| DS17-028 | scan-fw-c7bfee3d5232d446 | not_run  | — | — | previously_evaluated_consumed |
| DS17-029 | scan-fw-bac72677cbb520e7 | not_run  | — | — | previously_evaluated_consumed |
| DS17-030 | scan-fw-57dc40c858e08df6 | not_run  | — | — | previously_evaluated_consumed |
| DS17-031 | scan-fw-4a25a326be928fc1 | not_run  | — | — | previously_evaluated_consumed |
| DS17-032 | scan-fw-a4acf9fc066cdde8 | not_run  | — | — | previously_evaluated_consumed |
| DS17-033 | scan-fw-faf66389f66f36c5 | not_run  | — | — | previously_evaluated_consumed |
| DS17-034 | scan-fw-21c4ca5e190aee20 | not_run  | — | — | previously_evaluated_consumed |
| DS17-035 | scan-fw-89a46fa06eca3443 | not_run  | — | — | previously_evaluated_consumed |
| DS17-036 | scan-fw-c60687ebcb2a8600 | not_run  | — | — | previously_evaluated_consumed |
| DS17-037 | scan-fw-f19be4ee7443fdb4 | not_run  | — | — | previously_evaluated_consumed |
| DS17-038 | scan-fw-de2ffd1076bbed84 | not_run  | — | — | previously_evaluated_consumed |
| DS17-039 | scan-fw-007104def3cc4fb2 | not_run  | — | — | previously_evaluated_consumed |
| DS17-040 | scan-fw-bb9c0b011134327c | not_run  | — | — | previously_evaluated_consumed |
| DS17-041 | scan-fw-d763b0938d2c73d8 | not_run  | — | — | previously_evaluated_consumed |
| DS17-042 | scan-fw-e1fe8a2e07277387 | not_run  | — | — | previously_evaluated_consumed |
| DS17-043 | scan-fw-21442a5061e1b639 | not_run  | — | — | previously_evaluated_consumed |
| DS17-044 | scan-fw-8e758884efd73e9f | not_run  | — | — | previously_evaluated_consumed |
| DS17-045 | scan-fw-6a03003ca0a65459 | not_run  | — | — | previously_evaluated_consumed |
| DS17-046 | scan-fw-9a65cd199e826d59 | not_run  | — | — | previously_evaluated_consumed |
| DS17-047 | scan-fw-82ee62657e29d639 | not_run  | — | — | previously_evaluated_consumed |
| DS17-048 | scan-fw-85e3bfb9e4cfcd46 | not_run  | — | — | previously_evaluated_consumed |
| DS17-049 | scan-fw-0faabd2537f4fafd | not_run  | — | — | previously_evaluated_consumed |
| DS17-050 | scan-fw-4a9c9e031c781aad | not_run  | — | — | previously_evaluated_consumed |
| DS17-051 | scan-fw-da79d96a4515ec30 | not_run  | — | — | previously_evaluated_consumed |
| DS18-001 | scan-fw-b299927c33fccc7a | complete  | 1.272 | 0.315 | previously_evaluated_consumed |
| DS18-002 | scan-fw-4e13bed3c09cadff | complete  | 0.305 | 0.406 | previously_evaluated_consumed |
| DS18-003 | scan-fw-c351a2d8f24c4455 | complete  | 0.365 | 1.314 | previously_evaluated_consumed |
| DS18-004 | scan-fw-0014cc103687b490 | complete  | 1.310 | 3.518 | previously_evaluated_consumed |
| DS18-005 | scan-fw-65e29ebee6f2a036 | complete  | 0.905 | 0.732 | previously_evaluated_consumed |
| DS18-006 | scan-fw-3d984efc721d4bc6 | complete  | 1.523 | 1.793 | previously_evaluated_consumed |
| DS18-007 | scan-fw-adcdd076e48cb2d8 | complete  | 0.219 | 0.633 | previously_evaluated_consumed |
| DS18-008 | scan-fw-db6e1b4079322617 | complete  | 1.258 | 1.647 | previously_evaluated_consumed |
| DS18-009 | scan-fw-1317eab1ab1dd263 | complete  | 1.477 | 1.603 | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-010 | scan-fw-a7930b52d1b01dff | complete  | 1.187 | 1.287 | previously_evaluated_consumed |
| DS18-011 | scan-fw-c5558b9d9ba7691e | not_run  | — | — | previously_evaluated_consumed |
| DS18-012 | scan-fw-7ce336d48ad3409b | not_run  | — | — | previously_evaluated_consumed |
| DS18-013 | scan-fw-b8ccfda98272ebe0 | not_run  | — | — | previously_evaluated_consumed |
| DS18-014 | scan-fw-5b1967c41451a971 | not_run  | — | — | previously_evaluated_consumed |
| DS18-015 | scan-fw-19235796dc3f06a2 | not_run  | — | — | previously_evaluated_consumed |
| DS18-016 | scan-fw-818f5d3b8ca6cbbe | not_run  | — | — | previously_evaluated_consumed |
| DS18-017 | scan-fw-fd728d9087fe35e2 | not_run  | — | — | previously_evaluated_consumed |
| DS18-018 | scan-fw-f5bf95a1570bece0 | not_run  | — | — | previously_evaluated_consumed |
| DS18-019 | scan-fw-e43a5641cecd1863 | not_run  | — | — | previously_evaluated_consumed |
| DS18-020 | scan-fw-a43bbffc6826cdc5 | not_run  | — | — | previously_evaluated_consumed |
| DS18-021 | scan-fw-f7f863971e4aa0b8 | not_run  | — | — | previously_evaluated_consumed |
| DS18-022 | scan-fw-f1a32cacd910c005 | not_run  | — | — | previously_evaluated_consumed |
| DS18-023 | scan-fw-8d37c3b59f1ca7d1 | not_run  | — | — | previously_evaluated_consumed |
| DS18-024 | scan-fw-d406a510f5473348 | not_run  | — | — | previously_evaluated_consumed |
| DS18-025 | scan-fw-c17fbfacad538641 | not_run  | — | — | previously_evaluated_consumed |
| DS18-026 | scan-fw-433aa9c47fea9cac | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-027 | scan-fw-1d39b7f1cd0643aa | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-028 | scan-fw-6c32f1804f9892a4 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-029 | scan-fw-4a5a8bdd0dd50f2d | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-030 | scan-fw-317151cefa87e8ac | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-031 | scan-fw-b68bdd7a7011688b | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-032 | scan-fw-7c7196b249b7798a | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-033 | scan-fw-713a66e116375e5d | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
| DS18-034 | scan-fw-4e603fa090384662 | not_run  | — | — | not_matched_in_reviewed_registry_not_unseen_claim |
