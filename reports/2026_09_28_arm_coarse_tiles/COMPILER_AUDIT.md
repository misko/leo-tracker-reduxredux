# Compiler-only coarse audit

The no-prefetch compiler variant preserves the complete scientific output on
the 16-probe all-rate ARM comparison. Every coarse-grid byte matches the FP64
FFTW baseline, and all 128 canonical candidate objects are identical. This is
a compiler-only result; the coarse algorithm and hypothesis inventory are
unchanged.

Mean end-to-end speedup rises from 1.17x at 2.5 MS/s to 1.31x at 7.5 and
10 MS/s. Mean coarse-stage speedup is 1.35x, 1.42x, 1.45x, and 1.42x at 2.5,
5, 7.5, and 10 MS/s respectively. Other stage timings move slightly in both
directions because the flags are global, so the coarse-stage comparison is the
cleanest evidence for the compiler effect.

`compiler-results/` archives both all-rate evidence directories, the variant
build receipt and executed sources, and hashes. Hardware execution was owned by
the root benchmark process; this audit only read and reconciled saved outputs.

The rejected 4-CFO tile explains its regression in assembly: its 0x500-byte
kernel uses a 180-byte stack frame and repeatedly spills eight vector
accumulators. Disabling prefetch leaves that function unchanged and cannot fix
the register pressure. The single follow-up 2-CFO tile reduces the kernel to
0x258 bytes and a 28-byte frame without accumulator spills, at the cost of six
sample passes. Target timing subsequently measured 2,260.68 ms/window,
still slower than the untiled no-prefetch path. Neither tile is selected.
