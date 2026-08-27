# Opened Long-Arc Satellite Association Audit

## Outcome

The first authorized catalogue-association run on the two registered POST-FIX
long arcs completed successfully. It demonstrates that long-arc curvature can
produce much more stable conditional Starlink candidates than the earlier
sub-second cohort, but it does **not** establish a secure NORAD identity.

- The 30 s `9981` arc selects NORAD 67930 at every rolling origin and the
  training winner remains rank one on every future block. However, the
  predeclared `delta=-500 s` catalogue field predicts the main future block
  8.2% better in equal-calendar-block RMS, and also beats true time in the
  60-to-80% rolling block. The label is stable but is not uniquely
  true-time-specific under the current model.
- The 13.825 s `150802` arc selects NORAD 59748 on the main split and on the
  later two rolling origins. Both `±500 s` fields are much worse. However, the
  earliest 40-to-60% origin selects NORAD 65438, which falls to heldout rank
  two behind 59748. True-time specificity is strong, but early-origin identity
  stability is not complete.
- On both main splits the orbit candidate has lower raw future RMS than the
  cubic radio-only polynomial. Nevertheless, the Gaussian predictive
  likelihood slightly favors the cubic on `150802` and strongly favors it on
  `9981`. The result is a warning that the current orbit and radio predictive
  covariance models are not yet calibrated for an identity posterior.

These are successful development outcomes: the method returned distinct,
diagnosable failure modes instead of converting convergence or a rank-one fit
into an identity claim.

## Execution and provenance

The first authorized presentation/science attempt failed closed before response
scoring because the response-free exact population work cap was too small for
the `150802` fields. The failure receipt was preserved. An additive amendment
changed only that numerical work cap from 20 million to 30 million propagation
units and authorized one retry to new exclusive paths. It did not change the
data, site, candidate population rule, tau support, masks, nuisance model,
ranking, score, or claim boundary.

| Item | Frozen value |
|---|---|
| Attempt | 2 |
| Status | complete |
| Runtime | 2026-08-27 05:35:24.916139–07:26:27.755570 UTC |
| Scientific implementation | `fff1786fc029d4e0c818cccc2317327f6aa3cf3c` |
| Authorized repository head | `f82031f4effe75cff696080f8a38afeec157afb3` |
| Amendment semantic digest | `sha256:02bd4bd74a62478015aff6d22f89e9cae5a92fad3ac7fa24c0f0327fbaf61ec7` |
| Sealed manifest SHA-256 | `sha256:6b57f8a07a0d284cf54e7fb19e4dacd239d854201779bcdfdadc7a5dec30b3b2` |
| Sealed manifest semantic digest | `sha256:f44d881ece067f840e7815fcf999cb8d347eb0652eba601746f99d3ed5d7904d` |

The exact [execution receipt](figures/2026_08_27_satellite_pnt_long_arc_development_attempt2-execution-receipt.json),
[sealed result report](2026_08_27_satellite_pnt_long_arc_development_results_attempt2.md),
[sealed manifest](figures/2026_08_27_satellite_pnt_long_arc_development_attempt2/manifest.json),
and [machine audit evidence](figures/2026_08_27_satellite_pnt_long_arc_development_attempt2/audit-evidence.json)
bind the run.

The two raw result JSON documents are 474,508,175 and 397,327,878 bytes. The
repository stores byte-exact Zstandard copies instead of adding 832 MiB of
ordinary Git objects. The [archive manifest](figures/2026_08_27_satellite_pnt_long_arc_development_attempt2/archive-manifest.json)
binds each compressed byte stream to the original sealed SHA-256 and semantic
digest. Static tests stream-decompress the archives and verify the original
hashes without regenerating or rescoring the science.

## Response-free candidate populations

Every population and SGP4 prediction bank was completed before response
scoring. The populations were independently frozen for each predeclared field;
no field was truncated or response-ranked.

| Arc | `delta=-500 s` | true time | `delta=+500 s` |
|---|---:|---:|---:|
| `9981` | 503 | 488 | 501 |
| `150802` | 572 | 573 | 576 |

The different counts are geometric field populations, not selected shortlists.
The `±500 s` fields remain observations only: two fields do not define a null
distribution, empirical p-value, threshold, veto, or secure-identity gate.

## Main future-block result

Candidate identity, tau, and the constant CFO offset were selected on the
training prefix. The selected state was then frozen and scored once on the
future suffix. Smaller RMS and predictive negative log likelihood are better.

| Arc | Train/future rows | Training winner | Tau | Future winner | Future rank | Pooled RMS | Equal-block RMS |
|---|---:|---:|---:|---:|---:|---:|---:|
| `9981` | 529/352 | 67930 | -0.50 s | 67930 | 1 | 154.911 Hz | 170.585 Hz |
| `150802` | 330/220 | 59748 | -0.25 s | 59748 | 1 | 54.749 Hz | 55.062 Hz |

Neither tau solution hits the `[-5,+5] s` boundary. The rank-one margins are
large under this conditional single-episode model: training/future negative-log
score margins are 827.758/24,075.978 for `9981` and 88.763/5,499.644 for
`150802`. Those numbers are descriptive because the likelihood calibration and
scientific thresholds remain unset.

The runner's `abstention_recommended=false` on these two main splits only means
that its structural NN diagnostics found no exact tie, boundary hit, or future
rank flip. It is **not** equivalent to catalogue compatibility or secure
identity.

## Rolling-origin stability

| Arc | Origin | Training winner | Tau | Future winner | Future rank | Equal-block RMS | Structural disposition |
|---|---|---:|---:|---:|---:|---:|---|
| `9981` | 40→60% | 67930 | -0.50 s | 67930 | 1 | 73.225 Hz | retained |
| `9981` | 60→80% | 67930 | -0.50 s | 67930 | 1 | 108.200 Hz | retained |
| `9981` | 80→100% | 67930 | -0.75 s | 67930 | 1 | 72.629 Hz | retained |
| `150802` | 40→60% | 65438 | -1.75 s | 59748 | 2 | 157.491 Hz | abstain: heldout-rank instability |
| `150802` | 60→80% | 59748 | -0.25 s | 59748 | 1 | 58.429 Hz | retained |
| `150802` | 80→100% | 59748 | -0.25 s | 59748 | 1 | 49.590 Hz | retained |

This is substantially better than the historical sub-second cohort's 1/8
exact rolling-origin stability. The comparison is not a promotion statistic:
the arcs, estimator, masks, candidate populations, and development status are
different. It does show why the long arcs are the correct development cohort.

## Wrong-epoch observations

The reported ratio is wrong-field future equal-calendar-block RMS divided by
true-field RMS. Values below one mean the wrong field predicted better.

| Arc/origin | `delta=-500 s` | `delta=+500 s` | Interpretation |
|---|---:|---:|---|
| `9981` main | 0.918 | 2.129 | negative field is 8.2% better |
| `9981` 40→60% | 1.094 | 1.824 | true field is better |
| `9981` 60→80% | 0.822 | 1.684 | negative field is 17.8% better |
| `9981` 80→100% | 2.411 | 3.671 | true field is better |
| `150802` main | 15.434 | 20.648 | true field is strongly better |
| `150802` 40→60% | 2.167 | 2.151 | true field is better despite label flip |
| `150802` 60→80% | 8.923 | 12.080 | true field is strongly better |
| `150802` 80→100% | 11.796 | 16.684 | true field is strongly better |

The two observations answer a limited engineering question: whether nearby
catalogue epochs separated by 500 s are grossly more or less predictive under
equal search opportunity. They do not estimate a false-association probability.

## Radio-polynomial comparison

| Arc | Orbit RMS | Line RMS | Quadratic RMS | Cubic RMS | Cubic radio NLL minus orbit NLL |
|---|---:|---:|---:|---:|---:|
| `9981` main | 170.585 Hz | 4,015.833 Hz | 1,222.416 Hz | 568.696 Hz | -928.856 |
| `150802` main | 55.062 Hz | 228.967 Hz | 159.427 Hz | 87.455 Hz | -1.299 |

The orbit curve wins the unweighted future RMS comparison on both main splits,
which is evidence that catalogue geometry contains useful predictive shape.
The cubic wins predictive negative log likelihood because the two model
families propagate different uncertainty. That disagreement is scientifically
important: a calibrated model comparison must make uncertainty and structural
flexibility commensurate, not select whichever statistic is favorable.

Accordingly, the next identity model must either integrate the radio null into
the same normalized hypothesis family or freeze a separately calibrated
cross-model score. The current RMS and NLL comparisons remain diagnostics.

## Claim boundary

The result establishes all of the following:

- exact POST-FIX long-arc evidence can be adapted without IQ reopening;
- full response-free Starlink populations and all tau states can be propagated
  before response scoring;
- training-only selection and one-shot future scoring work at real catalogue
  scale; and
- long curvature makes candidate stability and true-time specificity much
  more informative than the earlier sub-second arcs.

It does not establish any of the following:

- secure NORAD identity;
- a calibrated association probability or identity threshold;
- recurrence of one NORAD across independent arcs or passes;
- a validated transferable orbit/clock correction;
- a capture-bound observer/boresight authority; or
- positioning accuracy.

The two arcs select different candidates, both were already opened for
development, and the observer remains a reviewed site preset with no boresight.
They therefore cannot provide independent confirmation or close the PNT goal.

## Next milestone decisions

1. **Calibrate the model comparison.** Put the orbit and radio-only hypotheses
   on one proper predictive-evidence footing, then use known-truth injections
   to calibrate uncertainty and abstention behavior. Do not turn the present
   RMS or NLL differences into post-hoc gates.
2. **Upgrade from rank-one single-episode diagnostics.** Feed the registered
   physical episodes into the exact `K=0,1,2` association and then the causal
   multi-dwell filter. Preserve null, handoff, and ambiguity modes rather than
   forcing one candidate.
3. **Test nuisance transfer only through future prediction.** Share
   receiver/LNB state as a bounded continuity-local random process and keep it
   receiver-local. Candidate tau and satellite frequency state may transfer
   only through a validity-bounded correction product.
4. **Build the known-position correction lane.** Use these opened arcs for
   development only, freeze the correction artifact, and replay it on later
   known-position observations before any blinded navigation claim.
5. **Freeze an untouched confirmation protocol.** New response or RF remains
   closed until model scope, thresholds, candidate population, correction
   validity, and truth-isolation rules are committed. Any new RF collection
   still requires explicit user authorization.
