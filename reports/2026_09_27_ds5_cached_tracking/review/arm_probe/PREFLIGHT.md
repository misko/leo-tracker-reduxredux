# Physical ARM execution readiness

On 2026-09-27, local validation matched the current v0.59 deployment receipt,
its pinned SSH host-key file, and all 16 prepared saved-IQ cases. The older r30
and v0.49 target descriptions are not current. No credential contents were
printed or copied into this research report.

A bounded read-only preflight attempted to acquire the existing pipeline lock,
capture authority lease, and serial lock before opening SSH. Capture admission
raised `CapturePausedError`:

> capture is paused: operator stopped capture from web UI

Execution stopped before SSH, payload staging, or benchmark execution. The
authority was not resumed or bypassed. Separately, systemd reports the adaptive
capture timer still active, with 300-second captures and 120-second idle gaps.
That separate service does not invalidate the authority's explicit pause or
authorize this benchmark to ignore it.

The host runner must therefore remain unexecuted until the ownership conflict is
resolved. A later run must revalidate the current receipt, capture state, next
timer deadline, and idle target attestation; these local checks do not establish
the current target boot, actual credential acceptance, or ARM performance.

The prepared comparison is a stateless detector component benchmark. Even a
successful run would not establish the causal whole-pipeline 10x objective.
