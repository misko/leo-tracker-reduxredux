# Frozen residual schedule on two 192-visit prefixes

The unchanged conditional schedule saved **11.9–14.5%** of native factor-call CPU on the first 192 scheduled DS30-0374 visits and **18.0–20.1%** on the first 192 visits of the public northern simulation. It preserved all **78** and **76** ordered selections, respectively, with empty continuation histories at the start of each arm. The conditional receiver removed three verified residual factors on the physical prefix and eight on the simulated prefix. The measurements cover these prefixes and do not establish final position accuracy. [Receipts](measurements/residual-prefix-192.json)

## Matched receiver calls

Both arms use the exact fractional-batch kernel. The full-search control executes the original two-scan entry. The conditional arm invokes the original entry whenever the frozen per-lane schedule requests a residual. Its primary-only entry skips cancellation and residual detection while keeping the original primary verification. The rule requests residuals at admitted opportunities 1, 4, 7 and so on, and on every opportunity through eight device seconds after an observed verified residual. Each observed lane visit, including empty results, advances that arm's released continuation history independently. [Frozen schedule](receiver-residual-schedule.md) · [Fractional kernel](receiver-fractional-batch.md)

Both readers start at visit zero and stop after exactly 192 scheduled stereo windows. The physical capture rejects 61 windows under the released admission check. The northern simulation admits all 192. Input hashes cover every scheduled visit, including exclusions. The trial checks the conditional build's full and primary-only entries separately on every admitted lane before the timed calls. Full ordered factors and every retained primary field agree byte for byte with the control.

| Prefix | Scheduled / admitted stereo visits | Native factor calls, both arms | Residual requests, control → conditional | Actual residual scout calls, control → conditional | Actual residual scouts avoided |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0374, upper edge | 192 / 131 | 262 | 262 → 134 | 111 → 65 | 46 (41.4%) |
| Northern simulation, lower edge | 192 / 192 | 384 | 384 → 134 | 127 → 41 | 86 (67.7%) |

The physical schedule skips 128 requests (48.9%) and the simulation skips 250 (65.1%). A separate instrumented replay counts the scouts that actually run. The raw scout may reject a lane before it reaches cancellation and residual discovery. The physical conditional arm requests 92 sentinels and 42 activity extensions. The simulated arm requests 128 sentinels and six activity extensions.

| Prefix and first arm | Full-search native CPU (s) | Conditional native CPU (s) | Saved native CPU (s) | Saved native CPU |
| --- | ---: | ---: | ---: | ---: |
| DS30-0374, conditional first | 0.84684 | 0.74600 | 0.10083 | 11.9% |
| DS30-0374, full search first | 0.87095 | 0.74480 | 0.12615 | 14.5% |
| Northern simulation, conditional first | 1.08714 | 0.89093 | 0.19621 | 18.0% |
| Northern simulation, full search first | 1.06691 | 0.85219 | 0.21472 | 20.1% |

Each repeat interleaves the two native calls on the same admitted lane. Reversing arm order gives the second repeat. The CPU clock brackets the noninstrumented native factor call after setup. The archive reader, policy, continuation and downstream stages are outside this clock.

## Factor order and cold continuation

In DS30-0374, three factor lists at receiver 1 changed from `[0,1]` to `[0]` at visits 20, 28 and 178. The returned reference list with a residual ahead of the primary was preserved. Both arms first selected at visit 42 and kept 77 primary selections and one residual selection. In the north, the eight changed factor lists comprised five `[0,1]` and two `[1,0]` becoming `[0]`, and one residual-only list becoming empty at visit 111, receiver 0. Both arms first selected at visit 40 and kept 76 primary selections. Each ordered selected-probe digest is the same across arms and across both timed orders and the count replay.

The earlier DS30-0016 prefix lost one selected primary because its residual donor history changed. The new prefixes preserve selections despite the observed factor losses. A fixed 192-visit prefix exercises only its own cold history. Neither prefix was fitted or published. [Earlier receiver comparison](receiver-residual-schedule.md)

## Reproduce

The frozen `c5fca3e2` control builds with `--pack-stencil --batch-refine --fractional-batch`. The optional residual entry on the same kernel is SHA-256 `1b4c43dc1f2edc64ead9c4b9c0f4d724f79f623e04a13f40812a1d4bb40345a5`. The prior optional 950c build also rebuilt byte for byte. All nine targeted tests passed, including the scheduled prefix boundary, original factor order and residual-only behavior.

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_assets=/opt/leo-algo08/current/assets
algo08_native=tools.pipeline_eval.variants.experimental
algo08_trial=reports/ALGO08/single-core-2x/residual_prefix_trial.py
algo08_control="$algo08_work/receiver-fractional-batch.so"
algo08_conditional="$algo08_work/receiver-residual-fractional.so"
algo08_control_profile="$algo08_work/receiver-fractional-batch-profile.so"
algo08_conditional_profile="$algo08_work/receiver-residual-fractional-profile.so"

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}
algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
  "$algo08_control" --pack-stencil --batch-refine --fractional-batch
algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
  "$algo08_control_profile" --pack-stencil --batch-refine --fractional-batch --profile
algo08_lock "$algo08_python" -m "$algo08_native.receiver_residual_build" \
  "$algo08_conditional" --fractional-batch
algo08_lock "$algo08_python" -m "$algo08_native.receiver_residual_build" \
  "$algo08_conditional_profile" --fractional-batch --profile
algo08_lock sudo -n -u leo -- env \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 \
  /opt/leo-algo08/current/venv/bin/python "$algo08_trial" \
  "$algo08_control" "$algo08_conditional" "$algo08_control_profile" "$algo08_conditional_profile" \
  "$algo08_assets" --physical-binding /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0374.json
algo08_lock "$algo08_python" "$algo08_trial" \
  "$algo08_control" "$algo08_conditional" "$algo08_control_profile" "$algo08_conditional_profile" \
  "$algo08_assets" --panel /tmp/leo-regional-qZJKBw4W/public/panel.json \
  --public-recording 0abe7b4514be674d9f5388e3
algo08_lock "$algo08_python" -m pytest -q tests/pipeline_eval/test_residual_prefix_trial.py \
  tests/pipeline_eval/test_residual_schedule.py tests/pipeline_eval/test_residual_native_build.py
~~~
