# Complete likelihood input reuse

The dense restored-scout solve still made 280 ordinary likelihood calls with the same complete numerical inputs and backend context as an earlier call. Those repeat calls used **2.997 inclusive CPU seconds**. A simulated **64 MiB** least-recently-used cache could retain 267 repeats and avoid **2.776 seconds before lookup and copying**. None of the 356 posterior-export calls repeated. This leaves a small exact opportunity after the existing endpoint and paired-recovery caches. [Audit and solver receipts](measurements/solver-exact-likelihood-reuse.json)

The audit instrumented `NativeBound.__call__` on the corrected DS30-0008 saved detections and the original `ad417aaa…` solver. The exact argument fingerprints include observation values, design, noise scales, group labels, ordered shapes and strides, all likelihood options, the native/provider identity and reciprocal-condition limit. It separately checked the released validator’s normalized numerical operands and classified grid scope and actual export width, status and factor output. Both input fingerprints found the same repeats. All repeated output fields had identical fingerprints before the caller could mutate them. Prior endpoint reuse already avoided 90 evaluations on this solve. [Audit observer](solver_bound_repeat_audit.py) · [Published dense control](restored-scout-0008-solver-profile.md) · [Earlier endpoint and recovery work](solver-fixed-gram.md) · [Paired recovery cache](solver-recovery-reuse.md)

| Ordinary payload cap | Retained calls | Gross CPU avoided |
|---:|---:|---:|
| 8 MiB | 175 | 0.865 s |
| 32 MiB | 265 | 2.573 s |
| 64 MiB | 267 | 2.776 s |
| 128 MiB | 267 | 2.776 s |

Six repeats crossed major inference stages and accounted for 0.180 seconds. Sixteen crossed model instances. Most time remained within initial fitting, conservative recovery and history fitting. Across 1,110 ordinary calls, full SHA-256 fingerprinting used 1.726 CPU seconds and the cheap hint used 0.072 seconds. The hint nominated 283 possible repeats, three more than the complete fingerprints. The 64 MiB simulation would copy 6.31 GB of cumulative witness payload. The simulated avoided time includes validation and dense fallbacks but excludes fingerprint, witness and result-copy costs. [Cross-stage counts and cost](measurements/solver-exact-likelihood-reuse.json)

## Opt-in cache

The prototype indexes ordinary calls by a cheap hint and verifies every current numeric input byte against independently owned witnesses. It binds owner, native call route, fallback and condition setting. The bounded cache accounts for input and result array payloads and evicts the oldest entries before insertion. An oversized entry or a noncontiguous or unsupported numeric input uses the stock call. A transient native allocation failure yields no entry. Each result is independently copied on insertion and on a hit because ordinary callers rescale posterior coefficients and precision arrays. Grid calls continue through the stock export path, which needs a checked native factor and separate activation accounting. [Cache implementation](../../../tools/pipeline_eval/variants/algo08_likelihood_reuse.py) · [Caller posterior rescaling](../../../src/leo/analysis/localization_v3/history_position.py) · [Posterior export](../../../tools/pipeline_eval/variants/algo08_posterior_handoff.py)

| Saved input | Verified cache hits | Lookup and insertion CPU | Whole solve CPU, control → memo | Whole solve elapsed, control → memo |
|---|---:|---:|---:|---:|
| DS30-0008 | 267 | 0.792 s | 54.962 → 54.072 s | 55.694 → 57.170 s |
| Southern containing | 170 | 0.308 s | 35.135 → 35.770 s | 35.752 → 36.108 s |

Each replay reproduced both calibration arms, frequency residuals, completion and reason, complete observation ownership, numerical grid, optimizer path and endpoint replay exactly. Owner counts remained 4,472 per arm on the roof and 4,149 on the southern simulation. The southern cache rejected one hint collision after comparing the complete inputs. Each replay bypassed all 356 grid calls, retaining the existing posterior factor and dense fallback counts. Five component tests passed, including caller mutation, a false hint, the memory limit and the grid bypass. [Actual hit counts and exact evidence](measurements/solver-exact-likelihood-reuse.json) · [Component tests](../../../tests/pipeline_eval/test_algo08_likelihood_reuse.py)

The dense cache recovered all 267 simulated hits, at an average **10.4 ms of gross likelihood CPU per hit** in the audit. The single observed whole-solve CPU reduction was 0.890 seconds. Elapsed time rose, and the southern CPU rose by 0.635 seconds. These are single-process timings against archived uninstrumented controls. The audit bounds the available duplicate work, while the complete measurements do not establish a repeatable speedup. [Archived uninstrumented controls](measurements/solver-wide-private-plain-controls.json)

## Reproduction

Use the corrected DS30-0008 input and frozen bundle from the dense profile, or the released southern containing input from the wider private-block comparison. Run the existing locked saved-solve command with `--likelihood-cache`, leaving its optional profiling file unset. To repeat the fingerprint audit on the dense input, invoke `solver_bound_repeat_audit.py NATIVE SPEC ARCHIVE OFFER NEW_OUTPUT` inside the frozen runtime with the same Gauss lock and one numerical thread. [Locked command and inputs](restored-scout-0008-solver-profile.md#reproduction) · [Southern inputs](solver-wide-private-blocks.md#reproduction)
