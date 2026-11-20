# Can a cheaper pilot search keep the position?

The original receiver searches 12 pilot anchors on both antennas. When just one antenna finds a pilot, it searches 22 anchors on the other. Removing that retry increased fitted position error from 262 to 780 m on one complete recording and from 516 to 1,279 m on another. This study measures cheaper ways to carry out the search, compares their effects on the pilots and the position, and tests which measurements distinguish geographic locations. [Earlier complete retry comparison](../retry-and-transfer/README.md)

On the entire five-minute DS26-0162 recording, the new initial anchor set lost 105 net gate-positive antenna observations. The fitted error rose from **417 to 636 m** with the same compact solver. The four original v5 settings gave **415–421 m**. At zero calibration the compact errors were 402 and 604 m. Replaying the new detector took 456 s on eight host workers, with 532 s through the position decision. Every valid detector visit exceeded 20 ms. [Complete waveform, per-visit clocks and per-calibration positions](coarse-waveform/README.md)

## Pilot search

| Change | Measured result |
| --- | --- |
| Use 12 anchors from the wider search for the initial search | Reusing the 12 partial sums gave the same detector outputs as recomputing the new wider search on all 48 visits. It saved 12.0% of complete detector CPU on the seven held retry visits and 3.4% across all 32 held visits. Changing the initial anchors retained 18 of 19 original held winners. [Same-visit comparisons](nested-anchors/README.md) |
| Shorten the prepared FFT from 512 to 256 samples | The selected FFT plan saved 4.18% of complete detector CPU over 40 matched pairs at eight held visits. All 128 ordered candidates matched the original and previously optimized detectors. [Detector outputs, memory and timing](fft-length/README.md) |
| Compute the pilot bank by carrying a running sum for each pilot tone | The 22-anchor retry saved 32.44 ms in development. On two held visits with real retries, the complete detector saved 35.32 ms, or 8.15%. All six held visits retained their original candidates. The 12-anchor initial search gained only 2.92 ms in development. [Pilot bank and held measurements](sliding-pilot-bank/README.md) |
| Track a pilot forward between periodic full searches | On the held recording, only four of 29 positive follow-up probes had a usable seed. Local tracking reproduced one, versus eight for the native comparison with a similar CPU budget. [Saved-waveform timing and outcomes](seeded-acquisition/README.md) |
| Stop computing a fractional control when its best possible score cannot beat the incumbent | On 112 fractional refinements, the bound available at the integer stage certified four skips. A bound using the later exact score avoided 25 control spectra. Compared with the same scoring code with skipping disabled, it saved 0.008 ms at the median on 345 paired spectral calls. [Bounds, retained winners and matched timings](winner-bound/README.md) |
| Run the verifier from coarse pilot seeds in standalone C | Native x86 and two emulated ARM builds reproduced the original frequency bins and gate decisions on 112 candidates from six stereo visits. Two effectively tied candidates exchanged seed order. Whole-process CPU on x86 was 9.09–9.97 ms per supplied candidate. [Portable build and observed error](portable-verifier/README.md) |
| Choose costly original-detector visits when the fast detector sees an unfamiliar track | On six held recordings, the novelty rule and a control selected by a hash each used 2,369 calls. The novelty rule lost more net passing probes on every recording. Its fitted median was 0.510 km and its P95 was 3.122 km, versus 0.804 and 2.089 km for fast alone. Both met the individual 10% allowance on three of six. The compact solver using the original observations met it on all six. [Measured positions and modeled acquisition costs](adaptive-visits/README.md) |

## Position without the roof location

At eight real beacon sites, the relative antenna phase between satellites predicted held measurements better than shuffling their times or identities. Every anonymous position was withheld. On the five sites with usable simultaneous measurements, forced median errors were 12.30 km with phase, 10.88 km with matched Doppler alone and 8.79 km at the centres of the offered regions. This receiver and frequency range differ from those of the DS26 and DS29 roof. [Independent-site measurements and geographic error distributions](array-closure/README.md)

Transferring a satellite's carrier offset across observations provided a forecast for ten of 41 held roof targets. The method withheld all offers on the four roof recordings and at a separate simulated site. The free per-frequency terms made the RF calibration coefficient unidentifiable, so this analysis reports the zero-calibration solution and marks fitted calibration unavailable. [Clock transfer and missing-region decisions](clock-transfer/README.md)

## Running the existing receiver

An option that returns one requested calibration result can omit two unused association reports and share repeated calculations. The compact receiver still uses both calibration arms to decide whether to publish. All eight selected results reproduced the installed paired receiver on four recordings, including a withheld result near a region edge. The median CPU saving was 0.51 seconds, or 0.98%. [Runtime and both position distributions](arm-execution/README.md)

The ordinary acquisition command now determines validity while processing the signed visits and validates the resulting count while reading the output. Across three complete field replays, eliminating a separate signed-index pass saved 1.48–1.84 CPU seconds per recording. Reading each measurement file once saved a further 0.10–0.14 CPU seconds. The revised command uses 31 fewer source lines across three files. Each fresh compact fit reproduced the earlier positions from the same measurements. [Paired collector timings, full input verification and positions](scan-accounting/README.md)

The position plots count every scheduled recording in the denominator and show the median among returned positions. Roof plots use the same recording IDs for the four original v5 options and supply matched zero and fitted calibration when identifiable. Each detector-only experiment has a figure at its last measured stage. [Browse the figures](benchmark/index.html) · [Download the figures and CSVs](benchmark/modification-charts.zip)

## Rebuild the benchmark

The standard command regenerates the per-change plots, recording-level CSVs and offline archive from the sealed results. Use a new output directory.

```sh
.venv/bin/python -m tools.pipeline_eval benchmark \
  --study reports/2026_11_19_receiver_screening/coarse-and-navigation \
  --pack --out /var/tmp/leo-coarse-navigation-benchmark
```
