# Protected orbital-consistency track merge experiment

The first continuous-curve prototype can worsen localization by changing initialization rather than by changing the recorded observations. This iteration preserves the original selected discovery tracks and tests whether a joined trajectory agrees with their orbital candidate matches before replacing them. It repairs the two identified candidate-loss mechanisms in the exposed DS20 diagnostic. Full positioning improvement has not yet been demonstrated.

This experiment follows the [continuous track merge study](../2026_10_12_continuous_track_merge/README.md), whose complete proposal census includes all 18 DS20 and 63 DS16 recordings. The same sealed membership and random whole-recording development/validation roles apply. DS15 still lacks an authoritative manifest; no other dataset is substituted for it. Initial full replays use the same two development recordings as the preceding experiment, not an independently held-out sample.

## Two distinct ways that discovery candidates disappear

On DS20 `fast-014c72ff95ab599c51ba3b3ec9b92cb8`, guarded replacement retains 17 of the 24 original selected bootstrap proposals. At the previously exposed grid point east −80 km, north −80 km:

* The unmerged CH1 RX0 segment from 14.56 to 48.96 seconds supplies candidate 62501 with 56.3 Hz sampled shape RMS. Longer joined proposals displace it under the longest-12-per-receiver quota. The resulting selected replacement set has no observations from this original segment.
* A CH4 RX1 segment from 192.80 to 214.80 seconds supplies candidate 69466 with 75.5 Hz sampled shape RMS. A guarded join adds an earlier segment, extending support to 27 windows over 40.44 seconds. The joined bootstrap prefers candidate 54102 with 193.7 Hz sampled shape RMS, removing 69466 from its discovered bank.

The first mechanism is competition under a quota; the second is a changed preferred orbital shape. They require different controls. Candidate numbers here identify numerical hypotheses, not established transmitting satellites. This grid point is an exposed posthoc diagnostic near the evaluation reference. It never seeds or restricts the full geographic searches.

![CH4 orbital residuals and candidate preservation](candidate-substitution.png)

The upper panels profile each candidate's timing over the existing −20 to +20 second grid and one constant over the entire joined arc, using all 27 retained windows. Candidate 69466 gives 432.4 Hz RMS and candidate 54102 gives 177.4 Hz RMS. These differ from the bootstrap's 12-sample statistics. Both residual trajectories have visible structure: a smooth measured CFO curve does not establish a correct orbital assignment or noise-only orbital residuals. The bootstrap removes a constant while selecting orbital shapes and estimates shared receiver drift afterwards, so calibration ordering remains an additional mechanism to investigate.

The lower panel separates protection of original proposals from the orbital-agreement gate. Original-candidate preservation plus a shape-RMS limit retains 62501 but still substitutes 54102 for 69466. Enabling orbital agreement retains both original candidates and excludes both substitutions. [Plot receipt](candidate-substitution.json) and [point diagnostics](point-diagnosis.json) record these exposed comparisons.

## A conservative candidate-preserving merge rule

The new analyzer profiles the same pool of original selected tracks and guarded joined proposals at each trial position. DS20's initial example has 24 original proposals and seven additional joined proposals; the DS16 example has 24 originals and four additions. All conditions use the same pool, 12 samples per proposal, existing timing grid, and five-second total bootstrap budget.

A join can replace original proposals only when it contains every observation of each overlapping selected parent, has a qualified orbital match, and has sampled shape RMS no greater than the larger of 200 Hz and 1.25 times the worst parent RMS. Orbital-consistency mode additionally requires its preferred catalogue candidate to agree with every selected parent's candidate. Unrelated original proposals always remain selected. Orphan joins and partial-parent replacements are rejected, so an added long proposal cannot evict an unrelated original via the quota.

Every accepted replacement rechecks the discovery bank after recomputing the initializer. Consistent mode requires exact equality with the bank discovered by the original selected proposals at that trial position. This condition deliberately preserves alternatives; it does not assert that the original candidate identities are correct. Timing and receiver-line initialization may still change. It can also prevent a longer arc from correcting a mistaken short-arc assignment, which requires a later alternative-hypothesis comparison rather than silent replacement.

The fixed modes are:

| Mode | Common proposal pool | Selected proposal rule |
|---|---|---|
| Baseline | Original plus guarded joins | Recompute using original selected proposals |
| Shape ablation | Same pool | Protected replacements with shape-RMS limit |
| Consistent | Same pool | Protected replacements with shape-RMS limit and candidate agreement |

At the prior origin, all three modes discover the same 11 candidates; shape and consistent each accept two joins. At the exposed −80/−80 km point, baseline and consistent retain the same 13 candidates, while shape mode substitutes 54102 for 69466. Consistent accepts two joins there, rejects two for increased orbital RMS, rejects two orphan proposals, and rejects the CH4 candidate disagreement. Thus the candidate guard is active and does not reject every join.

The numerical analyzer uses contracts and an injected bootstrap port. The B7 and Hard60 runners default to their original bootstrap behavior; using a custom initializer requires an explicit configuration binding. No production defaults or hardware settings are changed.

## Matched positioning and remaining work

Full default B7 replays are running for the first DS20 development example in all three modes and for the first DS16 example in consistent mode. They preserve original observations, RF frequencies, timing, initial satellite bank, priors, 400-point search budget, and per-stage fitting budgets. Each mode includes the existing conditional `c = 0` versus fitted-`c` final comparison, sharing fitted-`c` discovery/calibration and the final bank within that mode. Geographic evaluation references enter only after complete numerical outputs are sealed. Frequency fit and position accuracy must be assessed separately.

The prototype and affected components pass 32 tests, including native numerical parity, injected discontinuities, protected-parent replacement, differing orbital candidates, rejection of partial/orphan joins, original-baseline numerical reproduction, checkpoint resumption, and forwarding of the explicitly bound bootstrap through B7. Scientific fixtures remain unchanged.

Reproduction uses the new [study tool](../../tools/continuous_merge_consistency_study.py). Existing numerical evidence remains in the original study worktree; large derived inputs and checkpoint data are Git-ignored. Use the scientific NumPy/SciPy environment, one BLAS thread, and the existing compiled native orbit extension:

```bash
PYTHONPATH=src:tools python tools/continuous_merge_consistency_study.py freeze DS20 SESSION_ID
PYTHONPATH=src:tools python tools/continuous_merge_consistency_study.py diagnose DS20 SESSION_ID
PYTHONPATH=src:tools python tools/continuous_merge_consistency_study.py execute DS20 SESSION_ID --mode consistent --maximum-seconds 420
```

The tool freezes input and source hashes and refuses to overwrite a protocol. Repeating `execute` resumes immutable completed checkpoint stages after a yielded worker slice. Run baseline and shape with the same protocol, then call `evaluate` only after the desired matched conditions complete. No new RF collection is needed. Broader DS20/DS16 positioning comparisons, calibration-ordering diagnostics, sensitivity checks, and authoritative DS15 inclusion remain required before claiming that this merge algorithm improves results.
