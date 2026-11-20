# Causal three-visit peak continuation

On six complete ordinary-factor replays from one measured roof, the filter preserved every positive probe and removed 482 of 100,769 passing peaks (0.48%). It changed 80 of the 23,439 winners passed to tracking. The filtered standalone published 6/6 positions in each calibration arm. Strict ordinary published 5/6 under the same 165 s cap. The added publication was DS29-0247, where strict ordinary timed out. The filter worsened median position error in both arms across the four original matched captures and gave mixed preparation times. [Sealed predictions](predictions.jsonl.gz) · [Factor counts](factor-counts.json) · [Score summary](summary.json)

The filter uses the last two distinct strict ordinary winners in the same receiver and RF lane. It reduces an ambiguous current probe only when one passing peak is consistent with both the wrapped frame epoch and folded CFO history. A locally constant combined clock rate and satellite epoch cancel in the consecutive-interval comparison. This differs from the earlier simultaneous dual-RX pairing and CFO-only trajectory extraction. The original Graph receives an ordinary-format document and selects one winner per positive probe in both methods. Of 21,896 ambiguous probes, only 194 met the unique-continuation condition. [Predeclared rule and selection](PROTOCOL.md) · [Simultaneous RX study](../../integration/paired-peaks/README.md) · [CFO paths](../../deployment/peak-paths/README.md)

## Position and RF

| Input to receiver | c = 0 fixes | c = 0 median / max error | Fitted-c fixes | Fitted-c median / max error |
|---|---:|---:|---:|---:|
| Original capture-era v5 | 6/6 | 0.818 / 1.320 km | 6/6 | 0.832 / 1.458 km |
| Strict ordinary, 78-source v5 | 5/6 | 1.161 / 2.789 km | 5/6 | 1.224 / 2.654 km |
| Three-visit filter, 78-source v5 | 6/6 | 1.245 / 2.801 km | 6/6 | 1.264 / 2.667 km |

Across the four matched captures all three methods fixed 4/4 in both arms. For strict ordinary versus filtered, median position error rose from 1.025 to 1.430 km at c = 0 and from 1.019 to 1.378 km with fitted c. Original v5 medians were 0.726 and 0.717 km, respectively. Conditional RF RMS medians for strict ordinary and filtered were 108.46 and 108.46 Hz at c = 0, and 108.35 and 108.34 Hz with fitted c. Those RF residuals are conditional on each receiver's selected observations. On DS26-0036, filtered error increased from 0.218 to 1.736 km at c = 0 and from 0.180 to 1.595 km with fitted c, while RF RMS dropped by 0.28 and 0.29 Hz respectively. The other four completed pairs changed geographic error by at most 0.063 km in either arm. [Endpoint-level scores](scores.csv)

Both held recordings used the same containing offer as their paired strict controls. DS26-0122 went from 1.330 to 1.367 km at c = 0 and from 1.329 to 1.366 km with fitted c. Filtered DS29-0247 published at 1.017 and 1.050 km after 92.8 s. Strict ordinary reached cavity processing and hit the 165 s wall deadline. Systemd recorded 512 MiB peak charge and classified the exit as a timeout. There were zero scientific withholds among the five strict publications and no forced estimates were emitted by this receiver. [Prediction seal](prediction-lock.json) · [Runtime](runtime.json)

## Preparation and execution

The in-memory factor scan cost 18–42 ms per recording. Native preparation includes building observations and Graph tracks plus the initial sky and catalogue history. It received identical positive-probe counts in every completed pair, with at most one track difference per case. For the five completed pairs, adding the prefilter to native preparation changed wall time by a median of **+1.35 s** (−1.06 to +12.54 s). Whole standalone CPU time changed by a median of −0.86 s (−2.15 to +5.60 s) and service wall time by −0.71 s (−11.03 to +22.12 s). These are single measured runs of each pair. The filter-stage timer covers the resident factor scan, and the service timer includes its own preexisting native input read. The evaluation's intermediate JSON serialization is outside the filter timer. The strict DS29-0247 timeout is counted in publication coverage and excluded from these completed-pair differences. [Paired costs](runtime.json)

Both variants used the unmodified standalone receiver, one thread, zero swap and a 512 MiB service limit. Source, session, capture timing, broad screen, offer, configuration and strictly prior catalogue snapshots are bound per pair. The original v5 geographic reference enters only after the prediction seal. All results come from the one measured roof with containing offers. [Source lock](source-lock.json) · [Causal history](causal-history.json) · [Requests](requests.json) · [Score lock](score-lock.json)

The standard position books include both calibration arms, per-recording dots and an empirical distribution over all scheduled captures. [Chart manifest](figures.json)

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/detector-origins/coherent-peaks \
  --out /tmp/coherent-peak-position-figures
.venv/bin/pytest -q tests/pipeline_eval/test_coherent_peak_filter.py
```
