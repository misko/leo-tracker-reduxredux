# DS10 extension: recovered words, changing signs, and repeat candidates

This analysis adds the frozen DS10 recordings to the DS7–DS9 symbol census.
The combined analysis set is [local/census.json](local/census.json), bound to
the original census and DS10 membership digests. The previous analysis artifacts
are preserved and reused in place.

## Findings

**DS10 strengthens the distinction between a changing early region and the
known repeating structure later in the frame. It does not yet identify message
fields or a stable satellite-specific signature.**

| Main excerpt census | Earlier DS7–DS9 | Additional DS10 | Combined |
|---|---:|---:|---:|
| Recordings >=5 MS/s | 199 | 151 | 350 |
| Recovered receiver tracks | 11,870 | 9,610 | 21,480 |
| Tracks passing both pilot checks | 738 | 656 | 1,394 |
| Fixed-window accepted word observations | 2,404 | 2,381 | 4,785 |
| Exact known-family matches | 2,387 | 2,363 | 4,750 |

The complete main census recovered **85,920 frames** with zero binding failures
or decode exceptions. DS10 adds 281,242,800 non-pilot complex observations.
Of its 2,381 accepted fixed-window words, **99.24% match the known generator**,
covering all 59 nonconstant states. The other 18 observations are seventeen
one-bit deviations and one two-bit deviation. These are compatible with recovery
errors; they do not establish a new family. Counts are repeated word observations,
not unique packets or independent information units. The overlapping 64-symbol
tail assay separately accepts 998 DS10 words, 996 known; do not add these counts
to the fixed-window assay.

In **541 DS10 frames** with at least two accepted known-family windows, all
accepted windows give the **same state within the frame**. Conversely, **186 of
206 tracks** with consistent state estimates in both evaluation frames change
state between those frames. This supports a frame-dependent repeating structure,
not one fixed raw word per satellite. Unaccepted windows remain unknown.

### A new replication of changing early signs

Three longer visits in DS10-F010 reproduce changing signs across receivers:

| Visit | RF channel | Jointly clean frames | Selected held-out decisions | Receiver agreement | Mismatched-frame mean | Coordinate-bias baseline |
|---|---:|---:|---:|---:|---:|---:|
| 1085 | 2 | 45 | 1,395 | **80.22%** | 59.22% | 61.23% |
| 1150 | 4 | 18 | 631 | **78.45%** | 58.72% | 63.01% |
| 1162 | 2 | 21 | 828 | **75.60%** | 58.57% | 61.42% |

All three visits belong to the same conditional orbit candidate, **NORAD 63400**.
Visits 1085 and 1162 are **10.5845 seconds apart on the same channel**; visit 1150
is between them on channel 4. These are three visits in one recording and one
encounter, not independent orbital passes or verified RF identities. Their
changing signs reproduce above both the full mismatched-frame control ranges
and the coordinate-bias baselines. This replicates the early-region finding in
a new recording; it does not reveal the content's meaning.

![Changing-header agreement](local/header-agreement.png)

The other three paired visits have only 8, 1 and 9 jointly qualified frames,
so the changing-header assay abstains. Across all six paired visits, **61 words
pass independent receiver recovery and exact receiver agreement; all 61 belong
to the known family**. Raw early signs and confidence masks are exported in
[changing-header-signs.csv](local/changing-header-signs.csv); they have native
symbol/carrier coordinates rather than invented byte boundaries.

![Observed early signs](local/changing-header-signs.png)

### Known state explains later similarity much better than early similarity

Across recordings, same-edge/channel pairs involving DS10 have the following
mean phase-profile correlations. There are 3,380 pairs sharing an accepted tail
state and 44,024 pairs without a shared accepted state:

| OFDM region | Shared tail state | No shared tail state |
|---|---:|---:|
| 2–7 | 0.155 | 0.147 |
| 8–33 | 0.084 | 0.022 |
| 34–129 | 0.152 | 0.059 |
| 130–193 | 0.197 | 0.083 |

This reproduces the earlier separation on a broader corpus. Known-state
similarity is associated with later-region similarity, while explaining little
of the first six symbols. These are dependent, pooled descriptive comparisons,
not a causal estimate or significance test; rate and receiver mixtures can still
differ between groups.

![State-conditioned correlations](local/state-conditioned-correlations.png)

The qualified early-region hierarchy now contains **438 upper-edge and 956
lower-edge tracks**. Complete features and four-region correlation matrices are
retained locally. They organize signal observations, not satellite classes.

![Joint early-region heatmaps](local/joint-early-correlations.png)

Additional lower-edge checks give late-region residual correlations of about
**0.026, 0.031 and 0.049**, above their stored mismatch controls but much smaller
than the earlier DS9-middle value near 0.246. That strong residual has not emerged
as a consistent new alphabet in these examples. The 0.049 result uses only eight
eligible state-classified frames.

### What the repeat candidates add

Four conditional IDs have qualified observations in DS10 and an earlier dataset:

| Candidate | Datasets | Separation | Comparison result or limitation |
|---|---|---:|---|
| STARLINK-33881 / NORAD 63779 | DS7, DS10 | 42.12 h | Lower edge, different channels; four correlations −0.011 to 0.251, at the 22nd–83rd percentiles of small matched control sets |
| STARLINK-33935 / NORAD 63791 | DS7, DS10 | 42.12 h | Lower edge, different channels/rates/receivers; correlation −0.064, 16th percentile among 19 controls |
| STARLINK-33826 / NORAD 63641 | DS7, DS10 | 47.07 h | Opposite edges; common early carrier bits unavailable |
| NORAD 59571 | DS9, DS10 | 23.54 h | Opposite edges and different rates; common early carrier bits unavailable |

The lower-edge comparisons test channel-invariant profiles at the same relative
carrier coordinates, not identical RF resource elements. Controls share an
endpoint and match the other's channel, edge, receiver, rate and >2-hour
separation. Their small sizes and shared endpoints preclude interpreting
percentiles as significance levels. See
[cross-channel-repeats.json](local/cross-channel-repeats.json).

None of these four has qualified excerpts on both sides with the same edge
**and** RF channel in the main census. A separate pilot-selected follow-up
extends **NORAD 63854** to fourteen frames on the same stored excerpts:
DS9-F099 and DS10-F034, RX1, upper channel 1, 7.5 MS/s, **4 h 57 min 43.66 s apart**.
Both then have at least two qualified frames. Early correlation is **−0.236**
using two qualified frames per side, or **−0.331** using all qualified frames;
neither side yields an accepted tail word. Both labels remain conditional and
fail the stronger all-controls criterion. See
[extended-repeat/comparison.json](local/extended-repeat/comparison.json).

Within DS10 encounters, 32 same-candidate matched-edge/channel pairs have mean
early correlation **0.150**, versus **0.152** for 57 different-candidate pairs.
These pooled means have unequal rate/receiver mixtures and limited
endpoint-matched controls. They provide no clear identity advantage.

DS10 therefore adds real changing early content across multiple revisits and
wider confirmation of frame-dependent known states. It still lacks a validated
mapping from those signs to message bytes or identity. The three NORAD-63400
visits are useful next examples for testing small early regions on held-out
frames, keeping channel 2 and channel 4 separate.

## Scope and interpretation

DS10 contributes **151 recordings at 5 MS/s or higher and 9,610 receiver tracks**
with spans longer than three seconds and at least six observations. Together,
DS7–DS10 contains **350 eligible recordings and 21,480 receiver tracks**.
DS10's other 36 recordings, at 2.5 MS/s, remain dataset members but are outside
this decoder census, following the earlier bandwidth policy.

The main comparison uses the unchanged four-frame recovery from one
acquisition-pilot-selected 20 ms excerpt per track. This is coverage of the
eligible track census, not a decode of every visit or every stored sample.
The trajectory builder is bounded, including its per-lane track limits; these
counts do not represent every satellite physically present. Two evaluation
frames must each exceed 0.5 held-pilot coherence to enter qualified comparisons.
Low-quality excerpts remain in the recovery ledger without being treated as
decoded payload.

Real-sign strings are waveform observations. Known-family matches are checked
only after independent even/odd-symbol recovery and shuffled-code controls.
Nothing here establishes message bytes, FEC/CRC validity, plaintext, a satellite
address, UTC, or orbital/position fields. A known T-code state index is not an
interpreted protocol field.

## Comparing orbit candidates

Archived production candidates are retained in two tiers. A held-out candidate
must persist as the leading candidate on held-out observations and not recommend
abstention. The stronger, **control-supported candidate** tier additionally
requires its nominal held-out negative log score to beat the stored radio-null
and both wrong-time controls. This is a comparative filter, not verified identity
or a minimum effect-size claim. The production pipeline evaluates a bounded
subset of groups; unattempted groups remain unlabeled.

Production tracking uses different minimum-track settings from the symbol
census, so raw track IDs cannot simply be joined. `bridge.py` reconstructs the
production tracks through the public default trajectory function, requires the
exact archived production ID, and uniquely matches complete visit sequences,
nanosecond support-center timestamps and normalized CFO sequences (microhertz
precision) to the census. A nearest-time or nearest-CFO match is insufficient.
The bridge plan selects recordings containing an archived cross-session repeat
candidate or a control-supported candidate, before examining correlations.
Legacy DS7/DS8 conditional annotations are separately identified.

There are no cross-session repeated identities in the archived stronger tier.
Broader candidate repeats therefore require particular caution. Different
receivers, tracks and visits within one encounter are not separate orbital
passes; a cross-session label is also not proof of an orbital repeat.

## Correlation method

The early view uses symbols 2–7 on four fixed non-pilot carriers: upper bins
486, 487, 496, 497, or lower bins 526, 527, 536, 537. Later views cover symbols
8–33, 34–129 and 130–193. Unit-phasor means are converted to centered, normalized
real/imaginary vectors. Their dot product is a phase-profile correlation, not
decoded-bit agreement. No timing, carrier or phase search optimizes these scores.

Pair comparisons use the same edge and RF channel. Each repeat's endpoint-sharing
different-candidate controls match its receiver pair, sample-rate pair,
within/cross-session status and coarse separation bin (<10 minutes, 10 minutes
to 2 hours, or >=2 hours). Duplicate census selections of the same visit/receiver
are reduced by pilot quality. Control distributions remain descriptive: pairs
are dependent, identities are conditional and matching does not remove every
confound. Pooled same/different-ID summaries can still have unequal stratum
weights and are not significance tests.

Tail-state comparisons examine whether accepted state sets intersect; they do
not assume the entire frame shares an identical payload. The early heatmaps use
average-linkage Euclidean clustering on these explicit normalized features.
They show every qualified pair separately, without averaging cells into blocks.
Satellite labels do not influence the hierarchy.

## Longer paired observations

Six existing 10 MS/s visits were recovered over their first 120 ms, yielding
89 frames per receiver and 28 common data carriers. Selection began with pilot
quality, then followed two additional visits of one orbit candidate; it did not
select by unknown-header correlation. Source candidates and timing-compatible
peer candidates are bound to the frozen analysis and raw manifests.

The changing-header assay keeps its existing protocol: at least 12 jointly
pilot-qualified frames; the first half selects variable coordinates and
confidence thresholds using RX0 alone; the later half measures RX0/RX1 sign
agreement. All nonzero cyclic frame mismatches retain the same RX0-only mask.
The coordinate-bias baseline is also reported. This is not a transmitter BER
measurement, and shared distortion cannot be ruled out solely by receiver
agreement. Raw signs, masks and `?`-marked consensus observations are preserved
under each paired visit's `summary.json`.

Known-word confirmation independently recovers the full 60-slot word on each
receiver over symbols 194–257, requires both even/odd and shuffled-control gates,
then requires exact cross-receiver equality. These are dependent observations of
the known family, not 60 newly interpreted information bits per word.

For an exploratory residual check, state is estimated from symbols 194–225,
complex gain from 226–257, and residual correlation tested on 258–289. Cyclic
mismatch controls preserve the shared subtracted pattern, which otherwise can
manufacture apparent correlation. Residual results require at least eight
eligible frames and are not a newly identified modulation alphabet.

## Reproducibility and retention

`extend.py` checkpoints census, decode, fixed-window analysis and audit stages;
`decode_available.py` consumes completed census checkpoints. `associations.py`
and `bridge.py` freeze and bind orbit candidates. `compare.py` produces joint
features, full pair correlations and hierarchies. `word_structure.py` separates
within-frame state consistency from between-frame changes. `paired_recovery.py`
and `paired_summary.py` apply the existing paired assays. `extend_repeat.py`
revisits one matched cross-session candidate pair with 14 frames.

Read-only source access uses release
`17484895464c225ebba977487aa36d3d81658bd8`, public storage readers, one BLAS thread
per worker and bounded replay jobs. There was no new RF acquisition, firmware
change or production-analysis job launched by this study. Generated numerical
artifacts, figures, raw signs, receipts and source snapshots remain under
Git-ignored `local/`. Nothing was committed or pushed.

Validation: **42 relevant tests passed**, Ruff checks passed, and the complete
350-recording audit reports no missing recordings, missing window results,
binding failures or decode exceptions. The 88 planned production/census bridge
checks completed, yielding 5,463 unique full-sequence mappings. Numerical
outputs and source versions are indexed by `local/analysis-seal.json`.
