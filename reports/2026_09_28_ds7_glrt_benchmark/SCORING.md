# DS7 reference-relative GLRT scoring

`score(reference_rows, candidate_rows)` compares one method against a frozen
reference method. It does not select signals, establish truth, or call extra
candidate positives false alarms.

Each row follows the runner contract:

```json
{
  "context": {
    "session_id": "...",
    "visit_index": 0,
    "sample_start_counter": 0,
    "rate_hz": 2500000,
    "target_index": 0,
    "target": {"channel": 1, "edge": "lower"}
  },
  "status": "ok",
  "result": {"probes": []},
  "timing": {"cpu_s": 0.0, "wall_s": 0.0},
  "method": "D",
  "repeat": 0,
  "diagnostics": {}
}
```

`status` is `ok` or `failed`; a failed row must have `result: null`. The
context plus repeat is the row key. Score one repeat at a time, or retain the
repeat in rows to keep independent repeated outputs separate.

Candidate hypotheses are associated only within the same row key, receiver,
and probe. A pair is eligible when its epoch difference is at most 2 microseconds
at that row's rate and its tracking-CFO difference is at most 8 kHz. The scorer
finds maximum-cardinality one-to-one matches, then deterministically prefers
the nearest timing/CFO edges. It calculates a separate matching using only
margin-positive hypotheses for recovery credit, so a nearby negative cannot
consume a positive identity. This prevents one candidate from receiving credit
for multiple reference hypotheses and prevents association across receivers,
probes, sessions, visits, or repeats.

The output keeps independent sections for:

- exact serialized-result equality among successful row pairs;
- reference positive/negative and method-unprocessed denominators;
- positive candidate identity, receiver/probe, and confirmed receiver/visit
  recovery. Confirmed receiver/visit reports both matched-identity recovery and
  activity-only recovery; only the former credits the same associated pair;
- unmatched candidate positives and all unmatched candidates, explicitly
  labelled as not false alarms, plus candidate positives paired to a
  reference-negative hypothesis in all-candidate diagnostics;
- matched timing, tracking-CFO, exact/control/margin deltas; and
- CPU and wall-clock aggregates supplied by the runner. Speedups are reported
  only when every reference and candidate row has a successful, matched-context
  result and both timing values; negative timings are rejected.

A confirmed receiver/visit requires two same-receiver candidate positives with
margin at least 0.025, non-overlapping 20 ms probes, and tracking CFO within
8 kHz. This reproduces the scanner's standard confirmation rule. It remains a
reference-relative recovery measure, not an oracle-truth assertion.
