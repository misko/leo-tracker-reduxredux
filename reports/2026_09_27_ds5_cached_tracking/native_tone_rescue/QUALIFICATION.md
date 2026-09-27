# Tone-removal scorer qualification

The native scorer builds successfully with the same scientific profile and
FP32 FFTW backend as the frozen native detector. Its workspace is a separate
TG11 allocation, reusing existing allocation code (including unused rank
workspace), not a newly minimized allocation. Runtime Python template handling
uses this checkout; reference source is a pinned compilation/numerical oracle.

Generated-array engine tests establish exact scientific parity with raw guided
scoring when tone removal is not applied, at both rates and edges, both receivers,
fractional timing and the upper frame seam, using the final probe and 400 kHz
scoring frequency. Applied-tone tests use a generated pilot-plus-tone mixture at
both rates and compare against the frozen blind binary: nuisance receipts and
final exact/control/margin/tracking values match bit-for-bit when the original
integer epoch and fractional offset are supplied separately. These tests do not
assert bit parity after collapsing and renormalizing blind timing components.

Additional tests cover the qualified support tolerance, unchanged physical-CFO
rejection, caller-IQ immutability, output untouched on invalid receiver input,
one final GLRT with zero search work, and a child-process guard page immediately
after RX1's final sample. They are bounded component tests, not exhaustive
frequency/interference or concurrent-workspace qualification. Saved controls
provide the next scientific gate; validation remains unopened.

All 20 engine/controller/runner tests passed before the original experiment
freeze. A later reporting-adapter test brings the directory total to 21.

## Control result

The frozen 42 original controls completed. Native tracked and tone-removal
rescue each passed all 84 receiver policies, retaining 52 positive decisions.
The frozen raw rescue reproduced its two tone false positives. In the 12-parent,
24-execution original/swapped negative audit, native and tone-removal rescue
remained inactive on all 48 receiver checks; raw rescue reproduced three false
positives. These include two repeats of original failures and one additional
parent-RX tone. There were 48 native tone-guided calls in the original controls
and 69 in the orientation audit; nuisance removal applied to all these calls.

This resolves the measured raw-rescue tone failures on development controls.
It does not establish a rare field false-alarm rate or recorded-signal recovery.

## Reporting failure and repeat

The first diagnostic process completed 26 calls but raised TypeError during
summary construction: absent `raw_rescue_result` values were None. No scientific
receipt survived. `diagnostic_reporting_failure.json` records this terminal
failure. Its outcomes are not claimed or used to select detector parameters.

The original frozen runner remains unchanged. `run_reporting_fix.py` adapts only
summary inputs to omit the absent comparator, leaving original rows, detector
calls, membership, timing and stage gates unchanged. Its independently frozen
`reporting_fix_lock.json` pins the original inventory, control receipt, failure
record and adapter/test. New diagnostic/real receipts use
`results.reporting_fix.<stage>.json` and include the reporting lock hash in
their summary. The diagnostic repeat is an explicitly identified rerun after a
reporting failure, not independent validation.
