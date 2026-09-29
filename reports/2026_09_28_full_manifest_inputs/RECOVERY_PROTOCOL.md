# One bounded recovery for DS9-F028 observation timeout

The first observation stage for DS9-F028 exited 124 at 60.17 seconds. It used
48.73 user CPU seconds, 0.53 system seconds and 407,828 KiB peak RSS. It wrote
observations.json and printed `tracks 61`, but the process did not exit within
the original 60-second cap. This is a failed execution, not successful input
readiness. The exact cause of its late process exit is not established.

Authorize one explicitly documented recovery of this unit under the same
scientific exporter, immutable manifest, candidate-bank rules and partition.
Increase only the observation-process cap to 120 seconds. Keep bank/validation
caps 240/30 seconds, the 4 GiB address-space cap and BLAS1/nice19. Use a single
worker holding the original exclusive global lock; no other input or model
worker may overlap. Before stages require 2.5/3/2 GiB available memory for
observations/banks/validation. No automatic retries or additional attempts.

Preserve the original outputs, failed receipt, resource data and seal unchanged.
Write recovery exports, receipts and validation into separate directories.
The recovered observation JSON must equal the original written JSON after
removing only elapsed_seconds. Any other difference fails the recovery.
Require all three recovery processes to exit zero, ordinary loader eligibility
and DS9 minted GLRT bindings before considering the recording ready.

Use audit_recovery.py for subsequent checkpoints. It retains the original
failed stage in resource accounting and the recording's prior_failed_stages;
it reports successful readiness only through separately sealed recovery
validation. Never rewrite the earlier failure or its historical checkpoint.
If this attempt fails, retain that failure and investigate separately.

This is recovery from an execution timeout, not outcome-based filtering,
substitution or model retuning. No waveform reads, new RF collection, provider
fetch, production-service changes or QNAP writes are authorized or required.
