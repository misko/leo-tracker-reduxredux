# Frozen TRAIN element-age diagnostic

Use the 151 TRAIN session IDs and snapshot digests in the completed strict
metadata artifact. Read those immutable snapshots only through the public
`TleArchiveReader`, which re-verifies each content digest. For every sealed
paired-residual row, require exactly one catalogue member matching its fixed
candidate ID and recover that member's parsed TLE epoch. Define element age as
the pair reference UTC (snapshot collection UTC plus the already sealed
collection age) minus the actual parsed element epoch. Do not use snapshot
collection age as element age.

Join exactly to the sealed `(session_id, candidate_id)` pair rows. Report
coverage and every missing/duplicate failure. Describe common slope and common
quadratic residual versus actual element age overall and after demeaning within
TRAIN group, RF lane, and look quadrant. Also report age-bin summaries with
whole sealed scan/candidate groups as the observational grouping. These are
descriptive diagnostics: no causal claim, position fit, epoch shift, orbit
correction, TEST/VAL/truth access, RF replay, or new RF collection is allowed.

Bind the protocol, helper, analyzer, sealed paired inference, strict metadata,
and every public archive snapshot digest used. Preserve the previously reported
causal orbit update history only as context, not as a joined outcome.
