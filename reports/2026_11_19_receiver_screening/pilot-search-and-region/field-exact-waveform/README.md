# Pruned fine-CFO detector on the complete DS29-0082 recording

The fresh detector exactly reproduced all **42,162 ordered published candidates** on DS29-0082. Independent compact fits on fresh and archived factors returned the same coordinates and frequency diagnostics in both calibration arms. The eight-worker replay took **496.59 seconds** and used **1,892.84 detector CPU seconds**. Every valid visit exceeded the 20 ms detector wall budget. [Native audit](audit.json) · [Timing comparison](comparison.json) · [Prediction lock](prediction-lock.json)

DS29-0082 is the 299.997-second upper-edge dual-antenna recording. The replay composes the prepared folded FFT grid, row-wise peak selector, pruned binary64 fine CFO transform and checked refiners inside the installed original capture producer. Each worker uses the signed capture policy. The original 25 km offer and 45 causal TLE snapshots bind the compact fits. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

## Native fidelity

The workers authenticated **106 chunks and 6,772 scheduled visits**, including **4,868 valid visits and 1,904 original exclusions**. All **9,736 physical probe rows**, including 38 empty probes, matched the original capture archive and the earlier complete combined replay byte for byte in canonical encoding. The audit checks candidate rank, integer epoch, fractional epoch, fractional CFO, exact and control scores, fractional margin and gate flag separately. It found zero changes to candidate masks, probe order, delivery clocks, UTC anchor, final sample counter or capture exclusions. All 4,582 gate passes and 1,868 probes with a passing candidate matched. The pruned path handled 87,000 fine calls on 4,868 valid visits with zero fallbacks. [Fresh native stream](native.json.gz) · [Fine call ledger](fine.csv) · [Nine-window public launch check](receipts/smoke.json)

## Position

The fresh and archive compact fits used separate CPU-pinned, 512 MiB, zero-swap services. Each fit ran both calibration arms with matched observations, candidates, priors and search budgets. The signed compact predictions preceded geographic scoring against the held survey. The earlier combined and wide full-waveform runs used the same recording, causal catalogue and 25 km offer. [Geographic scores](scores.csv) · [Original v5 roles](v5-roles.csv) · [Score lock](score-lock.json) · [Position chart, c = 0](charts/c0/modifications.pdf) · [Position chart, fitted c](charts/fitted_c/modifications.pdf)

| Position input | Error at `c = 0` (km) | Error with fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Fresh pruned fine-CFO replay | 0.56810 | 0.51579 | 97.0034 / 96.6838 |
| Original archive, independent compact fit | 0.56810 | 0.51579 | 97.0034 / 96.6838 |
| Earlier complete combined replay | 0.56810 | 0.51579 | 97.0034 / 96.6838 |
| Earlier complete wide four-region replay | 2.48917 | 2.34573 | 84.4215 / 84.2481 |
| Earlier complete wide five-region replay | 1.73502 | 1.75710 | 89.6104 / 89.2502 |
| Original v5 no-repair | 0.56695 | 0.51723 | 97.0036 / 96.6836 |
| Original v5 selective gap | 0.56695 | 0.51723 | 97.0036 / 96.6836 |
| Original v5 omitted-track-one | 0.11542 | 0.48617 | 109.5587 / 105.4708 |
| Original v5 omitted tracks | 0.11542 | 0.48617 | 109.5587 / 105.4708 |

Fitted `c` reduced the fresh compact geographic error by **52.31 m** at this site. Conditional RF RMS fell by 0.3197 Hz and the frequency score rose from 6,337.72 to 6,342.81. Both errors stayed within 5% of the matched no-repair and selective-gap references. The two omitted-track roles attained smaller errors in each respective arm.

## Host resources

The raw workers used CPUs 0, 1, 4, 5, 6, 7, 20 and 21 on the Intel Core Ultra 9 285K, each capped at 512 MiB charged memory with zero swap. They read 8.405 GB of compressed data, authenticated 10.835 GB of decoded IQ and ran 10,875 full folded grids. Their bound intervals consumed 1,919.27 cgroup CPU seconds. Peak worker RSS was 208.92 MiB and peak charged memory was 512 MiB. [Worker receipts](receipts/) · [Per-visit timing CSV](timing.csv) · [Timing chart](timing.pdf)

| Complete original producer replay | Fresh pruned path | Earlier combined path |
|---|---:|---:|
| Raw launch through worker exit, wall s | 496.59 | 498.13 |
| Resident detector CPU, total s | 1,892.84 | 3,035.22 |
| Resident detector CPU, P50 / P95 / P99 / max ms | 290.89 / 754.94 / 1,105.40 / 1,683.75 | 600.13 / 1,197.36 / 1,467.57 / 2,008.31 |
| Resident detector wall, P50 / P95 / P99 / max ms | 401.22 / 1,197.60 / 3,804.31 / 15,699.16 | 633.72 / 1,549.92 / 4,870.07 / 17,470.74 |
| Valid visits at or under 20 ms detector wall | 0 / 4,868 | 0 / 4,868 |

The two complete runs used different detector compositions and CPU rosters. The isolated interleaved test held the prepared row-wise detector fixed and changed only the fine search. On the four held DS29-0082 windows, its paired median saving was 31.39 CPU ms per visit, or 6.41%, across 20 timing pairs. The all-root panel median saving was 28.93 ms over 80 pairs. Earlier wide four- and five-region controls met the 20 ms detector wall budget on 38 and zero valid visits, respectively. [Isolated held comparison](../fine-search/summary.json) · [Earlier combined replay](../../antenna-confirmation/capture-whole/README.md) · [Earlier wide resource records](../../latency-and-support/complete-timing/resources.csv)

| Compact position service, both arms | Wall s | Cgroup CPU s | Charged memory peak (MiB) |
|---|---:|---:|---:|
| Fresh factors, CPU 0 | 29.60 | 27.08 | 272.79 |
| Archived factors, CPU 1 | 29.08 | 27.32 | 273.43 |
| Earlier wide four-region factors | 41.13 | 39.66 | 512.00 for full replay and fit |
| Earlier wide five-region factors | 42.26 | 42.11 | 512.00 for full replay and fit |

Both fresh position services used zero swap. The elapsed time from the fresh raw launch to its coordinates was 627.01 seconds. That interval includes roughly 101 seconds between raw completion and the fresh fit for ledger finalization, native assembly and fit dispatch. A stalled XFS lookup during the raw ledger write contributed to that gap. The raw elapsed measurement ended before the ledger write. [Fresh service receipt](receipts/actual/terminal.json) · [Archive service receipt](receipts/archive/terminal.json) · [Resource comparison](comparison.json)

## Reproduce

Use the interpreter, capture release, native libraries and compact receiver named in the source lock. The freeze command creates a new source lock for an unpublished study directory. For a repeat against the frozen inputs, copy the existing source lock to a new work directory and pass that directory to the remaining commands. Raw files and compact receipts stay in the chosen work directory. The original IQ corpus is read-only.

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.field_exact_waveform freeze
.venv/bin/python -m tools.pipeline_eval.qualification.field_exact_waveform preflight
.venv/bin/python -m tools.pipeline_eval.qualification.field_exact_waveform run
.venv/bin/python -m tools.pipeline_eval.qualification.field_exact_waveform_results position
.venv/bin/python -m tools.pipeline_eval.qualification.field_exact_waveform_results publish
```

Regenerate the two position charts from the published prediction archive.

```bash
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/pilot-search-and-region/field-exact-waveform \
  --out /var/tmp/field-exact-waveform-charts
```
