# Runtime research checkpoint: complete native replay and ALGO03 experiment

This checkpoint preserves pending research code and completed execution receipts.
It does **not** qualify a new production release or establish the 10× overall
runtime goal. The deployed ALGO07 numerical runtime remains iteration004,
`336715a398c2e6b9295318261bb63da76aaa2726`.

## Completed measurements

| Experiment | Observation | Qualification limit |
| --- | --- | --- |
| Native GLRT tiling, DS27-0004 complete recording | 6,772 windows replayed; 6,767 processed; all published candidate comparisons exact; 1,436.04 s with eight workers | Compared against published tracking; no matched full-scan baseline timing, no downstream localization replay |
| ALGO03 original runtime | 546.88 s | One scan, private replay |
| ALGO03 prepared geometry/cache composition | 495.77 s; published selected position exactly unchanged | Full scientific parity, both arms and intermediate decisions still require review; 20 s nonblocking sampling occurred during this run |
| Blocked GEMM coarse correlation | Second measured call 2.349 s versus native 0.500 s | Rejected for speed on this fixture |
| NumPy overlap FFT coarse correlation | Second measured call 2.571 s versus native 0.810 s | Rejected for speed on this fixture |

The two rejected correlation prototypes preserved the tested score grids within
1e-12, winning epochs exactly, and published candidates exactly. These limited
checks do not establish general scientific equivalence. Neither is connected to
production.

The full replay used `tools/profile_algo07_full_glrt.py`, public recording ports,
complete segment iterator exhaustion and a 30-minute bound. All 708 frozen
runtime/input files remained unchanged. Its stage-specific result records exact
published-candidate comparisons; the generic timing receipt intentionally does
not claim downstream scientific parity. See [result](receipts/full-glrt-result.json)
and [timing](receipts/full-glrt-timing.json).

The ALGO03 experiment used `tools/algo03_runtime_prototype.py` to compose an
explicitly research-only runtime. The original scientific manifest remains
unchanged; the new complete runtime composition is separately hash-pinned and
checked before and after execution. Both runs preserved all 1,910 frozen inputs.
The endpoint check is saved in
[the comparison checkpoint](receipts/algo03-comparison-checkpoint.json).
Timing and provenance differ; complete scientific comparison remains pending.

## Profiling evidence and next step

`algo03-annotation.folded` is the original nonblocking py-spy sample of a private
ALGO03 annotation child, sampled for 20 seconds at 100 Hz. The sampler reported
24 read errors; one sampled stack contains invalid UTF-8. Preserve the raw file
and exclude that corrupted row when interpreting it. Of 1,974 valid samples,
451 ended in `numpy.linalg.solve`. Training fits dominate inclusive stacks.
Investigate whether repeated per-target training fits share exactly identical
inputs before attempting reuse. This is a hypothesis, not a validated shortcut.

## Validation at publication

- Four tool tests passed in the development environment.
- Four correlation tests passed using the installed native acquisition oracle.
  These are explicitly marked `hardware`; the ordinary environment lacks that
  compiled oracle and skips them.
- Ruff passed on all eight new Python files.
- No production deployment or change to scientific acceptance gates was made.

Raw complete-window outputs remain under
`/srv/bulk/leo/research/algo07-runtime-20261103/full-glrt-DS27-0004/candidate`.
The compact execution receipts are committed here; raw IQ is not added to Git.
