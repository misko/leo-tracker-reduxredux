# Independent review: geometry-association pilot

## Review status

**Pre-fit review passed for one bounded existing-artifact run; no geometry result exists yet.**
The implementation and tests satisfy the gates below. A successful run would be evidence about predictive density
under a shortlist-plus-fallback model. It would not identify a satellite, resolve an integer
alias, estimate antenna tilt, establish physical arrival order, or demonstrate localization.

## Frozen pilot interpretation

The executable pilot is narrower than the AR(1) primary model discussed in
`reports/2026_09_28_rx_sequence_followup/MODEL-DESIGN.md`. It must use one shared latent
window state integrated by fixed five-point Gauss-Hermite quadrature, standard deviation one,
and `rho = 0` in D, S and T. There is no temporal autoregression claim. Quadrature nodes,
weights and latent scaling must be identical in every arm and control.

All arms use the same complete candidate-set frequency, mark and clutter model. Uniform
periodic clutter intensity `lambda` and periodic-normal width `sigma` are fitted using only
reception windows from the six calibration recordings, then frozen for every arm, evaluation
reception conditioning and held-frequency score. Evaluation reception may update component
weights but may not update a coefficient, nuisance parameter, alias, CFO or candidate domain.
Calibration held-frequency windows and all four evaluation recordings must remain sealed while
fitting `lambda`, `sigma` and arm coefficients.

The common frequency, clutter and mark factors are ancillary to arm contrasts and can cancel
algebraically only after the complete likelihood has been formed. They must remain in absolute
component likelihoods used to update the track-by-candidate mixture and the `other` branch.
Dropping them earlier can change normalized reception weights even when an arm contrast appears
unchanged.

## Required nesting

The detection logit must be nested with a common coefficient convention and common
standardisation fitted on calibration reception only:

- D: nuisance intercept, receiver contrast and sequence rate.
- S: D plus same-receiver LOS up, north and east.
- T: S plus signed-receiver east and its up interaction, using the frozen nominal 20-degree
  receiver axes.

Setting both T-only coefficients to zero must reproduce S exactly at machine precision. Setting
all S- and T-only coefficients to zero must reproduce D. Receiver swap and trajectory reversal
change only their declared geometry covariates; they retain the fitted T coefficients,
candidate sets, frequency predictions, receiver offsets, mixture priors, timestamps, window
population and denominators. Neither control is refitted.

## Leakage and population gates

Before a real fit, the dataset audit must demonstrate all of the following:

1. Training candidates are absent from the fitting and scoring rows. Training supplies only the
   already-frozen track, candidate, CFO, alias and receiver-calibration authorities.
2. Each source group has exactly one role, and train, reception and held-frequency source-group
   sets are pairwise disjoint.
3. Every eligible paired source window appears once in the likelihood. Receiver views are two
   factors inside that contribution; tracks and catalogue candidates are mixture components,
   not replicated rows.
4. Eligibility is outcome-independent after requiring the frozen exact lane, qualified paired
   views and training-qualified receiver calibration. Empty qualified candidate sets remain
   observed outcomes. Visibility changes component detection probability, not window inclusion.
5. The six/four recording split is taken from the frozen partition. Only calibration reception
   rows reach any fitting function. Evaluation reception and held rows are accepted only by
   prediction/conditioning functions whose parameter objects are immutable.
6. Raw candidates are the complete passed sets. No closest candidate, frequency gate, residual
   threshold, unique-hit filter, ambiguity filter or held-derived alias choice is permitted.
7. Lane transfer respects the mapped anchor receiver and signed RX1-minus-RX0 offset. It cannot
   assume RX0 is the anchor.
8. Every exclusion has one frozen reason and all partition windows reconcile to included plus
   excluded counts by recording, role and lane.

## Mixture and score gates

Track priors must be fixed within an exact lane. Candidate weights must be reconstructed in the
log domain from frozen training log likelihoods without flooring, temperature changes or
reranking. Retained mass remains explicit. The omitted mass contributes through one common
`other` component; it may not be renormalized away or recreated once per candidate.

For a unique window, the implementation must first form each component's joint two-receiver
set likelihood under the common latent window state, then sum the track-by-candidate and other
components exactly once. Evaluation reception updates the single normalized joint component
mixture in log space. Each held window is scored before its observation is consumed. The primary
denominator is unique eligible paired windows per evaluation recording, followed by equal
recording weighting; receiver rows, tracks and candidates are never denominators.

The pre-fit tests must cover finite periodic densities, alias-period invariance, empty and
multi-candidate sets, candidate permutation, shared-state two-receiver integration, one-window
mixture accounting, prior normalization including other mass, prequential score-before-update,
and exact D/S/T nesting. Large finite negative log densities are valid evidence; silently
clipping or dropping them is not.

## Decision boundary

Proceed to the bounded fit only after the executable configuration, dataset digest and audit
counts are frozen and the implementation review below has no open blocker. The final decision
requires actual held predictive evidence: T must improve on D and S on the predeclared
equal-record score, and its gain must exceed both fixed-coefficient receiver-swap and
trajectory-reversal gains on the identical population. Passing this gate would support a
model-specific nominal-geometry association only. Failure, numerical instability, population
non-reconciliation or a nesting/control failure is a no-go; thresholds, priors, candidate
domain and split must not be changed after inspection.

## Implementation review

The review covered `tools/rx_geometry_dataset.py`, `tools/rx_geometry_likelihood.py`,
`tools/rx_geometry_fit.py` and their three component-owned test modules. The installed runtime
passed 17 focused tests. Ruff passed all six files. The reviewed SHA-256 hashes are:

| File | SHA-256 |
|---|---|
| Frozen protocol | `2531773d88755928648921de15629aa5088d8e0b26e65f2818163ed98896fb81` |
| Dataset builder | `986d15ab2ea33c305b131529b5c4cb6d9b936eeed77cf3b534c5775bebb334cb` |
| Likelihood | `812760d50ce18fcf40b49b99b6276a6eadb23817ff2a9f784cc9bb40afc88c56` |
| Fit and evaluator | `855b9499e087ece0d2fbb0237e55f64d109f217b5e7fb1cf436f24db980d2fff` |
| Dataset tests | `db64650c37aa0f80b884bdbaecc696f82167001d249909768a4d3e21cac237fe` |
| Likelihood tests | `da6d1884732ebdaf842d2812a19ffbbdc2e9e1f419b0be633a0bde985fc16ee9` |
| Fit tests | `a9d2879417fb14f01984f089fe2fba19a0069f753362d7296f947686f9fff592` |

The dataset builder binds the bank, mapping, partition and opportunity artifacts; requires the
bank and mapping track sets to agree; reconstructs finite log-domain candidate priors; retains
the common other mass; preserves qualified empty sets; validates passed candidate identities,
marks and CFOs; checks split, sample rate, timestamp and exact-lane identity; preserves the
partition group ID; rejects cross-role groups; and prevents a source window from entering two
lanes. Its lane accounting records forecast, included and excluded windows by role. An
unqualified receiver-calibration lane is retained as a reconciled zero-window lane with every
forecast window assigned the explicit `unqualified_receiver_bias` exclusion. The completed
upstream mapping reports every receiver-calibration lane qualified; the dataset receipt must
independently reproduce that fact.

The numerical likelihood retains Poisson clutter and count normalizers in every absolute
component likelihood. It sums all candidate signal alternatives, handles empty sets, is
invariant to candidate order and alias-period shifts, and integrates both receivers over the
same five-point quadrature node. The other component is clutter-only. Tests cover normalization,
empty sets, alias invariance, candidate permutation, shared versus independent receiver
integration, extremely concentrated finite priors and sequential held score-before-update.

The fit code computes feature transforms only from calibration reception covariates. During the
three-value sigma grid and every D/S/T optimization, signal arrays outside calibration reception
remain uncomputed zeros and are not addressed by the objective. Sigma and RX clutter intensities
are selected with D, frozen, and reused by every arm and control. All arm fits finish before the
code constructs evaluation signal densities. Tests mutate calibration-held and evaluation
outcomes and reproduce the scaler and calibration objective exactly. They also reproduce D from
S and S from T when added coefficients are zero, verify the declared control column scope and
reject missing calibration/evaluation roles. Evaluation asserts identical held denominators
across every arm and control.

No scientific promotion follows from this review. The dataset stage must first freeze and
reconcile its actual counts and hashes. The bounded fit may then proceed once under the resource
limits. Promotion still requires the actual held evidence specified above; optimizer convergence
alone is not a positive result.

## Independent outcome audit

The bounded run completed with exit status zero. The dataset stage took 2.21 seconds and
644,540 KiB peak RSS; the fit took 2.91 seconds and 134,468 KiB peak RSS. Both remained inside
the frozen limits. The dataset SHA-256 is
`7680b762edc3c3599b65494156f53bb1d60fc9a9edfd7d6fc1914a04a78628f7`; the result SHA-256 is
`aeb6b79d4030644bde28c74be8609e406205df81bf6e351c9d5a2cab21169d8b`.

The dataset audit reconciles 4,282 unique paired windows across 19 exact lanes: 1,356 calibration
reception, 1,363 calibration held, 767 evaluation reception and 796 evaluation held. The fit
uses seven evaluation lanes from four recordings. I independently matched every stored held
window score to its dataset role, summed every lane score back to the recording total, and
reproduced all four denominators: 108, 231, 242 and 215 held windows. D, S, T, swap and reversal
use these identical denominators. Every prior, reception and final log-weight vector normalizes
to one within numerical precision. The per-window scores sum to each held-block score, and every
reported equal-record contrast exactly equals the arithmetic mean of its four stored
record-level contrasts.

| Contrast | Equal-record mean, nats/window | Record signs | Audit decision |
|---|---:|---:|---|
| S − D | +1.001056 | 4 / 4 positive | Static geometry adds predictive density in this pilot. |
| T − S | +0.000805 | 3 / 4 positive | Increment is very small and inconsistent. |
| T − swap | +0.000735 | 2 / 4 positive | Receiver-swap control is not clearly beaten. |
| T − reversal | −0.004527 | 2 / 4 positive | Reversal scores better on the equal-record mean. |

The nominal-tilt claim therefore fails the prespecified decision rule. T is not promoted. The
negative reversal contrast alone is sufficient to reject a positive nominal temporal-geometry
interpretation, and the swap comparison is also too small and inconsistent to rescue it.

The S result is materially different: S beats D in all four evaluation recordings, by
0.7582--1.1804 nats per held window. This is evidence for the frozen static-geometry
candidate-set model on these reused recordings. It remains a model-specific predictive result,
not a physical direction calibration, antenna characterization, satellite identification or
localization result. The planned no-refit full-likelihood versus count-only decomposition is
needed to state whether the gain comes from frequency-conditioned association, reception-count
modeling, or both.

Reception conditioning does change the model's selected mixture component, but these changes
are latent model assignments rather than truth labels. Relative to the frozen prior, the
reception argmax changes in three of seven evaluation lanes under D and in two of seven under S
and T. Comparing arms directly, S and D choose different reception argmax components in three
of seven lanes; S and T choose the same reception argmax in all seven. Their mean reception
posterior total-variation distance is 0.00418, with maximum 0.01467. After held consumption,
S and T still share every argmax, although their maximum posterior total-variation distance
reaches 0.07341. D versus S differs much more and has different final argmax components in three
of seven lanes. None of these component movements identifies a catalogue object: priors are
highly concentrated, the other branch is a common fallback, and no decoded emitter truth is
available.

The independent outcome decision is therefore: retain the positive static S-over-D predictive
finding as exploratory evidence, reject a positive T/tilt finding, and make no satellite,
direction, tilt, arrival-order or geographic-accuracy claim. Any stronger interpretation must
wait for the frozen decomposition and subsequently reserved confirmation data.

## Post-fit count and conditional-frequency decomposition

I reviewed `tools/rx_geometry_score_decomposition.py`, its frozen diagnostic protocol and its
tests. No model is refitted. The tool reloads the frozen feature transform, sigma, clutter
intensities and D/S/T coefficients from the original result. Swap and reversal reuse the frozen
T coefficients. The count likelihood is the proper two-receiver count PMF: the full set kernel
is evaluated with uniform signal sums equal to the candidate count, then corrected by
`n log(period) - log(n!)` per receiver. This yields
`Poisson(n; lambda) [(1-p) + p n/lambda]` while retaining the same shared five-point latent
window state.

The diagnostic uses the full candidate-set posterior before every held window for both the full
and count score. It then updates history with full evidence only. Thus conditional frequency is
the pointwise full score minus count score under the original full-evidence path. It is a
descriptive decomposition of the primary score, not a separately count-filtered model or a new
endpoint. The unit tests explicitly distinguish these histories.

The frozen decomposition completed in 1.10 seconds with 134,896 KiB peak RSS and exit status
zero. Its SHA-256 is
`a0e259953e404b31368b45c60807c6b0bd85ccc9b3cb71e5baafeebc5c3474b0`. Three focused tests and
Ruff passed. I independently compared every decomposed full-window score with the original:
the maximum difference was `7.11e-15` nats, all record totals matched exactly, and
`full = count + conditional frequency` closed within `3.64e-12` nats. Stored per-record means
and equal-record contrasts also reproduced exactly.

| Contrast | Full | Count | Conditional frequency | Frequency signs |
|---|---:|---:|---:|---:|
| S − D | +1.001056 | −0.017948 | +1.019004 | 4 / 4 positive |
| T − S | +0.000805 | −0.006158 | +0.006963 | 4 / 4 positive |
| T − swap | +0.000735 | −0.008798 | +0.009533 | 3 / 4 positive |
| T − reversal | −0.004527 | +0.000488 | −0.005015 | 3 / 4 positive for T |

The static S-over-D improvement is therefore frequency-conditioned association evidence under
the frozen full-history mixture, rather than a gain from predicting candidate counts. The small
T-over-S full gain also comes from its conditional-frequency term, but this does not change the
tilt decision: reversal remains better than T in both the complete score and the
conditional-frequency decomposition. The post-fit diagnostic cannot override that prespecified
control failure.

The final independent decision is unchanged in scope but stronger on mechanism: static LOS
geometry improves ungated conditional-frequency predictive density in all four reused
evaluation recordings under this frozen shortlist-plus-fallback model. Nominal signed-receiver
tilt is not supported. These results remain exploratory association evidence without decoded
target truth, calibrated antenna orientation, physical arrival order or geographic validation.
