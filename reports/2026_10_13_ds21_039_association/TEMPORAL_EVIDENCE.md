# DS21-039 temporal continuity metadata audit

**Zero temporal edges result from the recorded scan inventory and the original reset rules.** Each original observation has a unique receiver/channel/visit/exact-RF family key. No pair reaches the 25 ms gap check. Dropping visit from the key alone would still yield zero edges: the shortest observed same-RX/channel/exact-RF revisit is **352.244 ms**. Extending continuity across visits is a new scientific assumption, not a graph bug fix.

Audit scope: original training metadata and already-recorded detector candidates only. No raw IQ access, GLRT kernel calls, orbit/model/likelihood calls, optimization, held projection/scoring, reference coordinates, RF collection, or production changes. The original fitted-c input manifest is the binding authority; this report performs no c-arm analysis.

## Bindings and method

Machine-readable bindings, exact per-channel gap quantiles, probe-start gap summaries, support hashes and source-module hashes are in [TEMPORAL_EVIDENCE.json](TEMPORAL_EVIDENCE.json). Input manifest SHA-256: `sha256:27bd4bbb567c6d16a819467f92924b813d5547928dc6c51bcaba743924917356`; original source SHA-256: `sha256:2631e731b3ef0b2ba13ee0ff2e6a689ec1a31c6fbb0f19047121eb214a03ac94`.

The pinned adapter reconstructs counter/UTC metadata. The unchanged `partition_channel_probes` uses seed **20261012**, whole **20 s** blocks, with held blocks **2, 6, 12**. Its assignments are hashed in the JSON. Of 7,136 original probes, **5,688** are training, **1,440** held, and **8** quarantined. Only training probes are projected. Their 2,844 visits produce 2,798 original winning windows. The winner policy is original highest margin, then rank, then candidate ID. Counts reproduce frozen diagnostics in all three views.

The native ambiguity-cell policy is replayed with arithmetic only using the bound `ALIAS_HZ = 1 / 4.4e-6` expression and the original margin/rank/ID tie break. All/low/high original-window and retained-native counts equal the original winner seed projection receipts: 2,798/3,714, 1,692/2,294, and 1,106/1,420. All report file-binding hashes and group accounting assertions passed. The prepared evidence digest is intentionally not regenerated: it includes trajectory bootstrap reconstruction outside this audit. Original source bytes, partition logic, public projection and metadata hashes provide the audit support.

## Why the graph has no edges

- `tools/joint_association_native.py:57` (`native_branch_inputs`) supplies `(receiver_id, channel, visit_index, actual_rf_hz)`. Every original probe has `probe_index=0` and `probe_start_ms=0`; there is exactly one probe per exact family key.
- `tools/ds21_joint.py:44` (`objective`) sets the maximum gap to `probe_ms / 1000 * 1.25`. The bound source has **20 ms** probes, so the original threshold is **25 ms**.
- `src/leo/analysis/joint_association_score.py:111` (`JointAssociationObjective`) constructs families using the original highest-margin winner's GLRT support-center timestamp. Native emission timestamps come separately from each selected native candidate's GLRT support center.
- `src/leo/analysis/joint_association_graph.py:20` (`continuity_families`) groups keys, sorts times, and splits gaps greater than the threshold or non-increasing times. Here all keys are singleton before either reset check: **zero gap resets and zero coincident resets**.
- `tools/ds21_039_association_diagnostic.py:75` (`native_input`) rejects non-singleton families for its conditional diagnostic. It does not create singleton families. The native graph can represent multi-observation histories when capture support exists. Source hashes in the JSON are the authority for these local line references.

| View | Original windows | Unique exact keys | Families | Temporal edges | Native candidates |
|---|---:|---:|---:|---:|---:|
| All CH1–8 | 2,798 | 2,798 | 2,798 | 0 | 3,714 |
| Low CH1–4 | 1,692 | 1,692 | 1,692 | 0 | 2,294 |
| High CH5–8 | 1,106 | 1,106 | 1,106 | 0 | 1,420 |

## Visit/revisit gaps

Both receivers have one recorded exact RF per channel: CH1–8 are **10.7096875, 10.9596875, 11.2096875, 11.4596875, 11.7096875, 11.9596875, 12.2096875, 12.4596875 GHz**. Reported RF values inherit the recorded LNB hypothesis; they do not identify a transmitter.

The table describes consecutive retained original winning windows at the same RX/channel/exact RF across visits. Gaps use GLRT winner support centers, in seconds. Gaps can span missing detections, held/quarantined blocks, or omitted original visits; they are descriptive and do not create cross-partition links. Thresholds **0.5/1/2/5 s** were requested for descriptive accounting and were not used for model choice. JSON also contains p25/p75 and probe-start gaps for every training probe, including probes without passing windows.

| RX | CH | Training probes | Windows | Native | Min s | Median s | p95 s | Max s | ≤0.5 s | ≤1 s | ≤2 s | ≤5 s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1 | 374 | 217 | 274 | 0.352 | 0.356 | 2.481 | 25.560 | 121 | 125 | 202 | 209 |
| 0 | 2 | 379 | 305 | 433 | 0.353 | 0.356 | 1.720 | 21.281 | 188 | 189 | 296 | 300 |
| 0 | 3 | 351 | 282 | 400 | 0.353 | 0.356 | 1.773 | 21.636 | 169 | 171 | 272 | 277 |
| 0 | 4 | 347 | 265 | 392 | 0.353 | 0.356 | 1.775 | 28.374 | 156 | 158 | 253 | 259 |
| 0 | 5 | 340 | 166 | 228 | 0.353 | 0.356 | 5.183 | 42.218 | 89 | 93 | 148 | 156 |
| 0 | 6 | 411 | 257 | 366 | 0.352 | 0.356 | 1.775 | 30.161 | 158 | 159 | 246 | 250 |
| 0 | 7 | 372 | 194 | 248 | 0.353 | 0.356 | 3.691 | 41.870 | 103 | 106 | 172 | 184 |
| 0 | 8 | 270 | 105 | 135 | 0.353 | 0.356 | 4.156 | 98.671 | 56 | 58 | 90 | 99 |
| 1 | 1 | 374 | 107 | 122 | 0.353 | 0.533 | 15.169 | 34.778 | 53 | 56 | 91 | 98 |
| 1 | 2 | 379 | 215 | 290 | 0.352 | 0.356 | 1.771 | 76.297 | 123 | 131 | 208 | 210 |
| 1 | 3 | 351 | 166 | 211 | 0.353 | 0.356 | 2.130 | 38.324 | 97 | 97 | 153 | 158 |
| 1 | 4 | 347 | 135 | 172 | 0.353 | 0.356 | 2.252 | 132.352 | 80 | 80 | 124 | 131 |
| 1 | 5 | 340 | 90 | 104 | 0.353 | 0.711 | 7.098 | 55.714 | 43 | 47 | 78 | 82 |
| 1 | 6 | 411 | 160 | 187 | 0.353 | 0.356 | 4.115 | 49.685 | 92 | 93 | 144 | 151 |
| 1 | 7 | 372 | 114 | 131 | 0.353 | 0.356 | 2.129 | 72.738 | 61 | 63 | 103 | 108 |
| 1 | 8 | 270 | 20 | 21 | 0.353 | 0.356 | 31.760 | 71.679 | 11 | 11 | 17 | 17 |

Across all 16 groups there are **2,782** consecutive winner revisits: minimum **0.352244 s**, p25 **0.354669 s**, median **0.356002 s**, p75 **1.418927 s**, p95 **2.134633 s**, maximum **132.351829 s**. Counts ≤0.5/1/2/5 s are **1,600 / 1,637 / 2,597 / 2,689**. **Zero** are within 25 ms. Changing graph time from original winner centers to native centers cannot bridge the roughly 327 ms minimum excess over the existing threshold.

## Candidate identity, repeated support, and overlap

There are **7,622** distinct passing candidate IDs, of which **3,714** are retained native cell winners and **3,908** are discarded alternatives. IDs bind capture/visit/RX/probe and rank plus analysis identity. They describe detector hypotheses; they do not persist as an emitter identity across visits.

The passing inventory includes **982 extra candidates** with exactly duplicated receive-support start/center/end and CFO within their original window. They retain different rank-derived candidate IDs. After cell selection, the **983 within-window pairs of retained native alternatives all overlap** in receive support. They are competing hypotheses from the same 20 ms probe, not independent repeated observations. There are **zero same-RX cross-window support overlaps**, and no duplicate original `(visit, RX, probe_index)` identities.

**906** retained candidates have native GLRT centers different from the original highest-margin winner center. Offsets range from **−0.977592 ms to +0.970506 ms**; median is zero. Thus original window identity, original window time, and native candidate identity/time must remain distinct in any later test.

Recorded candidate fields contain rank, integer/fractional epoch, native CFO, exact/control score, margin, and gate result. They contain **no emitter ID, decoded frame ID, persistent pilot/sequence ID, or transmitter-continuity attestation**. Continuous device counters and qualified UTC attest receiver timing and support placement. They do not attest that two revisits observe the same emitter. Matching RX/channel/RF, nearby times, matching ambiguity cells, or high detector margin cannot supply that missing identity.

## Smallest defensible next step

**Independent same-emitter continuity evidence is absent in these bound metadata.** The timestamps provide potential cross-visit link hypotheses, but no capture-backed scientific sticky-history fit is justified from metadata alone. Preserve the current graph and frozen receipts.

A future temporal test needs an explicitly prespecified independent frame/pilot continuity criterion, or an explicitly labelled sensitivity contrast of the new continuity assumption. Fix its reset/gap/retune and overlap rules before fitting; match original training blocks, observation/native candidate sets, other priors and search budgets. Allow transmitter switches/clutter and keep native receive times exact. Do not infer a temporal prior from the descriptive threshold counts. Compare frequency-fit/score effects separately from reference-only localization accuracy; a better in-sample score cannot establish better position accuracy. Any future control retains fitted c in both conditions, as requested; historical zero-c artifacts remain unchanged.

No temporal model, prior, fit or new RF collection was implemented by this audit.
