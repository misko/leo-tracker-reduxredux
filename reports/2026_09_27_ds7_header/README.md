# DS7 public pilot and unencrypted-header investigation

**Latest result:** [Raw data recovery and field interpretation](DATA_RECOVERY.md)
reports complete 60-bit repetition patterns verified independently by both
receivers in 38 frames from two visits, with a prospectively validated even-parity
relation. Satellite/time/orbit fields remain
unresolved. All IQ and derived data remain ignored under `local/`.

**Follow-up:** [Pilot-aided post-SSS recovery](RECOVERY.md) now establishes
eight-symbol template structure and exports calibrated soft symbols after
correcting timing drift. Hard decisions remain noisy. The initial negative
assay below is retained as the earlier result, not the latest conclusion.

## Motivation

Locate publicly predictable signal content and test whether DS7 contains the
header structure reproduced in the [clean UT recording](../2026_09_27_ut_header/README.md).

## Problem

DS7 contains narrowband, hopping recordings. Public known pilots, a detected
header structure, decoded header bytes, and interpreted metadata are different
claims. A pilot match does not identify a satellite or expose user traffic.

## Solution

**Public known-pilot content was isolated and replayed successfully. No
unencrypted header or metadata field was recovered by this bounded test.**

All 88 source manifests matched the frozen DS7 digests. Sample rates are:
19 recordings at 2.5 MS/s, 27 at 5 MS/s, 23 at 7.5 MS/s, and 19 at 10 MS/s.
Configured targets cover the upper/lower edges of channels 1–4. This metadata
audit is not a waveform analysis of all 88 recordings.

Waveform analysis used four distinct, strongest cached upper-edge pilot visits
in **scan-fw-a40658642d9ade6a**, at 10 MS/s. Four 20 ms single-receiver excerpts
contain 80 ms total IQ, covering 56 complete predicted frame windows. Selection
used pilot evidence only; it deliberately favors good signal and is not a
representative dataset sample. The reader verified the source chunk digests.

| Visit / receiver | RF tuning | Known-pilot replay | Wrong-pilot control | Header score, pilot-selected frame |
|---|---|---:|---:|---:|
| 2022 / 0 | 11.690 GHz | 0.8324 | 0.0495 | 0.1670 |
| 1969 / 0 | 11.690 GHz | 0.8306 | 0.0524 | 0.1546 |
| 1989 / 0 | 11.690 GHz | 0.8183 | 0.0428 | 0.1924 |
| 1482 / 1 | 11.190 GHz | 0.8165 | 0.0426 | 0.1149 |

Pilot scores are the existing conditioned GLRT-64 statistic, not probabilities,
bit accuracies, or SNR. Header scores are a different statistic: the mean BPSK
axis concentration after removing the published template, over symbols 2–9.
The pilot-selected frames' largest wrong-template header controls were
0.265–0.284. Across all 56 DS7 frame candidates, the header mean was 0.112–0.261.
There is no positive header finding here.

For comparison, real UT IQ filtered and decimated to the same 10 MS/s upper-edge
slice gave 0.929–0.948 on frames 250–255 versus at most 0.341 for the controls.
Frame 256's shorter header gave 0.745 over the same eight-symbol window. The UT
control used known full-band timing/CFO: this demonstrates restricted-band
demodulation, **not independent narrowband acquisition**. It also reuses the
published template's reference corpus, not an independent holdout.

## Method

1. Inspect all source manifests using DS7's pinned storage-reader release
   `17484895464c225ebba977487aa36d3d81658bd8`, with `read_only=True`.
2. Rank cached upper-edge candidates in the selected recording by fractional
   pilot margin; export the top four distinct visits, one receiver per visit.
   Each source visit is 120 ms, dual receiver. The four verified decompressed
   chunks total 38.4 MB; retained original excerpts total 3.2 MB.
3. Replay `conditioned_glrt64_score` on the retained IQ. All four exact/control
   pairs reproduced their cached values exactly, confirming the public known
   pilot structure in those excerpts under the existing assay.
4. Mix each excerpt by its cached pilot CFO, low-pass/decimate by five, and save
   complex64 pilot-band IQ at 2 MS/s. This isolates the band, not an individual
   emitter or an exclusive plaintext channel: interference can remain.
5. For the separate header assay, interpolate the captured 10 MHz band to
   240 MS/s, put it on the native OFDM frequency grid, and FFT inside the cyclic
   prefix. Interpolation supplies no missing spectrum. Use SSS-based per-bin
   equalization and bins 476–487 plus 496–507 (24 non-pilot subcarriers). Exclude
   pilot bins 488–495 explicitly. No header-template phase or timing fitting.
6. Test predicted complete frames at the cached epoch plus multiples of 1/750 s.
   Report every frame's eight-symbol score. Select one displayed frame per
   excerpt by the pilot matrix's rank-one energy fraction, without using header
   scores. Wrong-template controls use 100 temporal shifts, 11 through 110,
   without refitting equalization.
7. Run the same header demodulator on genuinely filtered/decimated UT IQ; test
   synthetic OFDM header/payload discrimination and a noise null.

The new SSS-equalized pilot coherence is only 0.319–0.437 in the selected DS7
frames, and the pilot matrix's rank-one energy fraction is 0.353–0.369. Thus the
new demodulator's phase/channel calibration is not qualified on DS7 despite the
successful native pilot replay. Timing/CFO alias transfer, SSS visibility,
interference, and waveform differences remain unresolved. The result cannot
establish that headers are absent, encrypted, or intrinsically unrecoverable.
No FEC/CRC, satellite ID, position, absolute time, or orbital fields were decoded.

## Isolated regions and local data

Everything under [local/](local/) is git-ignored; no source or derived IQ is
staged or committed. The eight pilot subcarriers coexist in time with other
content, so there is no time-only cut that makes an entire wideband sample
"unencrypted."

- `inventory.json`: frozen-manifest binding, all 88 configurations, excerpt
  provenance, original visit counters, cached candidates, and IQ digests.
- `visit-*-rx-*.npy`: original 10 MS/s int16 arrays, shape (200000, 2), I then Q.
- `visit-*-rx-*-pilot-band-2Msps.npy`: 2 MS/s complex64 pilot-centered excerpts,
  40000 samples each. Mixing center is the cached CFO in `inventory.json`;
  nominal eight tone offsets are −820312.5 to +820312.5 Hz in 234375 Hz steps.
  Polyphase filter transients affect excerpt boundaries.
- `regions.csv`: 56 predicted frame epochs and sample intervals for candidate
  header symbols 2–9 and known-pilot symbols 2–65, plus subcarrier indices.
  Coordinates are relative to each exported excerpt; fractional bounds are
  retained. Header regions are explicitly `not_confirmed`. Pilot support was
  verified in aggregate, not independently at every listed frame.
- `pilot-replay.json`, `results.json`, `ut-control.json`: separate numerical
  results; `demodulated.npz` contains complex FFT outputs on the 24 tested bins,
  not decoded bytes. `comparison.png` visualizes the result.
- `SHA256SUMS`: scripts and numerical artifact fingerprints.

## Reproduction and next experiment

### Side-by-side IQ plots

`plot_iq.py` compares visit 2022/RX0, candidate frame 2, with UT frame 250.
Both are processed at 10 MS/s around the upper pilot band. It writes the ignored
`local/iq-waveforms.png` (I/Q traces, time-domain clouds, normalized spectra),
`local/iq-header-constellations.png` (SSS-equalized non-pilot header candidates
before/after reference-template removal), and `local/iq-plot-provenance.json`.
Run with the same NumPy/SciPy/Matplotlib environment as `summarize.py`.

Power is independently RMS normalized; the analog receiver responses are not
matched. Constellations normalize RMS and phase per symbol, use identical
axes, and explicitly count points outside those axes. Color indicates OFDM
symbol. UT synchronization comes from the previous full-band solution; DS7
uses cached pilot timing/CFO. Thus the pictures compare the current processing
outputs, not calibrated receiver performance or encryption status. The plots
do not replace the four-excerpt, 56-frame numerical investigation above.

Run `export.py` and `replay_pilots.py` with the pinned release's Python and
read access to `/srv/bulk/leo`. They read source storage and write only this
report's ignored local directory. Source metadata inspection/export is bounded
to 120 seconds and pilot replay to 60 seconds in the recorded execution.

Run `analyze.py`, `control.py`, and `summarize.py` with NumPy, SciPy, and
Matplotlib; the UT files cataloged in the literature folder must already exist.
For example, from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_27_ds7_header/analyze.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_27_ds7_header/control.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_27_ds7_header/summarize.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_27_ds7_header -p 'test_*.py'
```

The next useful step is to transfer the native pilot timing/frequency convention
into the OFDM/SSS demodulator and qualify it against known pilot symbols on these
same four excerpts. Only then widen the header search to additional DS7 visits
and bandwidths. No new RF collection is required.
