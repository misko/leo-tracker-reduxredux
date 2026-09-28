# DS7 large ARM score audit

`score.py` reads only report artifacts: `inputs.json`, `baseline/rows.jsonl`,
and `arm/rows.jsonl`.  It refuses to score unless both receipt sets equal the
planned case inventory exactly.  It also rejects duplicate ARM cases, failed
receipts, misaligned confirmation records, and an executed ARM bit that was not
ranked.  Thus repeated ARM attempts, queue/timer rows, and partial cohorts
cannot inflate scientific counts.

The baseline is the full-original serialized runner schema.  ARM is the RAM
worker job schema with the original `context` retained on every job.  ARM bit
`n` denotes the 20 ms interval starting at `20*n` ms; its confirmation record
is aligned with set bits in ascending order.  Ranked intervals come from
`result.rank.order` (exactly six distinct intervals); executed intervals from
`confirmation_window_mask`.  The worker contract permits at most one executed
window per receiver and the scorer validates the reported count and alignment.

The command additionally requires `--baseline-run` and `--arm-run`.  Their
receipts must be complete, report exactly the planned 704 calls, and report no
failures before any score is emitted.

When present in a run receipt, `input_manifest_sha256` and `rows_sha256` are
recomputed from the supplied artifacts and must agree.  Every baseline and ARM
context must equal its sealed `inputs.json` row, and its case ID is recomputed
from that context.  For sealed large-cohort inputs, every baseline visit must
retain both receivers and all eleven stride-10-ms starts (22 windows).  This
prevents a shortened baseline from reducing the recovery denominator.

Positive windows are reported separately from individual positive candidates.
Candidate identity uses maximum-cardinality one-to-one matching inside the same
case, receiver, and 20 ms window with epoch error at most 2 us and tracking-CFO
error at most 8 kHz.  Additional ARM positives are explicitly reported as
unmatched and are not called false alarms.

`baseline_positive_positive_again_activity` means the executed ARM window also
contains a positive.  `matched_baseline_positive_windows_identity` is stricter:
it requires at least one one-to-one candidate identity match, and is the window
recovery count used for the report.

The report also emits the same accounting separately for each sample rate.
`margin_boundary` counts candidates whose serialized margin is exactly 0.025:
they are baseline positives under the original recorded gate, but ARM does not
call them positive under its strict gate (irrespective of recovery matching).

## Observed sealed result

`score.json` was produced from the complete 704-case baseline receipt and the
complete 704-case `arm03` receipt.  It reports 15,488 baseline windows (22 per
visit), 7,007 baseline-positive windows, 8,448 ranked ARM windows, and 1,408
executed ARM windows.  Of the 635 positive baseline windows that ARM actually
evaluated, 522 were ARM-positive by activity and 499 had a one-to-one matched
positive candidate identity.  The 499 figure is the recovery count; activity
does not receive identity credit.

There were 19,581 baseline-positive candidates, of which 1,790 were in an
executed window.  Maximum-cardinality one-to-one matching recovered 499 of
those; ARM produced 661 positive candidates, including 162 unmatched positives
explicitly retained as *not false alarms*.

| Rate (Hz) | Baseline windows | Baseline-positive | ARM ranked / executed | Positive evaluated | Activity positive | Identity-matched windows | Candidate matches |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2,500,000 | 3,344 | 1,682 | 1,824 / 304 | 150 | 138 | 126 | 126 |
| 5,000,000 | 4,752 | 1,874 | 2,592 / 432 | 169 | 148 | 144 | 144 |
| 7,500,000 | 4,048 | 1,933 | 2,208 / 368 | 175 | 133 | 126 | 126 |
| 10,000,000 | 3,344 | 1,518 | 1,824 / 304 | 141 | 103 | 103 | 103 |

No serialized baseline or ARM confirmation candidate had a margin exactly
0.025, so the native `>=` versus ARM `>` threshold distinction affected zero
observed candidates in this cohort.  It remains explicit in the scorer because
it is a contract boundary, not a claim of full-search parity.

The focused regression test loads the frozen DS7 scorer and the 28 unique
original cases retained in its prior saved run.  For every positive
case/receiver/probe group, the local matcher produces the same one-to-one
maximum-cardinality count as the frozen matcher.  This checks duplicate
hypotheses without treating repeated prior runner rows as extra evidence.

There is a real gate boundary: original uses its recorded
`passed_margin_gate` (`margin >= 0.025`), whereas ARM requires
`fractional_complete` and `margin > 0.025`.  The output preserves this rather
than claiming native/full-search parity.
