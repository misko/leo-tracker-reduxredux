# FP32 fine-frequency FFT prototype

This bounded research prototype starts from the immutable fine-reuse host-v4
and ARM-v3 snapshots. It changes the fine-frequency FFT input, transform,
stored spectra, and per-bin magnitude to FP32. Denominators and score
accumulation remain FP64; candidate ordering and interpolation operate on the
resulting scores as FP64 values. Conditioned refinement, verification, and the
final GLRT remain FP64.

`build.py` creates immutable per-mode snapshots. Raw mode always consumes FP32
fine scores. Guarded mode recomputes the complete requested fine range with the
original FP64 `fine_scores` when the FP32 scores contain a nonfinite value, the
top two scores differ by at most
`256*FLT_EPSILON*max(1,abs(best_score))`, or the winning three-point parabola is
shallow/near its one-bin clamp. The constants were fixed before cohort runs.
They are conservative engineering thresholds, not a proof or universal error
bound. A fallback therefore restores the original spectrum, winner, and
interpolation inputs for that candidate; an unguarded result remains an
approximation.

Build commands:

```sh
python3 build.py
python3 build.py --guarded
python3 build.py --sanitize --guarded
python3 build.py --arm
python3 build.py --arm --guarded
```

ARM builds are cross-compiled only. Target workloads are intentionally left to
the serialized benchmark coordinator. Each build receipt records commands,
the frozen baseline receipt hash, source and binary hashes, unit output, mode,
and exact guard formulas.

The v3 diagnostic snapshots add CPU-time partition fields named
`fine_precision_{plan,preparation,execute,storage,score,guard,recompute,free}_ms`.
These timers observe the unchanged v2 algorithm and remain inside the existing
acquisition and total timers; their values must not be added to total time.
