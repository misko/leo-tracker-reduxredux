# Guarded sliding-tone coarse acquisition

The shared-tone grid kept every candidate field and positive winner identical to the tiled and original producers on the 16 scheduled visits. It cut median holdout detector CPU by 23.4% on DS26-0036 and 6.9% on DS29-0082, below the predeclared 25% threshold for each recording. The tested candidate still required 43–48 times the 20 ms RF window duration on one efficiency core. Position and Doppler RMS were unmeasured. [Gallery rows](positions.jsonl.gz)

The capture-era producers for DS26-0036 and DS29-0082 ingest 200,000 CI16 samples per receiver over a 20 ms visit. Their initial coarse grid evaluates 21 CFO rows, 13,333 integer epochs and 12 short pilot anchors. When a fractional detection on one receiver triggers the producer’s fallback on the other, the same search evaluates 22 anchors. Each anchor spans 44 samples at the captured 10 MS/s.

The prototype shares the eight Qin tone correlations across anchors of each CFO. For an IQ block starting at `b`, it multiplies by the common complex tones and takes FP64 prefixes. For local offset `i`, the difference between prefix entries `i+44` and `i` gives the rectangular aperture. Rephasing that difference gives a tone product relative to the hypothesis epoch. The anchor’s eight Qin QPSK states enter as complex sign changes and swaps. A one-tap correction preserves the template’s floating time-to-symbol boundary, which can place the first sample in the preceding symbol. The bank folds all relevant anchors before discarding each eight-tone, 2,048-position block.

For one receiver’s 21-by-12 grid, the tiled direct bank evaluates 48,780,144 supported anchor magnitudes and 2,146,326,336 complex multiply-accumulates before peak selection. The block-prefix variant evaluates the same magnitudes with 44,883,888 complex modulation products, 33,592,776 complex rephase products and sign/swap sums across the eight tones. This arithmetic model excludes normalization, memory traffic and repair. On synthetic full-range search geometry the measured coarse CPU per receiver moved from approximately 0.228 s tiled to 0.138 s for the 12-anchor proposal, plus 0.030 s for selection and repair. For 22 anchors the corresponding measurements were 0.398 s, 0.193 s and 0.024 s. A development version that reread 12.8 MB of tone arrays for each anchor was slower than tiled direct. The blocked version uses 128 KiB for those arrays.

## Numerical guard

At each supported CFO/epoch cell, the error budget accounts for finite-precision phase tables, FP64 prefix differences, residual mismatch with the supplied complex template, and FP32 rounding in both the proposal and the tiled reference. The budget requires CI16 values exactly representable as integers. It uses an exact FP64 power prefix and the CI16 minimum nonzero local energy norm of one. The candidate repairs tiles covering all cells within twice the bound of the provisional last retained peak, including their immediate epoch neighbors. Repair calls the tiled kernel with the original lane alignment and end support. It certifies the result only if the repaired final peak set and its neighbors are exact and the lowest selected score exceeds every unrepaired upper bound. The complete tiled scan handles unsupported geometry and unresolved intervals.

## Replay

Both recordings use their installed capture-era sources and validated policy identity. The paired tiled and spectral modes share the same fractional sampler and keeper, with repeated order alternation. An additional unmodified producer call verifies end-to-end payload identity. Timed calls exclude archive reads, compilation and serialization. The CPUs are separate pinned efficiency cores on the same Intel Core Ultra 9 285K host, with one thread per numerical runtime. The two case processes ran concurrently and could contend for shared caches or memory.

| Recording and split | Valid / scheduled | Installed CPU s | Tiled CPU s | Spectral CPU s | Full CPU saved |
| --- | ---: | ---: | ---: | ---: | ---: |
| [DS26-0036 development](DS26-0036-development.json.gz) | 4 / 4 | 2.273 | 0.946 | 0.790 | 16.5% |
| [DS26-0036 holdout](DS26-0036-holdout.json.gz) | 4 / 4 | 2.382 | 1.125 | 0.861 | 23.4% |
| [DS29-0082 development](DS29-0082-development.json.gz) | 3 / 4 | 2.361 | 1.034 | 0.893 | 13.6% |
| [DS29-0082 holdout](DS29-0082-holdout.json.gz) | 3 / 4 | 2.586 | 1.038 | 0.966 | 6.9% |

Across all valid holdout repeats combined, DS26 CPU fell from 14.49 to 11.20 s and DS29 from 11.23 to 9.94 s. Holdout medians for the coarse provider moved from 446 to 266 ms and from 444 to 273 ms, respectively. Spectral peak selection and exact repair added 45 and 57 ms, including both peak-selection passes. The measured tiled time outside the coarse provider alone was 677 and 596 ms per visit, about 34 and 30 RF window durations. Eliminating all work in that provider would still leave those measured downstream costs.

The two producers agreed on all 17 archived integer positives and all 16 archived fractional positives across 14 valid visits. The two exclusions were reproduced. The 93 scored receiver grids, counting the three repeats, yielded identical tiled peak triples with zero fallback. Across four independently audited visits, the maximum pre-repair grid error was `1.13e-8` against bounds from `2.11e-5` to `2.21e-5`. At most 192 of 279,993 cells in one CFO/epoch map needed tiled repair.

At 731 samples and +48 kHz the planted pilots recovered the correct epoch on both receivers in both cases. All four fractional winner CFOs were within 0.1 Hz of truth. Zero IQ produced no integer or fractional positives. Both synthetic controls matched the installed and tiled full payloads. Full candidate-payload comparisons include ordered ranks, epoch, CFO, integer and fractional scores, and the margin gates. Per-receiver positive winner identities and provenance are in the receipts.

Peak traced allocations on one valid development visit were 21.49 → 21.53 MB on DS26 and 22.31 → 22.35 MB on DS29. Persistent arrays during the spectral stage peaked at 5.85 MB, including the 128 KiB tone block. Process high-water RSS was 1.22 GiB for the process that also ran the installed producer, archive loader, and both trial modes. It includes their shared state and does not isolate the incremental cost of either trial mode.

The AVX2/FMA component tests cover dense 11- and 44-tap maps, full-range and sparse CI16, zero energy, fallback for unsupported samples, and forced failure of the selection certificate. Development and holdout schedules, acceptance criteria, and geometry corrections are in [PROTOCOL.md](PROTOCOL.md).

Replay from the repository root with the frozen case producer’s `src` directory first on `PYTHONPATH`, the local `.venv` interpreter, one pinned CPU in 12–14, and `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, and `BLIS_NUM_THREADS` set to one. The producer paths and recorded configuration digests are in each receipt.

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.spectral_grid_eval \
  --case DS26-0036 --split holdout --out /tmp/ds26-spectral-holdout.json.gz
```
