# Field localization from held-out Doppler arc endpoints

The receiver published 8 fixes in 11 StarLoc queries with the correct
25 km square offered, covering six of eight nearby physical site groups.
All eight fixes were within 5 km. Median error was 2.593 km and P95 was
3.874 km. It withheld all 11 paired queries with the correct square
omitted. The frozen receiver withheld all 22. The endpoint rule also
published six false fixes in 40 simulated missing-region queries, so
the evidence supports localization on the StarLoc records while the
rule fails the broader withholding requirement.

## Observable and timing audit

StarLoc used zenith-pointed Ku-band horns, downconverters and USRPs on
a common reference clock. The source extracts a measured FFT bin
detected by all three receiver chains. Its processed archive stores
time since capture start and measured baseband Hz in the first two
columns of each main-tone record. Only those columns enter this
experiment. Array phases, GNSS, source satellite IDs and antenna
pointing are absent from inference. The source documents predeclared
track windows but does not document how they were chosen.
[StarLoc paper, sections 4 and 5](https://arxiv.org/html/2604.21147v1#S4) ·
[Pinned data contract](https://github.com/GiddaZhang/Starloc/blob/fc010f950dfac5ac6d7a345db24513217fbb81d5/data/README.md) ·
[Source extraction](https://github.com/ConnectedSystemsLab/starloc_preproc/blob/main/starlocProcessRawSignal/utils/track_centertones.py)

The audit read all 11 original MAT files, their archived orbit releases and
the SDR UTC start table. It regenerated all 80 public tracks exactly at
the frozen rounding precision, and regenerated every supplied catalogue
byte for byte. Every track used the nominal 11.325 GHz RF, with increasing
relative times within 0.5 µs of the 7 ms FFT-hop lattice. Submitted tracks
ranged from 15.18 to 47.13 s, with a 32.74 s median and a median of
61.5 retained samples. The largest within-track gap was 10.28 s. All
linear slopes were negative, from −3,399 to −2,989 Hz/s, consistent with
the sign and scale of range-rate Doppler from fast overhead passes.
Median per-track residual RMS was 229 Hz after a line and 84 Hz after a
cubic. The cubic describes a smooth measurement and includes any
smooth receiver or extraction error. The source time agreement and
causal elements exclude an obvious input-unit or sign repair. Exact
catalogue retrieval times depend on the source's documented
capture-start availability. [Observable audit](source_audit.json) ·
[Original field provenance](../../2026_11_18_blind_regional_receiver/field_private/provenance.md)

The original chronological split requires four complete tracks in each
half of a 900 s capture. Only one acquisition meets that requirement. The
other ten each supply 4–8 tracks in total yet fail the split. The
predeclared rule fits a point in each square from the first two-thirds
of each arc and scores the later samples with the identified orbit,
frequency bias and time shift held fixed. A region needs predictive
support from at least three distinct catalogue objects and a lead over
the other offers. Publication also requires a point more than 1 km
inside the square. Withholding leaves the best nominated point
available as a diagnostic. [Predeclared rule](predeclared.md)

## Position publications

Each panel contributes a paired present and missing query for every
acquisition. Both methods used the same observations, catalogue and
offers per query. Errors below are for published fixes in kilometers.
The Altrincham controls contained zero tracks.

| Panel and offer | Attempts | Frozen fixes | Frozen median / P95 / max | Endpoint fixes | Endpoint within 5 km | Endpoint median / P95 / max |
|---|---:|---:|---:|---:|---:|---:|
| StarLoc present | 11 | 0 | — | 8 | 8 | 2.593 / 3.874 / 4.010 |
| StarLoc missing | 11 | 0 | — | 0 | 0 | — |
| DS29 present | 8 | 5 | 4.076 / 6.129 / 6.560 | 7 | 3 | 5.343 / 5.983 / 6.055 |
| DS29 missing | 8 | 0 | — | 0 | 0 | — |
| Synthetic present | 40 | 15 | 2.673 / 6.209 / 6.964 | 36 | 26 | 3.600 / 10.012 / 12.155 |
| Synthetic missing | 40 | 0 | — | 6 | 0 | 7,257.729 / 10,078.587 / 10,981.843 |
| Altrincham present | 3 | 0 | — | 0 | 0 | — |
| Altrincham missing | 3 | 0 | — | 0 | 0 | — |

For the StarLoc present queries, the 11 forced endpoint positions had
median/P95/max error of 2.853/7.146/8.386 km. The corresponding
frozen values were 3.045/6.175/6.457 km. All three endpoint position
withholdings were boundary decisions. The forced endpoint positions on
the 11 StarLoc missing offers had median/P95/max of
51.244/205.591/279.995 km. The score file gives complete distributions
for both arms, including forced outputs and unavailable estimates.
[Independent scoring and per-query diagnostics](scores.json)

## Region selection and frequency fit

The region check refers to the score and track-support criteria before
the position boundary check. On present offers use the sealed region
identifier. On missing offers every accepted region is incorrect.

| Panel | Present, correct region nominated, frozen / endpoint | Present, correct region passed check, frozen / endpoint | Missing, false region passed check, frozen / endpoint |
|---|---:|---:|---:|
| StarLoc | 11/11 · 11/11 | 1/11 · 11/11 | 1/11 · 5/11 |
| DS29 | 8/8 · 8/8 | 8/8 · 8/8 | 2/8 · 4/8 |
| Synthetic | 40/40 · 40/40 | 32/40 · 40/40 | 0/40 · 11/40 |
| Altrincham | 0/3 · 0/3 | 0/3 · 0/3 | 0/3 · 0/3 |

The boundary check withheld every incorrect StarLoc and DS29 region
that passed the region check. Six synthetic wrong-region nominations
survived that check. The selected present StarLoc regions had a median
held-out lead of 0.253 over the next offer. The corresponding median
selected endpoint RMS was 163 Hz, computed only from supported held
samples. On 10 missing offers with a reported RMS the median was
315 Hz. The eight published StarLoc fixes had median held RMS of
159 Hz. These measurements quantify frequency prediction on a
conditionally supported subset. Position errors come from the
independent coordinate scorer.

At each fixed RF the additive calibration coefficient contributes a
constant to an arc. Its fitted training frequency offset absorbs that
constant, including when the offset is carried to held samples.
Both calibration arms have identical positions, decisions and
frequency residuals on all 124 queries. No site-specific coefficients
were fitted. The synthetic unit tests verify a known-position recovery,
withholding without the correct tile, matching after a fixed RF offset,
and independence of training nominations from endpoint frequencies.

## Scope and reproducibility

The experiment used an existing retrospective benchmark. The score
rule was written before the new coordinate and region results were
opened. All 124 input hashes match the previous transfer benchmark.
A rerun after source formatting yielded identical non-timing outputs
for all 124 queries. The holdout samples share the same extraction
and orbit propagation as the training samples, so the experiment
measures temporal prediction within tracked arcs. The 11 measured
captures share one array, one RF and one metropolitan area. The
position result begins with prepared tracks, with no measurement of
raw-IQ throughput or on-target latency.
[Predictions](arc_validation.jsonl.gz) · [Timing and error summary](transfer-summary.json) ·
[Implementation and prediction hashes](seal.json)

The [fresh synthetic confirmation](confirmation/README.md) repeated the
same offer design and simulator with a new seed. It reproduced the higher
within-5-km count and the missing-region publication failure.

Set `PIPELINE_EVAL_BLIND_ROOT` to the original blind study directory when its public
packets and sealed scoring records are on a separate corpus mount.
From the repository root, use the original mounted input paths and
one numerical thread per worker. The optional audit requires the
local StarLoc release files and its UTC start table.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m tools.pipeline_eval.qualification.field_shapes predict /tmp/arc-validation.jsonl.gz --jobs 4
.venv/bin/python -m tools.pipeline_eval.qualification.field_shapes score \
  /tmp/arc-validation.jsonl.gz /tmp/arc-validation-scores.json --summary /tmp/arc-transfer-summary.json
.venv/bin/python -m tools.pipeline_eval.qualification.field_shapes audit \
  /tmp/blind-starlink-field.OW2vZA2s /tmp/arc-source-audit.json
```
