# Blinded simulated Qin over real receiver backgrounds

The installed phase release achieved **1.036 km with zero `c` and 1.452 km with fitted `c`** on the containing offer at one blinded simulated site. The same injected waveform over matched Gaussian noise yielded 1.031 km and 1.460 km. Recorded backgrounds produced 258 extra dark-probe gate winners, yet both positive arms prepared 20 tracks. Both installed profiles and original v5 withheld on the donor-only control. This result separates signal recovery from false foreground detections at this site.

## Position and publication

| Waveform and receiver | Containing error, zero / fitted `c` | Near-omitted decision, zero / fitted `c` | Containing RF RMS, zero / fitted `c` |
| --- | ---: | ---: | ---: |
| Recorded + Qin, phase release | 1.036 / 1.452 km | False fixes at 1.570 / 1.545 km | 15.955 / 15.665 Hz |
| Recorded + Qin, 20 m interior | 1.036 / 1.452 km | Both withheld, 1.570 / 1.545 km forced | 15.955 / 15.665 Hz |
| Recorded + Qin, original v5 | 1.032 / 1.448 km | False fixes at 1.565 / 1.539 km | 15.955 / 15.665 Hz |
| Gaussian + Qin, phase release | 1.031 / 1.460 km | False fixes at 1.577 / 1.551 km | 15.920 / 15.646 Hz |
| Gaussian + Qin, 20 m interior | 1.031 / 1.460 km | Both withheld, 1.577 / 1.551 km forced | 15.920 / 15.646 Hz |
| Donor-only, all three receivers, two offers | All withheld | All withheld | — |

The geometric prior placed the containing center 8.223 km from truth. The near-omission center was 13.984 km away, leaving truth 1.5 km beyond the fitted face. Both ordinary receivers published their omitted solutions directly on that face. Compact's containing endpoints landed at least 3.09 km inside the offered tile. The pre-existing 20 m rule retained all four containing-arm fixes across both waveform backgrounds and withheld all four omitted-arm fixes. Independent installed runs preserved the arm coordinates, RF metrics and other scientific results exactly for all four planted offers. For actual recorded-background fits, fitting `c` reduced the containing RF RMS by 0.290 Hz and increased position error by 0.416 km. The donor-only inputs gave no active curvature under all three solvers on both offers, so that control has no forced coordinates, RF residual or geographic truth. [Matched both-arm scores and decision parity](scores.json) · [Installed predictions](prediction-lock.json) · [Independent original-v5 predictions](../hybrid-v5/prediction-lock.json)

| Standard comparisons | Zero `c` | Fitted `c` |
| --- | --- | --- |
| Recorded background vs matched Gaussian | [Chart](charts/c0/hybrid-site-recorded-background.png) | [Chart](charts/fitted_c/hybrid-site-recorded-background.png) |
| Prospective 20 m profile on recorded background | [Chart](charts/c0/hybrid-site-hybrid-interior.png) | [Chart](charts/fitted_c/hybrid-site-hybrid-interior.png) |
| Prospective 20 m profile on matched Gaussian | [Chart](charts/c0/hybrid-site-gaussian-interior.png) | [Chart](charts/fitted_c/hybrid-site-gaussian-interior.png) |

## Acquisition boundary

The three arms each sent 768 dual-CI16 visits through the unchanged stock wide GLRT at 10 MS/s. The test used one synthetic target location and a 300 s scheduled clock. A 20 ms visit took its background from one of two archived roof recordings on the same RF and Qin edge. The same newly simulated emission was added to each recorded/Gaussian pair. The recorded-only arm received the identical normalized real background without an injected signal. The original donor recording times were intentionally scrambled by a per-channel salted assignment without replacement. Recorded background can contain real roof emissions and interference. The target geography and simulated emitters remain distinct from the donor installation. [Frozen protocol](PROTOCOL.md) · [Donor selection authority](donor-plan.json) · [Full visit ledger](visit-ledger.jsonl.gz)

The detector and donor pipelines completed in 59.74 s wall within two CPU lanes. They consumed 2.50 GB of authenticated compressed payload and decoded 3.28 GB from four archive segments. Two lanes read 2,048 archived dual windows and assigned 768 distinct windows to the simulator. All eight channels supplied 128 geometry-valid candidates and contributed exactly 96. Each compressed read was at most 128 KiB. Waveform generation and mixing used 37.41 CPU s. Stock GLRT calls used 19.35 CPU s for the recorded mix, 10.20 CPU s for the Gaussian mix, and 18.61 CPU s for the donor-only input. Each arm carried 1.229 GB of scheduled CI16 mixture. The visit ledger binds raw archive, each mixture, normalized donor-only background, inserted emission and actual detector response. Raw arrays are regenerated on demand. [Per-lane archive and detector receipts](detector-lock.json) · [Source, libraries, templates and installed profiles](source-lock.json)

| Stock wide detector | Recorded + Qin | Gaussian + Qin | Donor-only |
| --- | ---: | ---: | ---: |
| Planted probes with any correct gate match | 346 / 346 | 346 / 346 | — |
| Planted probes with a correct observation winner | 340 / 346 | 343 / 346 | — |
| Dark probes with a passing winner | 258 / 1,190 | 0 / 1,190 | 345 / 1,536 |
| Median absolute wrapped CFO error on planted winner matches | 15.54 Hz | 15.70 Hz | — |

The frozen audit required matching epochs within two ADC samples and CFO within 1 kHz modulo the Qin alias. This post-lock audit joined 1,330 selected receiver probes to capture-era factors using the original window, receiver, counter, edge and RF. Of those probes, 244 had at least one passing historical candidate. In 205 probes, the normalized donor-only winner matched one of those positive capture-era candidates. This confirms some donated backgrounds contain reproducible signal signatures. All 258 dark positives in the hybrid mix matched the normalized donor-only winners. The six wrong winners on illuminated hybrid probes had zero exact donor-only matches. The dark positives add clutter to the simulated experiment and do not create a target location. [Stage figure](detector-evidence.png) · [Plotted counts](detector-evidence.csv) · [Stage seal](stage-lock.json) · [Per-probe native donor audit](donor-source-audit.jsonl.gz)

The sealed synthetic target lay 3,392 km from the previous stressed waveform site and at least 3,003 km from twelve earlier simulated locations checked. Its earliest independent revised orbit collection was received at 11:37 UTC. The simulated clock started at 08:12:40 UTC using the causal history ending at 05:37 UTC. Median absolute causal-to-revised projected mismatch was 2.184 kHz across the shared emitted probes. [Post-lock scene and seed](custodian-after-lock.json.gz) · [Causal catalogue authority](causal-authority.json) · [Blind targets released after terminal predictions](truth-after-lock.json)

The installed planted position calls took 17.59–19.63 s wall per offer, under a verified 512 MiB cgroup ceiling and zero swap. The installed donor-only calls returned in 1.09–1.53 s. Original v5 returned the paired planted positions in 81.85–114.99 s and withheld in 6.19–6.24 s on the donor-only offers, with its separately planned 3 GiB and zero-swap ceiling. These are post-GLRT measurements, with source prep and both numerical arms included. The test represents one new simulated site with a supplied region and shuffled real backgrounds from the original roof setting. [Installed runtime proofs](runtime-proofs.json) · [Independent original-v5 runs](../hybrid-v5/positions.jsonl.gz)

## Reproduce

Run `python -m tools.pipeline_eval.qualification.hybrid_site_trial` with `prepare`, `detect`, and `position` using a fresh ext4 work directory and a new evidence directory containing this protocol. Set `--seed-hex` to the post-lock seed to regenerate the same donor salt, opaque offers, source selection and samples. The archive read uses the existing `leo` service identity through the established worker runtime, with bounded streaming from the local sealed assets. The installed paired profiles verify exact native, causal catalogue, TrackConfig and offer identities. After the independent reference publishes its terminal prediction lock, run `python -m tools.pipeline_eval.qualification.hybrid_site_results` with the work directory and `--reference /path/to/hybrid-v5/prediction-lock.json`. [Independent original-v5 protocol](../hybrid-v5/PROTOCOL.md)
