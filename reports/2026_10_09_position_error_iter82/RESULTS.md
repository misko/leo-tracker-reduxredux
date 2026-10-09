# Iterations78/82: full-membership sensitivity comparison

**148/148 members have results; complete.**

All members remain below, including pending/input failures. Numerical failures retain fixed fallbacks. Comparisons use identical available membership per group; the JSON also retains the full frozen baseline. All data are consumed development.

| Dataset | Arm | Sigma Hz/s | Available / all | Mean km | Median km | p95 km | Worst km | Raw failed / not attempted |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DS16 | fitted-c | 0.25 | 63 / 63 | 1.017307 | 0.884608 | 2.238156 | 2.750798 | 1 / 0 |
| DS16 | fitted-c | 0.125 | 63 / 63 | 1.048718 | 0.977753 | 2.362875 | 2.534273 | 0 / 0 |
| DS16 | fitted-c | 0.5 | 63 / 63 | 0.979007 | 0.834879 | 2.088464 | 3.204798 | 0 / 0 |
| DS17 | fitted-c | 0.25 | 51 / 51 | 0.864203 | 0.707882 | 2.008805 | 2.635226 | 0 / 0 |
| DS17 | fitted-c | 0.125 | 51 / 51 | 0.885273 | 0.636444 | 2.105234 | 2.727193 | 0 / 0 |
| DS17 | fitted-c | 0.5 | 51 / 51 | 0.819111 | 0.696276 | 2.058978 | 2.483593 | 0 / 0 |
| DS18 | fitted-c | 0.25 | 34 / 34 | 2.739331 | 1.139814 | 3.167973 | 53.140384 | 0 / 0 |
| DS18 | fitted-c | 0.125 | 34 / 34 | 2.757489 | 1.140985 | 3.137097 | 53.012787 | 0 / 0 |
| DS18 | fitted-c | 0.5 | 34 / 34 | 2.691656 | 1.122461 | 2.903525 | 53.400741 | 0 / 0 |
| DS16 | zero-c | 0.25 | 63 / 63 | 1.363228 | 1.161220 | 2.846043 | 3.902727 | 1 / 0 |
| DS16 | zero-c | 0.125 | 63 / 63 | 1.407153 | 1.188109 | 2.868639 | 4.019921 | 1 / 0 |
| DS16 | zero-c | 0.5 | 63 / 63 | 1.321051 | 1.075030 | 2.937303 | 4.263626 | 0 / 0 |
| DS17 | zero-c | 0.25 | 51 / 51 | 1.417183 | 1.388078 | 2.793543 | 3.518910 | 1 / 0 |
| DS17 | zero-c | 0.125 | 51 / 51 | 1.473566 | 1.433366 | 2.821585 | 3.577776 | 5 / 0 |
| DS17 | zero-c | 0.5 | 51 / 51 | 1.326922 | 1.359911 | 2.874086 | 3.124958 | 0 / 0 |
| DS18 | zero-c | 0.25 | 34 / 34 | 2.917558 | 1.209166 | 3.818120 | 54.922335 | 0 / 0 |
| DS18 | zero-c | 0.125 | 34 / 34 | 3.034118 | 1.207073 | 4.366261 | 54.880085 | 3 / 0 |
| DS18 | zero-c | 0.5 | 34 / 34 | 2.815838 | 1.130151 | 3.701531 | 54.832123 | 0 / 0 |

![Matched available-member means](comparison.png)

Position and frequency statistics are separate in [summary.json](summary.json), with paired regressions, subgroups, convergence and fallback stages. No reference-error-based per-scan selection occurs. Changed-model scores are not ranked against one another. New90s controls may differ from old20s fits.

| Member | Session | Status | Failure |
|---|---|---|---|
| DS16-001 | scan-fw-ba4cd19379329520 | complete |  |
| DS16-002 | scan-fw-a326fb07c0e9b6e2 | complete |  |
| DS16-003 | scan-fw-1ad7f3926e9a03e5 | complete |  |
| DS16-004 | scan-fw-3ad2719629e7c60d | complete |  |
| DS16-005 | scan-fw-194e6f064a898b85 | complete |  |
| DS16-006 | scan-fw-e90e71153f3be029 | complete |  |
| DS16-007 | scan-fw-0b8d0887b97b192b | complete |  |
| DS16-008 | scan-fw-59521cec45054a41 | complete |  |
| DS16-009 | scan-fw-99f3c2befba57d44 | complete |  |
| DS16-010 | scan-fw-aa77506012889211 | complete |  |
| DS16-011 | scan-fw-8e8033677042ba97 | complete |  |
| DS16-012 | scan-fw-9284d4f6ce040d80 | complete |  |
| DS16-013 | scan-fw-330829d1e597d288 | complete |  |
| DS16-014 | scan-fw-dbf401c02543f194 | complete |  |
| DS16-015 | scan-fw-392b4f493b7c3c0e | complete |  |
| DS16-016 | scan-fw-3b61d64df77251ca | complete |  |
| DS16-017 | scan-fw-5fab2b5974ce6bfb | complete |  |
| DS16-018 | scan-fw-13998828c952f265 | complete |  |
| DS16-019 | scan-fw-96d70bdc5aef38ed | complete |  |
| DS16-020 | scan-fw-151ee2be70b82235 | complete |  |
| DS16-021 | scan-fw-389713be72cd8450 | complete |  |
| DS16-022 | scan-fw-79f5280d20dd9e65 | complete |  |
| DS16-023 | scan-fw-356acff46cd12764 | complete |  |
| DS16-024 | scan-fw-0e40d0535caa0b16 | complete |  |
| DS16-025 | scan-fw-6ad6175fa731231e | complete |  |
| DS16-026 | scan-fw-320fa74020b04d85 | complete |  |
| DS16-027 | scan-fw-84eb24f335b96c64 | complete |  |
| DS16-028 | scan-fw-6cfa779ffd41637a | complete |  |
| DS16-029 | scan-fw-d3b1edc33cb8210d | complete |  |
| DS16-030 | scan-fw-de9320ef0602bad8 | complete |  |
| DS16-031 | scan-fw-9f4e8b72d567c0bb | complete |  |
| DS16-032 | scan-fw-eb9ba03847cd10fb | complete |  |
| DS16-033 | scan-fw-0ffe1eede92820a9 | complete |  |
| DS16-034 | scan-fw-90722ab71ea4e7bd | complete |  |
| DS16-035 | scan-fw-2917f7344e48ba39 | complete |  |
| DS16-036 | scan-fw-a8fbd8c43834a765 | complete |  |
| DS16-037 | scan-fw-9061ae11d2702df3 | complete |  |
| DS16-038 | scan-fw-d6e344d47603fb34 | complete |  |
| DS16-039 | scan-fw-6f9e553db123bebd | complete |  |
| DS16-040 | scan-fw-fedf239661900a5a | complete |  |
| DS16-041 | scan-fw-85f7398f9b9461ec | complete |  |
| DS16-042 | scan-fw-a52fc8f717bd9f76 | complete |  |
| DS16-043 | scan-fw-c937db2e26dad0aa | complete |  |
| DS16-044 | scan-fw-64163dfbcc531a50 | complete |  |
| DS16-045 | scan-fw-58975d3328a47507 | complete |  |
| DS16-046 | scan-fw-c6c51bfeb6a7c3d9 | complete |  |
| DS16-047 | scan-fw-98990902df445215 | complete |  |
| DS16-048 | scan-fw-7e51f48fa65d6f81 | complete |  |
| DS16-049 | scan-fw-3bf66f35e3a07685 | complete |  |
| DS16-050 | scan-fw-7e6fe9f57ae2562c | complete |  |
| DS16-051 | scan-fw-899e83e995c96cdf | complete |  |
| DS16-052 | scan-fw-7b796c5b898df6bf | complete |  |
| DS16-053 | scan-fw-a88b75d9a4cad4ff | complete |  |
| DS16-054 | scan-fw-4dbadefb5dadb59d | complete |  |
| DS16-055 | scan-fw-5e190e43f0c8c9e2 | complete |  |
| DS16-056 | scan-fw-8d94198baa058d67 | complete |  |
| DS16-057 | scan-fw-6aa645776351507d | complete |  |
| DS16-058 | scan-fw-4099ab8ea46fad71 | complete |  |
| DS16-059 | scan-fw-aeea3ef6d81d637f | complete |  |
| DS16-060 | scan-fw-19a8822932068f7a | complete |  |
| DS16-061 | scan-fw-f8a93156e16bf663 | complete |  |
| DS16-062 | scan-fw-ecb0b93df67421a9 | complete |  |
| DS16-063 | scan-fw-82df8e587b0af01b | complete |  |
| DS17-001 | scan-fw-94a135be557220a2 | complete |  |
| DS17-002 | scan-fw-d52ab5a4255e6b69 | complete |  |
| DS17-003 | scan-fw-0b7f58e4a4c5f248 | complete |  |
| DS17-004 | scan-fw-489095a9b5fac6fa | complete |  |
| DS17-005 | scan-fw-3556024e5a9aca59 | complete |  |
| DS17-006 | scan-fw-ede4e78d97eba2b8 | complete |  |
| DS17-007 | scan-fw-489c6a2a9c099f1f | complete |  |
| DS17-008 | scan-fw-f6399482c82aa4ae | complete |  |
| DS17-009 | scan-fw-3aeb80c956be3aa4 | complete |  |
| DS17-010 | scan-fw-a8c6131bf5668000 | complete |  |
| DS17-011 | scan-fw-b730e91a3bc15f50 | complete |  |
| DS17-012 | scan-fw-90cf9bd2e3bdf17a | complete |  |
| DS17-013 | scan-fw-3998f1ce91552465 | complete |  |
| DS17-014 | scan-fw-80e0b5ff0c2281bd | complete |  |
| DS17-015 | scan-fw-02fa8ae90161a54e | complete |  |
| DS17-016 | scan-fw-cd431e86366d1a4c | complete |  |
| DS17-017 | scan-fw-edfd1d12c2197eb2 | complete |  |
| DS17-018 | scan-fw-9cc717ef20e35ab4 | complete |  |
| DS17-019 | scan-fw-311f43e4ce6623c9 | complete |  |
| DS17-020 | scan-fw-70960ed5154a66f4 | complete |  |
| DS17-021 | scan-fw-9842f56a548dce0a | complete |  |
| DS17-022 | scan-fw-e8dab4957e0fa180 | complete |  |
| DS17-023 | scan-fw-ae430bd782cebf78 | complete |  |
| DS17-024 | scan-fw-56d44c8114c78a9e | complete |  |
| DS17-025 | scan-fw-69d773d8350f9180 | complete |  |
| DS17-026 | scan-fw-ba074a45b06c3191 | complete |  |
| DS17-027 | scan-fw-2c2cda36cd4299ab | complete |  |
| DS17-028 | scan-fw-c7bfee3d5232d446 | complete |  |
| DS17-029 | scan-fw-bac72677cbb520e7 | complete |  |
| DS17-030 | scan-fw-57dc40c858e08df6 | complete |  |
| DS17-031 | scan-fw-4a25a326be928fc1 | complete |  |
| DS17-032 | scan-fw-a4acf9fc066cdde8 | complete |  |
| DS17-033 | scan-fw-faf66389f66f36c5 | complete |  |
| DS17-034 | scan-fw-21c4ca5e190aee20 | complete |  |
| DS17-035 | scan-fw-89a46fa06eca3443 | complete |  |
| DS17-036 | scan-fw-c60687ebcb2a8600 | complete |  |
| DS17-037 | scan-fw-f19be4ee7443fdb4 | complete |  |
| DS17-038 | scan-fw-de2ffd1076bbed84 | complete |  |
| DS17-039 | scan-fw-007104def3cc4fb2 | complete |  |
| DS17-040 | scan-fw-bb9c0b011134327c | complete |  |
| DS17-041 | scan-fw-d763b0938d2c73d8 | complete |  |
| DS17-042 | scan-fw-e1fe8a2e07277387 | complete |  |
| DS17-043 | scan-fw-21442a5061e1b639 | complete |  |
| DS17-044 | scan-fw-8e758884efd73e9f | complete |  |
| DS17-045 | scan-fw-6a03003ca0a65459 | complete |  |
| DS17-046 | scan-fw-9a65cd199e826d59 | complete |  |
| DS17-047 | scan-fw-82ee62657e29d639 | complete |  |
| DS17-048 | scan-fw-85e3bfb9e4cfcd46 | complete |  |
| DS17-049 | scan-fw-0faabd2537f4fafd | complete |  |
| DS17-050 | scan-fw-4a9c9e031c781aad | complete |  |
| DS17-051 | scan-fw-da79d96a4515ec30 | complete |  |
| DS18-001 | scan-fw-b299927c33fccc7a | complete |  |
| DS18-002 | scan-fw-4e13bed3c09cadff | complete |  |
| DS18-003 | scan-fw-c351a2d8f24c4455 | complete |  |
| DS18-004 | scan-fw-0014cc103687b490 | complete |  |
| DS18-005 | scan-fw-65e29ebee6f2a036 | complete |  |
| DS18-006 | scan-fw-3d984efc721d4bc6 | complete |  |
| DS18-007 | scan-fw-adcdd076e48cb2d8 | complete |  |
| DS18-008 | scan-fw-db6e1b4079322617 | complete |  |
| DS18-009 | scan-fw-1317eab1ab1dd263 | complete |  |
| DS18-010 | scan-fw-a7930b52d1b01dff | complete |  |
| DS18-011 | scan-fw-c5558b9d9ba7691e | complete |  |
| DS18-012 | scan-fw-7ce336d48ad3409b | complete |  |
| DS18-013 | scan-fw-b8ccfda98272ebe0 | complete |  |
| DS18-014 | scan-fw-5b1967c41451a971 | complete |  |
| DS18-015 | scan-fw-19235796dc3f06a2 | complete |  |
| DS18-016 | scan-fw-818f5d3b8ca6cbbe | complete |  |
| DS18-017 | scan-fw-fd728d9087fe35e2 | complete |  |
| DS18-018 | scan-fw-f5bf95a1570bece0 | complete |  |
| DS18-019 | scan-fw-e43a5641cecd1863 | complete |  |
| DS18-020 | scan-fw-a43bbffc6826cdc5 | complete |  |
| DS18-021 | scan-fw-f7f863971e4aa0b8 | complete |  |
| DS18-022 | scan-fw-f1a32cacd910c005 | complete |  |
| DS18-023 | scan-fw-8d37c3b59f1ca7d1 | complete |  |
| DS18-024 | scan-fw-d406a510f5473348 | complete |  |
| DS18-025 | scan-fw-c17fbfacad538641 | complete |  |
| DS18-026 | scan-fw-433aa9c47fea9cac | complete |  |
| DS18-027 | scan-fw-1d39b7f1cd0643aa | complete |  |
| DS18-028 | scan-fw-6c32f1804f9892a4 | complete |  |
| DS18-029 | scan-fw-4a5a8bdd0dd50f2d | complete |  |
| DS18-030 | scan-fw-317151cefa87e8ac | complete |  |
| DS18-031 | scan-fw-b68bdd7a7011688b | complete |  |
| DS18-032 | scan-fw-7c7196b249b7798a | complete |  |
| DS18-033 | scan-fw-713a66e116375e5d | complete |  |
| DS18-034 | scan-fw-4e603fa090384662 | complete |  |

## Input retry provenance

All 51 DS17 original input failures remain archived. The separately frozen iteration82 retries correct only protocol metadata loading. The coverage entries in summary.json record original status/error and both receipt paths. Pending or failed retries are not silently excluded from membership. No production changes or independent-validation claims.

## Paired comparisons on available membership

| Dataset | Arm | Baseline mean km | .25 mean km | .125 mean km | .5 mean km | .5 improved/regressed/tied versus .25 |
|---|---|---:|---:|---:|---:|---|
| DS16 | fitted-c | 5.964450 | 1.017307 | 1.048718 | 0.979007 | 41/22/0 |
| DS16 | zero-c | 6.355169 | 1.363228 | 1.407153 | 1.321051 | 39/24/0 |
| DS17 | fitted-c | 4.477043 | 0.864203 | 0.885273 | 0.819111 | 37/14/0 |
| DS17 | zero-c | 4.585465 | 1.417183 | 1.473566 | 1.326922 | 30/21/0 |
| DS18 | fitted-c | 4.422188 | 2.739331 | 2.757489 | 2.691656 | 18/16/0 |
| DS18 | zero-c | 4.618410 | 2.917558 | 3.034118 | 2.815838 | 23/11/0 |
| Pooled | fitted-c | 5.097594 | 1.360148 | 1.384951 | 1.317354 | 96/52/0 |
| Pooled | zero-c | 5.346353 | 1.738896 | 1.803801 | 1.666471 | 92/56/0 |

Sigma here is the satellite-specific slope prior in Hz/s, not timing sigma or the receiver hard60 bound. c=0 also locks the RF-time terms; other observations, banks, seeds and budgets are matched. These are conditional ablations sharing fitted-derived banks and seeds, not independent c-specific search pipelines.
