# Existing corpus inventory for the 600-second history gate

Date: 2026-09-30

## Result

No recording in the bounded, known adaptive corpus supplies 600 seconds of
continuous causal evidence.  The longest finalized source-counter span found is
300.1272296 seconds.  DS9 supplies exactly 300 seconds of recorded counter span
and 299.8017789333333 seconds in the retained native event fixture.  Existing
recordings therefore cannot test the native 600-second retention and expiry
gate without a new, genuinely continuous recording.  Concatenating or
time-shifting recordings would not close this gate.

## Recording evidence

| Session | Exact recording manifest | Counter and UTC evidence | Candidate/event availability |
| --- | --- | --- | --- |
| `scan-fw-3cfdaa6d75762cad` (DS9) | `/srv/bulk/leo/scanner-adaptive-recordings/scan-fw-3cfdaa6d75762cad/manifest.json`; file SHA-256 `7cf0e0f72f8465f4ad74c28cee97cc1a00aeec61ac51c84ae870f17c5a6eff56` | First/final counters `1247641617019` / `1249891617019` at 7,500,000 sample/s: exactly **300.0 s**. The manifest marks timing qualified and source span attested, reports 2,215 completed emitted visits, zero device drops and zero transport-missing samples. Its first-sample UTC bracket is `[1790557997116690851, 1790557997482631802]` ns (width 365,940,951 ns); terminal host UTC is `1790558299462723493` ns. The terminal-to-first-bracket interval is 301.980091691--302.346032642 s, but that host interval does not extend the 300 s source-counter evidence. | Full raw source remains under `/srv/bulk/leo`; the retained inventory is `../ds9/location-source-inventory/source-inventory.json`. Native inputs already exist as `../tracking/projection-inputs.jsonl` (24,681 rows), `../tracking/candidates.tsv` (11,747 data rows), and `../ds9/complete-scan-e1/candidates.tsv` (11,971 data rows). `full-span-paced-analysis.json` records an available event span of **299.8017789333333 s** and explicitly records `full_600_second_evidence_span_exercised=false`. No further export can turn this session into 600 s of evidence. |
| `scan-hop-8b1c5110e2fad852` (longest finalized manifest found) | `/srv/bulk/leo/scanner-adaptive-recordings/scan-hop-8b1c5110e2fad852/manifest.json`; file SHA-256 `efb32695b2741c14d8e9b0e0eac92cb1ec8f3f83ed7eb3919f112d15d93d273b` | First/final counters `309899096690` / `310649414764` at 2,500,000 sample/s: **300.1272296 s**. Timing is qualified and source span attested; 2,359 visits completed. The first-sample UTC bracket is `[1789978335932228666, 1789978335933750190]` ns (width 1,521,524 ns); terminal host UTC is `1789978637412383616` ns. The terminal-to-first-bracket interval is 301.478633426--301.480154950 s and likewise does not extend the counter span. | Persisted per-visit analysis is at `/srv/bulk/leo/scanner-adaptive-analysis/scan-hop-8b1c5110e2fad852/78a3a6d3852b3d22203eae5619d0fd28ef2a2435a8c678774e4ca67dfc81d676/`: 2,359 visit products, 37,744 integer candidates, 23,975 fractional candidates and 3,073 passing fractional candidates. No native projection/event fixture is currently exported for this session. Exporting one would exercise only about 300.13 s, so it would still not close the gate. |

The nearest retained live result is
`../live-qualification/admission100-nice19-continuous-receipt.json`: its wall
elapsed time is 586.3898083278909 seconds and it records four queue drops.  It
is scanner telemetry rather than a persisted, lossless candidate/event corpus,
and it is shorter than 600 seconds.  It is not qualifying evidence.

## Bounded search scope

- Read the retained native deployment reports, manifests and run documentation,
  including the DS9 source inventory, complete-scan exports, application paced
  receipts and live-qualification receipts.
- Inspected manifest metadata for
  `/srv/bulk/leo/scanner-adaptive-recordings/*/manifest.json`: 2,303 session
  directories were present, 2,205 had a parseable finalized manifest, none had
  a source-counter span of 590 seconds or more, and the maximum was the
  300.1272296-second session above.
- Checked the corresponding persisted analysis directories for DS9 and the
  maximum-duration session.  No IQ payload was copied or modified.
- The other 98 recording-store directories did not have a parseable finalized
  `manifest.json` in this bounded scan.  They remain unassessed recovery,
  interrupted, or otherwise incomplete entries.  No broad recursive search of
  QNAP or unrelated archives was performed, so this report does not assert
  absence outside the stated scope.

## Evidence still required

The gate requires one genuine, continuous session with at least 600 seconds of
qualified source-counter coverage, a counter-to-UTC bracket that remains valid
for the session, lossless visit/detector accounting, and enough candidate events
across the boundary to observe retention and expiry.  Once such a recording
exists, its manifest and per-visit analysis must be exported to the existing
recorded-event format with original counters, UTC brackets, target metadata,
candidate identifiers, and detector outcomes preserved.  This is missing
external evidence; the 600-second target must not be weakened and existing
sessions must not be concatenated.

This inventory performed no RF collection, hardware access, build, or mutation
under `/mnt/qnap01` or `/srv/bulk/leo`.
