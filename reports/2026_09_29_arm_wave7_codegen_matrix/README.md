# Wave 7 Cortex-A9 code-generation matrix

This isolates two previously unmeasured compiler choices on the sealed Wave 7
exact histogram ranker: Thumb-2 at `-O3`, and ARM mode at `-O2` instead of
`-O3`.  Every scientific, target, LTO, and strict-math flag remains unchanged.
The builds include the histogram test and all inherited component binaries.

`python3 build.py` creates immutable `builds-thumb` and `builds-o2` artifacts
with exact source hashes and compiler commands.  These are cross-build
candidates only.  Host timing cannot represent ARM-versus-Thumb encoding, and
neither variant has an ARM performance claim until the same saved ARM panel is
run.  Candidate parity must be checked against Wave 7 `arm4-v2` when timed.

Completed physical CPU0 checks (`run_arm.py`) retain all 182 candidate objects
and 119/119 standard hits for both variants. Thumb-2 takes 834.190 ms/dwell;
`-O2` takes 900.058 ms/dwell; the matched histogram control is 831.795 ms.
Ten component suites pass for each variant on ARM. Neither improves runtime.
These are four saved 2.5 MS/s dwells, with capture and file loading excluded.
