# Native sample-rate validation: 7.5, 5 and 2.5 MS/s

## Findings

Full 60-bit repetition-pattern recovery is demonstrated in native 7.5 and
5 MS/s recordings. Native 2.5 MS/s recovery is **not validated** by this assay.
The decoder does not require a single special sample rate, but it needs enough
usable data carriers, pilot quality, and accurate timing/channel calibration.
These are physical-layer patterns, not decoded packets or parsed metadata.

| Native rate | DS7 qualified / evaluated frames | DS8 qualified / evaluated frames | Full-word observations | Distinct qualified words |
|---|---:|---:|---:|---:|
| 7.5 MS/s | 9 / 24 | 0 / 24 | 9 | 8 |
| 5 MS/s | 19 / 24 | 6 / 24 | 25 | 16 |
| 2.5 MS/s | 0 / 24 | 0 / 24 | 0 | 0 |

Frame observations within a visit are dependent; these counts are not numbers
of independent passes. The selected visits emphasize strong cached pilots, so
the fractions are not population-wide decoder success rates. Agreement between
receivers supplies corroboration, not externally known ground truth.

## What the words mean

The recovered bits describe repeated sign choices relative to a published
physical-layer reference. In the tested mapping, compact non-pilot carrier
index `n` and OFDM symbol index `i` select bit `(n - 16*i) mod 60`.
Observing enough carriers and symbols can therefore reconstruct the same
60-bit pattern from only a narrow portion of the downlink.

The evidence establishes repeatable structure. It does not establish a text
encoding, satellite identifier, timestamp, position, orbital elements, or user
message. The earlier DS7/DS8 analysis found identical words under different
geometrically inferred satellite identities; a word is consequently not a
demonstrated unique satellite ID. Structured fill in unladen allocations remains
a hypothesis, not a verified field interpretation. Displaying a word as hex or
ASCII would not by itself give it semantic meaning.

## Native acquisition and independent checks

`export_native_rates.py` uses seed 20260928 to select one complete recording
per dataset and rate, without inspecting its data bits. Within each of these
six recordings it takes the two strongest distinct visits with qualified
dual-receiver cached pilot candidates and matching epochs. It exports at most
120 ms per receiver through the public read-only storage ports, verifies the
capture manifest, and records excerpt hashes. No new RF recording is made.

| Dataset / rate | Session | Visits | Edge |
|---|---|---|---|
| DS7 / 7.5 | scan-fw-efd8e02be70ea21a | 451, 524 | upper |
| DS7 / 5 | scan-fw-02511088637aaaea | 1427, 1452 | upper |
| DS7 / 2.5 | scan-fw-43b05b5c8bab1674 | 2052, 2056 | upper |
| DS8 / 7.5 | scan-fw-aadcd44b66085469 | 716, 746 | upper |
| DS8 / 5 | scan-fw-7121c83a8ce344d7 | 1429, 1463 | lower |
| DS8 / 2.5 | scan-fw-56e1947e3011e591 | 513, 574 | lower |

`native_rate_decode.py` processes 24 frames per visit at the recorded rate.
Timing and CFO come from that native recording's cached pilot acquisition;
no high-rate acquisition, phase slope, channel estimate, or reference word is
imported. Resampling onto the 240 MHz OFDM grid interpolates the captured band;
it does not recreate missing bandwidth.

For each receiver independently:

1. Retain carrier centers within 45% of the recorded sample rate, accounting
   for the receiver's original CFO **before** digital recentering. Select only
   known pilot carriers inside that support.
2. Fit pilot frequency and frequency-dependent phase using symbols 22–301;
   reserve symbols 2–21 to check pilot coherence. Measure and correct sample
   clock drift over the 24 frames using pilots alone.
3. Randomly reserve 12 whole frames (fixed seed 20260928) for SSS channel
   estimation. Evaluate data words in the other 12 frames. Data bits never
   enter the channel calibration. Pilot drift estimation uses all 24 frames.
4. Choose a 64-symbol window using receiver 0 alone, fitting its even symbols
   and scoring its odd symbols. Recover receiver 1's word independently.
5. Require receiver-0 selection correlation above 0.25, receiver-1 correlation
   above 0.25 and above 1,000 same-weight shuffled-code controls, exact agreement
   on shared observed bit positions, and both held-pilot coherences above 0.5.
   A **full-word** candidate also requires all 60 positions observed by both
   receivers. Unknown positions remain `?`.

Qualified receiver-1 correlations range from 0.389–0.476 at 7.5 MS/s and
0.463–0.557 at 5 MS/s. The shuffled controls are diagnostic checks, not a
multiple-testing-adjusted significance claim. This is a bounded exploratory
validation, not a general-purpose production decoder or blind-acquisition test.

## Why 2.5 MS/s is harder

In a conservatively filtered pilot-centered band, 2.5 MS/s retains only two of
the neighboring non-pilot carriers used here. Under the mapping above, one
carrier visits 15 bit positions because `gcd(16, 60) = 4`. Two adjacent compact
carrier indices cover 30 positions. More integration time does not fill the
missing residue classes in this model.

Native receiver frequency offsets change this geometry. In three sampled
2.5 MS/s visits, the receivers individually cover 30 and 45 positions, sharing
only 15; in the fourth they cover 30 each with **no shared positions**. Their
combined frequency coverage spans all 60 positions, but merging those separate
pieces would remove independent receiver verification for most or all bits.
We do not present that union as a validated full word.

All 48 evaluated native 2.5 MS/s frames failed the dual held-pilot threshold.
Across the 24 processed frames per receiver/visit, median held-pilot coherence
was approximately 0.39–0.50. Shared-bit comparisons also failed the pattern
checks. Thus the failures involve signal/calibration quality as well as reduced
independent bit coverage. Different tuning, filtering, or stronger recordings
could change the outcome; these results do not prove a fundamental 2.5 MS/s
limit. No additional RF acquisition is authorized or required by this report.

## Controlled bandwidth-loss comparison

For context, `rate_validation.py` anti-aliases and downsamples two previously
qualified 10 MS/s excerpts: eight upper-edge frames and four lower-edge frames.
This diagnostic **retains high-rate timing, CFO, phase-slope, SSS calibration,
and reference-selected symbol windows**. It is not native-rate qualification.

| Resampled rate | Errors against original words, both receivers | Observed bit comparisons | Per-frame coverage |
|---|---:|---:|---:|
| 10 MS/s baseline | 0 | 1,440 | 60 / 60 |
| 7.5 MS/s | 3 | 1,440 | 60 / 60 |
| 5 MS/s | 13 | 1,440 | 60 / 60 |
| 2.5 MS/s | 49 | 720 | 30 / 60 |

The stronger upper-edge example had zero observed-bit errors at both 7.5 and
5 MS/s. These comparison counts are against prior recovered words, not an
externally certified transmitter bitstream or a general BER estimate.

## Reproduction and data handling

Scripts: `export_native_rates.py`, `native_rate_decode.py`,
`rate_validation.py`, and `test_native_rates.py` in this directory.
The exporter uses the installed storage-reader runtime recorded in the dataset
manifest. The analysis needs NumPy and SciPy. The eight focused tests check
carrier support, receiver-offset geometry, unknown slots, native-grid tone
demodulation at all three rates, and calibration with a subset of pilots.

Results and source excerpts are under Git-ignored `local/rate-validation/`:
`controlled-results.json`, `native/survey.json`, `native/summary.json`, and
per-visit `inventory.json` / `native-results.json`. Inventories bind the input
manifests and raw excerpt hashes. No raw data is committed. The previously
published paper remains a dated account of the earlier analysis.
