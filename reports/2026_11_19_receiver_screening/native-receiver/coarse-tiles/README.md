# Shared Qin phase pairs in the standalone C detector

Applying the four relative QPSK phase sums to both anchor masks saved **3.98% median paired complete detector CPU** on 12 saved dual-radio visits from three producers. Complete median CPU fell from **294.94 to 283.20 ms**. The symmetric-carrier sliding window took **11.11% more paired CPU**. Both kernels regenerated every ordered seed and reproduced every verifier packet byte-for-byte against the standalone C incumbent. The phase-pair saving leaves the 20 ms input deadline far away. Position accuracy and physical embedded throughput were unmeasured. [Stage chart](stage.pdf) · [Plotted values](stage.csv) · [Paired comparisons](paired-clocks.csv)

| Kernel | Complete CPU median / P95 (ms) | Complete CPU range (ms) | Median paired CPU / wall ratio | Coarse CPU ratio |
| --- | ---: | ---: | ---: | ---: |
| Incumbent C | 294.94 / 480.10 | 280.06–488.83 | 1.000 / 1.000 | 1.000 |
| Shared phase pairs | 283.20 / 460.55 | 267.67–470.44 | 0.960 / 0.968 | 0.927 |
| Symmetric-carrier sliding | 324.91 / 536.65 | 311.10–549.08 | 1.111 / 1.115 | 1.156 |

Each CPU received three independently interleaved orders, with the opposite three orders on the second CPU. Each method occupied each order slot once on each CPU. The timed stages cover both physical lanes, seed selection, fine acquisition, GLRT and conditional retry after IQ is resident. Each visit includes its 12-anchor primary lanes and any 22-anchor peer retry. Four of the 12 visits used a peer retry. The phase-pair median CPU ratio was 0.957 on CPU 8 and 0.968 on CPU 9, with a CPU reduction in 69 of 72 matched observations and in every per-visit median. Time sharing affected the wall tail. Phase-pair P95 wall time was 524.94 ms versus 493.60 ms for the incumbent, with a 1,675.81 ms maximum. [Clock distributions and host](summary.json) · [Raw clocks and repeat checks](timing.json.gz)

## Profile and kernels

Separate line sampling on the same authentic inputs attributed 29.3–37.7% of incumbent detector CPU to anchor folding, and 20.9–24.3% to the eight-tone roll and transposition. The host blocked hardware performance counters. GCC profiling builds supplied 10 ms instruction samples. The timings above came from matched optimized release builds. [Profile attribution](profile.csv) · [Raw gprof tables](profiles.json)

The phase-pair kernel uses the incumbent's per-CFO rolling tone outputs and reuses adjacent-tone sums for the primary 12-anchor family as well as the 22-anchor retry. Qin's four QPSK phases reduce each pair to four relative phase combinations. Within 128-sample blocks the kernel reads four pairs per anchor in place of eight individual tones. The exact frame-origin formula jumps directly to the first frame that overlaps each block. It keeps the pilot seam correction, historical support normalization and peak selector. [Candidate kernel](../../../../tools/pipeline_eval/variants/c_coarse_tiles.h) · [Isolated sealed build](../../../../tools/pipeline_eval/qualification/c_coarse_tiles_build.py)

The second kernel mixes each sample once at the proposed CFO, using the exact 256-sample periodicity of the eight tone offsets. Symmetric tones share four real products. A 44-sample ring updates the eight complex sums, with direct rebasing every 128 samples. The output restores the relative tone phase, folds phase pairs, and normalizes the combined magnitude once. Its extra mixed-sample and carrier data movement and serial CFO oscillator work accompany the slower profile. Both candidates build as separate static binaries against the frozen C verifier. [Profile measurements](profile.csv) · [Exact build flags and binary hashes](build-lock.json)

| Resource | Incumbent | Shared phase pairs | Symmetric carriers |
| --- | ---: | ---: | ---: |
| Static x86 binary (bytes) | 958,016 | 945,728 | 949,824 |
| x86 text section (bytes) | 651,261 | 642,365 | 643,005 |
| Compiler-reported coarse grid stack (bytes) | 53,824 | 36,896 | 85,440 |
| Peak process RSS in a direct launch (KiB) | 13,320 | 13,184 | 13,380 |

Named heap allocations were identical across all three, including 5,374,168 coarse workspace bytes, 5,858,144 verifier bytes and a 1,600,000-byte input buffer. Direct shell launches provided RSS so the Python harness's pre-exec high-water mark would stay out of the memory comparison. [Stack and allocation evidence](summary.json) · [Direct resources](direct-resources.json)

## Seeds, gates and controls

| Native panel | Visits | Ordered seeds | Peer retries | Integer passes | Fractional passes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical held | 6 | 112 | 2 | 17 | 19 |
| Physical-manifest hash holdout | 6 | 112 | 2 | 8 | 8 |

Both candidates preserved all inventory, coarse peak keys including pre-nudge epochs, fine-search seeds and verifier bytes across all 144 timed candidate comparisons. The historical held verdicts additionally matched the independent archive. Two equivalent duplicates retained the incumbent's rank representation and physical meaning. The nearest published positive fractional margin was 2.31 × 10⁻⁶ above the 0.025 threshold, and the nearest negative margin was 7.16 × 10⁻⁵ below. The largest absolute historical verifier differences from the archived oracle were 7.79 × 10⁻¹⁴ in fractional margin, 3.01 × 10⁻¹³ samples in fractional timing and 0 Hz in the fractional residual frequency. [Per-visit qualification](qualification.csv) · [Ranked candidate ledger](candidates.json.gz) · [Independent oracle audit](archive-audits.json.gz)

Across 3,359,916 development score cells per variant, support and every ordered peak agreed. Maximum absolute differences from the incumbent were 4.91 × 10⁻⁹ for phase pairs and 8.11 × 10⁻⁸ for symmetric carriers. Across the 12 timed RF inputs, maximum retained-score deviations were 2.59 × 10⁻⁹ and 5.91 × 10⁻⁸. Null input, truncated geometry with one or both lanes, Nyquist CFO bounds and exact repeated visits agreed. Component tests also compare directly against finite complex pilot correlations and exercise positive equal-score ties at wrapped epoch boundaries. [Development grids](development-grids.csv) · [Component tests](../../../../tests/pipeline_eval/test_c_coarse_tiles.py) · [Sealed input provenance](input-cases.json)

## Replay

Use a fresh work directory for each command. The raw panel builder authenticates the prior qualification, the physical CI16, and the producer that supplies the calibrated search geometry.

    work=$(mktemp -d /var/tmp/qin-tiles.XXXXXX)
    py=.venv/bin/python
    qual=tools.pipeline_eval.qualification
    "$py" -m "$qual.c_coarse_tiles_build" "$work/build"
    "$py" -m "$qual.c_coarse_tiles_trial" prepare "$work/panel"
    "$py" -m "$qual.c_coarse_tiles_trial" profile "$work/build" --panel "$work/panel" --out "$work/results"
    "$py" -m "$qual.c_coarse_tiles_trial" clock "$work/build" --panel "$work/panel" --out "$work/results"
    "$py" -m "$qual.c_coarse_tiles_trial" qualify "$work/build" --panel "$work/panel" --out "$work/results"
    mkdir "$work/results/direct"
    for method in incumbent pairs tiles; do
      taskset -c 12 "$work/build/x86/$method/detector" "$work/panel/DS29-0082/held.ci16" \
        >/dev/null 2>"$work/results/direct/$method.json"
    done
    MPLBACKEND=Agg "$py" -m "$qual.c_coarse_tiles_results" \
      "$work/build" "$work/panel" "$work/results" "$work/report"

[Stage descriptor](stage-figure.json) · [Qualification seal](qualification-lock.json) · [Incumbent standalone C study](../../original-schedule/portable-coarse/README.md)
