# Exact-order NEON proposal fold

The ARM proposal fold loads four dual-receiver CI16 samples with `vld4_s16`,
selects the requested receiver lanes, widens exactly through int32 to FP32, and
computes lag-1/3/5 products or power with separate multiply and add/subtract
intrinsics. It reloads and stores interleaved complex accumulators after every
frame, preserving the scalar frame order without FMA or reassociation. Support
increments are vectorized and non-multiple-of-four tails use the scalar kernel.

The host proposal remains scalar. Its component test checks direct scalar
ordering. The ARM component test compares scalar and NEON buffers bit-for-bit
after every frame, for both receivers, all four methods, and all four sample
rates. ARM artifacts are cross-build only; the experiment owner runs the target
test and proposal benchmark serially.
