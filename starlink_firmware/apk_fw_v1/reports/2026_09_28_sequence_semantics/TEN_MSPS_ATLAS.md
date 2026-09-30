# First 10 MS/s symbol atlas: upper and lower edges

We reprocessed the existing strongest cached 10 MS/s visit at each edge,
expanding beyond the previous 24-data-carrier excerpts. Both receivers now
retain 39 supported carriers over OFDM symbols 2–301 in 89 frames per visit.
That is **4,165,200 complex observations** across four receiver/visit streams,
including known pilots and calibration frames. These are demodulated soft
observations, not that many independent bits or decoded bytes.

![Full-slice symbol atlas](local/ten-msps-atlas/atlas.png)

Green means a window is compatible with the established repeating generator;
purple means mixed/uncertain; gray means insufficient paired pilot quality.
The yellow binary-like-unresolved class has no windows in this first atlas.
Right-hand maps show centered cross-receiver complex correlation at each
data-carrier/OFDM-symbol coordinate across qualified evaluation frames.

## Selection and coverage

Selection uses the median, over existing evaluation frames, of the **weaker
receiver's held-pilot coherence**. It uses neither unknown symbols nor likely
satellite identity. We rank only existing soft caches with independently bound
10 MS/s inventories; this is not a search for the strongest recording in the
entire corpus.

| Selected visit | Dataset / edge | Session and visit | Weaker-pilot median | Qualified evaluation frames |
| --- | --- | --- | ---: | ---: |
| S23 | DS7 / upper | `scan-fw-a2d5dadd1a63c960`, visit 208 | 0.560 | 42 of 45 |
| DS9-middle | DS9 / lower | `scan-fw-fad62f2672600b46`, visit 50 | 0.625 | 45 of 45 |

The original excerpts contain 120 ms per receiver. No new collection was
performed. Excerpt hashes and cache/inventory bindings are checked. DS8 and
other cached visits remain candidates for later expansion; this first atlas
contains the two pilot-selected visits above.

The optional `all_supported_bins=True` mode in the existing native decoder
retains every in-channel FFT carrier whose original capture frequency lies
within ±0.45 times the sample rate, accounting for CFO before recentering.
The remaining 0.5 MHz at each nominal capture edge is a conservative filter
guard, not recovered bandwidth. The default decoder mode is unchanged.

Each receiver retains 39 carriers: eight pilots and 31 data carriers. Because
the receivers' CFOs differ, their supported bins differ. Paired analysis uses
the 36-bin intersection, containing eight pilots and **28 data carriers**.
Single-receiver-only bins are retained in the exported arrays, but not used
to claim independently corroborated structure.

| Visit | Additional paired data bins beyond the old cache | Mean centered correlation, new / original carriers |
| --- | --- | --- |
| S23 | 472, 473, 474, 475 | 0.296 / 0.297 |
| DS9-middle | 515, 548, 549, 550 | 0.491 / 0.495 |

Coordinates are native FFT bins. A gap in the carrier-index display corresponds
to the excluded pilot group; the numerical output preserves exact bin labels.
These averages are descriptive and do not prove individual bit accuracy.

The expanded SSS-based linear channel fit changes the original carriers' soft
values: relative RMS changes are 10.5% and 12.1% for S23's receivers, and 6.4%
and 7.0% for DS9-middle. Thus this is a separately calibrated atlas, not a
claim of bit-for-bit equivalence to the previous demodulation. All prior caches
remain intact. Channel-model extrapolation near the slice limits remains an
uncertainty even where carrier support passes the frequency guard.

## Region classification and results

Ten nonoverlapping windows cover symbols 2–301: nine 32-symbol windows and a
final 12-symbol window. In each frame/window, RX0's even-indexed window symbols
select one of the known 60 states. Acceptance requires full slot coverage in
that selection, the same independently selected state on RX1, RX0 unused-symbol
and RX1 full-window scores above 0.25, and RX1 score exceeding 99 shuffled-word
controls. Both receivers must pass held-pilot coherence above 0.5.

These are exploratory compatibility gates, not calibrated hypothesis tests.
In particular, shuffling an all-ones state cannot create distinct controls;
the strict control gate conservatively rejects such a case. No model-based
correction silently replaces stored soft symbols.

| Visit | Known-repeat-compatible windows | Mixed/uncertain windows | Pilot-quality-excluded windows |
| --- | ---: | ---: | ---: |
| S23 | 358 | 62 | 30 |
| DS9-middle | 412 | 38 | 0 |

The first window, symbols 2–33, is unresolved in 36 of S23's 42 qualified frames
and 29 of DS9-middle's 45 frames. Some unresolved windows extend later: S23 has
isolated failures as late as the 162–193 window, and DS9-middle as late as
98–129. All subsequent windows in these selected excerpts satisfy the repeat
compatibility gates. These observations nominate early regions for finer
analysis; they do not establish precise allocation or packet boundaries.

**Green is a window-level result, not a per-symbol decode.** A repeating
component can dominate a window containing other symbols. Purple can reflect
changing signal, interference, calibration error, a mixture, or insufficient
evidence. It is not a higher-order-QAM or encrypted-payload classification.
The axis-purity fallback is only a heuristic and supplies no constellation
order here.

## Artifacts, limitations, and next target

The ignored `local/ten-msps-atlas/` directory contains:

- `S23.npz` and `DS9-middle.npz`: all retained complex symbols, per-receiver
  carrier coordinates, calibration/evaluation frame lists and pilot diagnostics.
- `*-maps.npz`: classification maps, exact evaluation-frame indices, data bins,
  pilot quality and per-coordinate cross-receiver correlation.
- `atlas.json`: complete candidate ranking, raw-source bindings, expanded-cache
  hashes, per-window scores, state hypotheses and controls.
- `atlas.png`: the overview figure.

`ten_msps_atlas.py` reproduces the atlas from the original excerpts or its bound
expanded caches. Twelve focused tests pass: native-rate scientific guards,
full-slice frequency support, independent-receiver/unused-symbol acceptance,
and rejection of incomplete slot coverage. Ruff passes. Numerical data and
figures remain excluded from Git; no commits, remote changes or RF collection
were performed.

This atlas covers post-SSS OFDM symbols, not PSS or guard-interval waveform
recovery. Upper and lower visits are not simultaneous and cannot reconstruct
one combined RF frame. We have no newly verified message bytes, identities,
timing fields or FEC decode. The next concrete target is the first 128 symbols,
with finer windows and carrier-resolved residual tests that keep known-repeat
fitting separate from the observations being tested.
