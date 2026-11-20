# Receiver changes from saved IQ to position

[Open one position-error chart per comparison](charts/index.html) · [Fitted-calibration roof charts (PDF)](charts/fitted_c/modifications.pdf) · [Zero-calibration roof charts (PDF)](charts/c0/modifications.pdf) · [Original ten changes on the same 135 recordings](../../2026_11_19_position_atlas/original-ten.html)

The gallery has 18 roof comparisons and two region-holdout comparisons. Each has a standalone image for each calibration setting. The holdout PDFs include both the simulated edge offers and the two measured roof queries given an incorrect region. [Fitted-calibration holdout charts](charts/fitted_c/transfer.pdf) · [Zero-calibration holdout charts](charts/c0/transfer.pdf)

On the full 159-recording DS26 roster, compact v5 with a retry for diagnosed failures returned 154 fixes, including 151 within 5 km. Original no-repair v5 returned 143, including 141 within 5 km. Four fresh probes checked the routing decisions against the archive. Separately, shortening the lifetime of large arrays during the compact solve kept all four stored-GLRT test recordings within 512 MiB and reproduced every unrestricted coordinate and conditional RF residual. Two complete host replays then measured the path from saved IQ to position within that limit. [Full-roster scores](failed-only/README.md) · [Four capped position solves](cavity-lifetime/README.md) · [DS26 saved IQ](whole-cavity/README.md) · [DS29 saved IQ](whole-memory-chain/README.md)

## How close the positions are to original v5

The first two numerical columns count every recording offered. Median and P95 use the positions each receiver actually returned. The two calibration settings use the same inputs, search budgets and region.

| Receiver on DS26 | Published / 159 | Within 5 km / 159 | Zero calibration median / P95 (km) | Fitted calibration median / P95 (km) |
| --- | ---: | ---: | ---: | ---: |
| Original v5, no repair | 143 | 141 | 0.980 / 3.155 | 0.988 / 3.266 |
| Original v5, selective gap | 141 | 139 | 0.974 / 2.833 | 0.949 / 2.589 |
| Original v5, one omitted track | 138 | 136 | 0.965 / 3.220 | 0.973 / 3.343 |
| Original v5, two omitted tracks | 132 | 130 | 0.970 / 3.399 | 0.993 / 3.378 |
| Compact v5 | 149 | 146 | 0.990 / 3.545 | 1.014 / 3.541 |
| Compact v5 with diagnosed retry | 154 | 151 | 0.989 / 3.483 | 1.009 / 3.484 |

On the 142 recordings where original no-repair v5 and the retry policy both returned positions, the median and P95 differed by less than 1% in both calibration settings. On 138/142, the compact error was within 10% of the original error or smaller. Across each receiver's own returned positions, P95 increased by 6.7% with fitted calibration and 10.4% with zero calibration. Leaving a date out of the seven-day sample moved those full-publication P95 increases to 6.0–34.4% and 5.4–21.7%. All these recordings came from the same installation. [Full-roster error chart](charts/fitted_c/failed-only-all159.png) · [Previously excluded 32](charts/fitted_c/failed-only-excluded32.png) · [Recording-date sensitivity](time-sensitivity/README.md)

Median conditional Doppler RMS on each solver's selected support was 109.78 / 100.29 Hz for original no-repair v5 and 69.32 / 69.30 Hz under the retry policy, in zero / fitted order. The geographic statistics above score positions independently. The 159-recording result combines the original compact outputs and eight measured retries. Its serial timing estimate adds 613 seconds across the roster. Nine archived compact fixes took longer than the 195 s stage limit used in the fresh four-case probe. [Per-recording branch, interval and RMS](failed-only/scores.csv) · [Fresh probes and time-limit sensitivity](failed-only/README.md)

## What each modification did on its measured inputs

| Change | Measurement | Position-error chart with fitted calibration |
| --- | --- | --- |
| [Reuse the detector input buffers](glrt-hot-stage/README.md) | On 60 paired warm calls, median authenticated IQ-read-to-GLRT time fell from 27.84 to 23.71 ms. Calls meeting 20 ms rose from 1 to 8. The downstream check replaced the measured visits in two recordings. | [Partial IQ replay and position](charts/fitted_c/ordinary_prepared_position.png) |
| [Process three neighboring coarse GLRT epochs together](coarse-glrt/README.md) | Preserved every tested candidate field. Whole-detector CPU changed by −2.18% on x86 and +0.10% under Cortex-A9 emulation. Both measurements missed the 3% target. | [Two partial IQ replays](charts/fitted_c/coarse_glrt_triplet.png) |
| [Pair peaks across the two physical receivers before orbit decoding](paired-peaks/README.md) | Fourteen of sixteen band calibrations passed their held check. Median GLRT-to-decision time fell from 24.93 to 4.36 s against elapsed-time decoding. Pairing published zero of six correct-region offers and zero of two wrong offers. | [Diagnostic](charts/fitted_c/paired_peaks-diagnostic.png) · [Confirmation](charts/fitted_c/paired_peaks-confirmation.png) · [Wrong region](charts/fitted_c/paired_peaks-omitted.png) |
| [Run late orbital-state reads in rows](row-memory-panel/README.md) | A row-major complete recovery had previously finished one ordinary DS29 recording at 512 MiB. All four new capture-era workers exhausted that limit, including two during the signed-context fit. | [Four capped recordings](charts/fitted_c/v5_recovery_reads-roof4-capture-era.png) |
| [Use bounded working arrays through the compact cavity decision](bounded-cavity/README.md) | Same four recordings and limit. One worker finished with exact compact endpoints. Three exhausted memory. | [Capped versus unrestricted](charts/fitted_c/v5_bounded_cavity-roof4.png) |
| [Release large fitted objects at their last use](cavity-lifetime/README.md) | All four workers finished in 74–86 s at 424–476 MiB with zero swap. All eight coordinates and conditional residuals exactly matched unrestricted compact. On the three earlier failures, allocator trim and collection alone recovered one. | [All four](charts/fitted_c/v5_cavity_lifetime_roof4.png) · [Allocator control](charts/fitted_c/v5_cavity_lifetime_allocator.png) |
| [Call the row-major solver directly](compact-entry/README.md) | Reached 22 repository files and 1,581 lines versus 51 and 2,874 for the qualification entry. Three completed pairs agreed on position. CPU time changed little. | [Ordinary](charts/fitted_c/compact-entry-ordinary.png) · [Capture-era](charts/fitted_c/compact-entry-capture-era.png) · [Ordinary control retry](charts/fitted_c/compact-entry-ordinary-retry.png) |
| [Compose three numerical failure guards in the compact fit](orbit-repairs/README.md) | Five of eight previously failed cases returned positions. The other three reached a scientific withholding. Each of the two controls reproduced its compact result. | [Ten matched replays](charts/fitted_c/v5_causal_orbit_fit.png) |
| [Retry only a diagnosed failure](failed-only/README.md) | All 149 original compact fixes kept their positions. The five additional fixes brought the total to 154/159, with four live branch checks. | [All 159](charts/fitted_c/failed-only-all159.png) · [Excluded 32](charts/fitted_c/failed-only-excluded32.png) |
| [Require consistency at the offered region boundary](edge-holdouts/README.md) | Across three fresh simulated locations, the rule withheld all six wrong offers, published all three central offers and two of three valid near-edge offers. It withheld a valid location 593 m inside its region. | [Offered and omitted regions](charts/fitted_c/compact-edge-three-latitudes.png) |
| [Stream authenticated IQ into the ordinary detector and row-major solver](whole-memory-chain/README.md) | DS29 completed both positions in 203.22 s for a 300.02 s recording at 512 MiB with zero swap. DS26 reproduced the full detector output and exhausted memory in the position fit. | [DS29 full replay](charts/fitted_c/whole_memory_chain.png) · [DS26 first full replay](charts/fitted_c/whole_memory_chain_ds26.png) |
| [Use the lifetime-bounded cavity solver after the same ordinary detector](whole-cavity/README.md) | A fresh DS26 replay finished in 186.32 s under 512 MiB with zero swap. The two errors were 0.218 / 0.180 km. Both coordinates and both conditional RMS values matched the earlier same-input compact cavity. | [DS26 full replay](charts/fitted_c/whole_cavity.png) |

The last two rows start from complete stored IQ. Each used two single-core detector lanes followed by a single-core position fit on the x86 host. DS26 and DS29 used different final position policies. Earlier same-core timing pairs compared original v5 with compact v5 from stored GLRT and measured a median 3.65× speedup through usable output. Physical embedded throughput and location transfer to independent measured wideband installations remain open. [Same-core timing boundaries](../deployment/same-core-baseline/README.md) · [Blind simulated region margins and forced errors](edge-holdouts/README.md)

Rebuild this set from the saved measurements with the following command. Each roof curve retains the full offered denominator, including withheld positions and failed workers. The dots show individual returned positions, and diamonds show their medians. Both arms and the per-recording tables are included in the gallery.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/integration \
  --out /tmp/receiver-integration-charts
```
