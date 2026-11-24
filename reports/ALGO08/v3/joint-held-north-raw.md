# Guarded phase and selection before CFO on public North

The complete staged North containing run took **12.233 s elapsed and 12.227 s CPU**. The previously paired installed ALGO08v3 reference took **16.761 s elapsed and 16.757 s CPU** on the same resident input and offer. The new run was **1.370× faster through exit**, a 27.0% elapsed reduction. It returned both calibration fits within the frozen +250 m per-arm allowance. The earlier paired held-anchor candidate without refinement finished in 12.023 s. The new combined route took 0.209 s longer than that historical candidate. [Frozen scope](joint-held-north-raw-protocol.md) · [Sealed result](measurements/joint-held-north-raw-sealed.json.gz) · [Geographic score](measurements/joint-held-north-raw-score.json)

| Containing result | `c = 0` error (m) | Fitted-`c` error (m) | `c = 0` RF RMS (Hz) | Fitted-`c` RF RMS (Hz) | Owners per arm |
|---|---:|---:|---:|---:|---:|
| Installed named | 105.690 | 140.779 | 5.406 | 5.167 | 302 |
| Earlier held-anchor | 127.778 | 113.418 | 6.881 | 6.764 | 304 |
| Guarded phase, held-cycle and refined CFO | 113.236 | 132.068 | 5.242 | 5.065 | 304 |

The new route increased fixed-zero error by 7.546 m and reduced fitted-`c` error by 8.712 m against named. Fitting `c` within the new run lowered the RF RMS by 0.177 Hz and increased horizontal error by 18.832 m. The new result used 304 conditional observations in both arms, with the same ordered owners and roles as the earlier held-anchor run. The named result used 285 conditional and 17 predictive observations per arm. Both named and new estimates landed on the same offered face. The original simulated position lay 100 m inside that face. The original near-omitted offer has a known false fix from earlier tests. This run tests the containing offer only. [Historical named and held pair](north-held-anchor-pair.md) · [Earlier refined all-visit transfer](raw-cfo-north.md)

## Measured boundaries

| Measurement | Installed named | Earlier held-anchor | Guarded phase and held-cycle CFO |
|---|---:|---:|---:|
| Launch to verified detector file (s) | 8.154 | 6.245 | 7.399 |
| Original compressed bytes per launch-to-detector second (MB/s) | 193.69 | 252.91 | 213.47 |
| Authenticated acquisition, in-process (s elapsed) | — | 5.231 | 6.320 |
| Launch to solver terminal (s) | 14.884 | 10.045 | 10.837 |
| Launch to standard report (s) | 16.569 | 11.510 | 11.894 |
| Process exit elapsed (s) | 16.761 | 12.023 | 12.233 |
| Process CPU (s) | 16.757 | 12.018 | 12.227 |

All through-exit figures include process launch, the full verified scan of 1,579,423,424 original compressed bytes, one solve, eight official figures and process exit. The new child and archived named worker used CPU 2, nice 15, best-effort I/O priority 7, one numerical thread, a primed font cache and fresh tmpfs outputs. The archived named run observed every compressed page resident at launch. The candidate observed all 385,609 compressed pages and 188 index pages resident both before and after. It decoded 1,920,000,000 bytes from tmpfs with zero input blocks and zero major faults, and the async route hit all 18 submitted members with 0.101 ms total demand wait. The current acquisition-only throughput was 249.90 compressed MB/s. The denominator is historical and noninterleaved. An older full named run on this same fixture took 16.203 s. A twofold reduction against the selected reference would require an 8.380 s complete process. [Binding and exact command](measurements/joint-held-north-raw-binding.json.gz)

The new refinement used 0.659 CPU s inside acquisition and the selector used 0.0445 CPU s. Acquisition was 1.089 s longer than the earlier held-anchor run, while the following decision and publication phase was 1.008 s shorter. The new configuration added the named survivor fit, projected grid, verified PNG read reuse and six direct figures to the cumulative path. These clocks measure the combined configuration. The candidate's timed solve took 3.427 CPU s and its verified figure render 0.700 CPU s. The original named fit was paid and accepted in 0.0676 CPU s. Both-arm objective replay deltas were zero, the geographic projection had zero fallbacks, and the regional scan stopped at `inside_score` after 25 probes.

## Signed selection and publication

The actual guarded CLI ran 304 full and 2,096 short antenna calls across the original 1,200 stereo visits. The full verifier reported zero exact phase fallbacks and the short verifier reported seven. The CFO tail used 501 exact fallbacks and no signed-band retries. It attempted 996 short-positive refinements and updated 460, including 64 changes on factors that selection subsequently removed. Held-cycle log-score gains were +28.3664 and +26.3449. History selected the same 456 signed lanes as projection from the archived exact unrefined packet, including 60 full anchors and 396 short factors. All 396 retained short factors used updated signed CFO. The selected result matched the independently staged exact refined factors on rank, integer and fractional epoch, flags and opportunity order. The largest signed CFO difference was 2.04×10⁻¹⁰ Hz, and the largest score or margin difference was 3.59×10⁻¹⁴.

The selector sealed its pre-refinement row digest `sha256:e13c66eb68162fc286598b8599ac66502a6eb745edbd6c4387187f75ba42eb91` and candidate native digest `sha256:7b54d4aa6b3c12c4befd413f6fc68a86797803c1382b99de37b2fa202fc23266` before fitting. The archived exact pre-refinement row digest was `sha256:a3a2d174eadd089239a79910d27a16d00832b0101263c60dc42c11de49f54a8a`. The guarded receipt commits to the full pre-refinement view through its digest. Individual excluded guarded rows are unavailable to the offline verifier. The independent row comparison covers all final signed factors and confirms that the projected support agrees with the archived unrefined replay. The original authority and all 2,400 signed opportunities matched named. The cache census, renderer and owner evidence were sealed before the geographic scoring key was read.

Both calibration arms used the complete 137-node matched grid. The verified path and grid bind the candidate's actual position PNG. All eight official PNGs passed file authentication and full RGBA decoding, and each matched the corresponding named image's dimensions. All eight encoded and pixel digests differed. The first offline dimension summary compared tuples against archived JSON lists. The corrected verification reused the outputs from the single completed process. [Verification code](joint_held_north_raw.py) · [Component tests](../../../tests/pipeline_eval/test_joint_held_north_raw.py)

## Reproduction

Timed checkout `86041a95e` uses corrected selector `8280df546` and guarded pack `0d590b0c…`. The signed archived inputs and binary paths are pinned in the launch binding. Run the `launch`, `seal` and `score` operations from the repository root with distinct process boundaries. For `launch` use the original staging owner, existing low-priority Gauss wrapper and the release import path in the order below. For `seal` and `score` lead `PYTHONPATH` with this checkout's `src` so the read-only store API is available. The first script-form launch stopped on an import before starting the raw child. The module command below reaches the intended tooling. Seventeen focused tests passed.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
export PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD"
output=/dev/shm/leo-v3-joint-held-north-reproduction
runner=reports.ALGO08.v3.joint_held_north_raw
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env TMPDIR=/dev/shm \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -Bsm "$runner" launch "$output"
export PYTHONPATH="$PWD/src:$PYTHONPATH"
"$release/venv/bin/python" -Bsm "$runner" seal "$output"
"$release/venv/bin/python" -Bsm "$runner" score "$output"
```
