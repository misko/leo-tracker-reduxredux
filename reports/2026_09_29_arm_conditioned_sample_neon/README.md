# Four-sample NEON conditioned moments

This Wave4-based experiment vectorizes conditioned moment accumulation across
four samples. It retains all five complex moments, 41 frequencies, all 16
conditioned frames, exact rechecks, and the final FP64 GLRT.

Each 32-sample block has four partial sums per real and imaginary moment. The
kernel loads four interleaved complex samples, forms delta powers sequentially
in NEON registers, and updates ten moment vectors. At block end it reduces lanes
as `(lane0 + lane2) + (lane1 + lane3)` and then adds the scalar tail. This
changes FP32 reduction order and is treated as an explicit approximation. The
host path mirrors the same four partial sums and reduction order. Unlike the
rejected order-packed experiment, this design stores no per-sample delta-power
cache.

Host and sanitizer component tests cover every production rate, random and
structured inputs, zero input, extreme CI16-valued input, and partial final
blocks. Worst direct complex-moment error was `2.50290213e-7` relative to the
sum of term magnitudes. The established 41-bin comparison with the FP64
reference retained its prior bounds: maximum absolute error `0.000854492188`
and maximum screen-normalized error `0.00126164407`. ARM cross-compilation
succeeded and disassembly contains the intended packed loads, multiplies, and
adds. No ARM binary was executed here.

The fused 32-dwell gate recovered 834/843 standard hits, above the required
829 threshold. The correctly paired 704-dwell evaluation used
`arm_wave4_combined/host704` and the frozen omit-power feature rows. Aggregate
science matched the Wave4 control: 19226/19581 recovered hits and 21505
unmatched positive hits. FP32 screen values changed 7523 windows, as expected
from the new reduction order, while exact rechecks and final decisions preserve
the aggregate recovery result.

Host timing cannot measure the ARM-only vector loop. The mirrored scalar host
path reported 12.920 ms conditioned time versus 13.264 ms for Wave4, while
fused total was 99.955 ms versus 90.108 ms because other stages ran slower.
Physical Cortex-A9 timing is required before making a speed claim.

Evidence:

- `builds/{host,sanitizer,arm}/build-receipt.json`
- `build-manifest.json`
- `host32-fused/{summary.json,standard-audit.json}`
- `host704-fused/{summary.json,standard-audit.json,manifest.json}`
