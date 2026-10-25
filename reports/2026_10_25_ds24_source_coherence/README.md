# DS24 source coherence and the next localization experiments

Date: 2026-10-25. This iteration investigates the apparent departure of
DS24-0013 RX2 CH4 from the Doppler curve predicted by a separate CH5 source.
It also consolidates [the review of experiments and next directions](REVIEW.md).
Three SOL xhigh agents handled the source comparison, native-data reconstruction,
and independent audit/publication preparation. The coordinator reconstructed
historical support eligibility and reviewed the conclusions.

The reference algorithm and its inferred positions remain unchanged. There
are no new position fits, accepted satellite identities or ALGO promotion.
DS24-0013 retains its original 3,784/4,808 position-likelihood points
(78.7022%) in both c arms. None of the three selected source owners was
accepted by that baseline. The three sources and this scan were selected
after examining earlier residuals; this is development diagnosis.

## Native data do not establish a crossing fault

Every one of the scan's 4,808 original GLRT winners and every graph lane index
reconstructs exactly. CH3, CH4 and CH5 keep all 24, 43 and 57 original source
IDs, respectively. A uniform minus-two-period shift maps native CFO to the
graph convention; no candidate is individually wrapped to approach a model.

The 43-point CH4 owner spans 236.131-264.829 seconds. Its quartic was already
marked `structure_flagged`, with adjacent residual correlation 0.823. The
observed CFO remains continuous through the apparent departure near 250 s;
there is no receiver, RF or graph-owner transition there. The other local
CH4 graph owner starts at 266.247 s. Stored alternate peaks exist, but these
records do not establish a second coherent continuation following the CH5
prediction after 250 s.

![Original winners, graph owners and all archived candidate records in the fixed windows](ownership/native_ownership.png)

The CH3 source has a 7.795 s gap before its isolated last point. That point
is a real original winning peak. One unassigned original winner lies inside
the gap. These facts justify investigating source coherence, but neither
deleting the last point nor declaring a second satellite by inspection.

![Original native ownership and saved discovery-only predictions in both calibration arms](ownership/crossing_detail02.png)

The prediction overlays restore the original fixed parent-radio background
to the previously saved radio-conditioned prediction. They add no witness
fit. Their bands are saved mixture moments plus/minus two standard deviations,
not calibrated 95% intervals. Interpolation at contextual probe times stays
inside the original witness support. The same graph alias zero is retained
throughout the diagnostic residual panels.

The fixed windows contain 497 other archived CH4 candidate records, of which
219 pass their original gates; CH3 has 406/25 and CH5 has 734/148. These are
same-probe candidate records and can include nearly duplicate peaks. They
are neither additional independent measurements nor counts of distinct
emitters. No new IQ extraction or RF collection was required.

[Native findings](ownership/FINDINGS.md) preserve the exact IDs, windows,
candidate tables, processing failures and source/test receipts.

## Why the short apparent prefix never entered historical calibration salvage

The original runner source hash matches the archived scan result. Its support
generator considers prefix, suffix and whole supports with at least 12 points,
then requires at least 20 seconds and a separate curvature prerequisite.
The prefix at the middle of the new experiment's predeclared cuts lasts only
14.524 seconds. It therefore could not enter that curved-calibration route,
regardless of a candidate's physical fit.

![Predeclared support durations and the historical 20-second requirement](eligibility/support_durations.png)

| Cut after point | Prefix duration | Suffix duration | Historical duration test |
| --- | ---: | ---: | --- |
| 14 | 8.858 s | 18.424 s | Neither passes |
| 21 | 14.524 s | 13.820 s | Neither passes |
| 29 | 20.195 s | 8.148 s | Prefix passes duration only |

The original pure support generator returns 63 alternatives; 27 survive its
duration check. The historical result records 15 after all support gates,
30 satellite candidates and no selected salvage alternative. This trace
does not recompute the curvature test or recover an exact residual-gate
failure for each candidate. It is a proposal-eligibility explanation.

No calibration requirement is relaxed. A short physical portion would need
a separately qualified predictive role and independent identity evidence;
it cannot be used to calibrate receiver offsets or drifts merely because
it resembles the expected curve. [Eligibility findings](eligibility/FINDINGS.md).

## Controlled complete-observation comparison

The scientific protocol conditions on the previous ordinary CH5 candidate
57450, without declaring that identity known. All 57 discovery points D and
43 CH4 witness points W enter every model. It preserves the original parent
radio covariance, observation noise, fixed RF position, arm-specific
calibration, owner constants and finite alias measure. No geographic truth
is read and no position is optimized.

Four research model classes receive equal prior mass:

1. All W shares D's physical satellite curve.
2. All W follows a proper degree-four unresolved polynomial.
3. A contiguous edge portion shares D's physical curve, while a proper
   polynomial accounts for the remainder.
4. Two proper polynomial pieces account for W without a shared physical part.

The splits are fixed after native W points 14, 21 and 29. Class 3 averages
all six cut/prefix-or-suffix alternatives with normalized weights; class 4
averages its three cuts. A best cut is never taken for free. The two-piece
polynomial control asks whether the physical prediction contributes beyond
the flexibility of splitting alone. The whole original W has one shared
300 Hz owner constant and one alias across its pieces.

Shared physical rows use one orbital timing variable and three Gaussian
orbit-shape modes. The original Student timing prior remains normalized on
[-15,+15] seconds. A narrower computational window is an integration aid,
with explicit bounds for probability outside it. Independent quadrature
rules and conservative evidence bounds distinguish a numerical estimate
from a globally qualified model ordering. All 22 model/arm attempts and
eight class/arm outcomes remain in the record.
Unseen point noise uses the archived Gaussian predictive approximation with
variance twice the native variance, not a full integrated Gamma noise mixture.

See [protocol](scientific/PROTOCOL.md), [replay instructions](REPLAY.md) and
the scientific terminal artifacts for exact implementation and limitations.

## Result: partial physical compatibility wins in both arms

All 22 model/arm comparisons and eight class/arm outcomes completed. The
normalized physical-portion-plus-unresolved-remainder class beats every other
declared class in both arms, with nonoverlapping full-domain evidence bounds.
The evidence calculation includes the original timing domain outside the
computational window; agreement between local quadrature rules alone is not
used to make this decision.

![Full-domain model-score bounds, relative to each arm's split-window estimate](scientific/report02/class_evidence_bounds.png)

| Model class | Full-domain log-evidence bounds, c=0 | Full-domain log-evidence bounds, fitted c |
| --- | ---: | ---: |
| Whole W shares D's physical curve | [-2495.938, -714.170] | [-2485.366, -716.711] |
| Whole W unresolved polynomial | [-630.728, -627.114] | [-629.692, -626.723] |
| Physical edge portion plus unresolved remainder | **[-624.145, -623.588]** | **[-623.446, -622.953]** |
| Two unresolved polynomial pieces | [-659.479, -629.593] | [-658.390, -636.501] |

Larger log evidence is better within one arm. Equal class priors cancel in
these comparisons; cut/allocation priors are already averaged within each
class. These are bounds under the declared conditional models and proper
coefficient priors, not calibrated probabilities of satellite identity.
Even the winning class's lower bound exceeds every competitor's upper bound
by at least **2.969/3.277 log-evidence units** in c=0/fitted-c.

The computational-window estimates favor the first 14-point prefix and the
first 21-point prefix, with approximately 56%/44% relative weight in c=0 and
54%/46% in fitted c within the split class. These are local diagnostic weights,
not certified allocation probabilities or a precisely measured breakpoint.
The two prefixes span 8.858 and 14.524 seconds; both are below the historical
20-second calibration prerequisite. The physical suffix alternatives and
29-point prefix have negligible weights in that window.

![Within-window allocation diagnostics, not calibrated identity probabilities](scientific/report02/split_window_weights.png)

The discovery-only and original whole-polynomial replays agree to roundoff.
All independent quadrature comparisons pass. The full conservative bounds
are deliberately wider than an absolute 1e-3 objective tolerance; they prove
the ordering without claiming that absolute integration accuracy. In particular,
the whole-physical upper bound is dominated by the remote-domain bound, so its
computational-window objective must not be reported as a certified global
evidence value.

The successful run used 43.568 worker-seconds (21.924 s wall time), and
52.710 worker-seconds including the first failed attempt and actual input
smoke checks, under the unchanged 600-second cap. The first attempt failed
before scoring because a helper module lacked the referenced metadata-path
attribute. Its exact outputs are preserved. A path-only repair, two-arm
real-input smoke check, eleven passing owned tests and independent preflight
preceded the successful run; no priors, cuts or budgets were expanded.

[Complete execution](scientific/run02/execution.json),
[successful frozen protocol](scientific/run02/protocol.json) and
[original failed execution](scientific/execution.json) retain every attempt.
The independent [terminal audit](audit/terminal.json) passes 67 checks, including
exact data/background replay, normalized model priors, all 22 quadrature
comparisons, conservative bounds and the complete compute ledger. It performs
no new orbit propagation or position fitting.

## Interpretation and next decisions

The partly shared curve preference establishes a useful conditional model
comparison: CH5's full physical prediction contributes beyond adding polynomial
flexibility alone under these priors. It does not prove a graph switch,
identify another satellite or justify accepting a favorable prefix alone.
A second independently supported continuation or a bounded ordinary causal
catalogue challenge is necessary for a stronger identity claim. One such
challenge is justified by this result; if it remains ambiguous, preserve
unresolved status and move to the next source. No general splitting policy
or relaxed calibration gate follows.
The physical modes include level- and phase-like components; this comparison
does not isolate curvature. It tests one declared proper-polynomial scale,
not prior sensitivity or physical adequacy across alternative null laws.

The cumulative [review](REVIEW.md) prioritizes a small blind-association
control with exactly matched generation/scoring laws, recovery selected for
new position information, and a bounded check for independently calibrated
observables in existing recordings. Earlier continuous restarts, broad
recovery, receiver flexibility and phase/shape approximations have already
received substantial testing without a transferable large precision gain.

All localization work retains matched c=0/fitted-c controls, causal TLEs
and the 25 by 25 km search region centered at 37.906, -122.545. Evaluation
GPS is excluded from inference and acceptance. No dataset membership,
production component, golden fixture, original recording or QNAP path changes.
