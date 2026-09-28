# Joint location / clock prototype

Status: implementation, bounded offline replay, tests, and independent SOL review complete. No production changes or new RF collection.

## Outcome

**Shared three-scan location selection improves both difficult examples; clock regularization adds no consistent benefit.** All four groups select good locations with no timing penalty. This is a promising integration direction, not proof that the problematic scans' satellite associations are repaired or that performance improves on every individual scan.

| Group | Independent scan locations, mean / worst error km | Shared location, no clock penalty, error km |
|---|---:|---:|
| 08:40–09:00 (known failure) | 49.58 / 123.53 | 5.00 |
| 12:40–13:00 (known failure) | 239.16 / 706.76 | 3.99 |
| 02:00–02:20 (random validation group) | 6.40 / 9.41 | 5.79 |
| 03:00–03:20 (random test group) | 7.72 / 10.85 | 6.53 |

Each shared result is **one estimate per group**, not three independent successes. Independent controls use the same shared proposal inventory and training-only selection, isolating the common-location constraint. Full fixed-model, clock-only, competing-hypothesis, and weighting comparisons are in `comparison.md`.

## Question

Can shared location proposals, constrained per-scan timing, and a common stationary-receiver location across three scans improve on independent ambiguous assignments?

The preceding soft-assignment experiment recovered four large Reno errors through proposal sharing, not soft weights. Two difficult examples remained (08:50 and 12:50 UTC). This experiment separates candidate sharing, timing regularization, and multi-scan location pooling.

## Frozen evaluation scope

- Diagnostic triples: 08:40–09:00 and 12:40–13:00 UTC on 2026-09-26. Deliberately includes the two remaining failures.
- Additional whole triples were selected using metadata only, before examining their location outcomes: Python `random.Random(20260926).sample(['G0200','G0230','G0300'], 2)` selects G0200 for validation and G0300 for test. No tuning on either group. Exact assignments and the unused candidate group are in `group_manifest.json`.
- Each group receives the union of its historical Sacramento/Reno winning locations. No reference coordinates are used to construct new proposals; no local grid refinement is included.
- Models: free per-track timing; penalties 100, 1,000, and 10,000 Hz²/s² around a scan clock; hard shared timing as a stress-test control. Clocks and satellite identities may differ between scans.
- Primary aggregation gives each scan equal weight, using occupied-second weights within scans. Duration-pooled aggregation is a sensitivity check. Missing tracks remain in the fixed denominator at the 800 Hz cap.
- Keep complete competing location/identity/timing hypotheses. Do not average distant coordinates or require identical satellites in different scans.

## Interpretation limits

These are **conditional retrospective proposal-reranking experiments**, not independent end-to-end acquisition validation. Published proposal seeds were selected using historical evaluation observations; later training-only reranking cannot remove that leakage. The inherited within-track observation split is also not an independent whole-group holdout. Random assignment of additional whole scan groups avoids deliberately choosing those groups by location error, but two small nearby groups do not establish broad generalization. Report groups separately and do not count a common location repeated for three scans as three independent successes.

The diagnostic triples include one scan after each problematic scan (10 minutes of look-ahead). These are offline batch estimates, not demonstrated zero-latency online fixes. A live integration would need a causal trailing window or explicitly delayed/revised results, and a receiver-stationarity check.

A production-quality next step would generate proposals without access to reserved observations and assess a frozen policy on randomized independent receiver-session groups, with an explicit unresolved outcome for materially competing locations. This prototype does not alter persisted contracts or the live scanner.

Top-five retention is diagnostic bookkeeping, not calibrated posterior probabilities or an abstention policy. No unresolved-rate claim is made. The prototype retains per-track constant frequency offsets; shared channel/oscillator drift models are not implemented in this iteration. Satellite identity correctness also lacks independent ground-truth labels.

## Results and verification

The replay covered 12 scans in four frozen triples and five fixed timing models. Single-worker numerical replay took 1,060.9 seconds (17.7 minutes), without new collection. All 24 published Sacramento/Reno sites reproduced their original scores within 5.51e-12 Hz.

The new suite passes **21 tests**; the combined new and previous prototype suites pass **29 tests**. Tests cover fixed denominators, missing evidence, duration-weighted clocks, independent per-scan clocks, regularized ranking, equal-scan versus pooled weighting, complete hypotheses, reserved/reference isolation, compact-profile parity, public-store missing/tamper behavior, and summary integrity. A generic research-module import collision found during combined collection was fixed in the new test harness; combined collection now passes.

After numerical replay, the runner's adapter was refactored to use the public read-only `AdaptiveTlePositionStoreV2` port and a local geometry adapter instead of constructed storage paths and private CLI helpers. **The full numerical replay was not repeated after this adapter-only refactor.** All 12 public-store document hashes match the recorded inputs, and all 21 proposal receiver ECEF/up vectors match the original CLI oracle bit-for-bit (maximum difference zero). The numerical core is unchanged. `adapter_verification.json` records this equivalence and binds the results to the current runner; it does not claim the current runner itself produced the original replay.

SHA-256 provenance:

- Executed runner: `1ef94f7357aadd6d7b8a4238b2c72af002342624e627f6eda1dbbd5f80043bb6`.
- Post-run adapter-refactored runner: `d5a7ea63496aafa0b84bb5a981e3cb1354826600161038bcd6366765697dbda6`.
- Unchanged numerical core: `c1e706fcbb8e5bdedb65b1cdbf10d963589876c3e5db20fd9eaa3e85dfdf77a0`.
- Results: `cd024ebbef211d80e314c4f6388e5dc8f83088e3b4f7ca8a90b657d9ec004234`.
- Frozen group manifest: `c05cea8084fbc01dd5c94d59b5f1ea269723a31308a9f768039e6f92b188a659`.

Commands from the repository root:

```bash
sudo -n -u leo /opt/leo-tracker/current-api/.venv/bin/python -m pytest -q -p no:cacheprovider reports/2026_09_26_joint_location_prototype reports/2026_09_26_association_soft_prototype/test_prototype.py reports/2026_09_26_association_soft_prototype/test_stability.py
python3 reports/2026_09_26_joint_location_prototype/summarize_results.py reports/2026_09_26_joint_location_prototype/results.json
```

Published baselines, read only after the groups and policies were frozen (km):

| Group | UTC scan | Sacramento | Reno |
|---|---|---:|---:|
| D0850 | 08:40 | 6.72 | 5.00 |
| D0850 | 08:50 | 128.93 | 123.53 |
| D0850 | 09:00 | 18.50 | 42.65 |
| D1250 | 12:40 | 6.72 | 9.41 |
| D1250 | 12:50 | 13.44 | 706.76 |
| D1250 | 13:00 | 13.54 | 3.99 |
| G0200 | 02:00 | 13.96 | 9.41 |
| G0200 | 02:10 | 5.79 | 3.99 |
| G0200 | 02:20 | 5.79 | 3.99 |
| G0300 | 03:00 | 6.53 | 10.85 |
| G0300 | 03:10 | 5.79 | 18.91 |
| G0300 | 03:20 | 6.53 | 5.00 |

Thus the additional groups happen to be good-location controls; they cannot establish performance on unseen catastrophic failures.

### Why the 08:50 case improves

At lambda zero, independent selection still chooses the 123.53 km-error candidate for 08:50. Joint selection chooses the 5.00 km-error candidate. Its advantage is cross-scan consistency, not a better fit to the problematic scan:

| Candidate's reference error | 08:40 training RMS | 08:50 training RMS | 09:00 training RMS | Equal-scan group RMS |
|---|---:|---:|---:|---:|
| 5.00 km | 214.97 | 443.59 | 113.78 | 292.08 |
| 123.53 km | 515.12 | 268.05 | 640.43 | 499.12 |

All scores are capped, occupied-second-weighted Hz; group RMS uses equal scan weights. The isolated bad scan prefers the wrong site strongly, but its neighboring scans do not support that site. This is not evidence that the 08:50 satellite associations themselves became correct: their fit remains poor at the group-selected location. Keep scan-specific inconsistency visible instead of presenting a good group location as repaired RF evidence.

### The 12:50 case and weighting sensitivity

The independent training-only control still selects the 706.76 km-error site. Common-location selection without clock regularization chooses 3.99 km error; penalties 100, 1,000, and 10,000 choose the same site. Hard shared timing worsens it to 13.54 km. The bad scan's own training RMS rises from 180.07 Hz at its isolated winner to 270.06 Hz at the shared winner, again showing that the neighboring evidence overrules an inconsistent scan rather than repairing that scan's associations.

Equal scan weighting matters for the fine result: duration-pooled lambda-zero and lambda-100 choose the 13.44 km-error site, versus 3.99 km under the predeclared primary weighting. Both avoid the catastrophic failure, but precision is aggregation-sensitive. Do not choose weights retrospectively to optimize reference error.

### Timing without a common location

The read-only summary also reranks each scan independently within each frozen timing model using the already-computed per-scan penalized training objectives. The lambda-zero locations reproduce the stored independent controls. None of the finite penalties resolves either isolated catastrophic case. Hard shared timing resolves the isolated 12:50 failure, but still leaves a roughly 129 km error in the 08:50 group. This is not a general-purpose fix, and forcing shared timing is inferior to the unregularized common-location result on both diagnostic groups.

### Additional randomly selected groups

G0200's joint estimate has 5.79 km error for all five timing models, versus 6.40 km mean / 9.41 km maximum for independent lambda-zero locations. This is a modest group-level improvement, not improvement on every scan: an independently selected 3.99 km site is better than the shared 5.79 km site. Duration pooling selects 3.99 km under the three lowest penalties, further illustrating fine-location sensitivity. No model was changed after observing this validation group.

G0300's joint estimate has 6.53 km error for lambda zero, 100, and 1,000, versus 7.72 km mean / 10.85 km maximum independently. Lambda 10,000 and hard shared timing worsen the primary joint estimate to 10.85 km. The frozen test group therefore supplies no reason to introduce stronger clock coupling. Duration weighting changes the high-penalty winners, again limiting precision claims.

## Integration recommendation

The next implementation candidate is shared proposal search plus a stationary-receiver, multi-scan location score, keeping scan-specific identities and nuisance parameters free initially. Preserve per-scan disagreement and alternative complete hypotheses in the diagnostic output. Do not promote hard shared timing, infer confidence from a raw Hz gap, or silently replace an inconsistent scan's evidence with a confident group result.

Before live use: generate proposals from training-only evidence; evaluate a causal trailing window on more randomized independent groups; test receiver movement and bad/missing scans; and calibrate an unresolved outcome. Existing production contracts and scanner behavior are unchanged.
