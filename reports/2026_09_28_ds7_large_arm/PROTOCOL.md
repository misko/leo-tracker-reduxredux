# Larger DS7 full-search versus reduced ARM recovery experiment

## Selection

Use eight visits from every one of the 88 minted DS7 recordings, selected at
the midpoint of each of eight equal chronological strata. Avoid the earlier
28-visit smoke cohort with a deterministic index adjustment. No GLRT outcome
participates in selection. Freeze the visit indices and source manifest hashes
before reading the selected IQ or running either detector.

The resulting 704 unique, dual-receiver, 120-ms dwells are 25.14 times the
previous sample. They represent 84.48 seconds of recorded dwell time and
0.361% of DS7's 194,934 published visits. Covering all recordings does not mean
processing all DS7 data. This is a development cohort, not a hidden holdout.

| Rate | Recordings | Selected dwells | Full-search receiver/windows | Native selected receiver/windows |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 19 | 152 | 3,344 | 304 |
| 5 MS/s | 27 | 216 | 4,752 | 432 |
| 7.5 MS/s | 23 | 184 | 4,048 | 368 |
| 10 MS/s | 19 | 152 | 3,344 | 304 |
| Total | 88 | 704 | 15,488 | 1,408 |

There are 440 upper-edge and 264 lower-edge dwells. All eight target indices
are represented. IQ extraction uses the public read-only recording reader.
Every selected payload is bound by SHA-256 and source counters; no whole-corpus
IQ integrity claim is made. The extracted dual-CI16 inputs occupy
4,185,600,000 bytes before NPY headers.

## Methods and hardware

The full original method runs its eleven overlapping 20-ms probes per
receiver, with starts 0, 10, ..., 100 ms, and up to eight acquisition
candidates per probe. Eight independent server processes execute the original
scientific baseline. Parallel scheduling does not change its search and is
not an ARM runtime measurement.

The unchanged `goal40mag` native binary runs on physical PLUTO+ 192.168.1.15,
CPU0. Per receiver it ranks six non-overlapping 20-ms intervals, then executes
the full native confirmation for one selected interval. The same exact and
control templates used by the qualified native experiment are selected by
each input's sample rate and edge and hash-verified on the device.

Each ARM process reads a batch of eight saved dwells into RAM, warms each once,
then emits one measured result per dwell. Warmup executions are excluded from
the unique scientific counts. The 1,408 selected receiver/windows therefore
mean unique scored intervals, not total physical calls including warmup.
No simultaneous radio capture or synthetic RAM producer runs in this quality
experiment, so every selected dwell is processed without queue admission loss.
Neither firmware nor source recordings are changed.

## Denominators and matching

Report these separately:

1. Unique receiver-specific 20-ms windows evaluated.
2. Windows with at least one positive GLRT candidate.
3. Individual positive GLRT candidates, including separate returned candidate
   hypotheses even when their timing/frequency values coincide.
4. Baseline-positive windows selected by ARM; positive again in ARM; and
   containing a matched baseline detection.
5. Individual baseline-positive candidates recovered one-to-one by ARM.

The baseline uses its serialized `passed_margin_gate` (margin >= 0.025).
Native positives require completed fractional refinement and margin > 0.025.
The scorer counts any exact-boundary cases rather than silently changing
either method's decision rule.

Recovery requires the same source visit, receiver, and 20-ms window start.
Positive hypotheses match within 2 microseconds in timing and 8 kHz in
tracking CFO. ARM timing includes its fractional offset. Maximum-cardinality
one-to-one matching prevents one ARM result from recovering several baseline
hypotheses. A positive elsewhere in the dwell does not recover a skipped
window. An unmatched ARM positive is not automatically a false alarm.

Both methods must finish the complete planned inventory before the final
score is issued. Missing, failed, duplicated, or unbound results are errors,
not opportunities to reduce the denominator. Transport continuations retain
explicit provenance; see `TRANSPORT.md`. No quality equivalence or 80%/90%
recovery target is assumed from the previous native-baseline speedup.
