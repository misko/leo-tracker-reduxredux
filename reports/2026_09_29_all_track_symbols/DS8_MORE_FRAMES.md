# More frames recover additional qualified DS8 observations

Reprocessing the same selected 20 ms excerpts with up to 14 frames makes seven
additional candidate-labeled DS8 tracks pass the existing requirement of at
least two pilot-qualified evaluation frames. Nine of 72 tracks now pass,
compared with two previously. Seventeen accepted 60-bit candidates match the
already known generator family. No new field meaning or independent payload
bit has been established.

## Controlled inputs and scope

Use all 72 exactly bound conditional DS8 candidate tracks, including the two
previously qualified tracks, across four recordings. The underlying public
read-only input and IQ adapters, track reconstruction, candidate selection,
20 ms excerpt selection, native demodulator, pilot threshold (>0.5), and fixed
64-symbol word assay are unchanged. Recover up to 14 frames instead of four.

For every track, the new receipt's selected candidate ID, track ID, and raw
excerpt SHA256 match the original result. All new artifact hashes were checked.
Original census data and labels were preserved; the rerun uses a separate
ignored output directory. The four captures completed without decode errors,
using two worker processes and a 20-minute timeout. This was offline analysis;
no new RF was collected.

Seventy-one tracks provide 14 complete frames; one provides 13 after the
decoder's end guard. That is 1,007 recovered frames, with seven evaluation
frames per track (504 total). The remainder supply SSS channel calibration.
The sample rate is 10 MS/s throughout this selected DS8 subset.

## Qualification versus calibration

| Transition | Tracks |
|---|---:|
| Insufficient pilots → qualified | 7 |
| Insufficient pilots → insufficient pilots | 63 |
| Qualified → qualified | 2 |

The rule remains at least two evaluation frames exceeding 0.5 pilot coherence.
However, there are now seven opportunities instead of two. Therefore the
qualification increase must not be described as a controlled calibration gain.

Frame index 3 is the only evaluation frame shared by both decoder splits for
each track. Across these 72 matched frame observations, threshold passes change
from 6 to 7. The median coherence change is 0.0000047; the 5th–95th percentile
range is −0.00249 to +0.00471. The main benefit is recovering usable frames later
in the same excerpt, rather than a large improvement to the original frames.
The new decoder's pilot retiming and SSS fit use more frames, so the recovered
symbols are separately calibrated observations, not an appended old array.

## Qualified candidate tracks

| Original census track | Conditional satellite candidate | Qualified evaluation frames |
|---|---|---|
| DS8-F017-T0000 | STARLINK-35850 | 5, 11 |
| DS8-F017-T0001 | STARLINK-35850 | 2, 3, 8 |
| DS8-F017-T0003 | STARLINK-35850 | 3, 10 |
| DS8-F017-T0007 | STARLINK-34992 | 3, 5, 10 |
| DS8-F017-T0036 | STARLINK-31567 | 2, 5 |
| DS8-F027-T0002 | STARLINK-34271 | 2, 3, 5, 10, 11 |
| DS8-F027-T0021 | STARLINK-31643 | 5, 8 |
| DS8-F039-T0005 | STARLINK-30711 | 2, 3, 5, 10, 13 |
| DS8-F039-T0039 | STARLINK-31407 | 2, 3, 5, 8, 10, 11, 13 |

Frame indices are local to each selected excerpt and do not establish equal
transmit times between tracks. Multiple tracks with one candidate label are
not automatically separate passes or independent satellite-ID confirmations.

## Word recovery and next use

Accepted words use the existing symbols 194–257 assay: complete slot coverage,
even/odd agreement, score threshold, and shuffled-code controls on each
pilot-qualified frame. All 17 accepted strings are exact members of the known
60-state family. They are single-receiver candidate observations, not newly
receiver-confirmed messages; repeated patterns do not supply 17 × 60 independent
information bits.

The original four-frame run accepted seven words in this same track subset;
the longer run accepts 17, but the calibration and evaluation partition change,
so this is a count comparison rather than a claim of ten distinct new words.
Sixteen new-run observations belong to the nine qualified tracks; one comes
from a track with only one qualified frame. There are 36 qualified evaluation
frames in total across all 72 tracks.

The added usable observations make selected DS8 tracks available for further
paired-receiver and repeat-visit checks. Those checks must use explicit frame
timing and retained conditional labels. The 63 remaining failures apply to this
selected excerpt, not every visit or all raw recordings of those tracks.

## Reproduction and validation

`extend_ds8_frames.py` reuses the unchanged census decoder with a separate output
root and frozen track subset. It requires the pinned installed reader environment
and read access to the existing corpus. `compare_ds8_frames.py` validates identical
inputs and summarizes common held frames. The plan, index mapping back to original
track IDs, receipts, words, soft symbols, and comparison are under ignored
`local/ds8-fourteen-frames/`.

All 33 existing research tests and Ruff checks pass. The run additionally verifies
all 72 track/candidate/excerpt bindings and saved artifact hashes. No data were
committed and no remote or deployed service was changed.
