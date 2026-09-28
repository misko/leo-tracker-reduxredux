# Repeat-pass comparison and observation frequency

This descriptive follow-up uses all 5,142 DS7 annotations and the 245 annotated
DS8 tracks from four recordings. It is not a complete DS8 satellite census.
Only `likely_conditional` DS7 and `conditional_doppler_label` DS8 assignments
are included: 2,863 tracks, 1,177 candidate identities. Names are inferred from
orbital Doppler, not decoded from the waveform.

## Counting encounters

For each identity, sort track intervals by UTC, merge overlaps across receivers,
channels and recordings, and merge gaps no larger than ten minutes. A resulting
interval is an observational encounter, not an independently confirmed orbital
pass. Repeating the calculation at five and twenty minutes gives identical
encounter counts for every identity. Track identities are deduplicated before
counting; simultaneous RX0/RX1 tracks do not count as separate passes.

| Candidate | NORAD | Encounters | Tracks | Earliest track starts, 27 September 2026 UTC |
|---|---:|---:|---:|---|
| STARLINK-31235 | 59038 | 3 | 5 | 09:12:31; 12:32:12; 14:10:26 |
| STARLINK-33826 | 63641 | 2 | 12 | 07:40:47; 12:38:22 |

STARLINK-31235 is the sole three-encounter candidate. Sixty-eight identities
tie at two encounters, and 1,108 have one. STARLINK-33826 is listed second
because it has the most qualifying tracks among the tied identities. Both
receivers contribute in each of its encounters; their validation RMS values
range from 64.6 to 132.2 Hz. STARLINK-31235 has both receivers in its first
encounter and one receiver in each later encounter, with validation RMS values
40.3–235.6 Hz. These residuals do not establish identification probabilities.

Counting track fragments instead produces a different answer:
STARLINK-32446 (NORAD 61262) has 13 tracks but only one encounter;
STARLINK-33826 has 12 tracks across two encounters.

All observations of these leaders are in DS7. STARLINK-31235's first encounter
was recorded at 7.5 MS/s and its later two at 10 MS/s. STARLINK-33826's two
encounters were recorded at 5 MS/s. Neither has a validated decoded-word
comparison in this study; they should not be conflated with STARLINK-31567.

## Decoded comparison: likely STARLINK-31567 / NORAD 59199

This remains the candidate with verified word recovery across datasets.

| Quantity | Earlier DS7 pass | Later DS8 pass |
|---|---:|---:|
| Earliest qualifying track, UTC | 13:13:42 | 18:11:10 |
| Successful decoded visits | 857, 1014 | 1246, 1389 |
| Captured edge | Lower | Upper |
| Accepted words in those visits | 9 / 16 attempted frames | 13 / 16 attempted frames |
| Distinct exact words | 6 | 11 |
| Distinct rotation/polarity-normalized families | 6 | 9 |

Three distinct exact words and three normalized families are shared. These
account for three DS7 word observations and four DS8 word observations.
The family union has twelve members, so its descriptive Jaccard overlap is
3/12 = 25%. This is not a bit-error rate, decoding accuracy, or persistence
probability: only short selected excerpts were decoded, and absence from the
other excerpt does not imply a word was absent from the full pass.

The earlier pass additionally has a rejected visit, 786, with 0/24 accepted
frames after correction. The 9/16 above is therefore conditional on the two
successful visits, not the total DS7 repeat-target attempt rate. DS8 visit
1074 lacked a qualified peer receiver. Visits 1246 and 1389 are 19.2756 seconds
apart within one pass; the earlier DS7 encounter is roughly five hours before
that pass. Satellite identity remains conditional on independent orbital fits.

Exact recurrence across passes supports repeated physical-layer structure.
It does not uniquely identify a satellite: two of these three shared words
also occur under other likely identities. Stable header semantics, time,
position and ephemeris fields remain unestablished.

## Reproduction

`compare_passes.py` writes ignored `local/pass-frequency-comparison.json`,
including complete ranked lists, intervals, receivers, residuals, threshold
sensitivity, exact shared words and input hashes. Two tests check replica
merging and nested-interval handling; both pass. No new IQ was read, no new
satellite associations were fitted, and no numerical data was committed.
