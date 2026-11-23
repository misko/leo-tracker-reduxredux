# Directed searches for frozen paid-anchor donor lanes

The causal orbit query matched **all 96 verified factors** on the southern donor slots within 400 Hz and one sample in a saved-ledger backtest. Both the ideal directed and full-search controls recovered 60 original owners and produced the same position. The southern fixed-zero error still exceeded the 250 m tolerance. On physical DS30-0016, two queries matched **11 of 135 verified factors** at the tight tolerance. Full search on the same slots provided 69 usable factors, and both second fits worsened the unusually accurate first sparse estimate. This was a saved experiment using the older archived receiver's pre-continuation factors. [Frozen protocol](directed-donor-protocol.md) · [Complete numeric result](measurements/directed-donor.json)

## From paid anchors to two native queries

The 129 physical and 102 southern lane slots were frozen from the blind first paid solver's labels. Both predictions use its two most recent strictly preceding paid measurements on the same antenna, channel, edge and tuned RF, at most eight seconds earlier. The first linearly extrapolates signed baseband CFO and wrapped absolute frame arrival. The second subtracts nominal Doppler and propagation delay at the supplied region center, extrapolates the measured residuals and restores the target's nominal values. Both preserve the physical 750 Hz frame cadence. The window-relative native phase maps to the receiver's 13,333-sample circle. Forecast files seal the output before any join with held factors. Projection uses the supplied region and causal TLEs. [Proposal and matching code](directed_donor.py) · [Frozen slots and paid-plan bindings](measurements/quadratic-support-slots.json)

The original 25 km square and capture-era clock bracket bind each forecast. The causal orbit reads use TLEs collected and epoch-dated before the bracket. They use the bracket midpoint and original antenna time counters. DS30-0016's bracket width was 178.04 ms and the southern width was 10.00 ms. After subtracting and restoring the anchor-relative orbit model, moving the second query from the offered center to the four corners changes its p95 predicted CFO and phase by **10.30 Hz and 0.323 sample** on physical, and **11.66 Hz and 0.672 sample** on south. That quantifies sensitivity within these offers. No corner queries were issued. [Orbit dates, slot digests and chart sensitivity](measurements/directed-donor.json)

## Verified-factor backtest

| Save | Frozen lanes / nonempty / saved factors | One secant, tight / loose matches | One orbit-corrected, tight / loose matches | Cap two, tight / loose matches | Cap two, signed-only at 400 / 2,250 Hz |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 129 / 69 / 135 | 11 / 35 | 0 / 30 | **11 / 35** | 63 / 69 |
| South containing | 102 / 96 / 96 | 0 / 8 | 96 / 96 | **96 / 96** | 96 / 96 |

Tight means at most 400 Hz and one wrapped sample, matching the previous native timing/refinement study's nominal seed perturbation envelope. Loose means at most 2,250 Hz and six samples. The backtest maximizes one-to-one unique matches before minimizing mismatch. Each lane has at most one query for each model. A slot with two eligible queries cannot count the same saved factor twice. Of the physical ledger's 135 factors, 69 are primaries and 66 are signed residuals. Every match was a primary. The cap-two plan issued 258 physical and 204 southern queries, including on 60 and six empty saved lanes. The additional model provides all southern reach and adds no physical joint matches at either tolerance. The physical signed-only reach with few joint successes shows that phase was the binding constraint on this saved experiment. [Counts, residual ranks and method ablation](measurements/directed-donor.json) · [Authentic directed verifier benchmark](directed-verifier.md)

The full-search availability control adds the highest-margin saved verified factor on every nonempty frozen lane. The ideal directed control applies the same selection among the tight cap-two matches. The latter gives the native verifier credit for producing the exact saved factor when the prediction matches. Actual raw confirmation, false detections, refined waveform output and cancellation remain unmeasured here. [Matched-factor and purchase code](directed_donor_trial.py)

## Second signed solve

| Save and receiver schedule | Horizontal error km, zero / fitted `c` | RF RMS Hz, zero / fitted `c` | Published owners per arm |
|---|---:|---:|---:|
| DS30-0016, exact complete control | 1.644 / 1.661 | 109.375 / 109.479 | 109 |
| DS30-0016, original one-third paid | 0.247 / 0.182 | 121.482 / 121.379 | 36 |
| DS30-0016, add 11 tight directed matches | 1.101 / 1.049 | 117.343 / 117.244 | 48 |
| DS30-0016, add 69 full-search factors | 1.659 / 1.670 | 114.032 / 113.942 | 106 |
| South, exact complete control | 0.817 / 1.101 | 6.502 / 6.392 | 266 |
| South, original one-third paid | 1.266 / 1.109 | 6.388 / 6.322 | 118 |
| South, add 96 factors by either method | 1.198 / 1.070 | 6.855 / 6.692 | 214 |

Both physical second passes meet the 250 m tolerance against the complete control. Restoring paid donor factors improves in-sample RF RMS and worsens the first sparse position on this save. The southern expanded waveforms are byte-identical. Fitting `c` reduces error on that waveform by 0.128 km and RF RMS by 0.163 Hz. Fixed-zero error improves by 68 m relative to the first sparse fit, with a remaining 381 m loss versus complete. Both southern alternatives therefore miss the paired gate. No second pass changes a satellite label on a shared first-pass owner, and none uses full solver fallback. These are replays on containing offers. The southern displaced offer was never given this containing-owner proposal. [Paired solve receipts and owner changes](measurements/directed-donor.json)

DS30-0016 has 75 complete owners on unpaid visits. Sixty-nine sit on frozen donor lanes, reach the blind full-search result and keep their original satellites. Eleven reach the tight directed result. In the south, both methods recover all 60 originally owned measurements on the donor lanes. Another 116 of 176 unpaid complete owners sit outside the plan. Exactly 50 of those belong to NORAD 65235 or 69658, families absent from the first sparse solve. The lane rule needs a separate source of nominations to reach those families. [Unpaid-ownership census](measurements/directed-donor.json) · [Original owner diagnosis](quadratic-support.md)

## Native call, storage and solver charges

| Save | First paid detector + first solver CPU s | Forecast CPU s | Cap-two projected directed CPU s | Recorded original full native CPU s at extra lanes | Second directed / full-search solver CPU s |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 1.505 + 2.968 | 2.117 | 0.164 | 0.512 | 3.006 / 3.078 |
| South | 2.128 + 3.568 | 1.530 | 0.194 | 0.518 | 3.641 / 3.715 |

The directed call projection uses authenticated, resident-receiver timings from the separate native DS30-0008 and weak benchmark. The dense positive and negative lane means were 1.081 / 0.331 ms for one query and 1.991 / 0.443 ms for two. The weak slice supplied positive timings and no independent negative lanes. Its projection borrows the dense negatives. These unit costs came from real I/Q and the original waveform verifier on those earlier slices. Transferring the dense one-query rates to actual positive and empty slot counts gives 0.094 s physical and 0.106 s south. A center-only query keeps all southern tight matches in the backtest and still requires causal projection. The full-search column is the exact original native callback CPU on the frozen lanes of each short save. [Published native unit costs](directed-verifier.md) · [Charges and alternate budgets](measurements/directed-donor.json)

Including both fits and the incurred forecast, the directed component sum is **9.759 s physical and 11.060 s south**. For full search the frozen slot list suffices, and the component sums are **8.063 and 9.929 s**. These sums omit raw file reads, service overhead and figures. The saved code parses the causal TLE archive for the forecast, and this cost exceeds the native call savings.

| Save | Requested stereo visits | I/Q retained for those visits | Original members to revisit | Compressed / decoded member bytes |
|---|---:|---:|---:|---:|
| DS30-0016 | 129 | 206.4 MB | 13 | 0.992 / 1.293 GB |
| South | 51 | 81.6 MB | 16 | 1.322 / 1.613 GB |

Only authenticated member index metadata was read. A receiver that waits for the first solver's labels must retain earlier I/Q or revisit the indicated sealed members. The table prices volumes and member counts. It supplies no cold I/O latency or end-to-end speed measurement. [Member counts and physical index witness](measurements/directed-donor-physical-members.json) · [Southern index result](measurements/directed-donor.json)

## Reproduction

Under the pinned ALGO08v3 environment, run both `forecast CASE "$out/CASE-forecast.json"` invocations first using `directed_donor_trial.py`. Then run `replay CASE "$out/CASE-forecast.json" "$out/CASE-replay.json"` for each case. Cases are `DS30-0016` and `south-containing`. With the checkout and its `src` on `PYTHONPATH`, run `directed_donor_score.py "$out" "$out/score.json" --physical-storage reports/ALGO08/v3/measurements/directed-donor-physical-members.json`. The original exact owner-map capture bytes are now bundled for postfit verification. Five focused tests passed. [Owned tests](../../../tests/pipeline_eval/test_directed_donor.py) · [Archived scoring witnesses](measurements/directed-donor-owner-witness.json.gz)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$code:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$code/directed_donor_trial.py" \
  "$stage" "$case" "$@"
```
