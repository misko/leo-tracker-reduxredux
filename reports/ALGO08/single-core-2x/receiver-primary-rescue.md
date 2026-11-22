# Primary rescue from skipped historical residuals

The causal rescue recovered the single missing primary selection on DS30-0016 and reproduced **all 440 deployed selections**. It required **200 extra full native queries**. The southern simulation kept all **456 selections** and made **54 extra full queries** without finding a historical residual. Charging these calls against the existing measured native prefixes makes the rescue slower than the deployed receiver on both prefixes. [Ledger receipts](measurements/primary-residual-rescue.json)

## Frozen policy

The one-in-three foreground schedule and its eight-device-second activity extension remain unchanged. When a verified primary has fewer than three released continuation votes, the scheduler checks the same-lane history. It treats unresolved skipped visits as possible donors and uses the existing slope and age enclosure for known visits. If three votes remain possible, it queries the newest unresolved visit first. It repeats the vote and possibility checks after each read. It stops at three votes or when the remaining history cannot supply them.

Each historical query requests the original complete native factor call. Its primary must match the earlier primary-only measurement. Its verified residual, if present, enriches that visit's existing continuation slot. A rank-one-only historical result can also supply a donor. The released continuation selects the current factor, and the rescue leaves earlier published rows and the foreground activity clock intact. The policy uses only verified factors, same-lane RF metadata and device counters. It was committed as `ef491ec9b` before either ledger replay. [Policy](../../../tools/pipeline_eval/variants/experimental/residual_rescue.py) · [Released votes](../../../tools/pipeline_eval/variants/carrier_continuation.py)

The unresolved queue holds at most 64 lanes. Rows age out at eight seconds or when the original twelve-entry history evicts them. FIFO pressure discards the oldest unresolved row without a native call. Both antennas may refer to the same immutable stereo window. The ledger replay counts retained windows and full historical calls. It opens no I/Q and retains no actual waveform bytes.

## Selection and lifetime

| Saved case | Lane rows | Selections, deployed / conditional / rescue | Extra historical full calls | Historical stereo windows | Peak retained stereo payload |
| --- | ---: | ---: | ---: | ---: | ---: |
| Physical DS30-0016 | 1,426 | 440 / 439 / 440 | 200 | 188 | 80.0 MB |
| Southern simulation | 2,400 | 456 / 456 / 456 | 54 | 28 | 40.0 MB |

The rescued physical row is visit 68 on receiver 1. Its direct trigger requests visit 60, which returns rank one ahead of rank zero and supplies the missing vote. The physical run finds seven historical residuals in all. It preserves the 15 deployed residual selections and adds only the recovered primary relative to the conditional schedule. Both rescue outputs match their deployed ordered selection digests. The maximum resolved age is 6.38 seconds physically and exactly eight seconds in the simulation. The physical queue fills and evicts 86 unresolved lanes. The simulation peaks at 50 lanes.

Keeping the I/Q resident would let these backfills reuse the original decoded window without an extra archive read. A design that rereads the archive would need at least 300.8 MB and 44.8 MB of decoded revisit payload respectively, before accounting for compressed chunk boundaries and integrity checks. The payload peaks count retained windows only. The active capture, decoder storage and allocation overhead have separate costs.

## Native cost

The physical rescue replaces 354 full requests with primary-only requests that are never backfilled. It makes 1,072 full and 554 primary-only calls, against 1,426 full calls deployed. The simulation makes 854 full and 1,600 primary-only calls, against 2,400 full calls deployed. The extra calls are charged with the matching per-lane full native clocks in the recorded ledger. The five Python replays reverse arm order and measure the incremental planner CPU independently.

| Saved case | Added full-call CPU vs conditional | Added planner CPU vs conditional | Total added modeled CPU vs conditional | Optimistic CPU saving ceiling vs deployed |
| --- | ---: | ---: | ---: | ---: |
| DS30-0016 | 555.7 ms | 5.8 ms | 561.5 ms | 1,003.0 ms |
| Southern simulation | 176.4 ms | 6.6 ms | 183.1 ms | 4,059.9 ms |

The ceiling credits each skipped foreground call's entire original full-call CPU as removable and then charges historical calls and planner overhead. The raw scout and primary verification remain necessary, so the ceiling cannot establish actual full-record savings. The earlier matched raw-prefix receipts supply the measured cost of the foreground split. Subtracting the matching ledger clocks for cold-start backfills gives the following estimate. Those clocks come from a separate measurement. Retaining, copying or rereading I/Q could add further runtime.

| Previously measured native prefix | Historical full calls | Conditional native CPU saving | Historical calls and additional planner CPU | Estimated rescue CPU vs deployed |
| --- | ---: | ---: | ---: | ---: |
| DS30-0016, 128 scheduled visits | 32 | 91.7–106.7 ms | 128.4 ms | 21.7–36.7 ms slower |
| South, 40 scheduled visits | 8 | 17.6–18.8 ms | 29.0 ms | 10.2–11.4 ms slower |

The replay reproduces every cold prefix selection and historical query when stopped at the prefix boundary. The evaluated policy stays offline. It has no archive-to-publication, position or live buffer-lifetime measurement. [Existing native prefix measurements](receiver-residual-schedule.md#native-cpu-on-chronological-raw-prefixes)

## Reproduce

The runner verifies each ledger against its original selected detection document and the matched native-prefix receipt. Fifteen targeted tests passed, including newest-first resolution, exact donor-slot replacement, a residual-only historical factor, independent antennas, FIFO eviction and time expiry.

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_pairs="$algo08_work/integration-shared/pairs"

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}
algo08_lock "$algo08_python" reports/ALGO08/single-core-2x/residual_rescue_trial.py \
  --case DS30-0016 "$algo08_work/ledger-DS30-0016.json.gz" \
    "$algo08_pairs"/DS30-0016/candidate/fast-scan-automatic-work/*/detections.json \
    "$algo08_work/residual-native-DS30-0016.json" \
  --case south "$algo08_work/ledger-south.json.gz" \
    "$algo08_pairs"/south/candidate/fast-scan-automatic-work/*/detections.json \
    "$algo08_work/residual-native-south.json"
algo08_lock "$algo08_python" -m pytest -q tests/pipeline_eval/test_residual_rescue.py \
  tests/pipeline_eval/test_residual_schedule.py tests/pipeline_eval/test_deferred_continuation.py
~~~
