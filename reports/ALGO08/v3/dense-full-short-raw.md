# Full-short receiver and fused geography on archived dense DS30-0008

The complete raw candidate published in **95.429 s elapsed and 67.352 CPU s**. The archived same-recording installed ALGO08v3 control used **149.886 s elapsed and 109.103 CPU s**. The observed ratios were **0.637 elapsed and 0.617 CPU**, above the half-time target. The candidate began with 2.84% of its compressed payload pages resident, compared with 76.75% for the historical control. These clocks compare separate runs with different cache conditions. [Frozen protocol](dense-full-short-raw-protocol.md) · [Complete verification and timing receipt](measurements/dense-full-short-raw.json.gz)

The candidate passed the single-case 250 m-per-arm development screen. Horizontal error decreased from **1.639 to 1.289 km** with `c = 0` and from **1.512 to 1.138 km** with fitted `c`. RF RMS increased from **129.703 to 138.764 Hz** and from **129.663 to 138.654 Hz**, respectively. Each result uses the original user-supplied 25 km offer and the same survey reference. Support changed from 4,472 to 4,146 owners per arm, with 3,640 shared. The candidate added 506 and removed 832. On shared IDs, 142 NORAD assignments and 602 roles changed in each arm.

## Acquisition and publication

Both complete raw packets bind the same manifest, issued visits, compressed input authority and pre-RF archive. All **6,772 visits**, **6,765 admitted stereo pairs**, **seven exclusions**, and **13,530 ordered probe metadata rows** match. The candidate issued one native call per admitted antenna and selected 7,336 signed factors, compared with 7,016 in the archived control. The 848 stereo anchors paid **1,696** full 20 ms antenna calls, and the remaining 5,917 visits paid **11,834** genuine 12 ms primary calls. This stage includes the released compressed, index, per-window and whole-decoded checks. The independently recomputed recipe digest and analysis binding match the live receipt. [Full-short receiver entry](full_short_run.py) · [Independent verification](dense_full_short_raw_score.py)

| Candidate stage | CPU s | Elapsed s |
|---|---:|---:|
| Authenticated raw acquisition | 32.403 | 60.449 |
| Native calls within acquisition | 17.351 | 17.592 |
| Complete solve with numerical grid | 30.245 | 30.249 |
| Inside publication entry | 65.888 | 93.964 |
| Process launch through exit | **67.352** | **95.429** |

The early regional check used the prepared causal catalogue, made 25 probes and stopped on the original inside-score condition. It used **4.692 CPU s**, including **0.583 s** for fused geography across 82,789,350 projected cells. The fused operation recorded zero fallbacks. The full-catalogue cold finalist race selected a leader, the signed phase-history update qualified, and the direct route completed. Standard evidence took 7.816 CPU s and evaluated all 179 grid nodes with zero replay error in both arms. Both runs' eight PNGs were decoded and checked against their own byte and RGBA digests. Dimensions agree on all eight. Encoded and decoded contents differ between the two publications. [Fused projector and original proof](dense-geographic-kernel.md) · [Verified artifacts and route](measurements/dense-full-short-raw.json.gz)

The candidate started with **56,663 of 1,997,612** payload pages resident across all 106 compressed members and finished with all pages resident. The archived baseline started with **1,533,163** resident pages. Process input blocks correspond to **7.968 GB** in the candidate and **1.908 GB** in the baseline. The read-only cache observer issued no eviction. The candidate was still 20.486 seconds above half the archived elapsed time and 12.800 CPU seconds above half the archived CPU. This is one saved recording measured through a complete raw publication, with no new RF.

## Reproduction and retained outputs

The single run is retained at `/var/tmp/leo-full-short-dense-DS30-0008`, including the immediate launch-through-exit receipt, cache observations, original command and input pins, all published artifacts and both selected owner/role lists. Its detector is `sha256:ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85`. Its terminal is `sha256:f4a6bc1b090c14db82316e5ddc463fdd392b4adb02f53f2b58072806db70ba2a`. The score command can revalidate both sealed stores without loading any waveform bytes. The launch code uses the normal full-short entry and records exit or timeout before checking the result. Thirty-one component and adjacent tests passed. [Bound command and scoring code](dense_full_short_raw.py) · [Component tests](../../../tests/pipeline_eval/test_dense_full_short_raw.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
here="$PWD/reports/ALGO08/v3"
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
geographic=/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so
out=/var/tmp/leo-full-short-dense-DS30-0008
gauss() {
  sudo -n -u leo flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 env \
    PYTHONPATH="$here:$PWD:$PWD/src:$release/src:$release" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$release/venv/bin/python" -BPs "$here/dense_full_short_raw.py" "$fresh_output" "$short" "$geographic"
gauss "$release/venv/bin/python" -BPs "$here/dense_full_short_raw_score.py" "$out" "$fresh_receipt"
```
