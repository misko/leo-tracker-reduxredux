# Causal 72-hour catalogue and age-prior prototype

The 72-hour fallback recovers two strongly preferred diagnostic identities that the 48-hour catalogue excluded. Properly normalizing nuisance uncertainty and adding a mild recency preference does not remove either identity. One candidate passes the checked local inclusion gates; the other still fails and must remain unassociated.

This is a bounded research test on **20 previously audited residual sources, 1,546 native points, and 16 DS26/DS27 scans**, followed by local position probes of the two newly nominated older families. It is **not a fresh full-dataset ALGO04 run or a deployment**. The residual cohort and fixed radio corrections come from the prior ALGO05 residual investigation. That investigation reconstructed inherited baseline normal equations at published endpoints; it did not reconstruct every newly accepted family in a joint ALGO05 posterior. The two position-probe cases have no intervening selected recovery and their published endpoints equal the exactly replayed baseline. No GPS or later TLE enters nomination or fitting.

## Does a preference for newer TLEs make sense?

Yes, as a carefully defined model-reliability assumption. But **a broader uncertainty prior must already pay for its flexibility**. Ranking solely by optimized RMS, or only a squared prior pull, can favor broader models. For a normalized Gaussian predictive model:

```text
−2 log p(y | satellite) = residualᵀ Σ⁻¹ residual + log det Σ + N log(2π)
```

Increasing covariance can reduce the first term while increasing the determinant term. Phase and alias uncertainty should likewise be integrated with normalized priors:

```text
Z_satellite = Σ_alias ∫ p(y | satellite, phase, nuisance, alias)
                         p(phase, nuisance | causal TLE history, age) p(alias) dphase dnuisance

comparison_score = −2 log Z_satellite − 2 log prior_weight_satellite
```

The existing production `phase_mixture_evidence` already includes normalized phase weights and the Gaussian orbital determinant penalty. The earlier diagnostic `profile_rate` also included constant/rate determinant terms, but selected a best phase plus a squared phase pull rather than integrating the phase distribution. The new scoring probe explicitly integrates that missing phase uncertainty. It does not claim production previously omitted all complexity penalties.

Broader priors can legitimately improve evidence when the data require a large correction. The penalty is not a rule that a narrow prior must always win. If the data are completely insensitive to a parameter, integrating a normalized prior should not penalize it merely for existing; the numerical tests include this case.

Age is also not a satellite-transmission prior. A satellite with an old catalogue entry is not necessarily less likely to be emitting. A separate recency preference can represent additional distrust of stale-model predictions, but risks double-counting uncertainty already captured by physical priors. It should be calibrated on independent data before becoming an operational rule.

For each satellite we use its latest eligible causal element, not whichever historical TLE best fits the measured curve. Both element epoch and archive availability must precede the scan cutoff.

## Controlled scoring experiment

All four variants use the same observations, frozen receiver calibration and published inferred positions, fixed native aliases as mixture hypotheses, and the same matched candidate union across c arms. No points are discarded to obtain the comparison.

| Variant | Catalogue eligibility | Phase prior | Additional recency term |
| --- | --- | --- | --- |
| 48_fixed | At most 48 h | Gaussian scale 5 s | None |
| 72_fixed | At most 72 h | Gaussian scale 5 s | None |
| 72_age_scaled | At most 72 h | Scale `5 s × max(1, age_h / 24)` | None |
| 72_age_scaled_recency24 | At most 72 h | Same age-scaled prior | Relative weight `2^(−max(0, age_h − 48) / 24)` |

The corresponding extra −2 log score is `2 ln(2) × max(0, age_h − 48) / 24`. It is 0.153 for a 50.65-hour TLE and 0.238 for a 52.12-hour TLE. This is a modest preference, not a replacement hard cutoff. Sensitivity runs use 12-, 24-, and 48-hour half-lives. **All twenty winners remain unchanged under those three choices in both c arms.** The preference is applied once per candidate/source in this experiment. A future joined-family implementation must apply it once per satellite family, not repeatedly per point or fragment.

The scoring probe has a constant uncertainty of 300 Hz and a rate uncertainty of 0.5 Hz/s, analytically integrated, with 150 Hz point noise. These are predeclared diagnostic assumptions inherited from the earlier nuisance comparison, not freshly learned ALGO04 uncertainty. The rate belongs to the entire contiguous source; it is not a per-point correction or a recalibrated receiver rate. The probe does not include the full model's three physical orbital modes or shared receiver covariance; those are restored in the subsequent two-case position experiment.

Phase support is held at ±15 s for every variant, so age expansion is not confounded with a larger phase search. Gaussian phase priors are normalized over this declared box. Alias hypotheses −4 through +4 have equal prior weight and one alias applies to a whole curve, not an independent alias per point. Invisible phase components receive zero likelihood without their prior mass being renormalized away. A uniform-clutter score is exported as a diagnostic alternative, but beating clutter is not an acceptance gate.

The parent study screened complete causal catalogues of roughly eleven thousand elements. This experiment reuses its union of coarse finalists across models, phase limits and c arms: **218 source-specific candidate entries**, producing **1,734 candidate × policy × arm scores**. Every retained candidate receives full-native-point integration. This is not an exhaustive continuous fit of every catalogue object; uniqueness remains conditional on that shortlist.

Halving the diagnostic phase-grid step from 0.1 to 0.05 seconds preserves every winner and runner-up in all 160 source × policy × c-arm cells. The largest winning-score change is 2.214, so this is ranking stability, not a claim that all diagnostic evidence values meet the production quadrature tolerance. The subsequent physical-model local probes use the separate stricter score/gradient audit, including a 0.025-second grid.

Three reproducible random 12-second group holdouts, with 2-second guards, evaluate conditional predictions. Training alone determines phase/offset/rate posterior weights in each fold; held scores integrate that training posterior. Candidate nomination and the inherited radio model were prepared earlier, so these are **conditional stability checks, not a new blind identity validation**. Both new older identities win all three training-group comparisons in both c arms.

![Twenty-source comparison](twenty_source_comparison.png)

## Changes in candidate identity

| Source | Points | Best 48 h identity | Best 72 h identity | TLE age | Fitted-c RMS, 48 h → 72 h with recency | Residual screen |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| DS26-0062 RX1 CH3 | 86 | 65283 | **67821** | 50.65 h | 1,130.4 → **63.2 Hz** | Pass |
| DS26-0068 RX1 CH7 | 91 | 63573 | **58538** | 52.12 h | 1,175.8 → **119.3 Hz** | Fail: structured residual |

The other **18 sources retain their leading identities**. They are not thereby accepted: many still fail residual adequacy, need their existing shared-family model, or remain ambiguous. In particular, the DS26-0134 phase-bound problem is deliberately not solved by this experiment because ±15 s remains fixed.

The 72-hour recency-weighted winner beats its runner-up by approximately 6,524 −2-log-score units for 0062 and 647 for 0068 in fitted-c. These margins are diagnostic under the declared covariance and shortlist; they are not calibrated identity probabilities. Strong preference does not make the 0068 residual acceptable.

![Native curves and residuals for the two age-excluded identities](older_candidate_curves.png)

The curve figure uses native CFO on the saved unwrapped branch. Predictions include the frozen receiver correction and fitted source nuisance terms. Full raw GLRT-score context, polynomial orders, graph joins, retrospective TLE checks and 20-second zooms remain available in the [parent investigation](../2026_10_31_find_glrt_association/README.md) and its [track atlas](../2026_10_31_find_glrt_association/track_atlas.md). This experiment reuses those audits rather than presenting them as new measurements.

## Full physical-model local position tests

The two older nominees were appended to each scan's in-memory causal bank after propagation and timestamp checks. Incumbent candidate indices, owners, points, weights and priors are preserved. The numerical new-family likelihood integrates the original shared receiver covariance and three physical orbital modes. It does not give the target its own freely fitted receiver calibration or arbitrary rate.

Neither appended family has earlier-element history in the original prepared prior bank. Therefore the original physical model uses its existing **1-second phase-scale fallback**, zero phase mean, and unavailable-history orbital scales. The age-scaled sensitivity multiplies that actual phase scale by `max(1, age_h / 24)`, giving 2.111 s for 67821 and 2.171 s for 58538. This is distinct from the 5-second diagnostic phase scale above. Retrieving genuine older causal history is needed before treating either fallback policy as calibrated.

Controls and candidates have matched local search budgets: the original published endpoint per c arm, the configured 25 × 25 km box, up to three phase-refresh rounds, and 100 objective evaluations per round. These are conditional local refits; they do not repeat global association search from the regional center. They cannot establish global optimality. The recency term is constant for a fixed satellite and therefore changes its model-selection score, **not its conditional position optimum**; rerunning the optimizer with that same constant would be redundant.

GPS is used only by `render.py`, after the saved inference results, to compute great-circle errors at the approved evaluation site.

| Scan | Local model | c = 0 error | Fitted-c error | Both-arm checked inclusion gates |
| --- | --- | ---: | ---: | --- |
| DS26-0062 | Matched control | 660.2 m | 636.0 m | Pass |
| DS26-0062 | 72 h, original physical prior | **635.2 m** | **614.7 m** | **Pass** |
| DS26-0062 | 72 h, age-scaled phase prior | 656.8 m | 635.5 m | Pass |
| DS26-0068 | Matched control | 447.4 m | 297.4 m | Pass |
| DS26-0068 | 72 h, original physical prior | 599.0 m | 367.7 m | **Fail; diagnostic endpoint only** |
| DS26-0068 | 72 h, age-scaled phase prior | 537.6 m | 344.7 m | **Fail; diagnostic endpoint only** |

![Matched local position results](local_position_error.png)

For **0062**, both prior variants retain every existing owner, pass exact incumbent-orbit checks, target residual checks, continuous-phase checks, phase convergence, phase-interior checks, and a 0.1/0.05/0.025-second phase-integration score/gradient audit. The original physical prior gives about 63.2 Hz target RMS with phase −7.8 s. Its lag-one residual correlation is about 0.295, within the existing gate; passing this heuristic is not a proof of independent white noise.

If separately qualified for production, its **86 additional unique points** would increase scan coverage from **3,212 / 5,027 = 63.89%** to **3,298 / 5,027 = 65.61%**. This is potential coverage, not a changed production count. There is no independent blind catalogue nomination in this experiment and no production ownership was written.

The roughly 21 m fitted-c gain under the original prior is small. Widening the phase prior preserves the 63 Hz frequency fit but almost removes the position gain. Do not choose the tighter prior because its error happens to be smaller on this known site: its 1-second fallback is already about 7.8 scale units from the fitted phase, and lacks satellite-specific history. A more flexible fit can absorb signal that would otherwise constrain position.

For **0068**, the physical-model target residual has lag-one correlation around 0.54 and maximum step statistic around 5.1–5.2. It fails the residual checks even with continuous phase refinement. The 0.1-second integration grid also fails the score/gradient audit. In fitted-c, the original-prior attempt loses/changes 28 incumbent owners; the age-scaled attempt also changes ownership and reaches its optimizer limit. These are reasons to reject inclusion independent of evaluation GPS. Refining phase quadrature alone would not fix the remaining residual/ownership failures.

The failed 0068 position endpoints are explicitly shown so that a better satellite explanation is not confused with a successful localization improvement. Its accepted baseline remains unchanged.

## Recommendation

1. Continue with a general **48–72-hour causal fallback** for unmatched curved sources, selecting the latest available element per satellite. Keep the normal recent bank and preserve the option of no match.
2. Use the existing normalized predictive evidence, with proper phase and orbital uncertainty integration, as the main flexibility penalty. Do not replace it with RMS ranking or count a prior penalty repeatedly for every GLRT point.
3. Keep the tested recency preference as a sensitivity control for now. It changes none of these winners, so these data do not calibrate its half-life or demonstrate added protection against wrong identities. Larger independent evaluations must test that claim.
4. Fetch genuine causal history for newly admitted older satellites and repeat independent grouped nomination plus exact additive replay. Compare the recent control and fallback with matched c arms, including all rejected sources and incumbent regressions. Do not promote the ad hoc phase-width multiplier based on this two-case position result.
5. Advance 0062 as a provisional recovery; continue debugging 0068's structured residual rather than relaxing its gate. Dataset-wide evaluation and promotion remain outstanding.

## Reproduction and checks

No production code, persisted public contract, scientific golden fixture, RF recording, or QNAP path was changed. The prior causal72 export and native observations are read-only inputs. Numerical code runs in `/srv/bulk/leo-dev/fast-algo02-production-v1` at revision `a9a340309a004d31f133e59662c24414a6a71b22`; source hashes are recorded in the artifact manifest. The research adapter lives in this report directory.

From that numerical worktree, with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tools`:

```bash
.venv/bin/python /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_causal72_age_prior/test_evidence.py
.venv/bin/python /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_causal72_age_prior/run.py --workers 4
.venv/bin/python /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_causal72_age_prior/audit.py
.venv/bin/python /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_causal72_age_prior/local_inclusion.py DS26-0062
.venv/bin/python /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_causal72_age_prior/local_inclusion.py DS26-0068
.venv/bin/python /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_causal72_age_prior/render.py
```

The numerical tests check phase-prior normalization, recency odds, Gaussian integration against a dense covariance calculation, constrained versus unidentified parameter penalties, invisible phase mass, and invalid inputs. The source audit checks native IDs, matched candidate coverage between c arms, age eligibility and half-step integration ranking stability. Full local inclusion checks are stored separately and include failures rather than silently skipping them.

Artifacts: [protocol](protocol.json), [summary](summary.json), [candidate scores](candidate_scores.csv), [association summary](association_summary.csv), [recency sensitivity](recency_sensitivity.csv), [local position evaluation](local_position_evaluation.csv), [phase-resolution audit](quadrature-audit.json), [artifact hashes](artifact-manifest.json). Per-source NPZ files contain predictions, residuals, phase weights, native times and holdout masks; JSON contains original observation IDs and source provenance.
