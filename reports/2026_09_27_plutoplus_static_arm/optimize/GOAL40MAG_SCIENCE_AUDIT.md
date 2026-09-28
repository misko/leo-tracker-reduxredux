# goal40mag scientific audit

Candidate ARM SHA-256: `2f3d90978343b7e51bfe039e5a20fa9090b35ebccb26992d132f6a9c4d82f249`.
The build receipt fixes the candidate sources and retains the Cortex-A9/NEON,
hard-float, hybrid-rank, block-rotation, FP32 differential-dot, and bounded
magnitude flags.

## Comparison with D

The unchanged strict assessor compares each candidate with the saved D result.
The host sanitizer and physical ARM saved-IQ runs each pass 104/104 cases
across 2.5, 5, 7.5, and 10 MS/s. Across the 208 receiver comparisons in each
run, all of the following are identical to D:

- rank order, selected rank projection, and both screen orders;
- confirmation window and candidate count;
- fractional-complete state and final positive/negative decision.

The host run retains all 56 D-positive receivers with no added positives. Its
maximum timing difference is `2.4253192047278086e-13` us, maximum CFO
difference is `0` Hz, and maximum absolute exact/control/margin score deltas
are `3.597122599785507e-14`, `1.8318679906315083e-15`, and
`3.519406988061746e-14`. The full ARM run also retains all 56 D-positive
receivers with no additions. Its corresponding bounds are
`2.4253192047278086e-13` us, `0` Hz, `1.5432100042289676e-14`,
`1.8318679906315083e-15`, and `1.4876988529977098e-14`.

Flat/non-pilot behavior also remains stable. All 152 D-negative receivers in
each full run remain negative. This includes all 32 noise/tone-control receiver
cases per run. Among negative rows, the host
maximum absolute exact/control/margin deltas are `2.671474153004283e-15`,
`1.8318679906315083e-15`, and `8.604228440844963e-16`; ARM bounds are
`2.671474153004283e-15`, `1.8318679906315083e-15`, and
`8.534839501805891e-16`. Negative-row timing differs by at most
`2.4253192047278086e-13` us on either host or ARM; CFO is unchanged.

## Physical ARM real-case CPU

These values are arithmetic means of the per-case median dual-receiver visit
CPU reported by the assessor for the 80 real/dev saved-IQ cases. `D` is the
unchanged original reference and `goal40mag` is the candidate.

| Rate | Cases | D mean CPU (ms) | goal40mag mean CPU (ms) | Saved (ms) | Speedup |
|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 32 | 108.062 | 67.058 | 41.004 | 1.611x |
| 5 MS/s | 32 | 202.104 | 124.809 | 77.295 | 1.619x |
| 7.5 MS/s | 8 | 310.343 | 199.793 | 110.550 | 1.553x |
| 10 MS/s | 8 | 389.363 | 239.937 | 149.425 | 1.623x |
| All real cases, case-weighted | 80 | 194.037 | 120.720 | 73.317 | 1.607x |

Because the corpus has more 2.5 and 5 MS/s cases, an equal-rate average is
also informative: D is `252.468` ms and goal40mag is `157.899` ms, a `1.599x`
speedup. At the deployment rate, the saved-IQ mean of `67.058` ms is 44.12%
below a 120 ms CPU budget; concurrent capture results remain a separate claim.

Within these 80 real cases, all 160 receiver decisions equal D: 40 positives
are retained, 120 negatives remain negative, and none are added or lost. The
maximum absolute exact/control/margin score deltas are
`2.671474153004283e-15`, `1.8318679906315083e-15`, and
`1.6653345369377348e-15`; maximum timing and CFO differences are
`2.4253192047278086e-13` us and `0` Hz.

## Bounded-magnitude semantics

Relative to goal40b, goal40mag changes only the final GLRT ceiling's 64-value
loop from direct `cabs` to the already-qualified `magnitude` helper. For a
finite, normal squared magnitude, the helper returns `sqrt(re*re + im*im)`.
It recomputes from the original complex value with `cabs` whenever that square
is zero/subnormal, overflows, or is nonfinite. Thus underflow does not turn a
nonzero input into zero, overflow does not turn a finite modulus into infinity,
and NaN/infinity retain libc `cabs` handling. ARM disassembly still contains
the conditional calls to the dynamically linked `cabs`; the fallback was not
optimized away by `-fcx-limited-range`.

The fast path changes only floating-point rounding relative to robust `cabs`.
The strict results above bound that change on the saved-IQ corpus. Computing
the square before falling back can set floating-point underflow/overflow flags,
but detector code neither reads nor branches on those exception flags. The
current evidence does not directly exercise synthetic DBL-subnormal,
near-`sqrt(DBL_MAX)`, infinity, or NaN vectors. Public ingestion rejects
nonfinite inputs, templates are finite with component magnitude at most 16,
and input components are bounded at `1e12`, leaving ordinary accepted GLRT
correlations far from double overflow at every supported rate.

Conclusion: no material scientific delta is present in the qualified host or
four-rate physical ARM saved-IQ domains. Promotion should retain the fallback
and the strict D identity gates. Saved-IQ timing does not by itself establish
the concurrent capture cadence result.
