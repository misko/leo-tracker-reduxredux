# Wave5 final candidate

This combines the independently measured prepared CI16/coarse-prefix path with
the exact active-region peak extractor.  The extractor visits only the supplied
proposal epochs in the original CFO-major, increasing-epoch order and reads the
same neighboring grid cells.  The stable top-eight sort and basin-separation
helper is byte-identical to the prefix baseline.

All retained host and sanitizer units pass, including direct/prefix state,
sparse extraction versus the full-grid oracle, gate thresholds, final reuse,
fine budget, and conditioned numerical bounds.  Host parity is exact over
86,439 DS7 candidate objects, 3,624 DS8 objects, and 3,689 DS9 objects, with
zero changed candidates or windows.  `source-inventory.json` proves the only
source differences from the sealed prefix baseline are `full_search.c` and the
added sparse unit, and hashes the unchanged stable top-eight helper.

Physical ARM v1 (`arm152`) measures 915.434 ms mean, 897.812 ms median,
1,219.146 ms p95 and 1,421.993 ms maximum across all 152 2.5 MS/s dwells in
the DS7 benchmark cohort. It runs all 3,344 windows and recovers 4,506/4,573
standard hits. Only 105/152 dwells finish below one second; none finish within
120 ms. The common four-dwell v1 panel measures 960.375 ms. All six component
tests pass physically on PLUTO+ CPU0. Capture and initial file/setup work are
excluded; see `arm152/cpu-distribution.json` and the standard audit.

## V2 invalid-result fix

Read-only review found that v1 cleared prepared state before argument checks but
did not reject a null result until after rebuilding samples and prefixes.  That
path returned an error with prepared state still set.  Valid runner calls were
unaffected, so the v1 artifacts and ongoing ARM validation remain preserved.

`sources-v2`, `builds-v2`, and `host704-v2` add `!result` to the CI16 preflight
check.  The owned unit explicitly seeds prepared state, calls with a null
result, verifies the error, and verifies both state fields are cleared.  The
unchanged public complex entry still clears state through `ingest()`.  V2
reproduces all 86,439 host704 candidate objects with zero changes.  It is
physically tested with all six units and the same four-dwell panel: 960.455 ms,
119/119 standard hits and exact candidate parity to v1. The 152-dwell
distribution remains a v1 measurement. Recommended ARM v2 fused SHA-256 is
`ec5776c46969ef21e8dcd18edb5514dd4a1eb1fce7ec22e26c06f0633eef3a86`
and receipt SHA-256 is
`49c269da6579171d6abb7dd88e1d69bc2cd02c4d4747b7c122a400d300daaef9`.

## Supported rates and input examples

The runner accepts a complete 120 ms dual-RX dwell of little-endian signed
CI16 in sample order `I0,Q0,I1,Q1`. Templates are rate/edge-matched complex
FP64 files. For a prepared directory with the illustrative filenames below:

```sh
./fused_rate_coarse_gate_arm 2500000 exact-2500000.c128 control-2500000.c128 dwell-2500000.ci16
./fused_rate_coarse_gate_arm 5000000 exact-5000000.c128 control-5000000.c128 dwell-5000000.ci16
./fused_rate_coarse_gate_arm 7500000 exact-7500000.c128 control-7500000.c128 dwell-7500000.ci16
./fused_rate_coarse_gate_arm 10000000 exact-10000000.c128 control-10000000.c128 dwell-10000000.ci16
```

Expected dwell sizes are 2,400,000 / 4,800,000 / 7,200,000 / 9,600,000 bytes
respectively. Each invocation emits 22 receiver/window rows, with variable
candidate arrays after gating. All four rates have scientific cohort checks
and component tests; the larger physical-ARM timing cohort is 2.5 MS/s only.
The hash-bound evaluator in `../2026_09_29_arm_fused_pipeline/evaluate.py`
selects verified templates and exports the native raw files automatically.
