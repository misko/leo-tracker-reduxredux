# Eight milliseconds for each nonanchor signed primary

On the 192-visit DS30-0008 prefix, replacing the 12 ms nonanchor primary with 8 ms reduced mixed native CPU from **484.918 to 409.949 ms**, including the same 48 full-aperture antenna calls. The 8 ms detector matched **38 of 43** original v3 owner-lane factors in each calibration arm. The 12 ms detector matched **40 of 43**. The same two predictive factors dropped below tolerance in both arms. The saved trial gives a speed and support trade-off with no geographic fix measurement. [Frozen protocol](eight-ms-primary-protocol.md) · [Signed probes, per-call boundaries, and owners](measurements/eight-ms-primary.json.gz)

## Native aperture and build

The 80,000-sample aperture fits five consecutive 750 Hz pilot origins across the original full timing range. The last possible later-symbol gate ends at sample 79,777, leaving 223 samples. A sixth origin would exceed the aperture. The early confirmation groups contain three and two origins. The signed search band, two parity normalizations and independent fractional gate at 0.025 follow the 12 ms recipe. Installed 20 ms two-scan searches continue at slot zero modulo eight of each RF, channel and pilot-edge stream. Both antennas and every visit remain present.

The first synthetic training attempt exposed an odd-frame allocation bug. The packed AVX plane stores two frame lanes per stripe, and its original allocator counted only the five active frames. The corrected build pads that storage to six lanes and still evaluates exactly five origins. Both aperture builds then completed the same site-free GCC 15.2 PGO recipe. The fresh 12 ms primary reproduced the existing DSO byte for byte, and its complete dense probes and all weak primaries matched the prior reference. Saturating the input after sample 80,000 left all 336 dense nonanchor outputs and all 36 weak outputs unchanged. [Build entry](eight_ms_primary.py) · [Archived 12 ms geometry](short-signed.md) · [Short-primary ABI checks](mixed-aperture-receiver.md)

## Cost and measured support

| Scope, median of three alternating resident repeats | 12 ms CPU / elapsed, ms | 8 ms CPU / elapsed, ms | CPU reduction |
|---|---:|---:|---:|
| Dense, all 384 antenna calls | 484.918 / 485.063 | 409.949 / 410.079 | 15.5% |
| Dense, 336 nonanchor calls | 358.242 / 358.347 | 281.741 / 283.301 | 21.4% |
| Dense, complete callbacks through selected rows | 489.736 / 489.780 | 414.102 / 414.141 | 15.4% |
| DS26 weak, 36 forced short calls | 45.762 / 45.780 | 33.298 / 33.306 | 27.2% |

The first context setup took 451.9 ms CPU with the 12 ms arm first in the process. Subsequent setups across both arms took 2.4–4.8 ms CPU. The first clock includes shared cold initialization and cannot isolate an aperture setup difference. The native workspace reported per short context fell from 9.853 to 9.377 MB. Input authentication and loading took 0.795 CPU s outside the callback comparisons. The fresh PGO build took 14.228 s elapsed. [Complete timing records](measurements/eight-ms-primary.json.gz)

| Same-antenna/visit comparison | 12 ms selected | 8 ms selected | Within 2 samples and 250 Hz | New 8 ms lane | Lost 12 ms lane | Changed co-located factor |
|---|---:|---:|---:|---:|---:|---:|
| Dense antenna 0 | 128 | 134 | 109 | 14 | 8 | 11 |
| Dense antenna 1 | 67 | 67 | 51 | 10 | 10 | 6 |
| Dense total | 195 | 201 | 160 | 24 | 18 | 17 |
| Weak antenna 0 | 18 | 18 | 14 | 0 | 0 | 4 |
| Weak antenna 1 | 16 | 16 | 15 | 0 | 0 | 1 |

The 25 selected dense full-anchor factors and 23 empty anchor lanes matched exactly. Among 135 matched short dense nonanchors, median absolute differences were **0.191 samples and 48.8 Hz**. Across all co-located nonanchors, absolute signed-CFO differences reached **939.7 kHz**. The matched weak medians were **0.138 samples and 87.0 Hz**. Five weak lanes retained a factor outside the tolerance, despite unchanged selection counts. The archive contains 18 sparse stereo opportunities across five DS26 recordings with incomplete RF-stream history, so the weak run forces both short apertures and supplies no ownership or schedule transfer result.

In each calibration arm, the dense prefix intersects **43 of 4,472** published installed-v3 owners across three satellites. The 12 ms path returned a factor on 42 owner lanes and matched 40. The 8 ms path returned a factor on 41 and matched 38. Both matched 31 of 33 conditional factors and all five anchor owners. The two previously matched predictive factors lost at 8 ms were not offset by a new matching owner. The evidence measures survival of existing signed factors, with no new assignments or position solves. More selected lanes alone do not establish equivalent leverage on another recording or in another region. [Original owner witness and matching rule](full-short-cold.md)

## Reproduce

Use the archive-readable account, fresh output paths and the common one-core slot. The runner verifies the weak archive SHA, exact per-visit weak hashes and the authenticated prefix from the original first three dense members. Twelve focused and adjacent tests passed. [Measurement runner](eight_ms_primary_trial.py) · [Component tests](../../../tests/pipeline_eval/test_eight_ms_primary.py)

```bash
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
installed=/opt/leo-algo08/algo08v3/payload/receiver.so
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
weak=/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip
gauss() {
  sudo -n -u leo flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.eight_ms_primary \
  "$bench" "$fresh_build" "$installed" "$release/assets"
gauss "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.eight_ms_primary_trial \
  "$fresh_build/build.json" "$installed" "$release/assets" "$short" "$weak" "$fresh_receipt"
```
