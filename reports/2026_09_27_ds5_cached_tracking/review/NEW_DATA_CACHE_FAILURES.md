# New-data failed-cache coordinate diagnostic

This receipt-only, post-outcome diagnostic classifies the 52
`failed_prediction` rows in `new_data_v6.json`; 38 have an independent positive
reference. It did not open IQ, rerun a detector, change policy, or tune a
threshold.

The predicted coordinate was compared with the independent reference in common
source coordinates. Timing uses the circular 750 Hz frame period across 20 ms
windows; CFO uses physical tracking CFO. The frozen association remains timing
within 2 microseconds and CFO within 8 kHz.

## Coordinate classification

| Population | Count | Prediction already associates | Strict local-correction envelope | CFO-compatible, timing outside 2 us | Timing and CFO both outside |
|---|---:|---:|---:|---:|---:|
| All failed cache checks | 52 | 24 | 2 | 12 | 14 |
| Reference-positive failures | 38 | 22 | 2 | 12 | 4 |

The all-failure row also contains two nonpositive references whose timing is
within 2 microseconds but CFO is outside 8 kHz. Of the 24 associated predictions,
22 are outside the strict local-correction envelope.

`known_state_v2.c` evaluates timing at offsets -1, 0 and +1 sample. It accepts a
timing fit only when the center cell is best, then clamps its log-parabolic
correction to +/-0.5 sample; an edge maximum sets `TIMING_REACQUIRE`. Only two of
the 38 reference-positive failures are within that +/-0.5-sample envelope while
also within 8 kHz. Three fall somewhere in the full probed +/-1-sample span, but
the third is outside the accepted center-bracketed correction range. These are
coordinate eligibility counts, not claims that local recovery will produce a
positive score. The separate unchanged-algorithm recovery replay is the valid
empirical check because GLRT peak shape and evidence also determine its result.

Sixteen reference-positive failures are outside the original 2 us/8 kHz
association. Twelve retain CFO compatibility but have a different timing phase;
four differ in both timing and CFO. The other 22 reference-positive failures
already select the independently fitted hypothesis by the declared association,
so a larger hypothesis bank does not address their failed evidence.

## Causal multi-hypothesis upper bound

For each of those 16 switches, earlier reference-positive observations were
considered only for the same session, receiver, channel, edge and rate. This
preserves time order, but reference outcomes are unavailable to a real strategy,
so both counts below are oracles:

- Two of 16 have an earlier observation within two seconds that directly
  predicts the current reference within 2 us/8 kHz without fitting a rate.
- Thirteen of 16 have an earlier observation compatible with the frozen
  learning envelope: at most 2.12 seconds old, 50 ppm timing motion, and
  `5 kHz/s * age + 2 kHz` CFO motion.
- Three have no compatible earlier positive reference under those bounds:
  visit 1109, RX0/channel 4 at 2.5 MS/s; visit 1089, RX1/channel 1 at 5 MS/s;
  and visit 1126, RX1/channel 4 at 5 MS/s.

Thus a causal multi-hypothesis cache is plausible for trajectory returns, but
13 is only an optimistic upper bound. It selects the compatible historical
hypothesis using the current independent reference, assumes a bank retained it,
and does not define causal clustering, eviction, scoring, or ambiguity handling.
It cannot be counted as 13 recovered visits. At least the three history-novel
switches still require acquisition under the frozen bounds, and the 22 failures
whose prediction already associates require better evidence or recovery rather
than another cached trajectory. No runtime strategy or 10x claim should use
these oracle labels without a preregistered causal implementation and replay.

The complete row-level errors and prior-history identifiers are in
`new_data_cache_failures.json` (SHA-256
`71165dcd3131c462f7c7ddd4744bc74229e237c49c32f12743b6efb14df3cbf2`).
Its generator is `review/new_data_cache_failures.py` (SHA-256
`1c7f129c8e12d276e71bc3a20a4813968336566d4cbf96c21986afb0199d7cb2`).

