# Exhaustive FFT acquisition in the capture-era detector

The native FFT grid ran inside both installed dual-receiver detectors and preserved every public candidate row and decision in the matched sample. On the legacy DS26-0036 producer, median complete detector CPU fell **55.8%**, from **2.009 s to 0.889 s**. On the screened DS29-0174 producer, the warmed repeat was **8.2% slower**, at **0.818 s versus 0.756 s**. The legacy producer is the measured performance candidate. [Frozen sources and eight raw visits](source-lock.json) · [Detector summary](summary.json) · [Complete detector evidence seal](detector-lock.json)

| Producer and subset | Paired executions | Complete CPU medians, installed → FFT | Coarse CPU medians, installed → FFT |
|---|---:|---:|---:|
| DS26-0036 lower edge, authentic | 8 | 2.009 → 0.889 s | 1.536 → 0.424 s |
| DS26-0036 lower edge, second run per visit | 4 | 2.009 → 0.889 s | 1.536 → 0.439 s |
| DS29-0174 upper edge, authentic | 8 | 0.840 → 0.818 s | 0.445 → 0.501 s |
| DS29-0174 upper edge, second run per visit | 4 | 0.756 → 0.818 s | 0.429 → 0.506 s |
| DS26-0036 lower edge, synthetic | 4 | 1.444 → 0.644 s | 1.071 → 0.285 s |
| DS29-0174 upper edge, synthetic | 4 | 0.542 → 0.578 s | 0.305 → 0.329 s |

Each original producer used its capture-bound two-receiver configuration and own exact and rolled pilot templates. The eight new visits were drawn by segment/index before execution. Two counterbalanced comparisons per visit yielded **256 matching raw candidate responses across 32 receiver rows**. Separate empty, seeded noise, weak and +720 kHz tests at both edges yielded another **96 matching candidate responses across 16 receiver rows**. Full public results, projected factor probes, and original acquisition attempts matched byte for byte after canonical serialization. The comparison includes incomplete and rejected candidate rows. Both old primary and 22-anchor fallback acquisitions stayed in place. [Legacy trace](DS26-0036.json.gz) · [Screened trace](DS29-0174.json.gz) · [Sampling and timing protocol](PROTOCOL.md)

## Native boundary

The opt-in C library calls the same FP64 overlap-save body verified on the capture-era coarse grid. The Python adapter borrows the in-memory complex samples and exact template, prepares the original frame and CFO geometry, and returns the complete score grid. The legacy path retains the installed coarse peak selection. On the screened producer the candidate supplies an exhaustive FFT grid to the installed complete-grid fallback selector, replacing the screened search. The installed CFO refinement, conditioned GLRT, fractional interpolation and detector gates still run. Scope exit restores the original module functions. Unsupported native inputs use the original grid. All 56 coarse calls in this benchmark used the FFT path. [Portable kernel comparison](../folded-bank/README.md) · [Tested x86 library and source](capture-fft-x86.tar.gz) · [Distribution checksum](distribution-sha256.txt)

The recorded legacy median per-call geometry setup was **1.33 ms CPU** and the native grid was **143.37 ms**, including the bank’s allocation and FFT planning. Screened-release medians were **1.50 ms** and **141.19 ms**. Before each paired process, the library load cost 0.55 and 0.37 ms CPU respectively. A 22-anchor retry used **3,809,280 named FFT buffer bytes**, plus **2,293,276 bytes** for the output grid and support arrays. FFTW plan storage and the enclosing receiver use additional memory. Peak process RSS for the mixed-method legacy and screened runs was 204.0 and 216.7 MiB. Those high-water marks cover both methods in their respective worker processes.

The full detector timings start at loaded saved IQ and include the detector calls and their factor projection. IQ archive reading and geographic inference are outside these timings. The screened coarse timing includes its private screen and any fallback, so it does not isolate a direct inner-kernel comparison. Stage timings are inclusive where named and should not be added together.

### Opt in from a dedicated capture process

Verify the distribution hashes and use the supplied x86 library with the matching FFTW double dependency, or build it against the local double FFTW development package. The Python module works with the already installed capture environment and NumPy. Keep the original scanner entry and feed it the same saved window, receivers, and policy.

```python
from pathlib import Path
from leo.analysis.starlink import acquisition
from leo.scanner.fast_scan_analysis import analyze_window
from capture_fft import FullGrid

fft = FullGrid(Path("/path/to/capture_fft.so"))
with fft.route(acquisition):
    result = analyze_window(window, receiver_ids, predictor, policy)
```

The measured legacy port uses this route without a screen argument. For diagnosis on the screened release, pass its imported `coarse_screen` module as the second argument to `route`. Compare the two implementations separately for each production release.

## Partial-IQ geographic check

Four authenticated visits from each recording supplied the matching FFT-native stereo probe rows. The other **6,761 DS26** and **6,700 DS29** admitted visits retained their original factor rows exactly. The substituted rows also reproduced the archival factors exactly on these inputs. The resulting factor documents declare the FFT library, source archive and substituted visit mask. Both are partial-IQ substitutions. [Fit request and unchanged-row audit](fit-lock.json) · [Both-arm results](scores.csv)

The released phase receiver ran fresh from each mixed and unmodified document under **512 MiB and zero swap**. All four attempts finished. The paired coordinates and conditional Doppler RMS agreed exactly in both calibration arms.

| Recording | Zero / fitted position error | Zero / fitted conditional Doppler RMS |
|---|---:|---:|
| DS26-0036 | 1.260 / 1.196 km | 74.760 / 74.682 Hz |
| DS29-0174 | 0.886 / 0.918 km | 95.404 / 95.518 Hz |

[Zero-c position chart](charts/c0/capture-fft-partial-iq.png) · [Fitted-c position chart](charts/fitted_c/capture-fft-partial-iq.png) · [Capped run receipts and position seal](fit-result-lock.json)

The byte-exact measured Python sources are archived at repository-relative paths. Their digests match the original detector and fit locks. The current sources were formatted after measurement and have identical Python syntax trees. [Measured Python sources](measured-source.zip)
