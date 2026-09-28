# Lower-edge validation and the STARLINK-31567 repeat pass

We now recover validated 60-bit words from both DS7 and DS8 observations
independently associated with **STARLINK-31567 / NORAD 59199**. Three exact words
recur across the two passes, roughly five hours apart. This supports recurring
signal structure across a likely satellite's passes, not a unique identity code.

## What changed

The original UT raw-IQ control was inappropriate for the T-code test: its seven
frames did not contain the long contiguous T-code blocks assumed by the
64-symbol window decoder. The upper-edge control also gave low scores. That
failure did not isolate a lower-edge demodulation problem.

We separated two checks:

1. **Raw waveform demodulation:** use known pilots at each edge, fit symbols
   22–301 and reserve symbols 2–21. Across the seven UT raw frames, lower-edge
   held-out pilot correlation is **0.966–0.970**, versus at most **0.180** for
   100 shifted-sequence controls. Upper-edge correlation is 0.978–0.984, with
   controls below 0.197. This checks demodulation of known symbols, not full
   T-code recovery from these raw frames.
2. **Code mapping:** download only **122,181 bytes** via bounded HTTP ranges
   for the lower edge of published UT hard-decoded frames 806–818. Source ETags
   match the previously obtained upper-edge reference; local files are hashed.
   Select the code and 64-symbol window using the upper edge only, then predict
   the lower edge without fitting it. The simple periodic mapping
   `T[(n - 16*i) mod 60]` yields correlations **0.9948–0.9974** in all 13 frames.
   The earlier finite 1004-element wrap mapping yields only 0.435–0.547 without
   refitting its phase. It was rejected. The corrected mapping observes all
   60 code slots in the lower narrow band, rather than the 52 predicted by the
   rejected model.

The corrected mapping is exactly equivalent to the existing upper-edge model
at all previously used bins and symbols. The primary raw DS7 decoder otherwise
retains its known-pilot calibration, independently estimated receiver channels,
receiver-held-out correlation, 1,000 wrong-code controls and exact bit agreement.
No decoded identity, orbit label or desired shared word guides bit decisions.

## Bounded DS7 retries

The initial DS7 visit 786 remains rejected: 0/24 frames pass after the mapping
correction. A diagnostic known-pilot-only channel estimate also yields 0/24;
these are alternative analyses of the same frames, not independent trials or
accepted observations. Their SSS channel estimates are poorly coherent.

Two other already-labelled DS7 tracklets were selected before reading their
bits, then their strongest bound cached pilots selected the visits below.
All are existing recordings; no new RF was collected.

| Dataset | Visit | Captured edge | Accepted frames | Distinct families |
|---|---:|---|---:|---:|
| DS7 | 1014 | Lower | 4 / 8 | 4 |
| DS7 | 857 | Lower | 5 / 8 | 3 |
| DS8 | 1246 | Upper | 7 / 8 | 6 |
| DS8 | 1389 | Upper | 6 / 8 | 6 |

The DS7 rows together contain nine codewords from six families. The DS8 rows
contain thirteen codewords from nine families. Across both passes there are
22 accepted observations and twelve families. Three families—and three exact
unrotated, uninverted words—are shared:

```text
001101011101001111110101011111011101010110011101111100010101
001101110101100111010101101101010101001101011111110101010101
111111010101101101111111011111011111010101110101100111111111
```

The first word also occurs under likely NORAD 57526. The third occurs under
likely NORAD 57526 and 59250 as well as 59199. Thus repeat-pass recurrence does
not make these words unique satellite identifiers. The identity association
remains based on orbital Doppler evidence, independent of the bits.

Header-symbol signs in these lower-edge excerpts fail strict agreement across
receivers and time splits. Also, lower- and upper-edge header samples cover
different subcarriers and cannot be directly equated. No satellite-ID, time,
position or orbital field is interpreted by this follow-up.

## Evidence

- `local/raw-ut-demodulation-check.json`: raw-IQ hash, known-pilot validation
  and shifted-sequence controls.
- `local/ut-lower-inventory.json` and `ut-lower-reference-check.json`: range
  extraction provenance and upper-to-lower prediction scores.
- `local/repeat-ds7-selection.json`: the two additional tracklet selections.
- `local/repeat-4/` and `repeat-5/`: source-bound inventories, raw excerpts,
  soft evidence, receiver checks and decoded words.
- `local/repeat-binding-verification.json`: independent reconstruction checks
  connecting each decoded acquisition solution to its labelled persistent track.
- `local/lower-retry/` and `lower-pilot-only/`: preserved rejected trials.
- `local/decoded-bits.csv` and `joint-results.json`: expanded joint results,
  now **85 accepted codeword observations and 27 families**.

All numerical data and raw excerpts are ignored by Git. No data was committed.
