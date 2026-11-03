# Corrected wideband interval-bounds layout research v1

This isolated experiment starts from the frozen exact-next-up research source
and changes only the private `interval_bounds` address layout. The certified
coarse loop updates every CFO for one epoch, so bounds now use
`epoch * REFERENCE_CFO_CAPACITY + frequency`, matching the existing
`accumulated` scratch. The scientific grid, possible mask and repair mask keep
their established CFO-major layout. Allocation and clear sizes are unchanged.

The loop nesting and each cell's sequence of additions are unchanged. At the
7.5 MS/s visit-301 geometry, the old inner-loop writes were 80,000 bytes apart
because `n` is 10,000; the new 21-CFO span is contiguous. Later bounds-only
passes step 176 bytes between epochs. This locality argument is a hypothesis
until measured on physical ARM and is not a real-time claim.

`test_interval_bounds_layout.c` proves the mapping is an in-bounds bijection
and that the active CFO row for each epoch is contiguous. Normal host,
ASAN/UBSAN, and QEMU ARM executions pass. Host and sanitizer replays of saved
DS9 visit 301 are exactly equal to the frozen next-up result after removing
timing, thermal-sensor, and RSS diagnostics; sanitizer stderr is empty.

The corrected 32-visit slice also passes: 32 visits, 64 receiver windows, 512
retained candidates, 318 of 318 rank-level gate comparisons equal, and 88
passing candidates. It consumed 127.67 host CPU seconds and 22.70 seconds wall,
within the approved 300-second CPU cap. Raw IQ stayed in the existing read-only
store and was not copied into this report.

The frozen ARM replay is `artifacts/arm/leo-native-adaptive-replay`, SHA-256
`c52a40dbd9249d8f53e7751180361f96259281c0f8efd88b79d25546303a95e6`.
The focused ARM test is `artifacts/arm/test-interval-bounds-layout`, SHA-256
`c5791da9a93995dc489419fb23104e5b1890507e6ad57afce15e6346ae245d38`.
Physical ARM execution passes the focused mapping test in 0.016007640 seconds
wall. The visit-301 replay preserves every non-timing row field and raw numeric
lexeme relative to the consecutive frozen next-up candidate. Its detector-call
time was 50.033386763 seconds versus 50.274828596 seconds, a 0.480244% single-run
difference. That is too small to demonstrate a speedup, so the experiment was
not repeated and is not a promotion candidate. Whole-process time was
50.414392071 seconds, CPU time 50.401067 seconds and peak RSS 40,184 KiB.
`physical-comparison.json` binds the comparison.

No production source, contract, golden, device software, or RF data changed.
