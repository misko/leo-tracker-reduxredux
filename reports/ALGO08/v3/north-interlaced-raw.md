# Northern raw-to-web transfer of the primary interlaced receiver

The primary interlaced receiver returned both fixes, but the northern transfer failed the frozen 250 m tolerance. Fixed-zero horizontal error rose from **106 m to 749 m**, a **643 m** increase. Fitted-(c) error fell from 141 m to 118 m. Both frequency-fit residuals increased. The common acquisition-lock to publication-report interval fell from **14.758 s to 12.636 s**, or **1.17×** over that file-stamped boundary. The external launch clocks and resource counts were lost during post-run validation. [Frozen protocol](north-interlaced-raw-protocol.md) · [Recovered publication and schedule receipt](measurements/north-interlaced-raw.json.gz)

## Verification and paid work

The same public northern 1,200-window tmpfs capture and causal archive entered the installed v3 launcher and the experimental wrapper, running candidate first in fresh roots. Both verified the original signed waveform input and emitted 2,400 ordered probes with identical RF, time and stream metadata. Both raw authorities are `da1704254f8f5aa7ab83f5ff34a945075cb5144d367f720a264ecf81ea62703c`. The installed baseline also reproduced the previous sealed v3 coordinates and RF residuals on the same offer.

The candidate paid for 800 original signed native two-scan antenna calls on 800 distinct stereo buffers. Its authenticated index prepass verified eight RF streams with 150 admitted visits each and built the primary mask before extracting any waveform factors. Every detector call used the installed v3 receiver and pinned waveform reference. The raw outputs contained 263 verified native factors at paid lanes, from which the highest-margin rule selected 244 factors including ten rank-1 factors. The installed receiver selected 456 factors with its released continuation, all at primary rank. Applying the earlier frozen `slots` function to the newly published metadata independently recovered exactly the candidate's 800 measured slots. Every probe also matched the recorded native maximum-margin choice or the expected empty result.

The candidate passed those observations to the six-point quadratic graph and the existing signed joint solver. It used the standardized signed correction and completed through the normal publication surface with 138 conditional observations per arm. Both arms of the pair published a full 137-point grid and position path. The audit independently decoded all eight PNGs in each publication and checked their encoded and RGBA digests. Candidate objective replay differed by zero in both fits. Scoring opened the public location only after the native schedule and publication receipts were sealed.

| Calibration | Installed v3 horizontal error | Interlaced horizontal error | Installed RF RMS | Interlaced RF RMS |
|---|---:|---:|---:|---:|
| Fixed zero | 106 m | 749 m | 5.406 Hz | 8.323 Hz |
| Fitted | 141 m | 118 m | 5.167 Hz | 6.581 Hz |

The complementary mask on the earlier DS30-0016 saved replay had already failed the sensitivity requirement, adding 2.146 km fixed-zero and 2.024 km fitted error versus that complete receiver. The primary mask passed DS30-0016 and the earlier southern development checks recorded in commit `81cdf6503`. The northern result adds a separate failure of the primary configuration. The far-offer replay was omitted after the containing transfer failed. The recordings and offers are development evidence.

## Recovered clocks and their scope

Both raw children exited successfully. Post-run audit used a newer evidence-reader keyword unavailable in the pinned storage API. It failed before writing the parent's in-memory launch and process resource measurements. The artifacts, schedule, candidate internal timings and file timestamps survived. The runner now writes each arm's external timing and resource counts as soon as the child exits, before receipt or artifact validation. The recovered figures below are differences between the same files' modification times on each side. They exclude launch, preflight and final child exit and do not establish a raw-to-web launch speedup.

| Common file boundary | Installed v3 | Interlaced |
|---|---:|---:|
| Acquisition owner lock to detections file | 7.360 s | 4.908 s |
| Detections file to terminal | 5.661 s | 6.031 s |
| Terminal to standard publication report | 1.737 s | 1.697 s |
| Acquisition owner lock to standard publication report | 14.758 s | 12.636 s |

The candidate's independent process timer records **12.713 s elapsed and 12.689 s CPU** inside its publication call. The solver used 6.015 s elapsed and 6.015 s CPU. The separately logged authenticated-index plan used 0.233 CPU s before that internal publication clock, and the paid native callbacks used 1.681 CPU s within it. No matching stock process CPU or input-block count survived. The raw pair was not repeated.

## Reproduce

Run from the trial worktree. The reference scheduler should be materialized from its committed bytes, SHA-256 `334f9795489d9a85e535eb848623637cd59ff18903b9cb8e478c6ac4c30c6db1`. The runner checks the previous offer, manifest, archive, stock launcher and the native receiver independently. Use a fresh output directory. The raw command runs exactly one pair. The separate audit command reads an existing pair's published artifacts and requires a fresh audit directory. Twenty-one focused tests passed. [Runner](north_interlaced_raw.py) · [Schedule and native margin tests](../../../tests/pipeline_eval/test_north_interlaced_raw.py)

```bash
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
git show 81cdf6503:reports/ALGO08/v3/interlaced_lanes.py > "$reference_schedule"
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout --signal=INT 100s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$here:$PWD:$payload:$release/src:$release" "$@"
}
lock "$release/venv/bin/python" -BPs "$here/north_interlaced_raw.py" pair "$out" "$reference_schedule"
lock "$release/venv/bin/python" -BPs "$here/north_interlaced_raw.py" audit-existing \
  "$out" "$reference_schedule" "$audit_out"
lock "$tree/.venv/bin/python" -BPs -m pytest -q tests/pipeline_eval/test_north_interlaced_raw.py \
  tests/pipeline_eval/test_joint_publication.py
```
