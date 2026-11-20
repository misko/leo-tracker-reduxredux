# Held GLRT epochs on original v5 orbital arcs

**The physically verified positive propagation delay did not improve held epoch prediction on this roof.** The reflected range term predicted the real epochs markedly better, even though the compiled detector reports genuine pilot arrivals with positive timing sign. In the separately labeled exploratory comparison, reflected epochs separated the surveyed point from every 25 km alternative on both held records. CFO alone also separated all eight. Neither timing sign established added ability to identify the exact surveyed point. [Measured chart](range-epoch.png) · [Full results](scores.json)

## Native observation and physical sign

The study authenticates the capture-era native document, original no-repair v5 publication, matched ownership in both calibration arms, and the latest causal catalogue in each original archive. Each retained owner is joined to the winning native factor by observation hash, RX, channel, actual RF, hardware-counter midpoint and folded CFO. All 9,867 extracted owned observations matched. The fixed chronology rules retain 204 arcs of 10.3–59.9 s, with 4,989 training epochs and 2,538 held epochs. The two held recordings contribute 132 arcs and 1,605 held epochs. Their final thirds supplied zero fitted phase or slope measurements. [Frozen protocol](PROTOCOL.md) · [Per-recording identity and timing proof](scores.json)

For an actual QIN pilot template, the compiled ±800 kHz native producer measures the imposed `−9`, `−4`, `0`, `+4`, and `+9` sample circular waveform shifts with the same signs. Both sidebands and both receivers agree in all twenty planted calls. On the first authenticated DS26-0036 CI16 window, both receivers agree on all ten checks within 0.000034 samples. A compensating change in the hardware starting counter cancels the phase movement. The arrival coordinate therefore uses starting counter plus integer and fractional local epoch. The independent forward model also emits on the 750 Hz frame lattice before adding positive propagation delay. On the measured sampling schedules with injected epochs, its recovered shared-clock error is 0.08–0.10 samples. Reflecting the injected delay produces 1,527–1,959 samples of error. [Compiled wide native origin experiment](native-origin-results.json) · [Origin seal and digest](native-origin-lock.json)

## Primary chronological test

Mean held-arc median absolute error in samples at the surveyed site, using the shared sample-clock slope. `+15 s` shifts modeled satellite timestamps while holding the receiver clock and observations fixed. The shuffle exchanges observed epochs separately within each training and held partition.

| Recording | Arcs / held epochs | Clock only | Positive range | Reflected range | +15 s timestamp | Shuffled epochs |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036, development | 55 / 703 | 1,359 | 2,048 | 506 | 2,097 | 2,099 |
| DS29-0082, development | 17 / 230 | 1,067 | 1,834 | 479 | 1,822 | 1,732 |
| DS26-0237, held | 61 / 801 | 1,194 | 1,974 | 437 | 1,978 | 1,936 |
| DS29-0174, held | 71 / 804 | 1,022 | 1,465 | 377 | 1,512 | 1,532 |

Allowing independent phase and clock rate per arc retains the sign result. For the held records, positive propagation has 647 and 641 samples of arc error, clock alone 364 and 472, and reflected propagation 168 and 333. Pooled held median absolute errors for the reflected arc clocks are 18.9 and 7.1 samples. A smaller median and higher arc-average error show that some arcs remain poor even under the empirical reflection. The detector sign is resolved by the waveform experiment. The reason measured long arcs favor a reflected term remains unresolved. [Primary chronological seal](measurement-lock.json)

## Geographic information beyond CFO

The physical Doppler proxy uses the same orbits and chronology. It fits a constant offset per RF arc, which absorbs a static RF calibration `c` term on that carrier. The observed measurement, model geometry and epoch estimates are common to both stable owner arms. The separate sign check scores physical CFO at 228–616 Hz mean arc error and reversed CFO at 68.9–72.6 kHz.

| Recording | Surveyed rank by CFO | By physical epoch | By CFO + physical epoch | By CFO + reflected epoch, exploratory |
|---|---:|---:|---:|---:|
| DS26-0036 | 2/9 | 2/9 | 1/9 | 3/9 |
| DS29-0082 | 4/9 | 4/9 | 4/9 | 3/9 |
| DS26-0237 | 3/9 | 6/9 | 2/9 | 2/9 |
| DS29-0174 | 3/9 | 3/9 | 2/9 | 3/9 |

CFO alone selected a 2 km alternative on both held recordings. Adding positive-delay timing changed which 2 km location ranked first and moved the surveyed point from third to second. This occurred with large timing misfit at the surveyed point. The reflected grid was fixed separately after observing the signed timing control at the surveyed site. With the shared clock, all eight held 25 km alternatives had higher reflected timing errors, by 1.2–38.3 samples. Reflected timing alone ranked the surveyed point third on both and preferred the 2 km south hypothesis. The reflected+CFO ranking selected a 2 km alternative on both. With independent arc clocks, the reflected+CFO surveyed ranks were third on both. The observed timing coherence and coarse spatial sensitivity therefore remain conditional on the orbit and timing assumptions used here. [Separate reflected-grid plan](reflected-spatial-plan.json) · [Exploratory results and RF sign controls](reflected-spatial.json)

All recordings share one physical roof. The grid is centered on an external survey and uses original archived orbital identities. It produces no receiver fixes or blind position estimates. [Chart and data seal](chart-lock.json) · [Plot data](range-epoch.csv)

The archived source snapshots preserve exact measured code before import and formatting cleanup. [Measured source bytes](measured-sources.tar.gz)

```sh
.venv/bin/pytest -q tests/pipeline_eval/test_range_epoch.py
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.range_epoch_figure
```
