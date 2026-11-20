# Receiver runtime, code complexity and position coverage

[Open the per-modification charts](charts/index.html) · [Fitted-calibration roof comparisons](charts/fitted_c/modifications.pdf) · [Zero-calibration roof comparisons](charts/c0/modifications.pdf) · [Geographic holdouts](charts/fitted_c/transfer.pdf) · [Original ten on the same 135 recordings](../../2026_11_19_position_atlas/original-ten.html)

The gallery contains 21 comparisons, each with a fitted-calibration PNG and a zero-calibration PNG. The upper curves count every offered recording. The lower rows show the returned positions, with a diamond at the median. Each chart names its own recordings and controls.

The same ordinary GLRT and compact cavity solver processed both five-minute recordings under 512 MiB with zero swap. DS26-0036 took 186.32 seconds from saved IQ to position and DS29-0082 took 130.23 seconds. Both returned the exact unrestricted coordinates and conditional Doppler RMS in both calibration settings. The timings use two single-core RF lanes followed by a single-core position solve on the x86 host. [Full IQ, factors, endpoints and memory](whole-pair/README.md)

The faster **full-visit detector** reuses its input buffers and evaluates the fractional interpolation terms in the original numerical order. It reproduced the scientific output on all **11,633 valid dual-receiver visits**, including 102,997 retained candidates. Both positions and conditional RMS values remained bit-identical on each recording. The experiment checked each raw visit against the earlier full control and compared the effective inputs after accounting for the new detector's provenance. Each configuration ran once per recording. [Matched chart of three complete IQ pipelines](charts/fitted_c/whole-iq-three-frontends.png) · [Both arms and complete receipts](whole-fractional/README.md)

| Host, 512 MiB and zero swap | Ordinary end-to-position | Optimized end-to-position | Ordinary → optimized total CPU | Ordinary → optimized calls within 20 ms | Zero / fitted position error |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 186.32 s | 174.60 s | 287.28 → 259.15 s | 86 → 1,650 of 6,765 | 0.218 / 0.180 km |
| DS29-0082 | 130.23 s | 122.79 s | 205.57 → 190.67 s | 44 → 861 of 4,868 | 2.789 / 2.654 km |

End-to-position wall time includes input authentication, decoding, GLRT, assembly, and both coordinate estimates. It fell by 6.3% and 5.7%. The scientific outcomes matched even though the files correctly record different detector build identities. The physical embedded runtime of this complete chain and its accuracy on a second measured wideband installation remain unverified. [Per-stage costs and detector output comparison](whole-fractional/comparison.json) · [Independent-site evidence](measured-transfer/README.md)

## What accuracy means when the receivers publish different numbers of fixes

The benchmark now reads the error-radius curves at a fixed fraction of **all 159 offered DS26 recordings**. This answers, for example, how far a user must allow the receiver to miss before 90% of recordings have a returned fix in range. The data come from the sealed compact stock-first routing comparison. Its eight retries use measured repair outputs, and four fresh probes separately verified routing. [Per-recording chart](../integration/charts/fitted_c/failed-only-all159.png) · [Sealed archive and timing scope](../integration/failed-only/README.md) · [Numerical coverage report](coverage-159.json)

| Receiver and calibration | Fixes | Radius for 50% | Radius for 75% | Radius for 90% | Radius for 95% |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original no repair, zero | 143/159 | 1.078 km | 1.932 km | Unreached | Unreached |
| Compact with targeted retry, zero | 154/159 | 0.993 km | 1.806 km | 3.176 km | 6.695 km |
| Original no repair, fitted | 143/159 | 1.049 km | 1.970 km | Unreached | Unreached |
| Compact with targeted retry, fitted | 154/159 | 1.024 km | 1.774 km | 3.324 km | 6.584 km |

Reaching 90% requires 144 fixes on this roster. Compact gained twelve and lost one relative to original v5. Among the 142 fixes both produced, 138 were within 10% of original error or better in each arm. Looking only at each receiver's published positions gives a fitted P95 of 3.484 versus 3.266 km and a zero-calibration P95 of 3.483 versus 3.155 km. These two comparisons measure different user outcomes. DS26 and DS29 share the same physical installation. [Accuracy across acquisition dates](../integration/time-sensitivity/README.md)

## Results by modification

| Change | Measured result | Chart |
| --- | --- | --- |
| [Ship the compact cavity fit as a direct entry](direct-cavity/README.md) | Four fresh paired tests reproduced all eight compact positions and conditional RMS values. Removing the evaluation runner reduced traced paths from 280 to 272. The numerical code still dominates, and wall time improved on two of four. | [Ordinary GLRT](charts/fitted_c/direct-cavity-ordinary.png) · [Capture-era](charts/fitted_c/direct-cavity-capture-era.png) · [Hash-selected recording](charts/fitted_c/direct-cavity-held.png) |
| [Fit the same direct entry under 512 MiB](direct-cavity-cap/README.md) | Both ordinary workers exhausted memory before initial satellite selection. Discarding parsed TLE records after use let both reach selection, where they exhausted memory. The lifetime-bounded cavity control published on both inputs. | [Four capped direct attempts and passing controls](charts/fitted_c/direct-cavity-cap-ordinary.png) |
| [Cache one exactly repeated phase solve](phase-cache/README.md) | Skipped 757 of 3,388 native normal solves in three capped workers. This saved 0.87–1.16 CPU seconds in the targeted operation. All six coordinates and conditional RMS values matched. Whole-worker CPU improved in two of three. | [Three capped pairs](charts/fitted_c/v5_phase_cache_confirm.png) |
| [Compute fractional IQ interpolation in ordered pairs](fractional-runtime/README.md) | Relative to the prepared-buffer parent, warm authenticated input-to-GLRT median fell from 25.44 to 22.88 ms on the host. Calls meeting 20 ms rose from 5 to 12 of 60. Fractional CPU fell 14.5% on x86 and 2.7% under Cortex-A9 emulation. | [Detector boundary](charts/fitted_c/fractional_runtime.png) · [Two mixed-factor positions](charts/fitted_c/fractional_runtime_position.png) |
| [Skip one in four visits while retaining all bands](interleaved-visits/README.md) | All six capture-era recordings returned both positions. On four hash-selected recordings the fitted P95 rose from 1.374 km for original v5 to 1.559 km. | [Six matched recordings](charts/fitted_c/interleaved-visits-roof6.png) |
| [Run that schedule before GLRT on real saved IQ](iq-schedule/README.md) | Retained 75% of the actual ordinary detector calls. Complete wall time fell from 186.32 to 152.43 s on DS26 and from 130.23 to 123.68 s on DS29. Fitted errors rose from 0.180 to 0.226 km and from 2.654 to 3.212 km. | [Complete scheduled IQ](charts/fitted_c/iq_schedule.png) · [Complete full-visit controls](charts/fitted_c/whole_pair.png) |
| [Run late recovery only when unowned Doppler curves show curvature](late-routing/README.md) | Recovered both diagnosed corrections but dispatched 127/135 times. The eight bypasses accounted for 4.9% of archived late-stage time and missed one correction of about 75 m. | [All 135](charts/fitted_c/late-curvature-roof135.png) · [Fresh comparisons](charts/fitted_c/late-curvature-live.png) |
| [Build arcs directly from anonymous GLRT and causal orbits](independent-arcs/README.md) | Allowing unpaired peaks brought median native-input-to-decision time to 8.41 s. It published one of six matched offers, with 6.74 km fitted error, and withheld both wrong offers. Four fresh reserves were from DS26. | [Development](charts/fitted_c/independent_arcs-diagnostic.png) · [Held recordings](charts/fitted_c/independent_arcs-confirmation.png) · [Wrong offers](charts/fitted_c/independent_arcs-omitted.png) |
| [Test held Doppler evidence across a region edge](edge-evidence/README.md) | The added check took 24–34 ms per evaluated face and left all decisions unchanged. Both new simulated center offers published, one of two true near-edge offers published, and both near and both far wrong offers were withheld. A separate full stock far solve missed by about 74 km. | [Fresh sites](charts/fitted_c/compact-held-face-fresh.png) · [Far control](charts/fitted_c/compact-held-face-far-stock.png) · [Measured roof parity](charts/fitted_c/compact-held-face-roof.png) |
| [Test geometry using independently measured beacon tracks](measured-transfer/README.md) | Eight real sites and 16 offers. Two sites supplied no simultaneous frequency contrast after allowing a free receiver clock. On the other six, author-supplied identities gave better held RF fits on all containing tiles. Their forced positions still had 6.75 km median error. Single-band data make the two calibration arms identical. | [Diagnostic positions at eight sites](charts/fitted_c/beacon_observability.png) |

The independent-site source inventory found no second measured installation matching both the wideband Qin pilots and the required clock, orbit and truth records. The physical beacon comparison used site-assisted identities. Both its fitted positions and the separate synthetic region tests have explicit evidence boundaries. [Physical source inventory](measured-transfer/source-inventory.md) · [Missing-region decisions](edge-evidence/README.md)

## Can the detector keep up with the actual arrivals?

The measured detector calls usually exceed 20 ms. Feeding their durations into a queue at the original host delivery timestamps gives a different operational measure. A single worker with space for one waiting visit admitted every valid ordinary visit on both recordings. Repeating the calculation with measured native wall time gave the same minimum capacity. A short, genuinely wall-clock-paced run of 96 predecoded visits reproduced all detector outputs but reached four waiting visits and a 67.14 ms P95 delivery-to-result latency. The corresponding CPU-time model predicted 31.30 ms. Operating-system delays matter to a live buffer. [Queue plot](arrival-clock/queue.png) · [Clock source, service-time assumptions and paced replay](arrival-clock/README.md)

The complete compact position solver consumes the full recording. On these inputs the modeled lossless single-worker detector followed by the measured handoff and cavity fit would return the position about 69 s after the final DS26 delivery and 42 s after the final DS29 delivery. A stored recording can be processed faster than its original acquisition duration. A streaming run still waits for the last observation it uses. [Per-visit queues and time-to-position calculations](arrival-clock/queue.csv)

Rebuild the plots and run the fixed-coverage comparison from the repository root. Fresh `run` commands also save one PNG per calibration setting alongside the predictions.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/streamlined --out /tmp/streamlined-charts
.venv/bin/python -m tools.pipeline_eval coverage --panel ds26-all159 \
  --predictions reports/2026_11_19_receiver_screening/integration/failed-only/all159-replay.jsonl.gz
```
