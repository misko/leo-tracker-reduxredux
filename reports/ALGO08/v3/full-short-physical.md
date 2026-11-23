# Combined full-short receiver on one DS30-0016 raw recording

The candidate passed the prespecified two-arm position screen on the sealed physical recording. Horizontal error fell from **1.644 to 0.710 km** with `c = 0` and from **1.661 to 0.861 km** with fitted `c`. Both arms published a 179-node grid and all eight figures. Launch through exit took **14.521 s for stock and 9.472 s for the candidate**, with total CPU of **11.347 and 9.442 s**. Stock read an uncached input and the candidate read the same input after all compressed-member pages had become resident. The elapsed pair did not reach 2×, and the cache order prevents attributing the measured elapsed difference to the algorithm. [Frozen protocol](full-short-physical-protocol.md) · [Sealed raw pair and post-publication score](measurements/full-short-DS30-0016-raw.json.gz)

## The saved exterior gate

The all-times long-primary south-far proxy passed before physical acquisition. Its original displaced 25 km offer, exact selected native packet, quadratic graph and causal archive were bound to the receipt. Both receivers independently picked **(-62.5, 0.0) km** with 50 km clearance, zero separation, and exterior gains of **1.1552 and 1.0306**. The prepared archive handoff served one request. The published decision withheld with `both_receivers_support_far_exterior` before catalogue ranking or numerical fitting, after **96 probes** and **1.561 CPU s** in the proof. The complete saved check took **3.801 CPU s**. This gate used the long-primary proxy, so it establishes the early regional route on that signed proxy. [Saved gate receipt](measurements/full-short-south-far-gate.json)

## The raw pair

Both arms ran through normal installed-v3 compressed and decoded validation against the same physical inventory, offer and pre-RF orbit archive. All **808 issued visits**, **713 admitted stereo pairs**, **95 original exclusions**, and **1,426 ordered probe metadata rows** agreed. Each admitted antenna issued exactly one native call. The candidate uses the callback from cold-prefix commit `ccb13fbc4`. Its full-anchor slot is index zero modulo eight within each RF, channel and pilot-edge stream. The detector recipe binds both DSOs, the callback source, the aperture lengths, assignment rule and selection policy to a distinct analysis identity. On full-anchor visits it selects the largest verified margin with original rank as the tie-break. Each other visit runs the genuine short primary independently for both antennas. [Raw receiver binding](full_short_raw.py) · [Short-primary build](mixed-aperture-receiver.md)

| Measured stage or result | Installed stock | Combined candidate |
|---|---:|---:|
| Launch through exit, elapsed / CPU s | 14.521 / 11.347 | 9.472 / 9.442 |
| Publication function, elapsed / CPU s | 13.104 / 9.932 | 8.005 / 7.980 |
| Authenticated acquisition, elapsed / CPU s | 8.251 / 5.111 | 3.426 / 3.426 |
| Native receiver, CPU s | 3.185 | 1.676 |
| Full calls / 12 ms calls | 1,426 / 0 | 186 / 1,240 |
| Selected factors | 440 | 475 |
| Solve and grid, CPU s | 3.356 | 3.026 |
| Horizontal error, zero / fitted `c`, km | 1.644 / 1.661 | 0.710 / 0.861 |
| RF RMS, zero / fitted `c`, Hz | 109.375 / 109.479 | 108.253 / 108.046 |
| Owners per arm | 109 | 125 |

The candidate retained the same NORAD and role on all **105 shared owners** per arm. Four stock owners were absent and twenty were new. Each standard publication produced all eight decodable PNGs with the matching expected dimensions. The two publications' PNG bytes and pixels differ alongside their different measured support. The candidate grid sampled all 179 points and had zero endpoint objective-replay error for both arms. The full-catalogue shortlist held two usable finalists and completed both. The signed phase-history update qualified. The candidate's regional proof made 24 probes, used the prepared catalogue, and spent **0.387 CPU s** before continuing to the original fit route. [Detailed support, decisions, and plot comparisons](measurements/full-short-DS30-0016-raw.json.gz)

The 13 compressed members had **0 / 242,128 pages** resident before stock and **242,128 / 242,128** before the candidate. Residency stayed complete after the candidate. Stock issued 1,941,616 input blocks and the candidate eight. No cache advice or eviction was used. Native receiver CPU fell **47.4%**, while whole-process CPU fell **16.8%**. These are one recording's measured differences. The calculation in `ccb13fbc4` that motivated the pilot transferred the fastest dense-prefix detector rate and saved-solve cost to the historical 55-file corpus. Those projected ratios were 0.485 median and 0.504 summed with setup. This physical pair supplies no measured cohort throughput.

## Reproduce the entry point and score

The archived raw pair is retained in `/var/tmp/leo-full-short-DS30-0016-pair` with immediate child-process clock files, separate installed/candidate detections and terminal files, selected owner rows, and both publication stores. Run the scorer against those files without reading waveform payloads. The `gate` command takes only the saved south-far proxy. The `run` command uses the checked gate and a new output root, with the original certified detector and archive-readable account under one uninterrupted Gauss lock. The main paired entry delegates to `joint_publication.py` with the optimized route and early regional check. An earlier startup precheck failed before it created a stock publication directory or read data. The sealed measurement includes the single successful raw pair. Thirty component and publication tests passed. [Raw-pair entry](full_short_physical.py) · [Read-only validator](full_short_physical_score.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
gate=/var/tmp/leo-full-short-DS30-0016-far-gate.json
out=/var/tmp/leo-full-short-DS30-0016-pair
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
gauss() {
  sudo -n -u leo flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 env \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss env PYTHONPATH="$here:$payload:$release/src:$release:$PWD" \
  "$release/venv/bin/python" -BPs "$here/full_short_physical.py" gate "$fresh_gate"
gauss env PYTHONPATH="$here:$PWD:$PWD/src:$release/src:$release" \
  "$release/venv/bin/python" -BPs "$here/full_short_physical.py" run "$fresh_output" "$fresh_gate" "$short"
gauss env PYTHONPATH="$here:$PWD:$PWD/src:$release/src:$release" \
  "$release/venv/bin/python" -BPs "$here/full_short_physical_score.py" "$out" "$gate" "$fresh_score"
```
