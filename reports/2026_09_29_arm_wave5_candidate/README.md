# Wave5 candidate: 0.312 rate gate plus degree-one conditioned screen

This isolated candidate composes two sealed experiments without changing their
other behavior:

- the rate-specific coarse gate from
  `arm_rate_coarse_gate/sources-312`, with thresholds 0.312, 0.150, 0.175,
  and 0.152 at 2.5, 5, 7.5, and 10 MS/s;
- the degree-one, block-32 conditioned screen from
  `arm_conditioned_low_order`.

The gate still runs after coarse support validation and before fine refinement.
Every emitted candidate retains all 16 conditioned frames and 41 bins. The
final GLRT remains FP64. Host and sanitizer tests cover gate equality and both
`nextafter` sides, all-rate fine budgets and final-cache behavior, and the
conditioned screen's direct double-DFT analytic bound over random, structured,
tone, zero, extreme, and partial-block inputs. The direct-DFT test's worst
observed error used 63.9% of its stated bound. ARM was cross-compiled only.

The corrected variable-inventory audit tests pass 6/6. The 704-dwell combined
cohort emits exactly 86,439 candidates, matching the sealed 0.312 gate cohort.
Both recover 19,217/19,581 standard hits with 16,508 unmatched positive hits.
The matched reference-hit identities are not identical: the combined screen
loses five identities and gains five others. `hit-identity-diff.json` records
their session, visit, receiver, window, reference rank, epoch, CFO, and margin.
The number of windows containing any recovered hit changes from 6,920 to 6,919.

Host timing improved within the gated workload:

| Metric | Sealed 0.312 gate | Combined candidate |
|---|---:|---:|
| conditioned | 12.449 ms | 7.072 ms |
| search total | 50.303 ms | 46.760 ms |
| fused total | 80.202 ms | 77.932 ms |

These are host measurements. No ARM execution or ARM speed claim is included.

Evidence:

- `builds/{host,sanitizer,arm}/build-receipt.json`
- `build-manifest.json`
- `host704/{summary.json,standard-audit.json,manifest.json}`
- `compare_hit_identities.py` and `hit-identity-diff.json`
