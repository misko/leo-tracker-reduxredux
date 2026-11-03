# Local short-tracklet linking research receipt

This is the single frozen implementation of the third bounded research approach. It is an offline two-pass algorithm, not a streaming implementation: every eligible 8 s window (4 s step) produces bounded local linear hypotheses, then fragments are linked chronologically using local endpoint frequency and slope continuity. Output is a non-exclusive hypothesis bank.

The configuration was frozen before inspecting target results: canonical RF 11.2 GHz, scaled alias spacing `1/4.4e-6`, 2.5 kHz local gate, 5 kHz link-frequency gate, 3 kHz/s link-slope gate, 4 s maximum gap, ±15 kHz/s rate, and final minimum 8 unique source groups over 4 s. Lane authority is exact receiver/channel/edge/RF. Candidate center timestamps are retained through fitting; source-group mean time is used only to order groups.

The component tests cover a curved arc, crossing tracks, gaps, alias transitions, clutter, timestamp jitter, and noncanonical-RF normalization. Host and ASan/UBSan tests pass. The ARM binaries cross-compile for Cortex-A9 hard-float with the same repository toolchain as `curvature_tracks`; physical-board execution belongs to the shared benchmark and is not claimed here.

Frozen host reconstruction timing reported by the binary was 0.006639 s on synthetic, 0.079769 s on ARM observations, and 0.080412 s on server observations. These are workstation algorithm timings, not physical ARM timings. Strict shared parsing/evaluation passed: ARM produced 59 hypotheses, represented 9 non-ref10 references, recovered 9 one-to-one originals, and had 2236.62 Hz prediction p95; server produced 46 hypotheses, represented 13, recovered 12 one-to-one originals, and had 1594.64 Hz prediction p95.

Inputs, source files, and final binaries are recorded in `SHA256SUMS`. `pre-contract-fix/` preserves the rejected pre-freeze output attempt that used the wrong raw-CFO serialization. Final outputs are under `outputs/`; binaries are under `artifacts/`; test receipts are under `component/`.
