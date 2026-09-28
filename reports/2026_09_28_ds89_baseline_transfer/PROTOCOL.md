# Unchanged DS7 baseline transfer to DS8 and DS9

Freeze the first eight captures of each dataset ordered by capture-start UTC
and session ID, using only the sealed membership manifests. Retain all selected
records, including unavailable inputs or failed exports/fits; do not replace
them with successful later recordings. The first chronological capture in each
dataset is an export preflight, not a performance-selected subset.

Use the unchanged DS7 public track exporter and causal candidate-bank exporter,
then the unchanged DS7 stationary Student-t full-mixture baseline. Preserve
visit partition seed, minimum track span/support, constant-offset profiling,
causal catalogue selection, DS6 coordinate origin and five-anchor candidate
shortlist, timing grid, bounds and three timing starts. Record input eligibility
exclusions. No slope augmentation or model tuning is introduced.

The dataset manifests freeze capture membership. Exports freeze the tracking
analysis and causal TLE products actually read now, with their own hashes;
DS8's capture-complete admission does not imply analysis availability at mint
time. DS9's mint-time analysis evidence is retained separately from export
provenance. Never silently claim the current cached analysis is the mint-time
version without matching its bindings.

Use the installed public readers from the same release recorded in both dataset
manifests (17484895464c225ebba977487aa36d3d81658bd8). Record interpreter and module
source hashes before export. Exporters read existing derived tracking products
through public ports; no IQ, new RF or source-store writes. Candidate propagation
is allowed in this step and must remain bounded.

Stages are incremental: first DS8-001 and DS9-001 observation/bank exports,
then remaining frozen rows only after preflight review. Each observation export
is capped at 60 seconds, each bank export at 120 seconds, 4 GiB address space,
one numerical thread and nice19. No automatic retries or cap extensions.
Record each failure and partial artifact. Do not launch a multi-hour campaign.

Freeze exported inputs before fitting. Evaluate individual recordings first;
eight-record joint panels are a separate observation budget. Each later fit
must receive a bounded launch receipt and be sealed before geographic scoring.
Reference coordinates are excluded from exporter/solver requests; post-fit
scoring uses each dataset's sealed authority and the existing great-circle
metric. Report all failures, boundaries, held scores and error distributions.
These later captures are at an exposed, unsurveyed site, not new-site validation.
