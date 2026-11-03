# Full-scan native GLRT qualification: comparison tooling and frozen downstream evidence

This iteration is **in progress**. The tiled GLRT candidate has not been deployed.
There is no new full-scan speedup or end-to-end speedup claim in this checkpoint.
The tenfold ALGO07 objective remains open.

The prior native experiments showed a promising detector improvement, but the
completed full-scan trial used eight workers and lacked a matched baseline timing.
Current production uses sixteen GLRT workers. The next comparison runs the
original and tiled implementations sequentially, each with sixteen workers and
an 1,800-second bound, over the same frozen DS27-0004 recording. The original
runtime frozen for this experiment is byte-identical to the current production
native worker. Production continues running, so host contention remains a
measurement limitation; CPU time and launch load are retained separately.

## Stronger scientific comparison

`tools/compare_full_glrt_replays.py` compares the complete native result for every
window. This includes scores, every receiver hypothesis, fractional refinement,
gate decisions, acquisition metadata and invalid-window reasons. It checks the
frozen input/runtime files, launch identity, successful termination, segment
coverage and ordered visit inventories before comparing. Missing or duplicate
windows fail validation. Nonfinite numeric leaves fail equality. Timing ratios
are withheld if workers, interpreter, host, thread settings, profiling or replay
script differ. No tolerance is introduced.

The checker successfully loaded and validated the previous eight-worker candidate
trial's complete inventory:

| Evidence | Count |
| --- | ---: |
| Native windows | 6,772 |
| Processed windows | 6,767 |
| Receiver results | 13,534 |
| All receiver hypotheses, including unpublished candidates | 108,272 |

That inventory check is not a comparison against a new baseline. The original
eight-worker run's published candidates matched their frozen reference. Its
1,436.036-second wall time must not be compared directly with the sixteen-worker
baseline to claim a kernel speedup.

Eleven component tests pass, including changed unpublished hypotheses, invalid
window reasons, missing windows, duplicate ranges, timeout, extra unfrozen code,
nonfinite values and mismatched worker counts. Ruff passes for the new tool and
its tests. The profiling skill and benchmark protocol now describe this check
and the production-matched concurrency.

## Downstream reference

The public ALGO02 analysis export port supplied the completed analysis for this
same native recording. Its 23 analysis files plus descriptor are now frozen in
the private benchmark directory. This preserves both calibration arms, the
original causal preparation and the terminal reference without rebuilding a
catalogue from today's archive.

The historical terminal records preparation at 30.978 seconds, ALGO02 fitting at
209.875 seconds and family comparison at 53.871 seconds. These are historical
stage timings, not a new matched run. Exporting the analysis does not rerun
localization. Its stored results must remain reference evidence, never feed
the optimizer as answers.

The new `tools/profile_algo02_prepared.py` adapter now isolates **17 prepared
input files** from this export and freezes them with the installed ALGO02
runtime: **1,793 bound files** in total. The installed numerical runtime is
`1b63f5908785fc940446086aa4ef5de1a1539003`, identified from the live ALGO02 watcher.
The adapter preserves production's discovery subprocess, initial/ALGO02 fits in
one parent, and subsequent family comparison. It records per-stage timing,
optional cProfile output, and complete read ancestry under a 1,200-second total
bound. It does not rerun graph construction or ALGO03–07.

Three additional tests verify exclusion of archived fitted answers, rejection of
changed prepared inputs, and accounting for every stage and child in the read
audit. All **14 combined tool tests** pass. Snapshot creation has completed;
the prepared numerical replay has not yet run. It will follow the native timing
trials to avoid adding another research computation during those measurements.

## Remaining qualification

1. Finish the live sixteen-worker baseline; retain any timeout or failure.
2. Run the candidate sequentially with identical settings.
3. Compare all 108,272 hypotheses and verify every frozen file again.
4. Verify the published tracking input and run downstream localization checks
   with both c=0 and fitted-c, matching observations, causal inputs and budgets.
5. Publish complete timings, parity receipts and figures before deciding on a
   native production rollout. Keep component improvements separate from the
   full recording-to-ALGO07 runtime target.
