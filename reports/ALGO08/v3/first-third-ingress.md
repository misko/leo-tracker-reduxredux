# Verified acquisition after the first admitted third

Stopping detector calls after the first admitted third cut CPU from **0.999–1.050 s to 0.495–0.501 s** on a warm, authenticated 128-window prefix of DS30-0008. The candidate still verified every original window and emitted empty continuation rows after the cut. A streaming drain removed 86 CI16 arrays and saved only **1.8–2.8 ms** outside paid detector callbacks. Its complete input time was 0.500–0.509 s. The unchanged released reader with an empty tail is the measured default. [Pinned prefix receipt](measurements/first-third-input.json.gz)

| Input path to sealed detections | DSP-paid visits | CPU, reverse-order trials | Elapsed, reverse-order trials |
|---|---:|---:|---:|
| Full installed v3 | 128 | 1.050 / 0.999 s | 1.050 / 0.999 s |
| Verified-empty tail, released reader | 42 | 0.495 / 0.501 s | 0.495 / 0.501 s |
| Verify-only tail, whole-member buffer | 42 | 0.573 / 0.571 s | 0.573 / 0.571 s |
| Verify-only tail, reusable streaming buffer | 42 | 0.509 / 0.500 s | 0.509 / 0.500 s |

The experiment used two contiguous 64-window signed members, covering **154,722,097 compressed bytes** and **204,800,000 decoded bytes**. Both orders charged zero storage input blocks. The 42 paid visits produced no selected factors in this short slice. Full v3 produced 84 at later opportunities. The trial measures the input path through sealing and rereading detections. It supplies no position-quality result or full-recording elapsed time.

## Verification and continuation

Installed v3 reads each compressed member into one buffer, advises the next member, and uses paired SHA-NI for both decoded window and decoded member digests. It still constructs a decoded CI16 array for every window. The experiment keeps all released input authorities. It checks the inventory and manifest, authenticates and validates each signed index, authenticates each compressed member, verifies every individual I/Q digest, closes the complete decoded member digest, and checks decoded size and trailing data. The signed index prepass determines the admitted count with the same shape and validity policy as the decoder. The timed candidate pays for this prepass. [Released acquisition attribution](acquisition-split.md) · [Metadata and drain prototype](first_third_ingress.py)

Where a member crosses the cutoff, the streaming path uses full original input arrays for paid visits. Each tail window decodes into one reusable **1.6 MB** scratch buffer. After the window digest check, it passes only its authenticated metadata and dimensions to the released acquisition path. Empty probes still advance the original continuation history. Invalid capture rows still enter the original exclusion accounting. Every arm verified the same window digests and scoped raw authority. All three masked arms produced byte-identical sealed detections, including empty probe metadata and delivery clocks. Synthetic negative tests reject changed manifest, index, compressed digest, per-window digest, decoded member digest and trailing decoded bytes. Ten component tests passed. [Integrity tests](../../../tests/pipeline_eval/test_first_third_ingress.py) · [Matched acquisition probe](first_third_trial.py)

The streaming drain spent about 136.5 ms in decode, 48 ms in paired decoded hashing, and 64–65 ms in the compressed read and hash. The whole-member buffer spent about 203 ms just on decode and buffer preparation. Full verification accounts for nearly all the input work left after omitting DSP. The small streaming credit remains below the variation in the measured complete input path.

## Full recording cost model

DS30-0008 scheduled **6,772 stereo visits**, of which **6,765** passed quality. The first admitted third keeps **2,255** and has exclusive `visit_index` cutoff **2259** because four excluded visits occur before the cut. The alternate scheduled-third rule cuts at **2257** and keeps **2,253** admitted visits. The two extra visits in the admitted rule both have two saved selections.

The complete v3 phase receipt archives 37.338 CPU s across all original detector callbacks and 21.623 CPU s outside the callbacks. It stores only anchor and non-anchor sums. The short authenticated full-DSP sample estimates **12.811 CPU s** of kept callback time by pooling all 128 visits and **14.516 CPU s** by applying separate measured means for zero, one, or two selections to the full kept visit counts. The scheduled-third sensitivity gives **14.499 CPU s** with the same stratification. The native callback clock includes continuation. The stratified model uses the archived selection counts only to price the work. The actual routing rule computes its cut from authenticated index metadata before any waveform decision. [Full callback receipt](measurements/acquisition-split-DS30-0008.json)

Adding the archived 21.623 CPU s outside the callbacks, about 0.10 s for authenticated index planning, and about 0.035 s for empty continuation gives **36.27 CPU s** for the first third with the released reader. Giving the streaming drain its projected **0.12 s** additional credit gives **36.15 CPU s** against the observed full 58.96 CPU s. This is a processor-cost projection, about 39% less than the measured baseline. It holds outside work at the recorded full-acquisition cost except for the measured adjustments. No full raw replay measured cache effects, I/O wait, input overlap, downstream solver cost, or resulting position quality for the candidate. The entire suffix remains authenticated under either reader path.

## Reproduce

Use a fresh receipt path. The raw experiment uses the same 128 saved visits in every arm, one low-priority CPU, and no position solve.

```sh
runner="$PWD/reports/ALGO08/v3"
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 timeout 55s \
  sudo -n -u leo env PYTHONPATH="$runner:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  "$release/venv/bin/python" -BPs "$runner/first_third_trial.py" /var/tmp/leo-first-third-input.json
```
