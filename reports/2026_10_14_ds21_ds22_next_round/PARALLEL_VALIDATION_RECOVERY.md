# Parallel comparison: validation overhead and preserved scientific work

Supervisor 003 terminated after 798.612 seconds with 103 attempted pipeline
jobs: 96 returned successfully, four failed, and three reached their external
timeouts. These are pipeline jobs, not completed recording comparisons. The
full DS21/DS22 accuracy targets remain unverified.

The failures expose repeated recursive source/authority validation. The
coverage initialization failures for 001, 003 and 011 ended while rebuilding
source closures through Python AST parsing or path operations. Coverage 005
A-0 completed three stationary fit calls before its post-fit validation
exhausted the whole-slice deadline. More CPU workers do not remove this work.

| Preserved stage | Saved scientific state | Follow-up |
|---|---|---|
| Before 003 A-2 | Low/high/final stationary calls; no aggregate terminal | Requires explicit receipt recovery; no rerun authorized by an observation timeout |
| Before 007 A-0 | Complete terminal and slice termination; outer process timed out | Existing receipt-review port accepted it in 9.172 s, zero new optimizer calls |
| After 005 A-0 | Low/high/final stationary calls; failed outer slice | Requires explicit receipt recovery |
| After 025 cold-bootstrap | Complete terminal and slice termination; outer process timed out | Existing stage reader accepted it in 13.439 s, zero new optimizer calls |

The two completed reviews used fresh diagnostic namespaces
`local/pipeline-metadata-review-007` and `local/pipeline-metadata-review-025`.
They preserved the original failures and timeouts. The 007 review generated
the normal metadata review through `review_unit`; the 025 review was read-only.
Neither check prepared held observations, read a position reference, or refitted
a scientific call. Both used 90 s internal and 105/110 s external bounds.

The A timing-control agent separately measured approximately 43–52 seconds
for source checks, recursive parent validation and training preparation, while
its saved individual fits took 0.08–4.19 seconds. The implementation change in
progress qualifies authority once, binds the exact semantic file inventory,
and checks those bytes before and after each unit. It must reject changed,
removed and unexpected added authority files; it must not weaken the original
semantic checks or change the 20-second scientific fit budget.

Another broad fit batch is deferred until that change is qualified. An explicit
six-worker wave 011 was launched for previously unattempted baseline discovery
on 055, 057, 059, 061, 071 and 073. This advances missing dataset coverage through
the shallow discovery path without retrying any failed fit or affected deep
validation stage. Each discovery retains its original 480/495/500-second
internal/TERM/KILL bound. Results are pending; a subprocess success must still
be distinguished from a scientific checkpoint requiring an explicit next slice.

Wave 010 first failed at module import because the coordinator omitted
`PYTHONPATH=src:tools`. All six directories were checked for absence of scientific
claims before wave 011 was launched with the corrected environment. The import
failure logs remain intact. The explicit recovery record also discloses that its
first disk write lacked permission and was successfully persisted after launch;
it does not pretend that this record was sealed beforehand. No scientific fit
from wave 010 was retried because none had started.
