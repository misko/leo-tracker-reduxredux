# Simulated Qin IQ to an installed receiver fix at one new site

The stock wide GLRT and installed phase-release receiver produced a **0.751 km fitted-`c` fix** from generated dual CI16 samples inside the offered region. Zero `c` produced a 1.017 km fix on the same input. The ordinary release also issued both fixes from a region that excluded the true site. A separate retrospective replay with the existing 20 m interior profile retained both containing fits and withheld both omitted fits. This is a one-site synthetic pilot-band qualification with a supplied 25 km region, limited to this schedule and signal model.

## Position and frequency

| Installed profile and offer | Zero-`c` position error | Fitted-`c` position error | Conditional RF RMS, zero / fitted | Direct solve wall |
| --- | ---: | ---: | ---: | ---: |
| Phase release, containing | 1.017 km | 0.751 km | 15.536 / 15.306 Hz | 20.89 s |
| Phase release, omitted | 1.580 km, false fix | 1.534 km, false fix | 15.631 / 15.451 Hz | 20.82 s |
| Interior, containing | 1.017 km | 0.751 km | 15.536 / 15.306 Hz | 21.36 s |
| Interior, omitted | Withheld, 1.580 km forced | Withheld, 1.534 km forced | 15.631 / 15.451 Hz | 22.12 s |

Each cell represents one offer and one calibration arm at the same simulated site. The containing center was 8.939 km from truth. The omitted center was 14.025 km from truth, with truth 1.5 km beyond the nearest face. Both ordinary omitted estimates reached that face. The containing fits lay 4.319 km and 4.047 km from their nearest face. On the containing offer, fitting `c` lowered position error by 0.267 km and conditional RF RMS by 0.231 Hz. On the omitted offer, it lowered RF RMS by 0.179 Hz and the result still counted as a false publication. All solves used the same complete native document and causal orbit authority across both arms. The interior replay reproduced the coordinates, RF and other scientific metrics of the base numerical fit exactly, with the fixed publication rule applied inside the installed executable. [Primary scores](scores.json) · [Installed policy parity](interior-profile/parity.json) · [Installed policy scores](interior-profile/scores.json)

| Position evidence | Zero `c` | Fitted `c` |
| --- | --- | --- |
| Stock wide GLRT → installed phase release | [Chart](charts/c0/waveform-site-phase-release.png) | [Chart](charts/fitted_c/waveform-site-phase-release.png) |
| Installed 20 m interior policy, retrospective on the same data | [Chart](interior-profile/charts/c0/waveform-site-interior.png) | [Chart](interior-profile/charts/fitted_c/waveform-site-interior.png) |

## Waveform coverage

The 300 s device clock held 150 scheduled eight-channel sweeps. All 1,200 waveforms reached the compiled stock wide GLRT at 10 MS/s. Each was a genuine 20 ms dual CI16 sample array, for 24 s of represented dwell time and 1.92 GB of generated sample bytes. The 12 transmissions covered 528 receiver probes. The other 1,872 receiver probes still contained noise and a detuned interfering tone. All 2,400 probe rows reached the native document, including probes whose candidate set failed the gate. The numerical receivers each prepared 724 observations and 24 tracks. [Visit schedule](schedule.json) · [Ordinary native document](native.json.gz) · [Per-visit IQ and detector hashes](visit-ledger.jsonl.gz)

| Detector audit | Result |
| --- | ---: |
| Planted probes with a candidate passing the stock gate and the frozen epoch/CFO test | 527 / 528 |
| Planted probes whose highest-margin passing candidate matched the plant | 494 / 528 |
| No-emission probes with any passing candidate | 196 / 1,872 |
| Median absolute wrapped CFO error among the 494 matching winners | 16.58 Hz |
| Median absolute epoch error among the 494 matching winners | 0.599 samples |

The planted check used ±2 ADC samples and ±1 kHz modulo the Qin symbol alias. It took place after position predictions were sealed and never supplied identities, coordinates, or candidate values to the receiver. Seven of the twelve emitters had differing projected Doppler under the later and causal elements. Across all planted lane-probes the absolute difference had a median of 177.9 Hz, a 95th percentile of 8.989 kHz and a maximum of 9.256 kHz. Five emitter element pairs yielded identical projections. [Per-probe planted-hit audit](planted-hit-ledger.jsonl.gz) · [Unblinded seed, site and generator inputs](truth-after-lock.json.gz)

## Timing, authority and reproduction

Waveform generation used 72.06 CPU s and the compiled detector used 28.48 CPU s across two lanes. Detection median and p95 were 24.01 and 32.72 ms CPU per dual visit. The bounded detector replay, including startup, both lanes and native archive projection, took 56.96 s wall. Each installed base solve used 20.46–20.58 CPU s, with 255.1–261.8 MiB process peak RSS. The interior rerun used 21.01–21.39 CPU s and 252.8–274.8 MiB process peak RSS. Individual solver launches verified an effective 512 MiB cgroup memory ceiling and zero swap. The timings describe separate waveform replay and post-GLRT numerical stages on the host. The observations come from scheduled synthesized probe windows rather than continuous acquisition. [Process and cgroup receipts](resource-receipts.json) · [Detection lock](detector-lock.json)

The 35 causal Space-Track snapshots ended at the 2026-11-14 05:37 UTC collection. The device clock starts at 06:39:20 UTC. The 09:37 UTC revised snapshot was available only to the generator and post-lock scorer. The independent numerical worker ran in an isolated filesystem and network namespace that exposed the stock receiver, detected native JSON, TrackConfig and causal archive. Its opaque request supplied one region center. The generator, private seed, actual receiver location, emitter IDs and later TLEs were outside that namespace. The installed interior replay was selected after the two primary results were known and retained both original offers. [Frozen protocol](PROTOCOL.md) · [Generator, detector and installed source digests](source-lock.json) · [Blinding commitments](input-lock.json) · [Primary prediction lock](prediction-lock.json) · [Interior replay lock](interior-profile/prediction-lock.json)

The generator and trial are in `tools.pipeline_eval.qualification.waveform_site_model` and `waveform_site_trial`. Use a fresh writable ext4 work location and a new evidence location containing a copy of `PROTOCOL.md`. Run the `prepare`, `detect`, and `position` actions of `waveform_site_trial` with the same work argument and `--out` location, then run `waveform_site_results` on those paths. To regenerate this exact stimulus pass `--seed-hex` to `prepare` using the original public post-lock seed from `truth-after-lock.json.gz`. The original native backend was the compiled stock wide library whose SHA-256 appears in `source-lock.json`. The replay assumes the authenticated causal and revised snapshots and the exact installed release are still locally available. The optional `waveform_site_interior` action runs the same sealed requests using the separately published `interior` executable after the primary scoring seal. Per-visit IQ digests allow byte verification without retaining the sample arrays.
