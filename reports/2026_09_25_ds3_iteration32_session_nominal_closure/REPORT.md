# DS3 iteration 32 result

The prospectively frozen session-balanced nominal-basin extension completed
all blind numerical gates, but its post-seal error is **1.3235124655955364
km**. It therefore does not meet the sub-kilometre accuracy aim.

## Frozen method and fitted parameters

- Parent: sealed I21 coordinate; support: sealed I20 DS3/all56 support.
- Frozen identities: `balanced-interleave-1`
  `sha256:c6e88cd2ca4c031d89e46192793f030e25547c6445b7411b7ed629331533b4da`
  and `balanced-interleave-2`
  `sha256:f5e16bb66f54c5cf7702b1388ff728593a17225704c6c7ee2542c0b0c5f2a145`.
- Selected parameters: latitude `37.85654519329384` degrees, longitude
  `-122.47396176823618` degrees (`east_km=1.40380859375`,
  `north_km=-0.5126953125` from the I21 parent).
- Profiled nuisance parameters: one constant CFO per frozen track. These are
  profiled at every cell and are deliberately not promoted to selecting
  outputs by the reused cached engine.
- Non-selecting audit parameters: exact per-NORAD causal rates for both
  sessions are recorded without rounding under `rates_s_h` in
  `inference.json`; the widened bound is +/-0.5 s/hour.

The 48.828125 m stage closed at translation 29 (30 evaluated lattices), and
the 24.4140625 m and 12.20703125 m stages each closed at translation 1 (two
evaluated lattices each). The final equal-session objective is
`0.07801835151338547`.

## Gates

All ten frozen gates passed: plan blind, inference blind, interior closure,
all fits converged, no selecting rate boundary, both widened audits present,
both widened audits converged, no widened-audit boundary, exact SGP4 replay,
and deterministic replay. The primary and replay scientific views both hash
to `sha256:3271cf1deab06874ffa0fbf74e146fd0974c888440d0652b5dfc37de965a4c42`.

Both final audits had zero rates at the widened boundary and two rates beyond
the historical +/-0.25 s/hour control bound. Their exact-SGP4 maximum errors
were `0.00017835006292443722 Hz` over 17,687 observations and
`0.000038722995668649673 Hz` over 18,583 observations, below the frozen 0.2 Hz
tolerance.

The post-seal evaluator then compared the sealed estimate with
`(37.84903264307456, -122.4856541910174)`, producing the 1.3235124655955364 km
error. The qualification gate is a blind numerical qualification; it does not
encode or inspect this post-seal accuracy result.

## Comparison with earlier DS3 results

The closest matched full-DS3 comparator is the sealed equal-scan raw-MSE
surface fusion. On the same 56-scan dataset it reported
`0.6925484539098848 km` at
`(37.84280518331466, -122.48553021140697)`. I32 is
`0.6309640116856515 km` worse, or `1.9110756195085712` times that error. The
surface result remains the stronger full-DS3 estimate.

The RF-trimmed historical prior reported `0.11186936921843071 km` at
`(37.8480377975656, -122.48584392914726)` using the 42 of 56 scans retained by
its frozen 75% RF-residual rule. I32 is `1.2116430963771057 km` worse, or
`11.830874481926415` times that error. This comparison is descriptive rather
than matched: RF trim uses a selected 42-scan prior and position-vector votes,
whereas I32 fits the all-56 frozen track support through a nominal Doppler
objective.

The contrast is scientifically useful. I32 found a smooth, deterministic,
interior minimum with converged nuisance fits and exact forward replay, yet
that minimum is about 1.03 km east and 0.84 km north of the surveyed receiver.
Interior closure and numerical consistency therefore do not remove the bias
in this nominal track-level objective. Extending this basin further or making
the grid finer is not supported by the result; the full-DS3 surface fusion and
RF-trim prior remain better initializers for later DS4 work.

## Runtime and reproducibility

Primary inference took `103.64449515996967 s`; independent replay took
`116.59677433501929 s`. Their combined measured scientific runtime was
`220.24126949498896 s`. The durable pipeline consumed 5 min 50.821 s CPU,
peaked at 2.5 GB, and spent 12 min 11.957 s wall time including the wait for
the pre-existing I27 lock holder.

Authoritative artifact hashes:

- `plan-v2.json`: `86c6f6f5747402d5712fe93a9c7e3ef8a787940493c8520dde210da7eaf4c4ac`
- `inference.json`: `17709c08f3e246aa4333bf28b0806c77961b2f6a1ba7b412ce2163e80497c871`
- `replay.json`: `dfb5392f6319f26e7ebbc6f8d066b6fa11396b3ba12e0ac4c52d52d2acbceb24`
- `qualification.json`: `1e5310c3be33d4a0e352ceaa844ec11bd90d3369eb1f3e9e66c03b410950df9c`
- `postseal-evaluation.json`: `561a56c2db1fc7249871d1807205779e31f6eaf098b1256b10cbbf61a9d9dd77`

Run `run_pipeline.sh` to reproduce the ordered, lock-protected inference,
replay, qualification, and post-seal evaluation. Existing sealed artifacts
are verified and returned rather than overwritten. `plan.json` is retained as
the superseded pre-execution seal; no inference used it.
