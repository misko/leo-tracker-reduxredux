# Exact decision-only early exit

The report-owned prototype preserves the current `detect_first_glrt64`
`DwellDetection(first, best_margin, reason)` output while stopping after the
complete probe that establishes a confirmation. It leaves
`analyze_glrt64_dwell` unchanged. Every warmup, measured call, constructed
control, and instrumented diagnostic matched the current repository oracle
exactly.

The preregistered promotion gate failed. The 2.5 Msps development case stopped
after probe 2 and exceeded the 3.0x process-CPU gate. The 5 Msps case did not
establish its confirmation until probe 5 and achieved only 1.76x. Both rates
were required to pass.

| Recorded case | Candidate acquisitions | Candidate scores | Baseline CPU | Early-exit CPU | CPU speedup | Gate |
|---|---:|---:|---:|---:|---:|---|
| 2.5 Msps | 6 | 60 | 1,417.7 ms | 366.0 ms | 3.874x | pass |
| 5 Msps | 12 | 120 | 3,764.2 ms | 2,137.4 ms | 1.761x | **fail** |

Times are medians of three paired calls after one warmup per method, pinned to
P-core 0 with numerical thread limits set to one. The timed boundary is the
detector call on preformed immutable complex64 dual-receiver IQ. Loading,
conversion, hashing, output serialization, and diagnostic counters are outside
the boundary. The candidate also avoids constructing the full probe/candidate
response that the narrow decision API discards; this is part of the intended
specialized API implementation.

The earlier application-profile narrative inferred that both cases established
their decisions after probe 2 from a returned prior hit at probe 0. That
inference was wrong for 5 Msps. `first.probe_index` identifies the earlier hit
returned by the contract, not the later probe that confirmed it. Direct
candidate work counters show that the 5 Msps confirmation occurred only after
six probes had completed.

Both constructed all-zero controls returned no detection and completed all 22
receiver/probe acquisitions. Acquisition returned no candidates, so their
candidate-score counts were zero. One report-only timing per method was 525.9
versus 502.1 ms at 2.5 Msps and 2,233.9 versus 2,268.8 ms at 5 Msps. These
controls demonstrate the full negative schedule and exact output; they are not
physical absence truth and have no speed acceptance gate.

The component suite compares the prototype directly with the production oracle
for earliest and late confirmation, a complete negative, competing receivers,
candidate ties, overlapping probes, the inclusive 8 kHz CFO boundary, a value
just outside that boundary, and invalid shapes. It also proves that the earliest
confirmation finishes both receivers and all candidates in its confirming probe
before stopping.

This is a bounded, outcome-informed development diagnostic on two recorded
positive-path cases. It does not estimate average traffic speedup, qualify a
full corpus, change the full-analysis response, or establish deployment or ARM
performance. The failed two-rate gate means the candidate is not promoted from
this experiment.

Frozen evidence:

- `source_lock.json`: `5da4b70e1ed5d0ac85a28b76dafa1f71cf9d15b2eb0120b8cc38548d7954dcab`
- `design.json`: `b114f3f363974bda0de9e68edd5d4b4b30b5d13e37e8dbe83f434e2162195341`
- `prototype.py`: `b1cbd73249058f22bebafea288416c06fbdc6c29bd7badf340317f155a2817b2`
- `results.json`: `37c0c93a2c043b2c41fab122deb0b196e3ecd78e0584fa767e611251fa35ccfd`

