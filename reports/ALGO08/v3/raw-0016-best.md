# DS30-0016 original I/Q through process exit

The candidate finished in **10.497 s elapsed**, versus **10.824 s** for named ALGO08v3 in the same session. It saved **0.327 s elapsed (1.031×)** and **0.908 CPU s (1.092×)**. Both published complete fixes and all eight figures. The candidate reproduced the earlier 333 m improvement at fixed zero and the 33 m increase in fitted-calibration error. A 2× speedup would require 5.412 s through exit. The candidate's paid raw acquisition alone took 5.608 s elapsed. [Frozen protocol](raw-0016-best-protocol.md) · [Full receipt](measurements/raw-0016-best.json.gz)

## Charged costs

The previous warm comparison ran named first. This pair ran the cumulative candidate first, then the unchanged named release. Both fresh processes used CPU 2 and the same private tmpfs staging, original 25 km offer, authenticated signed recording and causal cutoff. The named process reported 10.816 CPU s and the candidate 9.908 CPU s. Each returned exit status zero.

| Elapsed boundary | Named v3 (s) | Candidate (s) |
| --- | ---: | ---: |
| Process start through durable detections file | 5.881 | 6.657 |
| Detections file to terminal file | 3.179 | 2.796 |
| Terminal file through process exit | 1.764 | 1.044 |
| **Total** | **10.824** | **10.497** |

File boundaries use each sealed file's timestamp relative to external launch. The unchanged named launcher provides no isolated current solver or native receiver CPU clock. Inside the candidate, authenticated acquisition used **5.028 CPU s** and **5.608 s elapsed**. Native work used **0.968 CPU s** for 186 full lanes and **1.518 CPU s** for 1,240 short-primary lanes. The compressed lookahead worker used **1.352 CPU s** and hit all 11 scheduled reads for 834.806 MB. Decision and publication used **4.374 CPU s**, including the **2.784 CPU s** scientific solve and **0.500 CPU s** rendering. These nested measurements must not be summed with the full phases.

All **242,128** raw payload pages were resident at each checkpoint around both arms. Before conditioning, the passive check found zero resident payload pages. One read-only pass over the 13 signed members read **991,734,597 bytes** in **7.266 s wall / 0.255 s CPU**, with **1,937,024** input blocks, equivalent to **136.5 MB/s** at that conditioning boundary. Conditioning was charged separately, once for both arms. The trial performed no payload eviction or cold receiver launch. Candidate and named process input blocks were **4,632 and 0**, with **8 and 0** major faults. The raw-member residency check covers compressed payload files. The available process counters do not identify which files caused those faults.

Stage and font preparation took **1.103 s elapsed** outside both clocks. The private archive used **35.764 MB** of unique verified bytes for 46 signed names with **82.259 MB** of logical content. The earlier warm same-recording comparison measured **10.813 → 8.638 s** in the opposite order. Candidate acquisition then took **3.392 CPU s**, including **0.167 CPU s** in compressed lookahead, and publication took **4.707 CPU s**. The current single pair does not separate order, session and acquisition costs from the cumulative software change. [Earlier matched pair](unified-short-layout.md)

## Scientific and publication checks

| Calibration | Named error (km) | Candidate error (km) | Candidate minus named (m) | Named RF RMS (Hz) | Candidate RF RMS (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed zero | 1.643669 | 1.311046 | −332.622 | 109.375 | 121.526 |
| Fitted | 1.661443 | 1.694025 | +32.582 | 109.479 | 120.291 |

Both arms processed the same 1,426 opportunities from 713 admitted visits, with 95 invalid out of 808 issued. The named receiver emitted 440 signed factors. The candidate emitted 475. The accepted owner count rose from 109 to 116 in each calibration arm, with 106 shared owners, three dropped and ten added. Every shared owner kept the same NORAD ID and conditional/predictive role. The stock owner list is from an independently sealed replay whose terminal and owner-label digests match the current named publication. The current candidate owns 93 conditional and 23 predictive observations in each arm.

The active time-support proof could not exclude curvature, so the candidate paid for the full graph, regional and publication route. Exact graph execution retained 4,137 ordered edges and 13 tracks, with 91 of 120 cached best-piece fits. The original signed final fit accepted both refits and cost 0.130 CPU s including qualification and its geographic decision. The grid library validated four phase views and produced 356 native selected designs and 708 native projections, with no recorded fallback. The raw candidate's terminal, fixed and fitted positions, RF values, owner digests, numerical path and complete 179-point paired grid exactly match both the prior authenticated saved original finish and the prior projected-grid comparison. The named terminal and numerical evidence exactly repeat its own prior raw comparison. [Saved grid qualification](cumulative-grid-projection.md) · [Saved original finish](measurements/named-finish-cli-0016.json.gz)

All eight official PNG file digests, decoded RGBA digests, sizes and position-image bindings independently validated in both actual publications. Each arm's eight PNGs matched its source-matched control. The candidate's two direct residual figures, four corrected native orbital figures, track RMS and position map matched the corresponding saved Cairo composition byte for byte. The native orbit legends independently reproduced both fitted satellite labels and the 26 px minimum legend separation. Production reused eight verified image reads with zero fallback. [Corrected renderer verification](direct-orbit-figures.md)

## Reproduce

The retained pair uses launch freeze `53e7f9a9b`. Set `$worktree` to this checkout and `$output` to a new directory name under private tmpfs. Run under the authorized archive-readable Gauss account with the frozen low-priority slot. The first command runs physical I/Q once per arm. The second uses only the resulting sealed publications. The candidate's original signed recording stays on its read-only archive path. All generated publications, shared font cache and staged catalogue bodies stay under `$output`.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial="$worktree/reports/ALGO08/v3"
python_path="$trial:$worktree:$worktree/src:$release/src:$release"
locked() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n systemd-run --quiet --wait --pipe --collect -p User=leo -p Group=leo \
    -p Nice=15 -p CPUAffinity=2 -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
    /usr/bin/env PYTHONPATH="$python_path" OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
locked "$release/venv/bin/python" -BPs "$trial/raw_0016_best_trial.py" "$output"
locked MPLCONFIGDIR="$output/fonts" TMPDIR="$output/tmp" \
  "$release/venv/bin/python" -BPs "$trial/raw_0016_best_score.py" "$output" "$output/result.json"
```

Forty-seven component and adjacent tests passed. The archived receipt contains both process logs' receipts, the conditioning and page checkpoints, source and product hashes, and separate provenance and science checks.
