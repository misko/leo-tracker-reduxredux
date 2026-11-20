# Stop fractional GLRT after an original ranked gate pass

On 16 genuine dual-receiver visits, stopping after the first ranked fractional pass skipped **126 of 312 fractional anchors** and saved **10.08 ms of complete detector CPU** in the pooled paired median (2.75%). Stopping after the second pass skipped **72 of 312 anchors** and saved **4.54 ms** (1.30%). All 39 physical attempts, including seven conditional retries, ran in the same order. The stopped outputs matched their numerical rank prefixes byte for byte at the per-attempt public, final public and native factor boundaries. [Complete detector chart](stage.pdf) · [Timing and work counts](summary.json) · [Protocol](PROTOCOL.md)

| Saved I/Q | First pass anchors omitted | First paired CPU saved | Second pass anchors omitted | Second paired CPU saved |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237, lower | 35 / 80 | 14.19 ms | 18 / 80 | 1.05 ms |
| DS29-0082, upper | 21 / 88 | −3.86 ms | 12 / 88 | 6.31 ms |
| DS29-0174, upper | 35 / 72 | 11.86 ms | 12 / 72 | −2.26 ms |
| DS29-0519, lower | 35 / 72 | 21.15 ms | 30 / 72 | 10.24 ms |

The timing panel includes five interleaved repeats per visit, on fixed CPUs 6 and 7 with one numerical thread. All modes use the prepared coarse grid, row-wise peak selector, pruned fine search and qualified fused GLRT refiners. Pooled paired wall savings were 8.34 ms and 5.61 ms. Per-recording changes include regressions. The chart shows the range of individual CPU and wall measurements under shared host load. [Input and source lock](input-lock.json) · [Detector qualification seal](qualification-lock.json)

## Where the stop applies

The original detector establishes candidate rank after evaluating every retained coarse seed's fine CFO, conditioned CFO and exact/control verification. Every mode keeps that work and batches all original integer GLRT anchors. The research path then calls the installed fractional scorer on one anchor at a time in original rank order. After the selected number of fractional margins at or above 0.025, subsequent circular grid and continuous refinements are skipped. Rejections and partial scores before the cutoff remain public, and complete native rows keep their original ranks. Singleton fractional grid calls trade batch efficiency for the ability to stop.

A primary receiver attempt with no fractional pass scores every candidate. The installed dispatcher may replace it with a retry when the partner primary has a pass. The same cutoff then applies to the retried attempt. The existing public saved-I/Q interface uses a single scheduled probe per receiver and emits its candidates. The stop rejects other probe schedules. In the held panel, the number of fractional passes across all attempts fell from 47 to 19 with the first cutoff and to 31 with the second. The preference for the earliest ranked passes can remove alternatives used by localization. [Operative detector source](../../../../tools/pipeline_eval/variants/first_gate.py) · [Stage tests](../../../../tests/pipeline_eval/test_first_gate.py)

## Saved-I/Q command

Use `--fractional-stop first` or `--fractional-stop second` to opt in. The default `full` evaluates all original candidates. The command records the pinned producer and variant source hashes, mode, gate threshold, and per-worker available and evaluated fractional anchor counts. Both options can be combined with the existing exact detector flags. [Normal receiver and input contract](../../original-support/receiver-command/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --case DS26-0237 --out /var/tmp/ds26-first-fractional --cpus 6 \
  --peak-selector row-wise --fine-search pruned --fractional-stop first \
  --raw-limit 120 --smoke
```

The normal command ran the full detector and then the first-pass policy on the first 64 visits of each recording, pinned to CPU 6 for DS26-0237 and CPU 7 for DS29-0082. Each of the four workers had a 120-second limit, 512 MiB of charged memory and zero swap. Across all 128 visit pairs, the clocks, source hashes, RF fields and exclusions were unchanged, and the emitted factor arrays exactly matched the offline numerical cutoff. The measured chunks ended before a position fit. [Worker receipts](smoke-receipt.json) · [Actual emitted visit records](smoke-visit-records.json.gz)

| First chunk | Valid / invalid visits | Fractional ranks skipped | Projected gate passes, full → first | Detector CPU, full → first | Raw wall, full → first |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | 64 / 0 | 238 / 1,176 | 79 → 34 | 19.74 → 19.93 s | 23.92 → 23.63 s |
| DS29-0082 | 48 / 16 | 189 / 864 | 77 → 27 | 15.26 → 14.76 s | 19.65 → 18.71 s |

The same coarse and fine search counts were observed on both sides of each pair. DS29-0082 ran 109 coarse grids in 108 physical evaluations. The existing rank tie guard can repeat a coarse search within one physical evaluation. The first-pass option used 0.95% more detector CPU on DS26-0237 and 3.31% less on DS29-0082. Zero valid detector visits finished within 20 ms in either policy on either chunk.
