# 0.312 gate plus quadratic block-64 conditioned screen

This isolated candidate composes the sealed rate gate from
`arm_rate_coarse_gate/sources-312` with the sealed degree-two, block-64 screen
from `arm_conditioned_quadratic`. Gate thresholds remain 0.312, 0.150, 0.175,
and 0.152 at 2.5, 5, 7.5, and 10 MS/s. Every emitted candidate retains all 16
conditioned frames and 41 bins, and the final GLRT remains FP64.

Host and sanitizer gate, fine-budget, final-cache, and direct-DFT tests pass.
The quadratic test covers every rate, random and structured input, a tone,
zero, extreme CI16-valued input, and partial blocks. Its worst observed direct-
DFT error used 4.40% of the analytic cubic-tail plus FP32-rounding bound. ARM
was cross-compiled only.

The candidate preserves the sealed 0.312 gate's matched reference-hit
identities exactly on all three evaluated panels:

| Panel | Candidates | Recovered | Unmatched | Identity losses/gains |
|---|---:|---:|---:|---:|
| DS7 host704 | 86,439 | 19,217 / 19,581 | 16,508 | 0 / 0 |
| DS8 transfer | 3,624 | 773 / 785 | 733 | 0 / 0 |
| DS9 transfer | 3,689 | 886 / 908 | 829 | 0 / 0 |

Per-rate transfer recovery also matches the 0.312 control. DS8 remains
114/115, 199/203, 216/218, and 244/249. DS9 remains 273/275, 251/259,
163/170, and 199/204.

Host conditioned time changes from 12.449 to 7.078 ms on DS7, 17.482 to
8.270 ms on DS8, and 12.266 to 6.925 ms on DS9. Fused totals are 77.904,
74.278, and 77.645 ms respectively. Since the quadratic candidate preserves
quality on DS7, DS8, and DS9, the conditional wide-128 fallback was not built.
No ARM speed claim is made.

Evidence:

- `builds/{host,sanitizer,arm}/build-receipt.json`
- `build-manifest.json`
- `host704/{summary.json,standard-audit.json,hit-identity-diff.json}`
- `../2026_09_29_arm_rate_gate_transfer/host-ds{8,9}-gate-quadratic/`
- `compare_hit_identities.py` and `compare_transfer_hit_identities.py`
