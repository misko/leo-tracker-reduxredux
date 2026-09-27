# Transfer the fixed-window diagnostic without retuning

Apply the unchanged distributed_proposal.search function, seed windows0/5/10,
candidate cap10, margin0.025, nonoverlap, 2us timing and8kHz frequency gates to
every inactive receiver in expanded_development/results.hash_adapter.json.
Include both receivers when both are inactive and all reference-negative visits.
Select targets only from candidate activity. Keep first accepted candidate per
seed, including unmatched outputs. Assess against saved application inventory
only after search. Preserve unknown physical truth; extras are not proven false
alarms. No held-out recordings are used.

Freeze source hashes and full membership before IQ. CPU0, numerical threads=1,
120-second total bound, immutable inputs and per-search checkpointing. Cost is
search-only and includes conversion, acquisition and confirmation; it excludes
primary processing and does not represent an integrated capped schedule. The
5 MS/s cohort has no reference positives and cannot establish sensitivity.
