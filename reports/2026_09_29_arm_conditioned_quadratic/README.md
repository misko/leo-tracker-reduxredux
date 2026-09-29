# Quadratic conditioned screen

This independent Wave4 experiment reduces the conditioned approximation from
moments zero through four to moments zero through two. It evaluates the
quadratic block expansion at all 41 frequencies for all 16 frames. The base
still skips near-maximum FP64 conditioned rechecks, and the final GLRT remains
unchanged FP64. Two separately tagged binaries use block lengths 32 and 64.

The numerical test compares each candidate magnitude directly with a
double-precision DFT; comparing only two implementations of the same quadratic
formula would not qualify its approximation. For every sample with
`x = abs(omega * delta)`, it sums the analytic complex-exponential remainder
bound

```
abs(sample) * exp(x) * x^3 / 6
```

and adds a conservative FP32 term of
`2048 * FLT_EPSILON * sum(abs(sample) * (1 + x + x^2/2))`.
Across all rates, 41 bins, random/structured/tone/zero/extreme inputs, and
partial final blocks, the largest observed error used 1.35% of this bound for
block 32 and 4.40% for block 64. Host and sanitizer tests pass. ARM binaries
were cross-compiled only.

Both variants cleared the fused 32-dwell gate at 834/843 recovered hits. The
correctly paired 704-dwell evaluations used `arm_wave4_combined/host704` and the
frozen omit-power feature rows. Both retained the Wave4 aggregate result:
19226/19581 recovered hits and 21505 unmatched positive hits.

Host conditioned-stage timing fell from the Wave4 control's 13.264 ms to
9.151 ms with block 32 and 8.514 ms with block 64. Host fused totals were
96.862 ms and 98.687 ms versus the control's 90.108 ms because unrelated stages
ran slower in these cohorts. ARM speed remains unmeasured.

Evidence:

- `builds/{host,sanitizer,arm}/build-receipt.json`
- `build-manifest.json`
- `host32-b{32,64}/{summary.json,standard-audit.json}`
- `host704-b{32,64}/{summary.json,standard-audit.json,manifest.json}`
