# GLRT acquisition and timestamp contamination diagnostic

Read-only replay of retained capture `scan-fw-4fd51c7c4c1a0273`, visits
706 and 806, native 10 MS/s, CH1 lower. Production analyzer release:
`5b75347a636fce413e7514efc2d0911d6eb7759f`.

## Updated finding: genuine RX0 signal outside the acquisition window

Further replay on September 25 recovered strong native-10-MS/s RX0 evidence
in both visits after masking timestamp words. The standard acquisition uses
a zero-centred CFO search from -400 to +400 kHz for each receiver. The genuine
RX0 pilot lies outside that domain. This is an acquisition failure, not evidence
that the native-rate GLRT cannot score the signal.

| Visit | RX0 tracking CFO | RX1 tracking CFO | Shared integer epoch | RX0 conditioned margin | RX1 margin |
|---|---:|---:|---:|---:|---:|
| 706 | approximately -524.10 kHz | +149.58 kHz | 12414 | 0.59808 | 0.74068 |
| 806 | approximately -571.58 kHz | +102.12 kHz | 8652 | 0.38816 | 0.43579 |

RX0 conditioned results search RX1's epoch +/-40 native samples and a frequency
grid centred on RX1 CFO minus 673721 Hz, +/-40 kHz in 10 kHz steps. The GLRT
then estimates residual frequency. These are diagnostic, timing-assisted
recoveries, **not** claims that the existing blind pipeline recovered both.
The detection margin gate is 0.025. Matched epochs and an approximately
674 kHz receiver-frequency difference are strong shared-signal evidence,
not independent satellite/track identification. Independent receiver/LNB
frequency offsets are a plausible explanation for the difference; their
hardware origin has not been measured here.

A clean 2.5-MS/s control, `scan-fw-84ded59806e73af6`, has strong detections
in both receivers: visit 707 has epoch 736 for both, CFOs -280644.349 Hz
and +384498.926 Hz, and margins 0.413987 and 0.442173. Visit 705 similarly
has shared epoch 2533 and a 665118 Hz receiver difference. Its timestamp
is outside the 20 ms probe; visit 707 has no identified timestamp outlier.
The two sessions were recorded at different times, so these frequency
differences should not be assumed constant across sessions.

The recorded CH1-lower LO is 960000000 Hz for the 10-MS/s example and
959687500 Hz for the 2.5-MS/s control. Moving the LO down 312500 Hz moves
the digital signal up 312500 Hz. Thus comparing rates also compares tuning:
it can move RX0 back inside the fixed search window. This mechanism is
supported by these examples, not yet quantified across the entire corpus.

Blind masked acquisition with a widened -1.6 to +1.6 MHz domain, 80 kHz
coarse spacing and 16 candidates recovers visit-706 RX0 at epoch 12414,
CFO -524145.239 Hz, fractional margin 0.581316. It still misses visit 806.
A narrower -650 to -450 kHz domain with 10 kHz spacing and 8 candidates
also misses visit 806. Consequently simply widening the range is insufficient:
timing/candidate acquisition needs investigation and regression coverage too.

Inspecting the folded anchor timing score at the recovered RX0 frequency
confirms the difference: visit 706 ranks epoch 12414 first (score 0.182884).
In visit 806 the strongest timing score within +/-5 samples of epoch 8652
is at 8650 (score 0.159936), with five other local timing peaks above it at
that frequency alone. Retention is global across timing and frequency, before
fine frequency refinement and GLRT adjudication. This exposes a concrete
shortlist bottleneck; it does not yet establish the optimal candidate budget
or timing refinement strategy.

In-memory mixing by +312500 Hz followed by the filter below and 4:1 decimation
recovers visit-706 RX0 with margin 0.528310 and CFO -211652.50 Hz (native
equivalent -524152.50 Hz). Visit 806 still fails blind acquisition. Direct
decimation without re-centring is not equivalent to the lower-LO capture;
it can discard outer RX0 pilot tones.

The previous equal-CFO cross-RX tests below tested the wrong frequency for
RX0. Their negative results do not imply that RX0's signal was absent.
The timestamp ablations remain valid for the original, different candidate.

## Earlier finding: timestamp contamination

The previously selected dual-RX positive control is contaminated by an
in-band timestamp. It must not be treated as a validated shared track.
The earlier conditioned test for the missing receiver also used RX0's own
unrelated epoch instead of RX1's epoch; that comparison was invalid.

Each row below is interpreted as four little-endian signed int16 values
`[RX0 I, RX0 Q, RX1 I, RX1 Q]`. Reinterpreting those same eight bytes as a
little-endian unsigned integer gives a sample counter:

| Visit | Local index | Four words | Decoded counter | Recorded start + index |
|---|---:|---|---:|---:|
| 706 | 92598 | -30671, -11837, 169, 0 | 729368725553 | 729368725551 |
| 706 | 1092598 | -13711, -11822, 169, 0 | 729369725553 | 729369725551 |
| 806 | 101729 | 30705, -9777, 169, 0 | 729503725553 | 729503725551 |
| 806 | 1101729 | -17871, -9762, 169, 0 | 729504725553 | 729504725551 |

Spacing is exactly 1,000,000 sample positions (100 ms). All decoded counters
are two counts ahead of the corresponding recorded coordinate. Surrounding
samples have ordinary amplitudes of tens of counts. These are digital
timestamp words, not evidence of analog clipping or AGC attack behavior.
Which layer should remove them, and the meaning of the two-count discrepancy,
remain to be traced.

## Controlled ablation

Only in-memory copies were modified. The two identified timestamp positions
were set to zero in both receiver columns; sample count and timing were
preserved. This is a diagnostic intervention, not a proposed production
repair or a reconstruction of lost IQ.

For visit 706, evaluate the original RX0 candidate at epoch 12440,
fractional offset 1.4268944787372897 samples and acquired CFO
74436.45290786665 Hz on the first 20 ms:

| Measurement | Original | Timestamp masked |
|---|---:|---:|
| RX0 exact score | 0.3133203879 | 0.0471190095 |
| RX0 control score | 0.0607768937 | 0.0373662531 |
| RX0 margin | 0.2525434941 | 0.0097527564 |

The threshold is 0.025. The claimed RX0 shared-track detection therefore
depends on the timestamp word. RX1's independently reacquired margin remains
0.740679 after masking, versus 0.740972 before masking.

At RX1's integer epoch 12414 and acquired CFO 149576.06870164236 Hz,
RX0's margin falls from 0.1363803532 to 0.0067880721 after masking.
Before masking, the affected frame contributes 38.645% of RX0's summed
coherent-ceiling weight, versus at most 8.241% for any RX1 frame.

The corrected visit-806 diagnostic searches +/-5 microseconds around RX1's
epoch at its acquired CFO, allowing the normal GLRT residual-CFO search:

| Rate | RX0 maximum integer margin | RX1 maximum integer margin |
|---|---:|---:|
| Native 10 MS/s | 0.0076313108 | 0.4356822662 |
| Filtered/decimated 2.5 MS/s | 0.0086200437 | 0.4002613721 |

This finds no RX0 recovery in the tested timing neighborhood. Batch scores
were checked against the scalar scorer at each selected maximum and agreed
to floating-point precision.

## Downsampling artifacts and limits

Filtering uses `scipy.signal.firwin(1025, 1190000, window=('kaiser', 8.6),
fs=10000000)` with `resample_poly(..., up=1, down=4, axis=0, window=taps)`.
It runs on the full 120 ms visit before analyzing the first 20 ms.
This filter is not guaranteed to preserve the newly recovered RX0 pilot's
outer tones unless the signal is appropriately re-centred first.

Blind reacquisition after downsampling can select unrelated epochs and CFOs.
For visit 806, its apparent new RX0 detection has margin 0.1532318236 on
unmasked data; after masking timestamps before filtering, the strongest
fractional RX0 margin is 0.0088318806. RX1 remains 0.400195.
For visit 706, downsampled RX0's strongest margin changes from 0.2774830970
to 0.0108756461 after masking, while RX1 remains approximately 0.6991.

Masking does not eliminate every native-rate passing candidate: native
reacquisition of visit 706 still returns another fractional RX0 candidate
with margin 0.203178. Its scientific validity was not established. This audit
establishes contamination and its causal effect on the original reported
candidate, not validity of all other candidates or a complete explanation
of the population-wide rate difference.

## Next diagnostic priorities

Make acquisition receiver-calibrated and aware of actual recorded tuning;
validate timing-basin retention rather than only increasing the CFO range.
Use strong-RX timing as a bounded diagnostic or explicit assisted-acquisition
path, while searching the other receiver's independent CFO and retaining
its own exact/control evidence. Validate against clean multi-rate positives
and negatives before changing production. Do not lower the GLRT threshold
to compensate for a missing acquisition hypothesis.

Trace timestamp framing from firmware through import and the analysis reader;
represent non-IQ words explicitly without changing the published originals or
silently shifting sample coordinates. Then replay a clean control cohort and
calibrate the GLRT against impulses, timestamp words and noise. The normalized
GLRT can be dominated by a frame or a small number of symbol correlations;
an exact-minus-control threshold alone did not reject this artifact.

No RF was collected, and no production configuration or recording was changed.
