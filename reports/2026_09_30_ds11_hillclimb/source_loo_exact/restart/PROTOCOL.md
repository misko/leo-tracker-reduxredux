# One bounded optimizer-restart diagnostic

This is a new engineering experiment prompted by the preserved index-4 screen
failure, not a retry within the original screen. No geographic errors enter it.
Rebuild exactly the retained t8/100 objective for index 4, omitted NORAD 65855,
from the frozen screen plan. Verify input hashes, full-scan assignments and
weights, omitted tracks, and the saved failed endpoint's objective and gradient.

Only an unsuccessful, interior, finite endpoint with maximum gradient at most
0.01 and finite-difference discrepancy at most 0.02 is eligible. Perform exactly
one fresh L-BFGS-B invocation from that saved endpoint using the original
optimizer options, bounds and success/gradient/audit qualification. Preserve
both attempts. No extra starts, parameter changes or acceptance of an
unsuccessful termination are allowed. Use one BLAS thread and a 90-second cap.

Report qualification, retained-objective change, endpoint displacement and
common held-score change. The diagnostic passes only if the new fit qualifies
and its retained objective is not worse by more than 1e-7 nats. Passing would
justify considering a separately declared, uniform continuation rule for a
future comparison; it does not repair the original failed screen or establish
any geographic improvement.
