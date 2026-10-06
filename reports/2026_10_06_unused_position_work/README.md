# Remove unused automatic tracking work

Implemented the four approved changes:

1. Automatic tracking requests per-track review PNGs without rendering the
   unpublished combined overview. Standalone reports keep the overview by default;
   omitted overview metadata is explicitly null. Review data and per-track PNGs remain.
2. Position scoring computes held-out RMS only for each usable candidate's
   training-selected tau. Training fitting, visibility masks, tie ordering and
   candidate selection remain unchanged. Temporary work stays candidate-batched.
3. Exact-invisible position candidates no longer trigger velocity gathering,
   Doppler prediction or residual scoring. Empty tracks still contribute their
   original unmatched penalty. Coarse and exact visibility tests remain unchanged.
4. Fixed interpolation indexes/weights are prepared once per regional evaluator
   instead of at each receiver point. They depend on the frozen track/bank and tau
   geometry, not the receiver location. All-visible blocks avoid extra gathers.

## Validation

49 tests passed across adaptive position/prediction analysis, report rendering,
tracking CLI, adaptive-position CLI, contracts and storage. Tests cover stable
ties, candidate and candidate/tau visibility, strided float32/float64 inputs,
multiple batch sizes, exact-invisible candidates without velocity reads, unmatched
penalties, cached metadata and byte-identical per-track rendering. Ruff and diff
checks passed. No scientific fixtures or persisted contracts were changed.

`tools/benchmark_unused_position_work.py` compares old and new modules on saved
2.5 MS/s (`scan-fw-cc609ed603589e6e`) and 10 MS/s
(`scan-fw-aadec7177d989684`) inputs. Both use the same two tracks (at most 128
observations each), first 1,024 catalogue candidates, banks, priors and search
budgets. Three fixed points and an eight-point bounded search are checked for
each Sacramento/Reno prior. All point scores and complete search results matched
exactly; both tracks matched at each fixed point. This is a numerical parity
check, not a localization accuracy experiment or a fitted-c comparison.

`position-parity.json` contains the alternating-order replay measurements. These
small subsecond timings vary by a few percent in both directions on the busy
server; they do not establish a fleet throughput improvement.

The saved 2.5 MS/s review was also generated with and without its overview,
bounded to one track. The numerical track data and published per-track PNG bytes
matched exactly; only the unpublished overview was omitted (`review-parity.json`).
The equivalent rendering helper is additionally covered by the component test.

## Deployment

Deployed at 2026-10-06 01:49:22 UTC from commit
`d41cba9a0285842377b394aea421f5641d867e1d`, pinned under
`/opt/leo-unused-position/d41cba9a0`. `deployment.json` records before/after module
hashes. All worker-service PIDs were unchanged. A fresh production Python process
resolved all four modules to the pinned files; the queue had no expired leases.
The 13/6 capacities and ten-minute timer remained effective.

Deploy only the four changed modules into the existing production overlay,
retaining backups. Install the report implementation before its CLI caller.
Fresh job subprocesses import the changes; running processes finish with their
already-loaded modules. Preserve the Hough, GLRT, lease and memory patches and
the existing 13-analysis / 6-tracking concurrency and ten-minute capture gap.

Rollback replaces each module's overlay symlink with its retained baseline copy.
No new RF collection, complete regional campaign or existing product rewrite is
needed for this deployment.
