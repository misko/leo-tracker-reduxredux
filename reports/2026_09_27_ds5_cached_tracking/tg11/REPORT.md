# Track-guided server compute experiment

The current objective is general compute reduction on saved DS5 recordings.
ARM access and the radio's capture pause are not prerequisites. No new RF
collection is needed. This experiment evaluates a new decision detector, not
an exact replacement for the scanner's complete candidate report.

The idea is to reuse a previously fitted signal's timing and frequency as a
prediction, then measure the current samples to confirm it. Each receiver still
screens all eleven windows. Missing, expired or failed predictions trigger fresh
blind acquisition; scheduled discovery also prevents indefinite reliance on one
track. A previous positive never counts as a current detection.

## Constructed controls

The frozen stage-0 run completed all 42 physical rows: 32 independent dual-RX
controls plus ten dual-RX sequence steps. All scientific gates passed and frozen
sources remained unchanged. The controls cover pilots, noise, tones, fractional
timing, large frequency offsets, multiple pilots and strong-tone interference.
Sequences cover appearance, disappearance and a changed signal. Finite-duration
pilot controls require actual injected pilot support in both confirming windows.

All 84 receiver decisions used blind acquisition: 74 cold starts and ten screen
disagreements. There were no accepted guided confirmations. These controls
therefore validate blind detection and fallback behavior, but do not demonstrate
native guided-route accuracy or a caching speed benefit. Separate mocked tests
exercise the guided state machine and forced-discovery counter.

See `control_results.json`, `source_lock_stage0.json`, `design.json` and
`RUN_PROTOCOL.md`. This is constructed-signal evidence, not real-recording
retention, a field false-alarm estimate or a speed result. The original holdout
remains unopened.

## Paired cost and real-data gate

The four metadata-selected saved visits completed one warmup and three paired
repetitions per method. Complete two-receiver CPU medians were:

| Sample rate | Current scanner | TG11 | CPU ratio |
|---|---:|---:|---:|
| 2.5 MS/s | 1,515.49 ms | 16.03 ms | 94.53x |
| 5 MS/s | 4,071.33 ms | 33.15 ms | 122.81x |

These ratios compare different detector implementations and candidate inventories;
they are not a qualified equivalent-computation speedup. The cost gates passed,
but the scientific gate failed: TG11 reported an extra RX0 detection on 2.5 MS/s
visit 1078, where the comparator had no qualifying pair. The other three visits
retained their active decisions and associated to comparator pairs. Real samples
have no independent physical truth, so this is a comparator disagreement rather
than proof that the extra detection is physically false.

All eight real receiver decisions used cold blind acquisition; none attempted
guided confirmation. The measured reduction comes from the smaller native blind
detector, not from reusing an already found signal. The failed visit's comparator
maximum margin was 0.01668 (below 0.025), while TG11's selected probes 4 and 10
had margins 0.09576 and 0.11411. See `PHASE1_REPORT.md` for the preserved evidence.

A separate frozen diagnostic subsequently scored the native hypotheses through
the current Python GLRT on raw samples. Both passed at their nearest integer
epochs, with margins 0.13562 and 0.11677 and a mutual tracking-CFO difference of
12.9 Hz. The application search had not retained those coordinates. This narrows
the disagreement to search coverage for this case; it does not prove physical
truth, revise the original comparator gate or qualify the full detector. See
`../tg11_diagnostic/REPORT.md`.

The fixed 64-visit replay was not run, as required by the stopping rule. No
threshold was adjusted, no failed result discarded and no holdout opened. See
`phase1_cost_results.json` and `source_lock_phase1.json`.

The separate `SCREEN_COORDINATE_AUDIT.md` identifies why the repeated-pilot
controls never entered guided confirmation: the rank statistic's epoch differs
substantially from the fitted GLRT epoch, yet the current gate compares them
directly. A constant correction is not supported by the evidence. This needs a
separate revised design and qualification, preserving this failed experiment.

CPU work, elapsed latency and batch throughput are separate measurements. The
earlier 8.20x/10.69x parallel latency gains used additional cores; they did not
reduce CPU work by 10x. No accuracy-qualified general 10x result is established.
