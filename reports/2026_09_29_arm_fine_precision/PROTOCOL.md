# Fine FFT precision and batching experiment

Use saved DS7 IQ only, with the existing restricted timing search and lazy
epoch cache. Final GLRT remains FP64. Two independent changes are tested:
FP32 fine FFT spectra with raw and guarded modes, and FP64 frame batches of
four/sixteen. Do not combine changes until independent measurements justify it.

Start with the existing 32-dwell panel (all four rates, both edges, 704 windows,
843 standard positive entries). Freeze timing proposals from the FP64 proposal
run to isolate the FFT change. Compare candidate objects with the existing lazy
FFT implementation, but always score hit recovery against standard analysis.
Match positive entries one-to-one within the same receiver/window, <=2 samples
and <=8 kHz, margin >=0.025. Count unmatched new positives separately.

Guard thresholds and batch sizes are fixed before cohort results. Guarded FP32
is an engineering approximation, not proof of numerical equivalence. Inspect
fallback count and conditioning alongside recovery and runtime. Preserve all
windows and candidate counts. Do not infer recovery from FFT score tolerances.

Run promising modes on PLUTO+ .15 CPU0, serially, using the same four 2.5 MS/s
dwells as earlier measurements. Include per-window plan/cache setup in total
CPU; disclose any initialization outside timing. No RF collection, concurrent
capture, SD reformat or service changes. Keep proposal cost separate.

Expand a promising result onto the existing 704-dwell DS7 development subset.
For the combined FP32 proposal configuration, rerun actual downstream GLRT
using its saved proposals and independently audit standard detections. Never
call this full DS7 or independent holdout. Repeat ARM timing only to quantify
a promising gain. Record binaries, sources, inputs, templates and outputs by
hash. Reject performance claims based solely on host speed or theoretical SIMD
width. Publication includes code, reports and receipts; no production change.
