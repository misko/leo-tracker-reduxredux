# Sampled causal widths for family confidence

DS29-0082's family-confidence peak fell from **875,764 to 589,548 KiB**. The complete worker subsequently reached **885,736 KiB** inside cavity nomination. The original full-worker peak was 875,764 KiB in the fresh stock trace and 882,412 KiB in the archived same-input control. The change removes the measured family-confidence peak. The later peak determines the unrestricted worker's memory requirement on this recording.

## Allocation trace

The frozen `phase_widths` call consumes alignments from three epochs at 0, 150 and 300 seconds. Stock `previous_bank` first calculates those samples and then propagates an aligned previous-state bank for other consumers. In family confidence, that second propagation used 1,680 satellites and 1,327 padded epochs. Its returned ECEF position and velocity arrays occupied 107,009,280 bytes. Peak RSS rose from 589,124 to 875,764 KiB inside `ecef_states`, which produces TEME states and rotates them into ECEF. The shifted full-catalogue prior held 27,017,080 bytes in the cache after width construction.

The scoped change computes the original three-sample alignment and supplies the resulting inventory to the frozen widths function. The three-epoch outputs occupy 241,920 bytes. Other prior-bank callers retain the full bank interface. The all-catalogue cache entry disappears from the measured confidence stage, and existing small prior caches stay available. The same DS29 trace generated all **145** RF profiles with exact width, full profile, ordering and confidence hashes.

| DS29-0082 measurement | Fresh composed stock | Sample-only family widths |
| --- | ---: | ---: |
| Family-confidence wall | 3.450 s | 0.686 s |
| Family-confidence CPU | 3.376 s | 0.672 s |
| Family-confidence peak RSS | 875,764 KiB | 589,548 KiB |
| Full worker wall | 118.588 s | 73.957 s |
| Full worker CPU | 111.402 s | 71.179 s |
| Full worker peak RSS | 875,764 KiB | 885,736 KiB |

Both fresh workers used nice level 3. The candidate ran on CPU 7 and stock on CPU 18. Whole-worker timing includes the different cores and the rest of the recording replay. The family timings cover the same instrumented stage.

## Endpoints and confirmation

DS29-0082 reproduces the fresh and archived same-input composed controls exactly. Geographic error is 2.784 km at `c = 0` and 2.651 km with fitted `c`. Conditional Doppler RMS is 106.670 and 106.587 Hz, respectively. Native tracks, ranked branches, confidence, residual and reassociation receipts, optimizer counts and both final coordinates agree.

DS26-0036's optional candidate completes at 0.229 and 0.185 km with conditional RMS of 102.259 and 102.295 Hz, exactly matching the earlier same-input tiled-salvage control. The fresh composed stock leg completed the confidence trace before CPU 18 was released for the orbit study. That observed stage matched every profile and rank. Its confidence peak was 827,248 KiB versus 688,436 KiB in the candidate. The figure shows the interrupted stock leg with a null endpoint and includes the earlier same-input control as a separate series.

[Allocation and resource receipts](stage-allocation.json) · [Scientific comparisons](comparison.json) · [Both-arm scores](scores.csv) · [Prospective protocol](PROTOCOL.md)

```sh
python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/redesign/family-memory \
  --out /tmp/family-memory-figures
```
