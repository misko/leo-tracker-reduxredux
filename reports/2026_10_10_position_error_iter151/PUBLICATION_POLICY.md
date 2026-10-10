# Evidence publication for the running pilot

Publish the completed Markdown report, position-error plot, compact summary and
receipt byte hashes after all 36 member/phase receipts are terminal and the
frozen source, input and evaluation checks pass. Until then, progress and source
reviews are not completed positioning results.

Keep the raw point fits, traces, slice receipts, stage claims and intermediate
states in the local `results/` directory. The compact summary hashes those
artifacts and retains qualification, missing-stage and cost evidence. This is
an auditable report with local raw evidence, not a remote raw-data reproduction
bundle. Do not imply that hashes alone reproduce the fits or preserve the raw
bytes outside this host. This follows the explicit publication scope of the
earlier twelve-member iteration 129 report.

Do not create a large compressed archive while both numerical workers are
active. The observed shared-host journal contention and automatic Git repacking
make unnecessary bulk writes particularly unhelpful during the frozen timed
comparison. No raw receipt is removed, rewritten or substituted by this policy.

The completed report must keep the interpreter-path deviation and host timing
limitations visible through links to ENVIRONMENT_AUDIT.md and
HOST_IO_OBSERVATION.md. Report discovery policy effects separately from matched
final c=0/fitted-c effects, and describe conditional handoff differences using
HANDOFF_OBSERVATIONS.md. Neither pilot accuracy nor its progression screen
updates the full 193-member metric or authorizes deployment.
