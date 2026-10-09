# User-authorized ablation running

The user resumed work specifically to run the agreed hard60 ablation and plots
on all DS16/DS17/DS18 members. No production change or new RF is authorized here.
The supported goal tool still reports paused and exposes no resume operation;
the newer explicit user instruction authorizes this ablation task. Do not call
goal complete or recreate/shrink the existing objective to work around that state.

Frozen protocol/source commit b7cfee05b, published remote main before fitting.
1466 source/input hashes;13 configurations;148 members; two matched c arms.
Six synthetic model/control tests passed. B0/B1 reuse archived search receipts;
downstream fits are fresh90s/600iteration runs. Clock prior widening has its own
row, and C3/C4/C5/C6 distinguish model changes from an extra refit.

Active numerical workers:
- shard0 exec2683, PythonPID4133962 (sudo4133940).
- shard1 exec55837, PythonPID4133963 (sudo4133941).
Both authoritatively confirmed live,~99%CPU. First five members complete with
no input failures; verified B0errors match the full saved baseline. No full
candidate mean yet. Runtime approximately25–30s per early member, two workers.

Prior84 processes4121459/4121460 remain suspended in T state; do not resume them
alongside these workers. Their129 completed receipts are preserved. Any in-flight
work affected by suspension needs explicit timing review on later resumption.
Iteration83 remains checkpointed, no worker. It must not displace this requested
ablation. Neither prior experiment supplies selective replacements here.

Next: verify both85workers terminal, all148 statuses, frozen hashes, RF locks,
baseline reconstruction and every failure/fallback. Generate report.py outputs
and inspect mean/CDF plots. Publish receipts, complete results, source/integrity
and a decision report to remote main. Perform the subsequently frozen removal
study before claiming each final component necessary. Independent reserve,
cold pipeline/shadow and PNG verification remain later deployment qualifications.
