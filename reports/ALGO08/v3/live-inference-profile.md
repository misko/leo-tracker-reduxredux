# Dense live solver cost and visibility-first geographic proof

The optimized full-catalogue solver took **33.677 CPU seconds and 33.728 elapsed seconds** from the complete saved DS30-0008 detections through both numerical grids. The same-input historical installed solve took **60.966 CPU seconds and 61.015 elapsed seconds**. The live route includes the early regional proof, which used **10.040 CPU seconds** despite reuse of the prepared catalogue. The earlier 23.482 CPU second race comparison measured a route without the first-pass proof. Removing the measured proof time arithmetically leaves 23.637 seconds for the other live work. [Frozen protocol](live-inference-profile-protocol.md) · [Earlier race](cold-finalist-race.md) · [Numeric summary](measurements/live-inference-profile-summary.json)

| Complete saved numerical solve | CPU s | Elapsed s | Early proof CPU s | Horizontal error, zero / fitted `c`, km | RF RMS, zero / fitted `c`, Hz |
|---|---:|---:|---:|---:|---:|
| Installed v3, historical | 60.966 | 61.015 | — | 1.639 / 1.512 | 129.703 / 129.663 |
| Live, released dense proof | 33.677 | 33.728 | 10.040 | 1.088 / 1.079 | 128.822 / 128.753 |
| Live, visibility-first prototype | 43.984 | 44.024 | 19.817 | 1.088 / 1.079 | 128.822 / 128.753 |

The complete original detector packet, fixed causal archive, offered region and original track configuration isolate the change to the solver. The saved clock includes track preparation, inference, regional checks, and standard numerical evidence. It excludes saved authentication, Python startup, rendering, raw reads and publication-store writes. The installed row comes from a separately timed, sealed saved replay with identical packet, region and archive. These three rows are numerical solver comparisons on one physical development recording. [Archived installed comparison](full-family-amortized.md) · [Sealed profile and paired runs](measurements/live-inference-profile.json.gz)

## Profile of the live route

One instrumented solve took 39.602 CPU seconds. Track and causal preparation used 8.070 seconds, including 4.419 for the graph. The regional proof used 8.995 seconds, including 2.151 to prepare orbit geometry and 6.833 to evaluate 25 probe locations. The cold start used 8.215 seconds, including 5.320 for full-catalogue rank and 2.600 for the finalist race. The full pre-evidence proposal used 15.014, the signed update 0.759 and standard evidence 6.636. These are inclusive CPU times and the nested stages overlap. The instrumented run supplies attribution. The unprofiled pair supplies measured performance. [Profile rows and timings](measurements/live-inference-profile-summary.json)

## Exact proof, slower projection

All causal orbits keep their original prior weight. The new kernel computes every original range and the vertical sign first. A candidate contributes to a track only when all its original points meet the released elevation threshold. For those candidates the kernel gathers the corresponding orbit geometry and computes the original Doppler and phase derivative before applying the same likelihood and reduction. The probe lattice, order, scores, owner tie order and early terminal gate are the released ones. A failed sparse projection invokes the dense scorer for that probe. An unmatched runtime keeps the dense implementation. [Visibility-first kernel](visible_orbit_proof.py)

The candidate evaluated 71.659 million eligible track cells, **91.1%** of the 78.623 million cells of the dense probe-by-family-by-time projection. The sparse count includes repeats when tracks share an event time. The remaining work was too dense for repeated indexed gathers. The proof grew by **9.776 CPU seconds**, accounting for most of the **10.306 CPU second** increase in the complete solve. Both runs consumed 356 reduced predictive grid calls. Their evidence clocks were 5.947 and 5.903 CPU seconds. Keep the dense proof for this route.

All 25 visited probes matched exactly, including pooled and separate receiver scores, owners, and the same `inside_score` stop. The actual survey reference was 6.179 km inside the offered square. Both solves returned positions with 4,440 identical owner and role rows per arm. Each produced the same numerical path, all 179 ordered grid coordinates and every score in both arms. The minima stayed at indices 0 and 1 for zero and fitted `c`, respectively. Both endpoint objective-replay differences were zero, with zero fallbacks or withholdings. The geographic comparison covers this one containing offer. [Exact pair acceptance](measurements/live-inference-profile-summary.json)

## Reproduce

Run the same complete saved packet under the shared Gauss lock. The profile separately captures causal, fitting and evidence attribution. The two unprofiled processes both audit the probe scores. The scorer opens the survey reference after all three outputs have sealed. The first launcher attempt stopped at an import-order precheck before entering the solver. The archived profile is from the corrected import order in `bfa0b5262` and the scored pair uses the checked-in runtime source digest. Seventy-four component and adjacent tests passed. [Saved runner](live_inference_profile.py) · [Scorer](live_inference_profile_score.py) · [Component tests](../../../tests/pipeline_eval/test_visible_orbit_proof.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
out=$(mktemp -d /var/tmp/live-inference.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 100s \
    env OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
for mode in profile control visible; do
  gauss env PYTHONPATH="$here:$payload:$release/src:$release:$PWD" \
    "$release/venv/bin/python" -BPs "$here/live_inference_profile.py" "$mode" "$out/$mode.json" || exit
done
gauss env PYTHONPATH="$here:$PWD/src:$PWD" \
  "$release/venv/bin/python" -BPs "$here/live_inference_profile_score.py" "$out"
```
