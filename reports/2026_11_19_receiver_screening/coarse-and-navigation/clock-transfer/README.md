# Carrying anonymous satellite carrier levels across revisits

Overlapping donor tracks supported 2–7 carried satellite terms per roof recording. Only 10 of 41 untouched target heads received a carried forecast. On the three measured recordings with paired targets, the carried model lost to both the common receiver clock and the free local track clock on capped held CFO loss. All four containing offers and all four offers in each missing condition were withheld. [Held CFO and overlap figure](clock-carrier-support.png) · [Per-case scores](scores.csv) · [Both-arm geographic charts](charts/index.html)

## What changed

The existing absolute Doppler model shares a wrapped receiver level. The joint-pass model shares receiver-path slopes while fitting free pass levels, and the smooth-clock and clock-plus-offset variants fit smooth receiver terms with independent track offsets. The shared-orbit variant shares satellite phase displacement. This experiment estimates a separate fractional carrier level for each qualified automatic NORAD. It carries that level forward, scaled by actual RF, alongside a common affine receiver-path clock. A donor family qualifies when two independently extracted fragments on distinct receiver paths or RFs overlap for at least three seconds. [Absolute Doppler](../../receiver-core/absolute-doppler/README.md) · [Joint-pass clock](../../latency-and-support/joint-pass/README.md) · [Smooth clock and independent offsets](../../recovery/clock-transfer/README.md) · [Shared satellite phase](../../deployment/shared-orbit-fit/README.md)

Native GLRT peak alternatives and causal TLEs determine the donor and target identity candidates. The donor shortlist and owner choice are frozen at the public coarse center. Every control uses those same donor measurements and candidate states. A held target chooses its first anonymous identity from its first 20 seconds. Its remaining valid native visits stay unlinked and score the forecast. The identity sham rotates only the learned carrier levels across the qualified NORADs. The free-track control fits a new level and drift to the target head. Matched forecast RMS uses the same suffix visits at the carried method's selected location. It measures distance to the nearest gated native alternative, conditional on target availability. The capped loss adds unsupported target heads at the registered cap. [Frozen protocol](PROTOCOL.md) · [Input and prediction seals](prediction-lock.json) · [Same-target RF comparisons](paired-rf.csv)

The data-only receiver-clock rank was eight in every replay. Carrying satellite levels added 2–7 directions on the roof and five in simulation. The RF-linear `c` column equals 11.5 times the sum of all fractional satellite columns minus 11.5 times the sum of receiver-path intercept columns. Adding it to the unrestricted design increased rank on zero replays. The largest reconstruction residual was 2.3 × 10⁻¹⁴. Restricting which satellites may carry and shrinking their levels chooses a gauge. The charts show the `c = 0` gauge and mark fitted `c` unavailable. [Rank audit per recording](scores.csv)

## Measured roof

The four original five-minute recordings have disjoint time windows and come from one roof. The near and far control squares leave the surveyed receiver 2.318–2.319 km and 32.352–32.353 km outside, respectively. For the carried method the forced median errors were 7.263 km on containing offers, 10.123 km on near misses and 36.904 km on far misses. The containing median was 8.193 km with a free track clock and 8.193 km at the tile center. The four matched no-repair v5 runs gave `c = 0` errors of 0.670–1.320 km on their original offers. They use richer geometry and radio inference. [Per-offer and original v5 scores](scores.csv)

| Recording | Qualified donor families, all / cross-RF | Carried / eligible target heads | Matched capped held CFO loss, carried / clock only / free track / sham | Carried forced error |
| --- | ---: | ---: | ---: | ---: |
| DS26-0004 | 7 / 7 | 3 / 10 | 11.19 / 8.38 / 0.06 / 10.93 | 6.333 km |
| DS26-0032 | 4 / 3 | 0 / 11 | — | 8.193 km |
| DS29-0247 | 2 / 0 | 2 / 12 | 16.00 / 10.81 / 3.48 / 16.00 | 8.193 km |
| DS29-0316 | 5 / 4 | 5 / 8 | 10.07 / 9.77 / 4.51 / 9.88 | 6.333 km |

The held geographic lead of the carried result on containing tiles ranged from −0.153 to +0.053 capped loss units. The publication rule required +0.5 against a candidate at least 10 km away and +0.5 against the identity sham. DS29-0316 reached two qualified held blocks and two orbit hypotheses on its containing offer. Its spatial lead was +0.053 and its sham lead was −0.117, both below their thresholds. [Per-offer diagnostics](scores.csv)

## Blinded generated site

The simulation planted a shared fractional carrier level on two RFs per active interval and separate receiver clocks. On the containing square, the carried model assigned the planted identity on all four target heads it forecast. The clock-only and local-track variants assigned all eight correctly, and the sham assigned the four matched heads correctly as well. On those four common targets the carried CFO RMS was 1,162 Hz, compared with 1,839 Hz for the receiver clock alone, 1,339 Hz for the sham and 71 Hz for the free local track clock. The carried forced position was 2.027 km from truth, compared with 3.022 km for the free-track fit and 5.542 km for the center. The held spatial lead was −2.137. Each containing, near-missing and far-missing offer was withheld, with near and far forced errors of 5.703 and 36.028 km. These are separate simulated detector-factor results. [Released simulation labels](simulation-release.json) · [First-unknown identity audit](simulated-identity.json) · [Simulated geographic chart](charts/c0/clock-carrier-simulated-position.png)

All five numerical workers completed on CPUs 20–21. The shared measurement boundary includes anonymous peak handling, orbit propagation, every fit and the held comparisons. It used a total of 11.70 CPU-seconds, 2.76–3.77 s direct wall per capture and 220.39 MiB peak worker RSS. All methods ran together, so these costs measure the comparative experiment. [Raw worker outcomes](predictions.jsonl.gz) · [Stage input CSV](clock-carrier-support.csv) · [Score and stage seal](score-lock.json)

## Reproduce

Use new local paths and copy the protocol into the report directory. The fixed seed reproduces the generated factor input. The initial simulation preflight failed before any fit because its emitter channel index was incremented twice. The completed run corrected the index and reused the original seed. [Exact generated input and seed](as-run-simulation.tar.gz) · [Worker source archive](as-run-sources.tar.gz)

```bash
trial=tools.pipeline_eval.qualification.clock_transfer_grouped_trial
python -m "$trial" stage "$WORK" --report "$REPORT" --simulation-seed-file "$SEED"
python -m "$trial" run "$WORK" --report "$REPORT"
python -m tools.pipeline_eval.qualification.clock_transfer_grouped_results "$WORK" --report "$REPORT"
```
