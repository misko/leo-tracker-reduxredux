# Exact two-frame batched fine FFT

This bounded experiment keeps the preferred final-reuse scorer's original 500 Hz grid, transform lengths 5000/10000/15000/20000, weighted samples, frame selection, search bounds, interpolation, conditioned stage, and final FP64 GLRT. When exactly two fine-estimator frames are selected, one FFTW `plan_many` execution transforms their two independent complex arrays. Other frame counts use the original separate new-array executions.

The optimization removes one FFTW dispatch and lets the backend schedule both transforms together; it does not reduce the mathematical FFT count. A direct/pruned DFT over the roughly 321 requested bins would require more arithmetic than the full mixed-radix transform, while real-transform packing cannot combine two general complex inputs without four real transforms.

Host and sanitizer component tests execute locally. The batch test compares every output bin against two separate FFTW transforms at all four lengths. ARM artifacts are cross-compiled only. Runtime benefit is unclaimed until hardware measurement.
