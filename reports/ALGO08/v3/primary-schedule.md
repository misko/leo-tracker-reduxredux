# First-scan-only verification lowers the dense prefix acquisition ceiling

With a free hindsight schedule, first-scan-only verification and skipping saved **39% of acquisition CPU** on the first 128 signed stereo visits of DS30-0008. This strict schedule reproduced all 256 original probe rows and all 84 selections. Restricting preservation to the 25 factors eventually owned by either v3 calibration arm saved **61%** but dropped the other 59 original selections. That relaxation leaves the downstream solution untested. [Frozen protocol](primary-schedule-protocol.md) · [Full receipt and native factor ledger](measurements/primary-schedule.json.gz)

| Schedule | Skip / first-only / full | Paid calls without a selection | Selected rank 0 / 1 | Native CPU in paired runs | Complete acquisition CPU in paired runs |
|---|---:|---:|---:|---:|---:|
| Preserve every probe | 118 / 118 / 20 | 54 | 78 / 6 | 0.331 / 0.339 s | 0.602 / 0.613 s |
| Matching stock | 0 / 0 / 256 | 172 | 78 / 6 | 0.711 / 0.716 s | 0.990 / 0.997 s |
| Preserve owned factors | 207 / 39 / 10 | 24 | 25 / 0 | 0.127 / 0.128 s | 0.392 / 0.393 s |
| Matching stock | 0 / 0 / 256 | 172 | 78 / 6 | 0.714 / 0.715 s | 0.994 / 0.995 s |

Each comparison reverses run order. Strict CPU ratios were **60.8% and 61.4%** of stock. Elapsed was 0.603/0.613 s against 0.990/0.997 s. Ownership-only CPU ratios were **39.4% and 39.5%**, with elapsed of 0.392/0.393 s against 0.994/0.995 s. The measured native cost of the strict schedule averaged 47% of matching stock native CPU. The earlier hindsight schedule with full-or-empty calls took 83.7% of stock acquisition on this same prefix. Those earlier clocks come from a separate trial. [Earlier binary oracle](continuation-skip.md)

The half-acquisition target leaves the strict schedule about 0.224 s per prefix for native work at its measured outside cost. Its surviving calls average 0.335 s. Those calls would need a further **1.49× speedup** even with free scheduling. The relaxed schedule leaves about 0.105 s per prefix for a hypothetical classifier at the half-time target, contingent on preserving the needed downstream evidence. The relaxation used hindsight ownership and provides no evidence that a production classifier can meet that budget. The strict result leaves no classifier budget at the target.

## Native and ownership checks

The first-only helper links against the released `2258f592…` library and uses the archived stock `verify_peaks` body, one installed `timing_first_detect`, and the original-sample fractional verifier. It supplies a zeroed second peak. Before sealed replays, the helper matched every released rank-zero factor byte for byte, including all fractional scores. Of 256 lanes, 146 had primary factors and 80 of those also had a residual factor in the full call. The native ledger stores both factor lists and both measured costs for every lane.

The ownership join used the released observation mapping on the original full detection packet. Exact receiver, channel, relative clock time and CFO identified each archived owned observation. The reconstructed `observation_id → NORAD` maps matched both canonical ownership digests across all 4,472 owners per calibration arm. In the prefix those maps selected the same 25 original factors, all rank zero. The relaxed schedule preserved all 25 and lost 59 unconstrained selections, with zero gains or replacements. This check used historical solver ownership and did not rerun either position fit. [Original ownership packet](measurements/aperture.json.gz) · [Observation mapping and native helper](primary_schedule_trial.py)

The dynamic program keeps the cheapest path for each distinct twelve-opportunity CFO history within a receiver, channel and actual RF group. Skip, first-only and full actions all advance that history, including empty opportunities. Equivalent histories merge because the released continuation retains counters and factor CFOs only. The exact search peaked at 216 simultaneous states for strict preservation and 46,656 for ownership-only. Both schedules were replayed independently through the released continuation, then rerun against the original waveforms. Nine component tests passed, covering exhaustive small schedules, competing frequencies, residual-only histories, receiver separation and empty-slot eviction. [Optimizer](primary_schedule.py) · [Tests](../../../tests/pipeline_eval/test_primary_schedule.py)

The complete clocks start at signed acquisition and end after sealing and checking the prefix detections. Every arm authenticated both complete members, 154,722,097 compressed bytes, and used the same verified window receipts and scoped raw digest. All timed arms charged zero storage input blocks. Schedule search, its extra native cost census, and all position solving are outside the paired clocks. These measurements cover one warm physical prefix.

## Reproduce

The command uses the capture account and the shared Gauss benchmark lock. It reads only the first 128 saved visits per pass and creates fresh result and helper paths.

```sh
bench=/tmp/leo-algo08v2-2x-bench
payload=/opt/leo-algo08/algo08v3/payload
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
runner="$PWD/reports/ALGO08/v3"
out=$(sudo -n -u leo mktemp -d /var/tmp/leo-primary-schedule.XXXXXXXX)
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 55s \
  sudo -n -u leo env PYTHONPATH="$runner:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  "$release/venv/bin/python" -BPs "$runner/primary_schedule_trial.py" \
  "$out/result.json" "$out/native"
sudo -n -u leo cat "$out/result.json"
```
