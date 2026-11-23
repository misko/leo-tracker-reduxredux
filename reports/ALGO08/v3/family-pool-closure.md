# Adding missing families to the representative catalogue

One family addition resolved the outside-pool check on each containing offer. The dense route returned a complete **30.223 CPU-second** ordinary paired fix. That was faster than the full signed control at 39.045 s and the first-pool fallback at 42.744 s. It missed the 24 s target and increased both horizontal errors by more than 0.25 km versus full signed. The southern containing result matched both full controls, and the displaced offer withheld directly. The frozen trial stopped with these three saved offers. [Protocol](family-pool-closure-protocol.md) · [Numeric summary](measurements/family-pool-closure-summary.json) · [Sealed receipts and owner rows](measurements/family-pool-closure.json.gz)

| Offer | Installed CPU (s) | Full signed CPU (s) | First pool CPU (s) | Iterative pool CPU / elapsed (s) | Original evidence points | Terminal path |
|---|---:|---:|---:|---:|---:|---|
| Dense DS30-0008 | 60.966 | 39.045 | 42.744 | 30.223 / 30.328 | 179 | Ordinary paired fix |
| South containing | 4.620 | 3.878 | 4.754 | 3.817 / 3.829 | 137 | Signed paired fix |
| South displaced | 6.400 | 6.794 | 6.866 | 6.931 / 6.954 | — | Exterior withholding |

All three runs completed without a full-route fallback. Both returned positions completed their real grids and replayed the exact objectives with zero discrepancy in both arms. On dense, causal signed qualification succeeded and its original fitted-calibration check rejected one predictive track, `SCAN-RX1-CH5-T015-RF11709687500.000000`. The original policy retained the qualified ordinary pair. The signed refit still cost 2.310 CPU s through qualification and evaluation. The southern containing and displaced runs both accepted the signed adjustment. The latter withheld under the original `both_receivers_support_far_exterior` check.

| Offer and mode | \(c=0\) error (km) | Fitted \(c\) error (km) | \(c=0\) RF RMS (Hz) | Fitted \(c\) RF RMS (Hz) |
|---|---:|---:|---:|---:|
| Dense installed | 1.638978 | 1.511956 | 129.703040 | 129.662931 |
| Dense full signed | 1.086273 | 1.079543 | 128.821374 | 128.753307 |
| Dense iterative pool, returned ordinary pair | 1.463735 | 1.505753 | 129.457118 | 129.443925 |
| South containing, all full controls and iterative pool | 0.816789 | 1.101409 | 6.502299 | 6.391940 |

Dense position error fell by 0.175243 and 0.006203 km versus installed v3. It rose by 0.377462 and 0.426210 km versus full signed, exceeding the prespecified tolerance. The dense route published 3,381 curved and 863 predictive observations per arm. Of 4,149 observations shared with either full control, 197 had a changed satellite and none changed role. Relative to signed full, 291 observations were absent and 95 were added. The southern containing fix preserved all 266 observations and their owners and roles. The direct displaced withhold produced no plotted positions or associated rows.

## What changed after admission

Dense began with 47 families and admitted NORAD 63476 after the full-catalogue check found it compatible on two receiver 2, channel 5 tracks. The 48-family rerank selected it on three tracks. The exact refined cold location moved from \((5.335,-6.719)\) km to \((5.234,-7.709)\) km east and north within the offer. The next full-catalogue check found no compatible outside winner at that state. The final dense result retained 20 conditional observations per arm for the admitted family, the same count as full signed. South containing widened from 20 to 21 families and selected the admitted NORAD 65444 on both nominated receiver tracks. Its second check also found no compatible outside winner. The initial 20-family roster sufficed for the distant offer.

The ranked signatures changed across every containing rerank, so neither trial reused a zero-reference objective or an exact finalist. The immutable nominal projection cache reused 995 family rows on dense, including repeated anchors within each rank. It projected only five additional anchor rows when the roster widened and retained 22.41 MiB. The first-round exact top-two objective values on all three offers reproduced those of the first-pool experiment. Matching the full fixed-state guard after the rerank established closure of that test at the refined state. The different dense assignments, rejected signed refit and error deltas show what remained outside that claim.

| Dense CPU component | Iterative pool (s) | Full signed (s) |
|---|---:|---:|
| Cold context, pool, rank, refinement and full checks | 7.194 | 13.962 |
| Initial exact gate | 2.289 | 2.340 |
| Curved salvage, including rescan | 5.873 | 5.053 |
| Predictive nomination | 2.257 | 2.433 |
| Ordinary two-arm fit | 0.901 | 0.670 |
| Signed qualification and attempted refit | 2.310 | 2.345 |
| Original numerical evidence | 5.926 | 6.511 |

The dense rerank, exact finalist and full check alone cost 1.808, 1.104 and 0.257 CPU s on the second round. Curved salvage processed 49 tracks versus 32 on full signed. The pool tried 647 inside-shortlist candidates. It rescanned 36 tracks, evaluating 654 outside candidates and skipping 236 entries. The outside tests cost 1.978 CPU s. Even removing all measured dense salvage would leave about **24.350 CPU s** under the same surrounding work. That counterfactual ignores the support supplied by salvage and only prices the completed route. On the distant offer, the candidate rescanned eight of ten salvage tracks, tried 218 outside and 52 inside candidates, and skipped 50. Its exterior check alone used 2.948 CPU s.

## Reproduce

The runner reused the original saved detections, complete Graph and supplied offer in each case. The independently sealed stock, full signed and first-pool controls used the same causal inputs. The measured boundary includes all work from saved detections through full numerical evidence or withholding. Position scoring used the held reference after the three candidate receipts sealed. Waveform acquisition and PNG encoding are outside these clocks.

```bash
runner=reports/ALGO08/v3/representative_family_pool_trial.py
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/family-pool-closure.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 125s \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
for case in DS30-0008 south-containing south-far; do
  gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release" \
    "$release/venv/bin/python" -BPs "$runner" run "$case" "$out/$case.json" --closure || exit
done
gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src" \
  "$release/venv/bin/python" -BPs "$runner" score "$out" "$out/summary.json" "$out/full.json.gz"
```
