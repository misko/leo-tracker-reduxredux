# Selective guarded CFO through a North raw fix

The original staged North simulation published a complete two-arm fix in **11.224 s elapsed and 11.222 s CPU**, from fresh process start through exit. The historical same-fixture and same-native-pack all-paid guarded control took **12.233 s elapsed and 12.227 s CPU**. Named ALGO08v3 took **16.761 s elapsed and 16.757 s CPU**. The measured differences are 1.008 s (8.24%) and 5.536 s (33.03%), respectively. These are single historical comparisons with the same resident assignment. The 0.538 s reduction inside the instrumented refinement itself is narrower than the whole-process difference.

| Scope | All-paid guarded | Selective guarded |
| --- | ---: | ---: |
| Process elapsed, s | 12.233 | 11.224 |
| Authenticated acquisition, elapsed s | 6.330 | 5.349 |
| Fixed-epoch refinement, CPU s | 0.659 | 0.121 |
| EOF held-cycle selection, elapsed s | 0.044 | 0.039 |
| Sealed detections since start, s | 7.399 | 6.404 |
| Decision and publication, elapsed s | 5.218 | 5.346 |
| Standard report since start, s | 11.894 | 11.026 |

Acquisition contains refinement, and the file timestamps are cumulative. The combined native primary/full calls were unchanged at 2,096/304. The tail attempted 396 of 996 short positives and amended 396 instead of 460. Exact tail retries fell from 501 to zero. Each receiver paid 198 attempts. The 600 skipped calls would contribute 64 frequency amendments to the discarded lanes. The original continued receiver still advanced history over all 2,400 probes and recorded 1,078 positives before route selection. With both original held-cycle scores unchanged (+28.366 and +26.345 nats), the history route emitted the same 456 factors, including 396 short and 60 anchor factors. All 2,400 projected probe rows, including RF opportunities, rank, timing and signed CFO, matched exactly.

| Publication | `c=0` error, m | Fitted-`c` error, m | `c=0` RF RMS, Hz | Fitted-`c` RF RMS, Hz |
| --- | ---: | ---: | ---: | ---: |
| Named ALGO08v3 | 105.690 | 140.779 | 5.406 | 5.167 |
| All-paid and selective guarded | 113.236 | 132.068 | 5.242 | 5.065 |

The original 25 km containing offer placed truth 100 m inside the face. The selective endpoints lie on that face and match the all-paid positions exactly. The named survivor finish was accepted, with matching owner identities and roles for all 304 rows in each arm. Both outputs share the 137-point calibration grid and numerical path. The verifier opened all eight official PNGs, matched dimensions, file hashes and decoded RGBA hashes, and checked each grid and path binding to the actual position PNG. The published native identity `sha256:5f2cc8c112d18a25911f9e47de1d5064ee36ffd0b2b1ac686c5ef6a1d4c1dcaa` records the distinct receiver recipe. The identical projected probes have canonical digest `sha256:041622052cde63478ecd35a8aca397774af8e27287e7273513a745962a378f9f`.

The before/after censuses found all 385,609 compressed payload pages and 188 index pages resident across 19 original members. The child incurred zero major faults and zero filesystem input blocks. The measured input was 1,579,423,424 compressed bytes and 1,920,000,000 decoded bytes. Setup outside the timed child consisted of source checks, font setup on a fresh output root and passive cache census. No waveform was copied or warmed for this trial. The protocol used the already staged public recording. The raw timing covers a single containing simulation and supplies no physical throughput estimate or claim about other offers.

## Original near-omitted offer

One saved replay put the **identical 456-factor packet** in the original mirror offer, where truth lies 100 m outside. It published a false fix in **5.791 s elapsed and 5.790 s CPU** with no waveform calls, one authenticated handoff and the same signed causal archive. Both fitted longitudes ended at the limiting face, with the original 304 conditional owners and their roles unchanged. The named finish was accepted, the matched grid contained 137 points, both objective replays agreed, and all eight official and decoded PNGs validated including the position image bindings.

| Calibration | Endpoint (lat, lon) | Error, m | RF RMS, Hz |
| --- | --- | ---: | ---: |
| `c=0` | 47.773058848, 16.098151774 | 134.371 | 5.249 |
| Fitted `c` | 47.771790989, 16.098151774 | 112.201 | 5.067 |

The prior archived 1,078-factor all-paid exact packet was a different mirror input. The original named-v3 mirror also published a false fix. The speed result on the containing offer therefore comes with a demonstrated near-edge withholding failure under the same selective receiver. The saved clock is separate from the raw containing clock.

## Reproduction

Timed commit `2fc39430ac68bc5c21d79eeae7398f423a42d51f`. The compact receipt `measurements/continued-cfo-north.json.gz` includes the launch binding, after-exit evidence and post-seal score. `sealed.json` SHA-256 is `4411ba5508e7cec22d0ded179af3da1d50fc2c8a3e75c235852a646e66dfb424`. Twelve focused component tests passed. Use the staging owner, verified asset paths and a fresh tmpfs destination.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
export PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD"
runner=reports.ALGO08.v3.continued_cfo_north_trial
output=/dev/shm/leo-v3-continued-north-reproduction
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env TMPDIR=/dev/shm \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -Bsm "$runner" launch "$output"
export PYTHONPATH="$PWD/src:$PYTHONPATH"
"$release/venv/bin/python" -Bsm "$runner" seal "$output"
"$release/venv/bin/python" -Bsm "$runner" score "$output"
```

For the mirror, use the same staging owner, lock and environment with `runner=reports.ALGO08.v3.continued_cfo_north_mirror` and a fresh tmpfs output. That entry verifies the original sealed containing root and independently binds the mirror offer. Timed commit `727be9134` includes a corrected worker initialization. An initial 0.293 s process triggered the fresh-runtime import guard before graph construction or waveform access. The compact [mirror receipt](measurements/continued-cfo-north-mirror.json.gz) records that guard and the sole numerical solve, with final seal SHA-256 `d86d1ce68827d84ff87fc54a57efbf4fc194676cf568ff7d7e4deab16436b80a`. Twenty-three focused component tests passed after the correction.
