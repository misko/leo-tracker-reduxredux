# Same-receiver rescue control result

The fixed rescue candidate failed its first scientific gate, so the diagnostic
and recorded-data stages were not opened. The immutable control receipt is
`results.controls.json`, SHA-256
`cddba5d93b7093b9e95fe522233a292635a000f25c034e35b61fae92d4cb0727`.
Its 103-file source lock is SHA-256
`0c12603cba55e137501032577f36bb8c7b0a0c3bbe7e06da34a949c687cabb54`.
The receipt is complete and source-stable, with 42 original control/sequence
occurrences and 24 separately reported negative-orientation executions.

## Scientific result

The unchanged tracked baseline passed all 84 original receiver truth policies.
The rescue candidate passed 82/84. It falsely accepted two constructed tone
receivers at 5 MS/s:

- `control-tone-upper-r5000000-s13903-13904`, RX0
- `lag3-r5000000-tone`, RX0

Both false decisions contained two fresh native observations at probe zero and
probe two. Their native margins were just above the fixed `0.025` gate and all
status, support, timing and physical-frequency checks passed. The failures are
therefore real outcomes of the frozen rescue rule rather than forged flags or
missing confirmation evidence.

The paired orientation audit used the twelve fixed independent negative
parents in original and RX-swapped form, with fresh detector state for every
execution. The baseline remained inactive on all 48 receiver checks. Rescue
produced three false active receivers: the two failures above in their original
orientation and an additional swapped RX1-origin tone from
`control-tone-lower-s3901-3902`. This confirms that always selecting RX0 in the
ordinary control pass would otherwise hide an orientation-dependent failure.

## Work and timing

Across the 42 original occurrences, rescue ran 16 acquisitions, scored 148
Python candidates, made 36 native seed calls and four native confirmation
calls, accepting two rescues. Event outcomes were 112 Python-margin failures,
32 native-seed failures, two native-pair failures and two accepted pairs.

Median tracked/rescue CPU per visit was 14.91/15.29 ms at 2.5 MS/s and
29.53/32.37 ms at 5 MS/s. Rescue p95 rose to 78.73 and 193.31 ms respectively
because inactive visits pay the Python acquisition path. These control timings
are diagnostic and do not establish application-relative speed because the
expensive application comparator was intentionally omitted from this stage.

## Decision

The candidate is rejected unchanged. `DESIGN.md` requires later stages to stop
on any constructed-truth failure, and the frozen receipt records five failures
across the original and orientation-audit executions. No diagnostic or real
saved-IQ stage, validation, holdout, RF, QNAP, or production operation followed.
Before freezing, 33 owned runner and detector tests passed.
