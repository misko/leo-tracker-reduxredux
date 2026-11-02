# Fresh ALGO07 evaluation of the recent outliers

The promoted ALGO07 science completed all 12 retrospective cases. All ten
provisional outliers retain the exact saved ALGO06 endpoint and ownership count.
The two additional ranking checks accept the original repairs: DS26-0034
53852→59188, and DS26-0251 56548→58787. Both accepted endpoints and objectives
match their frozen research candidates exactly in both calibration arms.

| Rank among the ten | Case | Fitted-c error, m | c=0 error, m | Associated points | Primary rejection |
|---:|---|---:|---:|---:|---|
|1|DS26-0203|6857.97|6681.34|2337|Inherited predictive admission|
|2|DS26-0070|6715.66|7268.99|2023|63571/67047 receiver-shared competition|
|3|DS26-0072|4329.08|4354.56|1526|65829 admitted; fitted-c physical gates and optimizer fail|
|4|DS26-0221|4070.15|4070.85|3486|48127 and 67186 admitted; no qualified paired fit|
|5|DS26-0044|3714.55|3593.62|2803|58786 already owned; 63186 receiver-shared competition|
|6|DS26-0100|3629.05|3641.79|2763|59315/63315 receiver-shared competition|
|7|DS26-0014|3405.04|3415.13|2979|Inherited predictive admission|
|8|DS26-0201|3355.73|3191.22|2514|Inherited predictive admission|
|9|DS26-0309|3126.78|3162.10|3008|53859 admitted; no qualified paired fit|
|10|DS26-0209|2589.07|2596.80|3030|Inherited predictive admission|

The ranked errors use the supplied evaluation coordinate only after inference
and selection, with a 6371000 m haversine radius. The deployed numerical runner
receives no truth coordinate and returns null error metadata. This reporting
radius differs from the older saved reports by less than 0.01 m in these cases.
Observations, candidates, priors and search settings stay matched between c=0
and fitted-c. Frequency objective changes are reported separately in the CSVs;
an improved objective does not establish improved position accuracy.

This is saved research authority, not a live public-terminal test. Each private
SCAN replay first verifies exact saved ALGO06 coordinates, objectives and owner
maps. Only the public-terminal adapter is replaced with that explicit research
check. Production science, guard thresholds and selection remain unchanged.

Source is the deployed ALGO07 release at repository HEAD
af21461ea5d9af7a34dcc8e067d021951b170d3d. All tracked src/tools files and the
evaluation runner are frozen in [code-freeze.json](code-freeze.json).
Every case has a fresh input and output directory, a full causal archive bank
exported through TleArchiveReader and algo07_history.export_history, and an
independent 1200-second cap. Six processes run with BLAS thread counts set to
one. All cases complete successfully in 51–579 seconds; no hardcap or worker
failure occurs. The archive adapter is read-only, and its exported files are
readable by the normal user. No RF collection or production change occurs.

Use [diagnostics.json](diagnostics.json) for target rankings, all proposed
identities, inherited admission and receiver-shared guards, final selection
reviews, and the actual qualification and gate flags for each candidate start.
The final policy review treats a missing qualified pair as absent flags, so its
generic reasons must not be read as a claim that every underlying fitted start
failed every listed condition. Actual start flags are authoritative for that
diagnostic distinction.

[diagnostics.csv](diagnostics.csv) provides both-arm before/after errors,
counts, objectives and rejection reasons. [summary.csv](summary.csv) provides
the simpler evaluation table, and [summary.json](summary.json) retains guards
and paired candidate summaries. [validation.json](validation.json) passes all
12 cases: frozen hashes, exact research replay, full history request parity,
exact rejected fallbacks and qualified/native-matched accepted pairs.

The publication set omits large history banks, copied private inputs and full
scientific fit traces. Their hashes and byte counts remain in
[retained-artifacts.json](retained-artifacts.json); the local originals remain
available for audit. Per-case compact input/source receipts and launches are
included. `publication_manifest.json` lists the
compact publication files, with paths relative to the parent report root.
