# Causal carrier stacking with verified anchors

The causal stack matched **90 of 109** installed receiver factors and **69 of 84** continued selections on the saved South prefix. It charged **1.382 CPU ms per antenna lane** against **1.807 ms** for the installed receiver. The scheduled search with the same new-arrival trigger retained 107 factors and 82 selections at 1.338 ms per lane. Stacking recovered no additional factors over the same bank using only the current visit. Both the 0.60 ms cost screen and the 95% evidence screen failed. [Frozen protocol](verified-anchor-stack-protocol.md) · [Complete receipt](measurements/verified-anchor-stack.json.gz)

## Genuine held acquisitions

This trial uses the same 256 upper-edge stereo windows as the trajectory-oracle study. The sealed input and installed profile-guided receiver reproduced all 84 archived continued selections with identical signed CFOs. The full receiver independently returned 109 waveform factors before continuation and no residual companions on this prefix. Its other 403 antenna lanes supplied native negative controls. The available physical clips still have fewer than six same-RF repeat opportunities. No cold physical I/Q was opened. [Original oracle and clip census](track-before-detect.md)

Pay the full named receiver every eighth same-RF opportunity, and again on the next opportunity after an isolated positive anchor. A paid result supplies signed CFO and fractional timing for subsequent visits. The single-track route starts only after two compatible full anchors and uses two preceding samples to extrapolate signed frequency and hardware-counter arrival phase. It scores nine local slope/offset pairs over the current and at most three previous unthresholded carrier surfaces. The existing directed native verifier refines one proposed carrier and phase, then runs the independent pilot gate and original-sample fractional comparison. A directed measurement never becomes an anchor. No full-data ownership, future measurements, catalogue, position or noiseless simulated trajectory enters the receiver. [Runner](verified_anchor_stack.py) · [Directed verifier](directed-verifier.md)

The mandatory discovery check operates on each nonforced lane, including negatives. A standardized global score of at least 10 outside the forecast envelope, or a waveform rejection with a peak at least that strong, pays the original complete two-scan search. The scheduled control uses the same positive confirmation rule and wake threshold, and pays a fresh full search for every wake. Count a first arrival when the installed path finds a nonempty factor after an empty same-RF opportunity, or at the first available visit. Here all selective modes recovered eight of the nine arrivals. The missed arrival failed the wake threshold and had no usable earlier anchors. A weak second carrier hidden by a main signal would require its own independent discovery, which this simulation did not exercise.

| Measured arm | Native factors matched / 109 | Continued selections matched / 84 | Unmatched factors / selections | Full receiver calls / 512 | CPU ms/lane |
|---|---:|---:|---:|---:|---:|
| Installed v3 | 109 | 84 | 0 / 0 | 512 | 1.807 |
| Scheduled searches plus discovery | 107 | 82 | 0 / 0 | 307 | 1.338 |
| Latest surface plus directed verification | 90 | 69 | 23 / 14 | 272 | 1.321 |
| Stacked surfaces plus directed verification | 90 | 69 | 23 / 14 | 272 | 1.382 |

For both directed arms, **37** installed factors occurred on lanes that avoided a full search. The new method reproduced **18** of those. The factor comparison requires the original rank, a signed CFO within 250 Hz and timing within two wrapped samples. The two directed arms took the same acquisition routes and differed in three emitted native tuples. The stack used more than one surface at only 28 of its 83 directed calls. Paid retries continually refreshed the anchor and cleared the preceding surfaces.

## Where the cost and evidence went

All **83** directed calls nominated a carrier within 4.55 kHz of an installed factor, and only **10** nominated a phase within four native samples. **47** directed calls paid a full retry after rejecting the proposal. The other full searches comprised 64 scheduled anchors, nine follow-up confirmations and 152 discovery wakes. Of those discovery wakes, **144** came from lanes with no installed factor. The tight timing need persists even when the narrow carrier bank proposes a broadly correct signed frequency. [Timing, force paths and mismatches](measurements/verified-anchor-stack.json.gz)

| Stack component | CPU ms for all 512 lanes, last repeat |
|---|---:|
| Full native acquisitions and retries | 522.3 |
| Carrier surfaces and global wake peaks | 42.5 |
| Nine-hypothesis local scoring and routing | 5.8 |
| Directed verifier calls | 103.3 |

The arm totals are medians of three counterbalanced chronological repeats. The component clocks are from the last repeat. With the actual paid work fixed, free propagation, free scoring and free verification still leave **1.020 ms per lane** for full searches alone. An unrealizable oracle that wakes only the true first arrivals, pays the actual explicit scheduled and follow-up anchors, and verifies every foreseeable factor for free uses **0.316 ms per lane** on this sparse simulation. Perfectly routing only the observed lost factors to further full searches would add about **67 ms** to the stacked arm. These are different counterfactuals that use measured stock call costs.

The replay retained the 409.6 MB of decoded prefix I/Q to give each arm the same resident samples. Authenticating and decoding it once used **1.040 CPU seconds**. Adding that common measured input charge to the median native totals gives approximately **1.965 → 1.748 s** for installed to stacked, or **1.12×** for the prefix. This acquisition model excludes solver and publication and uses a common measured input clock. A streaming anchor bank can verify using the current I/Q and keep only four small spectra per live antenna/RF history. Current published short-aperture measurements cover separate inputs and scientific outcomes. For example, the prior dense 12 ms paid-primary arm averaged 1.073 ms per paid antenna on its own panel. [Earlier mixed-aperture timing](mixed-aperture-receiver.md)

## Dense acquisition ceiling

The dense DS30-0008 full measurement spent 4.594 CPU seconds on the prespecified one-in-eight anchors and reported 6,170 selected non-anchor factors. Use the fastest archived fixed-offset oracle verifier on the separate dense saved prefix. Grant it exact signed CFO, exact fitted phase, free detection of negative lanes and no false proposals. It spent **0.442 ms per matched factor** after including the original native signed residual work when present. Applying that rate to the 6,170 factors and charging the measured scheduled anchors uses **7.319 CPU seconds** before any proposal or rediscovery. The measured cold callback allowance is **7.858 s**, leaving **0.539 s**. Even the earlier optimistic 0.066 ms native surface rate on 11,834 non-anchor lanes would cost about **0.78 s** and exhaust that allowance with free local propagation and zero rediscovery. The warm historical model leaves 1.999 seconds before surfaces, about 1.22 seconds afterward, with verification still granted its perfect oracle inputs. These projections carry timing across recorded samples and exclude dynamic fallback costs. [Dense split](acquisition-split.md) · [Verifier oracle](directed-verifier.md) · [Surface clock](track-before-detect.md)

The feasible conditional oracle signal gain from stacking did not carry into a causal waveform receiver with paid rediscovery. The small local bank is inexpensive. Arrival phase, false wakeups and original verification dominate this design. The matched saved receiver trial stops before position, solver or raw-publication testing.

## Reproduce

Set the workspace variables as in the [original stacking trial](track-before-detect.md#reproduce), then run its `lock build "$scratch/surface.so"` command. The native directed library is the archived `/var/tmp/leo-v3-directed-pass2/use.so` with SHA-256 `d66ab774f8844fbaec21e28eb2c6ecf42e57152705ea5d4677ca8f032d52397d`. The runner binds the I/Q manifests, native packet and installed terminal, and writes decisions and stage clocks for every antenna opportunity. Thirteen focused tests passed, including causal anchor history, signed search, bounded accumulation, and existing directed-verifier and score-surface tests. [Owned tests](../../../tests/pipeline_eval/test_verified_anchor_stack.py)

```sh
flock -x "$bench/gauss.lock" nice -n15 ionice -c2 -n7 taskset -c 2 timeout 75s \
  env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$code:$PWD:$PWD/src" \
  "$release/venv/bin/python" -BPs "$code/verified_anchor_stack.py" \
  /tmp/leo-regional-qZJKBw4W/public/6bd1f26bfa0bedfcf3f100f8 \
  "$bench/exact-curved-lookahead-south-inside/pair.json" \
  "$bench"/exact-curved-lookahead-south-inside/candidate/fast-scan-automatic-work/*/detections.json \
  "$release/assets" "$scratch/surface.so" /opt/leo-algo08/algo08v3/payload/receiver.so \
  /var/tmp/leo-v3-directed-pass2/use.so "$code/measurements/acquisition-split-DS30-0008.json" \
  /var/tmp/leo-v3-directed-final.json "$scratch/verified-anchor-stack.json"
```
