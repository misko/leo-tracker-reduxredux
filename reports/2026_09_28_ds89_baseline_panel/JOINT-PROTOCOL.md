# Separate eight-record pooled baseline budget

After individual preparation is complete, attempt one unchanged joint-position
fit for each dataset only if all eight frozen records have validated observation
and bank inputs. An unqualified individual position does not disqualify its
observations; missing/failed input preparation prevents a complete pooled fit.
Do not silently omit a record or average independently fitted positions.

Construct each pooled request by concatenating the original eight input rows in
chronological order, retaining the same scientific config, DS6 coordinate origin,
three timing starts and original bounds. Fit one shared horizontal position and
eight independent timing offsets with the unchanged DS7 fast baseline adapter.
No new nuisance, reweighting or geometry-dependent membership selection.

Each pooled attempt is capped at 300 seconds and 4 GiB, one numerical thread,
nice19, with no retries or automatic cap extensions. Preserve all available
failure/partial evidence. Seal inputs and responses before scoring against the
dataset's bound unsurveyed pose authorities, first verifying all eight refer to
the same coordinate. Report this observation budget separately from individual
results and retain all attempted-record denominators. Failure or a favorable
pooled result does not change the individual-record benchmark.
