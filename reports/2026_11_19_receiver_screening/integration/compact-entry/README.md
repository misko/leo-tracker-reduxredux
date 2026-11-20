# Direct row-major compact v5 entry

The direct worker returned identical coordinates for both calibration arms on all three paired recordings after the ordinary control’s retry. Frequency scores, association and late-adoption decisions, and optimizer, projection, and salvage work counts also matched. The timings leave most of the CPU cost in numerical inference. The direct entry cut dependency and output overhead, with mixed wall times and peak child RSS reductions of 2.57 to 16.88 MiB. Neither worker produced a fix in the separate 512 MiB service trial.

[Both-arm position charts](charts/index.html) · [Frozen protocol](PROTOCOL.md) · [Measured positions and timings](receipt.json) · [Scientific comparisons](parity.json)

## Entry and boundary

`v5_compact_receiver.run(case, work_dir)` is the ordinary method entry. It compiles the existing projection kernel and launches the direct worker with the authenticated stored-native request. The worker reads native factors once, runs the existing candidate preparation, paired position solver, and full late compact decision, and writes one result. It reuses the row-major kernels and the frozen fine-screen routines, the bounded Armijo optimizer, ordered catalogue-slot phase initialization, and the existing scratch-cache policy. It retains scientific input, catalogue, and source verification plus the small counters used in this trial. The shared salvage routine still constructs transient shortlists, which the direct worker discards. The ordinary entry has no qualification imports, and no CLI registration was added in this study.

The source lock identifies every requested case, the stored native factor bytes, the causal catalogue, original offered tile, canonical request, software provenance, and scheduled order. DS29-0082 is an ordinary whole-IQ-derived input. DS26-0026 and DS29-0174 use stored capture-era native factors. Each recording was run on one x86 core at nice 10, with the order reversed on CPU 13. No new radio acquisition was needed. All six scheduled attempts were recorded within 375.45 seconds of the lock. The ordinary control stopped at a short orbit scratch write after 83.39 seconds wall and 79.83 seconds CPU. A single identical-input same-core retry completed, and its results have a separate chart. The primary chart retains the failed attempt.

[Direct worker](../../../../tools/pipeline_eval/variants/v5_compact_receiver.py) · [Source and input lock](source-lock.json) · [Primary and retry timings](timings.csv)

## Scientific parity

Each position-error value below is shared by both completed methods. The numbers use the held roof reference and follow the two calibration arms independently. The frequency score is the receiver’s fitted objective. The RMS values describe conditional Doppler fit. DS29-0174 took a qualified residual-addition path and both result contracts omitted its conditional RMS. Its two frequency scores matched exactly at 31,948.964069490874 and 31,939.048832629687.

| Recording | `c = 0` km | Fitted `c` km | `c = 0` RMS Hz | Fitted `c` RMS Hz |
|---|---:|---:|---:|---:|
| DS29-0082 · control retry | 2.784419 | 2.651096 | 106.670029 | 106.587065 |
| DS26-0026 | 1.622126 | 1.550916 | 72.218209 | 72.084323 |
| DS29-0174 | 0.880914 | 0.912241 | Unreported | Unreported |

| Recording | Observations | Tracks | Initial branches | Projector calls | Optimizer calls | Objective evaluations | Salvage tiles |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS29-0082 · control retry | 2,044 | 70 | 3 | 2,494 | 80 | 537 | 525 |
| DS26-0026 | 3,964 | 110 | 3 | 5,752 | 90 | 678 | 1,235 |
| DS29-0174 | 4,018 | 128 | 3 | 6,177 | 90 | 561 | 1,157 |

The cavity gate was closed on these three recordings. Both methods took the same subsequent finish decision, offered three residual targets per recording, and made the same reassociation decisions. The underlying cavity-fit path is shared with the control. The evidence covers the closed-gate replay and the observed late paths. [Per-arm scores](scores.csv) · [Exact comparisons and absent fields](parity.json)

## Unrestricted launcher cost

Wall time starts before the normal launcher and includes kernel compilation, scientific input verification, preparation, inference, and result output. CPU is the launcher and child CPU in that scope. RSS is the maximum child-process RSS. Stage wall times and output sizes are in the timing CSV.

| Recording and CPU | Control wall s | Direct wall s | Control CPU s | Direct CPU s | Control peak MiB | Direct peak MiB |
|---|---:|---:|---:|---:|---:|---:|
| DS29-0082 · CPU 12, control retry | 91.76 | 87.02 | 88.57 | 85.22 | 529.68 | 513.28 |
| DS26-0026 · CPU 13 | 126.51 | 137.11 | 123.94 | 123.17 | 883.32 | 866.44 |
| DS29-0174 · CPU 14 | 189.31 | 182.97 | 178.85 | 179.03 | 1547.87 | 1545.30 |

The ordinary retry was 4.75 seconds slower in wall time and used 3.35 more CPU seconds than the direct run. Both capture-era CPU differences were below one second. Completed control runs emitted 1.03–1.44 MB of stage logs and 46.99–51.89 kB of result JSON. Direct runs emitted zero stage-log bytes and 1.89–2.01 kB of result JSON. These are one-off paired measurements. [Whole-launcher and per-stage timings](timings.csv)

## Executed Python paths

A separate source-bound first-visit line trace used the ordinary input on CPU 12. Each traced result matched the corresponding untraced endpoint. The direct route reached 22 repository files and 1,581 unique file/line pairs, versus 51 files and 2,874 pairs for the instrumented route. Runtime qualification imports fell from 23 to zero. Both traces reached the same totals in the frozen science archive and launcher, 286 science paths and 28,846 lines plus four launcher paths and 205 lines. These totals include import-time execution and separate generated screen fragments. The full inventory also includes virtual environment paths and stores each function bearing executed lines. The compiled projection kernel is represented separately by its call counts.

The traced direct run took 101.01 seconds wall and 90.53 CPU seconds, +13.99 and +5.31 seconds against its untraced run. The traced control took 91.04 wall and 85.18 CPU seconds, −0.72 and −3.39 seconds against its untraced retry. The observed differences include repeat-run variation. The primary timings exclude this diagnostic tracer. [Trace counts and timing](trace-summary.json) · [Compressed line and function inventory](trace-lines.json.gz)

## Live 512 MiB service diagnostic

The additional DS26-0026 pair was selected after its 16.88 MiB unrestricted RSS reduction. The services used the same authenticated input on CPU 13, disk-backed scratch, an observed 512 MiB cgroup limit, and zero swap. Both reached 512 MiB of cgroup memory charge. The old worker was OOM-killed after its final observed `screen_candidates` stage and emitted no position. The direct worker reached its 93-second remaining service deadline, with zero OOM kills in its samples and no position. The diagnostic allowed the old worker a 140-second limit before OOM. Equal memory limits and unequal time budgets leave the long-running direct outcome unresolved. Cgroup charge includes the service’s memory accounting and is separate from the unrestricted process RSS above.

| DS26-0026 | Service maximum s | Final status | Wall s | Cgroup CPU s | Swap MiB | Output |
|---|---:|---|---:|---:|---:|---|
| Instrumented control | 140 | OOM kill | 103.17 | 100.03 | 0 | None |
| Direct entry | 93 | Service timeout | 93.35 | 85.36 | 0 | None |

[Cgroup and service evidence](cap/receipt.json)
