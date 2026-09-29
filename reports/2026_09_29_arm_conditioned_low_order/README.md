# Degree-zero and degree-one conditioned screens

This Wave4 experiment tests four separately tagged conditioned screens: Taylor
degrees zero and one at block lengths 32 and 64. Every variant retains all 16
frames and 41 frequency bins. The base still skips near-maximum conditioned
rechecks, while the final GLRT remains full FP64.

The numerical tests compare candidate magnitudes directly with a double-
precision DFT. For degree `d`, each sample contributes the analytic remainder
bound

```
abs(sample) * exp(abs(omega*delta)) * abs(omega*delta)^(d+1) / (d+1)!
```

plus a conservative FP32 rounding term over the retained polynomial. Tests
cover all rates, random and structured data, a complex tone, zero input,
extreme CI16-valued input, and partial final blocks. All observations remained
inside their bounds. Maximum observed fractions of the bound were 63.9% for
degree1/block32, 81.6% for degree1/block64, 8.82% for degree0/block32, and
4.02% for degree0/block64. Host and sanitizer tests pass; ARM was cross-
compiled only.

All variants met the requested 32-dwell gate:

| Variant | Recovered / 843 | Host conditioned ms |
|---|---:|---:|
| degree 1, block 32 | 834 | 9.135 |
| degree 1, block 64 | 832 | 8.112 |
| degree 0, block 32 | 832 | 7.025 |
| degree 0, block 64 | 829 | 7.372 |

The Wave4-paired 704-dwell audit separates the viable frontier from the small
gate's uncertainty:

| Variant | Recovered / 19581 | Unmatched | Host conditioned ms |
|---|---:|---:|---:|
| Wave4 degree-4 control | 19226 | 21505 | 13.264 |
| degree 1, block 32 | 19228 | 21503 | 8.676 |
| degree 1, block 64 | 19207 | 21524 | 8.497 |
| degree 0, block 32 | 19172 | 21559 | 8.169 |
| degree 0, block 64 | 19097 | 21634 | 6.427 |

Degree1/block32 preserves aggregate recovery on this corpus while reducing the
host conditioned stage by about 35%. Degree1/block64 loses 19 recovered hits.
Both degree-zero variants lose materially more recovery and are rejected for
the preferred pipeline. These are host measurements of the scalar code; no ARM
speed claim is made.

Evidence:

- `builds/{host,sanitizer,arm}/build-receipt.json`
- `build-manifest.json`
- `host32-d{0,1}-b{32,64}/{summary.json,standard-audit.json}`
- `host704-d{0,1}-b{32,64}/{summary.json,standard-audit.json,manifest.json}`
