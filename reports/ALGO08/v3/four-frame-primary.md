# Four-frame primary at 6.6444 ms

The genuine four-frame primary saved **5.55–8.56 CPU ms** in the nonanchor receiver on each signed member comparison. Complete verified acquisition saved CPU in three of four comparisons. Both members failed the frozen signed-factor support gate, including losses of **seven** strong 8 ms factors on dense DS30-0008 and **four** on independent DS30-0169. The test stopped at acquisition. [Frozen protocol](four-frame-primary-protocol.md) · [DS30-0008 receipt](measurements/four-frame-primary-0008.json.gz) · [DS30-0169 receipt](measurements/four-frame-primary-0169.json.gz)

## Aperture geometry

At 60,000 samples, the fourth origin lacks support for the last confirmation gate for 6,444 of the 13,333 integer epochs. With only three origins, the existing integer `count / 2` rule gives one early confirmation group. Two independent early groups and complete support for the stock late gates require four origins and at least **66,444 samples**. The last origin starts at sample 40,000. The latest epoch adds 13,332 samples, the pilot offset adds 88, and its latest confirmation finishes after another 296 symbols of 44 samples each. FIR, integer stencil and fractional support end earlier. The selected shape fits the existing stride of four exactly. It uses the same scout and signed fractional margin gate as the five-frame build, with no 8 ms or 12 ms retry.

Earlier three-frame work nominated timing before a wider carrier search. The two-pair shortlist retained the full eight-frame verifier. This trial shortens both scout and verification end to end for each nonanchor. The pinned research DSO is `46cb969b66a16765128f7e196ede25ee49cc58b79f55da85beb48e876c014171` and the build took 7.276 s elapsed. A separate synthetic control made the stereo buffer unreadable from sample 66,444 onward using `mprotect`. The four signed positives on both pilot edges and antennas matched their unprotected results byte for byte. The negative test carrier used a 39,996-tick phase near the latest epoch. [Earlier partial-aperture receiver](../single-core-2x/receiver-aperture.md) · [Two-pair shortlist](frame-block-shortlist.md) · [Native build](measurements/four-frame-primary-build.json.gz) · [Protected-page control](measurements/four-frame-primary-guard.json.gz)

## Matched paid acquisition

Each fresh process read and authenticated the complete manifest, index and compressed payload of the same staged first member. The 77,442,779 compressed bytes for DS30-0008 and 78,852,856 for DS30-0169 both decoded to 102,400,000 stereo bytes. There were 64 issued visits in each case. DS30-0008 admitted all 64 and DS30-0169 admitted 51 under the original signed validity policy. Both antennas ran on every admitted visit. All 16 stock two-scan 20 ms anchor rows, including empties, matched the reference in both orders. The two ordinary 8 ms captures matched their archived probe bytes and the two four-frame captures matched each other. Source pages stayed resident before and after each launch. All workers exited successfully and reported zero process input blocks and major faults.

| Case and fresh launch order | Short native CPU, 8 ms → four-frame (ms) | Verified acquisition CPU, 8 ms → four-frame (ms) | Acquisition CPU saved (ms) | Process CPU, 8 ms → four-frame (s) |
| --- | ---: | ---: | ---: | ---: |
| DS30-0008, 8 ms first | 93.248 → 85.388 | 642.547 → 640.269 | +2.278 | 1.735 → 1.772 |
| DS30-0008, four-frame first | 92.585 → 87.039 | 650.559 → 663.582 | −13.023 | 1.737 → 1.827 |
| DS30-0169, 8 ms first | 73.468 → 64.904 | 639.183 → 622.100 | +17.083 | 1.705 → 1.718 |
| DS30-0169, four-frame first | 72.359 → 65.943 | 641.137 → 635.587 | +5.551 | 1.718 → 1.756 |

The short native saving was 6.0–11.7% including the signed verification boundary. The dense reference previously put the entire native short workload at 91–97 ms per member, a generous removal ceiling. The fresh complete acquisition clocks include context startup, cleanup and all original integrity checks. Process clocks also charge imports and the verified signed output seal. The four-frame launch through exit cost more CPU and elapsed time in every pair. [Earlier dense CPU attribution](dense-8ms-anchors.md) · [Fresh per-stage and final clocks](measurements/four-frame-primary-0008.json.gz) · [Independent clocks](measurements/four-frame-primary-0169.json.gz)

## Signed factor support and CFO

Comparisons match the same antenna and visit within two wrapped timing samples and 250 Hz of signed CFO. Counts exclude full anchors. The released 20 ms rows are an overlapping-I/Q reference and use the same strongest verified candidate rule when more than one is present.

| Case and antenna | 8 ms / four-frame selected | Signed 8 ms counterparts / 8 ms positives | Lost strong 8 ms factors | Preserved full counterparts / 8 ms factors matching full |
| --- | ---: | ---: | ---: | ---: |
| DS30-0008 antenna 0 | 40 / 40 | 29 / 40 | 5 | 25 / 28 |
| DS30-0008 antenna 1 | 21 / 23 | 12 / 21 | 2 | 11 / 13 |
| DS30-0169 antenna 0 | 29 / 30 | 25 / 29 | 2 | 7 / 9 |
| DS30-0169 antenna 1 | 16 / 17 | 10 / 16 | 2 | 3 / 3 |

The candidate gained 14 detections on previously empty short lanes and lost 12 on DS30-0008. It gained eight and lost six on DS30-0169. The support gate also counts changes outside the signed timing or CFO tolerance on two-positive lanes. The p90 CFO difference among the retained 8 ms counterparts was 85.79 Hz across 41 dense lanes and 147.27 Hz across 35 independent lanes. Dense CFO RMS against the full reference was 74.57 → 87.35 Hz on 36 common triplets. On 10 independent common triplets it went from 107.26 to 149.74 Hz, above the frozen 134.07 Hz bound. These CFO statistics condition on shared support. Both cases failed support against the 8 ms and full references, so no saved endpoint comparison, geographic accuracy claim or receiver promotion followed.

## Reproduce the signed member test

Use commit `7aff43ddb` from base `875d1ddc6`, the shared Gauss lock and the installed release Python. Start with fresh tmpfs output paths. The module verifies the resident original members, captures all emitted probes and stops at the first-member boundary. Run the dense launch as `mouse9911` and the independent launch as `leo`, the respective staging owners. Set `PYTHONPATH` to the checkout root, its `reports/ALGO08/v3` directory, and the installed release's `src` and root. Twenty-three focused and adjacent tests passed. [Runner](four_frame_primary.py) · [Component tests](../../../tests/pipeline_eval/test_four_frame_primary.py)

```bash
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$release/venv/bin/python" -Bm \
  reports.ALGO08.v3.four_frame_primary build /dev/shm/four-frame-build
```

Under the same lock and environment, use `launch /dev/shm/four-frame-0008 /dev/shm/four-frame-build --case 0008` and `launch /dev/shm/four-frame-0169 /dev/shm/four-frame-build --case 0169`. The uncompressed receipts hash to `733a55db68fbefc602b7ae8462b53205e7bfee7d61ca43e172d328be8264783f` and `f8e199f1866b490ec4a42fd60e9a72455cae2eed8a233902b7d3c317d87d3ab9`, respectively.
