# Early real-axis structure survives receiver controls

The strongest retained early-symbol evidence is shared **real-axis variation
in physical OFDM symbols 3, 4 and 6**. A new joint audit of the frozen receiver
comparisons supports it after coordinate offsets, common carrier level and
fitted template gain are removed. No quadrature comparison passes the same
correction. This supports recovery of structured signal components; it does
not identify message fields or satellites.

## Data and fixed comparisons

The inputs are the existing DS10-F010 excerpts v1085, v1150 and v1162, with
23, 9 and 11 chronological held frames respectively. They share a session and
conditional satellite candidate. They are not three independently established
satellite passes. Input cache hashes are checked against their original receipt.

The original 34 component/region comparisons are retained in their original
order: centered I, centered Q, Q after discovery-fit I regression, I after
common-level removal, and I after common-level/template-gain removal, over
their previously selected symbol ranges. No axis, region or confidence gate
is newly optimized. Every observed correlation reproduces the historical
receipt within 1e-6.

A score is the equal-excerpt mean of the three within-excerpt RX0/RX1
correlations. **It is not a correlation of bits between different visits.**
Discovery-only preprocessing is retained. Evaluation-coordinate centering is
used only to measure covariance, not to fit sign thresholds.

## Joint reference and session sensitivity

For the primary reference, RX1 rotates as one block within each excerpt,
preserving all dependencies between components, symbols and carriers. Enumerate
all 23×9×11 = **2,277** combinations, including zero rotation. Center each
comparison on its full reference mean, then use the maximum absolute score
across all 34 comparisons. This is a two-sided family correction.

Because the excerpts share a session, a second reference moves them together:
one common fractional cycle `u` selects shift `floor(u*n)` in every excerpt.
Its **41 unequal intervals** are integrated with their exact interval lengths,
rather than counted equally. It preserves a common fractional displacement
across excerpts and is a sensitivity check, not a physical-time alignment model.

Both references assume that circular misalignment is an appropriate null.
Qualified-frame gaps, shared calibration and previous use of the held data
limit inference. The resulting ranks are conditional finite-reference evidence,
not population-level probabilities or correction over the whole investigation.

![Receiver agreement by physical symbol](local/receiver-family.png)

## Results after common-level and template-gain removal

| Symbol | Mean RX correlation | Independent-excerpt family rank | Coupled-session family rank |
|---|---:|---:|---:|
| 2 | −.035 | .999 | 1.000 |
| 3 | .410 | .000439 | .04348 |
| 4 | .471 | .000439 | .04348 |
| 5 | .197 | .04523 | .09091 |
| 6 | .487 | .000439 | .04348 |
| 7 | .071 | .802 | .616 |

Symbols 3, 4 and 6 remain positive in **each** excerpt after those removals.
Their coupled ranks reach the reference's zero-shift interval floor, 1/23;
that coarse resolution should not be presented as highly precise significance.
Symbol 5 does not survive the coupled-session .05 threshold. All Q comparisons
fail the corrected screen; across symbols 2–7, mean Q correlation is .0135,
or .0183 after fitted I leakage removal, with family rank 1 under both references.

## Relation to known-state prediction

The existing `state-transfer.json` contains only one supported visit, v1085:
16 training frames and 13 held frames with eligible repeated states. The other
five attempted visits abstain. Across its ten residual assays (five regions,
two gain models), state-conditioned templates all lose to a state-independent
mean. The early 2–7 region's reductions are −.0090 and −.0156: small losses,
not improvements. Some scores exceed shuffled-state controls while still
losing to that mean; beating a shuffled model is not sufficient evidence of
useful new decoded structure. These prior negative assays were inspected,
not blindly rerun.

The receiver result and state-prediction result are compatible. A waveform can
be shared between receivers without being predictable from the known T-state,
and without yielding stable identity across visits. Shared frequency-selective
channel effects, calibration residuals or other encoded structure remain possible.

## Firmware interpretation and next evidential requirement

The firmware audit establishes software prefixes and device-role configuration,
but no carrier placement, scrambler or interleaver mapping to symbols 3/4/6.
Thus the ranking is shared received structure first, unresolved physical or
encoded modulation next, and semantic identity/field interpretation unsupported.
These are covariance measurements, not validated BPSK/QAM payload bits.

A satellite or field claim still requires cross-visit bit correspondence and
specificity against different satellites after known-state, receiver, channel
and time controls. The present result does not satisfy that requirement.

## Independent support and baseline audit

`state_scope.py` reconstructs the original chronological eligibility masks from
each paired summary and checks its NPZ hash. Only v1085 qualifies: 16 discovery
frames and 13 held frames, with eligible repeated training states 28/44/52.
The five other excerpts have no eligible held frames under the frozen rule.
They are abstentions, not negative evidence about their signals.

Across the supported excerpt's ten residual assays, all prediction improvements
over the state-independent mean are negative. Early symbols 2–7 score −.0090
and −.0156 for scalar/per-carrier gain subtraction; several later raw regions
improve by .0447–.0572, but their residual counterparts do not improve. The five
raw comparisons are numerically identical under both gain-model headings and
must not be counted as independent replication.

The audit checks the algebraic relationship between all three saved baselines:
state versus global mean, state versus zero, and global mean versus zero. An
initial float64 tolerance was inappropriate for scores originating from the
verified complex64 arrays; the check uses eight float32 epsilons of relative
tolerance. A test rejects a materially inconsistent baseline identity. The
eligibility test also verifies that future repetitions cannot make a state
eligible retrospectively.

No new significance claim is made. In particular, zero exceedances among 199
shuffled training-label controls do not rescue a model that loses to the mean.
Firmware's conditional prefixes and accounting units provide no contrary
mapping from T-state to a message field. Fifteen ledger entries now preserve
these ten assays and five abstentions explicitly.

```sh
uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/state_scope.py
```

## Combining improves the known waveform but does not validate early parity

The remaining receiver-combination receipts are now explicitly audited by
`combining_scope.py`. Across 23,296 held known-waveform decisions, disagreement
is 17.90% for RX0, 13.26% for RX1, 8.50% for equal averaging and 11.65% for the
discovery-fitted weighted method. These are pooled descriptive counts from
three excerpts, not independent bit-error trials. They compare against an
inferred late T-code waveform, not verified early message truth. Weighted
combining is not uniformly better than equal averaging.

The frozen historical-reference parity is
`(3,524) XOR (3,537) XOR (5,524) = 1`. Recomputing its ungated agreement and all
first-coordinate cyclic shifts from saved local signs reproduces the receipts.
The six excerpt/method ranks are 1, 1, .5556, .1111, .7273 and 1. Bonferroni
across these six comparisons has minimum 2/3: no supported transfer.

Requiring all three coordinates to exceed the frozen median-amplitude threshold
leaves **2/2/0/0/1/1 frames** across the six cases. Perfect agreement on such
subsets is not strong evidence: the v1085 two-frame subsets also have a
constant-sign baseline of 1. The saved gated shifts retain the target mask
without preserving shifted-donor eligibility, so no calibrated probability is
assigned to them. Higher gates do not fix the support problem.

This adds nine explicit ledger entries without refitting models or rerunning
RF extraction. It closes this inventory gap while preserving the distinction
between known-waveform recovery, shared early covariance and decoded fields.

```sh
uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/combining_scope.py
```

## DS9 quadrature associations have a different scope

An explicit coverage review found the historical DS9 header-quadrature receipt
was absent from the expanded ledger. `ds9_axis_audit.py` now reproduces all 32
region/axis correlations and their shifted means/extrema from hash-verified
DS9-middle/last soft arrays. Each excerpt has 23 evaluation frames, with eight
frozen regions and two axes. No coordinate or model search is added.

| Excerpt | Header real-axis correlation | Header quadrature correlation |
|---|---:|---:|
| DS9 middle | .5836 | .2199 |
| DS9 last | .3669 | .0168 |

This preserves a real historical observation: middle-excerpt quadrature
covariance was appreciably larger than in the last excerpt. It does not
contradict the DS10 residual result above, which uses other data and further
common-level/template-gain removal. The DS9 assay only centers each coordinate.
Do not summarize all datasets as having no quadrature structure.

For each excerpt the new audit jointly rotates the entire RX1 frame array,
takes the maximum absolute correlation over all 16 region/axis tests, and then
uses Bonferroni across the two excerpts. The smallest possible corrected rank
is **2/23=.08696**, so this reference cannot achieve a .05 rejection. The middle
header I/Q and last header I reach that floor; last header Q has rank 1.
Failure to reach .05 at this coarse resolution is not evidence of absent signal.
Gapped qualified frames, common calibration and earlier selection remain caveats.

The 32 associations now have individual ledger entries. A shared waveform,
channel error or calibration residual remains ranked ahead of a decoded extra
quadrature field. No firmware constraint supplies a bit interpretation.

```sh
uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/ds9_axis_audit.py
```

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/receiver_family.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Ignored `local/receiver-family.json` stores all 34 results, all visit scores,
coupled interval weights and hashes. The ledger now has 360 entries. All 20
component tests pass, including covariance-offset invariance and unequal-interval
weighting. No new RF, fixture modification or raw-data commit was performed.
# DS9 preprocessing reconciliation

The historical DS9 neighbor-leakage probe fits symbols 272–301. It explains
about 6% of their shared imaginary cross-power with the tested neighbor models;
it does not test early symbols 2–7. The historical tail-phase transfer instead
measures early real-sign agreement. Neither resolves early quadrature covariance.

`ds9_leakage_transfer.py` applies the existing DS10 per-coordinate linear I-to-Q
correction without changing its model or searching coordinates. Each receiver's
offset and slope are fit using the original 22 chronological discovery frames;
the original 23 reserved frames remain outside fitting. These reserved data have
already been examined, so this is a reconciliation, not fresh confirmation.

| DS9 excerpt | Early I correlation | Early Q | Q after fitted I removal |
| --- | ---: | ---: | ---: |
| Middle | 0.583551 | 0.219867 | 0.210720 |
| Last | 0.366873 | 0.016794 | 0.003402 |

Simple linear leakage from I does not explain the middle excerpt's shared Q.
The DS10 residual-Q negative finding therefore cannot be generalized to DS9.
Other shared calibration, propagation, interference, or modulation effects remain
possible; firmware has not mapped this variation to a field or an extra bit.
Removing I-correlated Q may remove modulation as well as instrumental leakage.

Controls rotate all RX1 coordinates together within each excerpt, preserve the
frame blocks, maximize absolute correlation over the frozen 21 component/region
assays, then apply a two-excerpt Bonferroni correction. The minimum attainable
corrected rank is 2/23 = 0.08696, attained by the middle aggregate Q assays.
This cannot reject at 0.05 and is not evidence of absence. Irregular accepted-frame
gaps and cyclic exchangeability remain limitations; the correction covers this
bounded reconciliation, not the whole research history.

![DS9 frozen preprocessing comparison](local/ds9-leakage-transfer.png)

Reproduce with `uv run --no-project --with numpy --with matplotlib python
reports/2026_09_29_firmware_cluster_reaudit/ds9_leakage_transfer.py`.
The receipt records raw-cache, split, method, and historical-reference hashes.
The component test checks leakage removal, retention of independent Q, and that
changing held data cannot change fitted coefficients. No native cache or fixture
is modified.

## Does known T-code explain DS9 early Q?

`ds9_t_quadrature.py` uses the existing accepted state assignments from windows
ending before symbol 242 and the established fixed T-code/carrier mapping.
It fits one intercept and one real slope per coordinate and receiver on the
22 discovery frames, then predicts the 23 reserved frames. There is no new
phase, lag, polarity, or coordinate search. The same fit applied to known late
real-axis symbols 272–301 is a positive control for the mapping and estimator.

| Excerpt | RX | Early Q error reduction | After I regression | Known late I control |
| --- | --- | ---: | ---: | ---: |
| Middle | 0 | −5.31% | −4.68% | +47.04% |
| Middle | 1 | −7.01% | −6.21% | +44.80% |
| Last | 0 | −3.80% | −3.59% | +37.49% |
| Last | 1 | −4.62% | −4.15% | +39.69% |

Error reduction is relative to a discovery-mean predictor, not zero. The model
works on the known late signal but fails to explain early quadrature variation
on later frames. This weakens the simple direct T-sign coupling interpretation;
it does not eliminate nonlinear state effects, unknown scrambling, or other
channel effects, and does not establish message bits.

All coordinates and models rotate together within each excerpt for controls.
The maximum over the 28 early assays is corrected over the two excerpts.
Previously inspected reserved frames and coarse cyclic references retain the
limitations above. A categorical state-mean alternative is unsupported: requiring
at least two discovery examples of a state leaves zero middle and only three last
evaluation frames. We therefore did not fit a high-dimensional state lookup.

Reproduce with `uv run --no-project --with numpy python
reports/2026_09_29_firmware_cluster_reaudit/ds9_t_quadrature.py`. Input state/cache
hashes and frame splits are recorded in `local/ds9-t-quadrature.json`.

## Phase-control scope and transfer

The existing nine-symbol pilot phase probe concerns **DS9-last only**, eight
frames, two receivers and two alternating pilot subsets. Its 32 rows report
held-pilot coherence; they do not report early nonpilot quadrature. Recomputing
its summary gives whole-frame coherence 0.58437 → 0.57638, with zero improved
rows, and early pilot coherence 0.56240 → 0.55778. These summaries cannot rule
out a phase explanation for the middle excerpt's early nonpilot Q.

`ds9_phase_scope.py` reproduces the separate historical tail-derived rotations:
per-frame/carrier phase is estimated from known signs in symbols 242–271, then
applied to symbols 272–301 and 2–7. All four historical late sign-error counts
and median rotation magnitudes reproduce. This is a noncausal diagnostic, not
an early-header online decoder.

| Excerpt | Early Q before | After tail phase | Known late errors RX0 | Known late errors RX1 |
| --- | ---: | ---: | --- | --- |
| Middle | 0.219867 | 0.211929 | 1946 → 1996 | 2010 → 2102 |
| Last | 0.016794 | 0.019107 | 2761 → 2819 | 2543 → 2564 |

Each late error count uses 16,560 signs. Because the correction slightly worsens
known-sign recovery, its failure to remove early Q is weak evidence against a
phase explanation. It does not exclude faster symbol-dependent phase errors.
There is still no demonstrated extra modulation bit or firmware-field mapping.

For early Q, all coordinates rotate together within each excerpt; the maximum
absolute correlation over 14 frozen before/after region assays is corrected over
the two excerpts. Middle aggregate ranks are 2/23, last ranks are 1. These are
conditional cyclic controls with the same frame-gap and prior-inspection limits
as above. No phase bandwidth or coordinate search was added.

Reproduce with `uv run --no-project --with numpy python
reports/2026_09_29_firmware_cluster_reaudit/ds9_phase_scope.py`.
The receipt distinguishes reproduced raw-cache calculations from the pilot
summary audit, whose original raw demodulation was not rerun.

## Carrier-group and frame influence

`ds9_carrier_scope.py` partitions early symbols 2–7 into the two complete
12-carrier groups already recorded around the lower pilot: 516–527 and 536–547.
It uses the original discovery-only I-to-Q correction and the same 23 reserved
frames. There is no carrier selection or new region search.

| Excerpt | Carriers | Q correlation | After I regression | Corrected leave-one-frame-out range |
| --- | --- | ---: | ---: | --- |
| Middle | 516–527 | 0.20568 | 0.19786 | 0.18021–0.21242 |
| Middle | 536–547 | 0.23193 | 0.22174 | 0.20765–0.23384 |
| Last | 516–527 | 0.04930 | 0.03528 | 0.02489–0.04567 |
| Last | 536–547 | −0.00980 | −0.02300 | −0.03249–−0.01183 |

The middle excerpt's corrected covariance divides approximately 43%/57% between
the two groups. Both retain positive correlation after every single-frame
omission. Thus neither one carrier group nor one frame alone explains the
pooled observation. This does not exclude dependence on a few coordinates, shared
calibration, or propagation. The last excerpt has weak opposing contributions;
its signed covariance fractions should not be interpreted as probabilities.

The four fixed group/component comparisons share one RX1 frame rotation per
excerpt, with a maximum statistic and a two-excerpt correction. Middle ranks are
2/23; none permits a corrected 0.05 rejection. Frame-omission ranges are influence
diagnostics, not confidence intervals. This is an attribution of already examined
data, not independent confirmation or evidence of satellite-specific content.

Reproduce with `uv run --no-project --with numpy python
reports/2026_09_29_firmware_cluster_reaudit/ds9_carrier_scope.py`.
