# Carrier frequency at a detected pilot time

The timing scout’s first proposal landed within two ADC samples of the original detector’s pilot on 15 of 32 selected receiver visits. At those 15 times, the phase at a 44-sample lag estimated the carrier frequency **modulo 227.27 kHz** within 40 kHz on all 15 and within 10 kHz on 12. Its median absolute folded error was 3.70 kHz. Using a second, shorter lag to choose one absolute frequency gave a median absolute error of **209.8 kHz**. Seven estimates picked the correct original 80 kHz grid bin. Among the eight aligned pilots the stock wide detector had missed, only two did so. [Stage figure](carrier.png) · [Data by receiver and candidate rank](carrier.csv)

| Selected receiver visits | Tested | First timing proposal within two samples | Also within 40 kHz after frequency folding | Also within 40 kHz in absolute frequency |
| --- | ---: | ---: | ---: | ---: |
| Original misses | 16 | 6 | 6 | 1 |
| Original retained controls | 8 | 7 | 7 | 5 |
| Later disjoint misses | 8 | 2 | 2 | 1 |

For a received waveform with a constant carrier offset, multiplying a sample by the conjugate of an earlier sample leaves a phase rotation proportional to the lag. The 10 MS/s signal advances an entire cycle per 227.27 kHz at a 44-sample lag. Several distinct in-band carriers therefore produce the same phase. A four-sample lag can theoretically distinguish all offsets in the ±800 kHz search band. On these real visits, its median absolute frequency error at an aligned pilot was 124.6 kHz, enough to choose an adjacent 44-sample alias. The half-frame control matched none of the 32 pilot times. [Prospective measurement rule](PROTOCOL.md) · [Summary](summary.json)

All sixteen signed synthetic pilot lanes, spanning strong, weak, alternating-sign and single-frame inputs on both pilot bands, produced an absolute estimate within 2.77 kHz. Thirteen were within 1 kHz. An all-zero input supplied no timing or carrier estimate. Numerical phase estimates on noise and tones still require the independent GLRT gate. The real comparison uses the capture-era fractional tracking carrier as its reference. For all four ranks combined, 20 of 32 visits contained a near-epoch proposal. Those later ranks were scored as diagnostics. [Planted and null controls](controls.csv) · [Frozen timing and actual native-gate results](../differential-pilot/README.md)

The Python measurement took median 2.32 ms of CPU to prepare both lag streams for one receiver, then 0.67 ms to project one nominated epoch. The existing timing search already computes the 44-sample complex correlation before taking its magnitude. The standalone accounting here includes recomputing it. A second checkout repeated all 32 raw reads, reproduced all 160 predictions and scores after excluding measured clocks, and produced byte-identical synthetic scores, summary, PNG and PDF. These measurements leave the native frequency search and its resulting geographic positions unmeasured. [Sealed raw estimates](prediction-lock.json) · [Captured waveform and code bindings](source-lock.json)

From the repository root, rebuild the figure with `MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.pilot_carrier_figure`. To repeat the saved-I/Q calculation, put `PROTOCOL.md` in a fresh local directory and run the two commands below. The prediction step needs the authenticated recording archive. The score step joins only the already frozen measurements to the original references.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.pilot_carrier_trial predict --out "$run_dir"
.venv/bin/python -m tools.pipeline_eval.qualification.pilot_carrier_trial score --out "$run_dir"
```
