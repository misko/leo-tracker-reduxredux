# Corrected wideband eight-CFO correlation research v1

This isolated experiment starts from the frozen exact-next-up source and
changes only the private FP32 certified-coarse correlation tiling. For 21 CFOs,
the Cortex-A9 path now uses two eight-CFO tap traversals, one four-CFO traversal
and the unchanged scalar tail, instead of five four-CFO traversals plus the
scalar tail. This reduces sample loads, broadcasts and loop control while
leaving every multiply/add and every CFO cell's increasing-tap accumulation
sequence unchanged. It excludes the separately measured epoch-major bounds
layout.

The focused test compares the old four-wide and new eight-wide kernels over all
CFO counts 1 through 22, tap counts 1 through 45 and 64 deterministic input
sets. Normal host, ASAN/UBSAN and QEMU ARM each pass 63,360 bit-exact cases.
The host fallback is scalar; QEMU ARM exercises the NEON paths. The linked ARM
replay's hot eight-wide loop keeps all four accumulator vectors in registers,
has no stack spill/reload inside the tap loop, and uses separate `vmul` then
`vadd`/`vsub` instructions without `VFMA`. See `arm-assembly-audit.txt`.

Host and sanitizer visit-301 replays reproduce every non-diagnostic field from
the frozen next-up result; sanitizer stderr is empty. The corrected 32-visit
slice passes 32 visits, 64 receiver windows, 512 retained candidates, 318 of
318 rank-level gates and 88 passing candidates in 127.60 host CPU seconds,
within the approved 300-second cap. These host replays exercise the scalar
fallback, while the focused QEMU comparison provides NEON numerical coverage.

The frozen ARM replay is `artifacts/arm/leo-native-adaptive-replay`, SHA-256
`4ca385e8ea10f254cabb12002dd3f0e244371500481fa98d829d04c8483cbf2b`.
The focused ARM test is `artifacts/arm/test-correlate-eight-fp32`, SHA-256
`2a27360a700309eff4b30e86e3a24b4d0caa4254fb7d147840705c0e891fd5b1`.
The physical ARM focused test passed 250,160 comparisons.  A serialized
control/candidate/candidate/control visit-301 run reproduced every non-timing
row field and every raw numeric lexeme.  Mean detector-call time changed from
50.264235802 s to 49.108611914 s, a 2.2990977% reduction.  This is below the
predeclared 3% threshold, so the candidate is rejected and was not promoted.
See `physical-comparison.json`.

No production source, contract, golden, installed device software, or RF data
changed.  The physical runs were CPU-only saved-data replay performed by root.
