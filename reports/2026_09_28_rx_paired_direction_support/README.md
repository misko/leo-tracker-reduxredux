# Receiver-relative evidence: paired observations and partial-arc support

The existing calibration corpus supports a bounded receiver-relative prediction
experiment, but a first-detection order test remains poorly identified. There are
1,246 windows with detections in both receivers, and several lanes have candidate
trajectories with different rates of nominal receiver-relative change. Other
lanes have essentially one candidate or duplicate track hypotheses with the same
geometry. A geometry model must distinguish these situations before interpreting
any gain as satellite-association evidence.

This is a descriptive audit of the original six calibration recordings, not a
fitted predictive result. It preserves all 2,719 qualified windows in 12 exact RF
lanes, including empty candidate sets. No original evaluation or DS8 outcomes are
used. The observation and forecast audits are separate; no correlations, fitted
slopes, frequency gates or outcome-dependent subsets were selected.

## Paired detector support

| Observed candidate sets | Reception (1,356 windows) | Later (1,363 windows) |
|---|---:|---:|
| Both empty | 357 (26.33%) | 547 (40.13%) |
| RX0 only | 222 (16.37%) | 278 (20.40%) |
| RX1 only | 22 (1.62%) | 47 (3.45%) |
| Both nonempty | 755 (55.68%) | 491 (36.02%) |

These are pooled census percentages. Equal-record mean percentages are respectively
26.59/18.63/1.51/53.27% in reception and 40.86/18.37/3.68/37.09% later.
Both receiver streams have valid finite margins for every retained candidate:
4,846 RX0 and 3,389 RX1 marks across both periods. There are no missing or
nonfinite marks in this frozen input.

**The marks are thresholded fractional detector margins, not received power or
SNR.** Counts represent retained detector hypotheses, not independent emitters.
Within receiver/window there are 711 repeated margin occurrences for RX0 and 603
for RX1 beyond the first equal value. Equality alone does not prove duplication,
so the audit neither removes these candidates nor treats them as separate signals.
Distinct candidate IDs/ranks can also share frequency and margin in the source.

The next primary response should therefore be the four-category paired detection
state (empty, RX0 only, RX1 only, both), which is unchanged by duplicate entries
inside a nonempty candidate set. It must retain all four categories. Counts and
all-candidate margin summaries can be secondary diagnostics; conditioning on both
receivers detecting something would discard the very asymmetry being tested.
Neither a thresholded detection nor its absence is a measured beam boundary.

## Candidate-specific partial arcs

For each track/catalog hypothesis, the nominal receiver contrast is
`q(t) = 2 sin(10 degrees) × LOS_east(t)`. We subtract each trajectory's mean within
the reported period, then compute prior-weighted RMS disagreement among the
centered trajectories. This measures differences in temporal shape after removing
constant offsets. It uses forecasts and frozen priors only, without visibility
gating or observed detection values. Units are dimensionless boresight dot product,
not degrees, seconds of arrival or calibrated gain.

| Recording suffix | Channel | Effective nominees | Reception RMS disagreement | Later RMS disagreement |
|---|---:|---:|---:|---:|
| 39ac2b14d1bb5f0f | 3 | 3.000 | 0.025977 | 0.011044 |
| 3ebf3526172258af | 1 | 1.000 | 0 | 0 |
| 3ebf3526172258af | 2 | 2.000 | 0.016052 | 0.002660 |
| 4c56320fb5ca6994 | 1 | 1.000 | 3.28e−24 | 7.29e−25 |
| 4c56320fb5ca6994 | 4 | 2.000 | 0.008057 | 0.007754 |
| 851486cc2a1acd99 | 2 | 1.593 | 0.007548 | 0.003831 |
| 851486cc2a1acd99 | 3 | 1.000 | 7.35e−7 | 9.68e−7 |
| 851486cc2a1acd99 | 4 | 1.000 | 1.10e−8 | 1.56e−8 |
| 9d7b6a0db558703a | 3 | 1.000 | 2.44e−88 | 3.94e−88 |
| 9d7b6a0db558703a | 4 | 2.000 | 1.50e−7 | 8.77e−8 |
| c559f436d578c9bd | 1 | 2.678 | 0.015938 | 0.009255 |
| c559f436d578c9bd | 3 | 2.000 | 4.34e−26 | 1.95e−26 |

Effective nominee count is exp(entropy), conditional on retained prior mass.
All forecast nominees are visible throughout these selected periods. The omitted
branch has mass 0.133792 in `c559f436d578c9bd` channel 1, and zero in the remaining
lanes; conditional normalization is descriptive and must not silently remove that
branch from a future predictive likelihood.

Two effective nominees do not guarantee two different satellite trajectories:
`9d7b6a0db558703a` channel 4 has two dominant tracks for catalog 66532, and
`c559f436d578c9bd` channel 3 has two for catalog 66538. Their tiny disagreement
illustrates why track multiplicity is not direction information. In contrast,
`39ac2b14d1bb5f0f` channel 3 has three similarly weighted satellites with positive
but different later secants: approximately 0.000666, 0.002097 and 0.001950 per
second. The useful distinction here is temporal shape/rate, not opposite signs.

Per-period centering is used only for this support diagnostic. A future causal
predictor must use its frozen reception centering rule; these diagnostic means
are not a license to center outcome features on future observations.

## Physical interpretation and next experiment

The [pose review](REVIEW.md) found no repository authority superseding the
provisional RX1-west/RX2-east physical-to-software mapping. Geographic north is
assumed; world tilt, RF boresights and phase centers remain unmeasured. A winning
sign convention would be predictive evidence under that convention, not a cable
trace or verified geographic direction.

Proceed with one calibration leave-one-record-out model of the **joint four-state
receiver detection outcome**, keeping common reception changes and static RX
sensitivity separate from the signed candidate trajectory. Freeze all preprocessing
on the five training reception subsets. Preserve an explicit absent/omitted
state and the frozen candidate bank; handle duplicate track views as alternative
hypotheses, not independent detections. Report held predictive scores against an
unsigned/common-elevation model, receiver swap, trajectory reversal and candidate
permutation. Keep all lanes in the main score and describe geometric disagreement
continuously rather than choosing a favorable cutoff from these observations.

The candidate-permutation control and subsequent frequency-prediction bridge are
necessary before calling a gain association-specific. A generic receiver/time
pattern could otherwise improve detection prediction without identifying a
satellite. The [earlier direction plan](../2026_09_28_rx_ds8_alignment/DIRECTION-PLAN.md)
specifies that separation. No association improvement is claimed by this audit.

## Validation and artifacts

Both exports completed with exit 0 under 60-second, one-thread, 1-GiB limits.
Nine component tests pass, including frequency independence of observation
summaries, outcome independence of forecasts, empty-set preservation, malformed
receiver rejection, receiver-swap sign, and partial-arc centering behavior.

- [Protocol](PROTOCOL.md) and [physical/scientific review](REVIEW.md).
- [Paired observation export](paired_mark.json) and [independent summary](mark-summary.json).
- [Forecast export](partial_arc.json) and [independent pairwise-distance audit](arc-audit.json).
- The mark audit reconstructs all 2,719 windows directly from the input and checks
  counts, asymmetries, means, contrasts, IDs, times and roles.
- The forecast audit recomputes all 24 lane/period RMS values with the independent
  weighted pairwise-distance identity, rather than the exporter's weighted-mean formula.
- Launch, terminal, resource and exit receipts preserve source/input hashes;
  `evidence-sha256.json` seals final artifacts and relevant source/tests.
