# Two-scan receiver on one core

The final experimental receiver measured **1.74–1.77× native factor-call CPU speedup** across the first three matched repeats of 80 saved dual-antenna visits. It returned the same ordered signed integer epochs, fractional offsets, carriers, and exact and rolled-control scores on all 160 lanes. The native clock excludes decoding, digest verification, Python orchestration and continuation, all solver work, and publication. With the historical DS30 acquisition share of 56.1%, a 1.75× receiver gives at most **1.32× total CPU speedup** by itself, even if all acquisition time were native factor calls. [DS30 timing basis](../single-core-directions.md)

## Which work changed

- Each antenna still gets its own first scan and, on confirmation, its own cancellation and second scan. The verifier reads the untouched samples for both scans. The released exact versus rolled-pilot gate and the causal continuation implementation remain in use.
- The timing scout uses shorter circular FFTs. Every retained lag-correlation offset fits the whole template inside the received block, so samples that would wrap around the circle contribute only outside the retained range. The quarter-rate timing transform falls from 8,192 to 4,800 points. Frequency-bin eligibility and the 4,096-bin carrier transform remain the same. FFTW performs the large transforms and the original 64-bin transform still evaluates the independent confirmation groups. A failed group can end the confirmation immediately because every group must pass.
- The nominal FIR pairs I and Q in registers while preserving the four accumulation chains and their sum order. The coarse refinement evaluates four adjacent frame offsets together in the latter pilot blocks, where the pinned compiler originally used scalar summation. Its earlier blocks keep the original four chains per offset. Refinement uses the original kernel at the modulo wrap. Hardware FMA computes the existing fused verifier operations. The integer timing stencil computes only the exact-pilot correlation where its rolled-control result was discarded. The terminal fractional verifier still computes both.

The FFT arithmetic order differs from the release. The saved comparisons show exact exported factors, and a sufficiently close scout ranking can in principle differ. The tests compare the FIR and refinement kernels against the pinned recipe, including wrap and CFO-boundary cases, and exercise a planted pair with a weaker short pilot, an empty opposing lane, antenna swaps, six causal observations, the exact/rolled margin, and both pilot edges. Three component tests passed. The benchmark also compares the released continuation state and selection for each sparse saved lane. Sparse raw panels supply little same-channel continuity, so they mainly constrain factor parity.

## Saved waveform checks

The final build was frozen before evaluating the 40-visit prefix from each public simulated recording. The two sites share neither waveform nor location. All three offers sharing a waveform map to one recording in this check. The mechanism uses only I/Q, the waveform definition, capture tuning and validity, and lane history. It takes no regional offer, coordinates, satellite IDs, or roof-derived frequency cuts. The two simulations are public development evidence. Field transfer and complete position accuracy require independent recordings at other sites.

| Input | Stereo visits | Empty / single / two verified factors by lane | Lanes with any changed factor | Native CPU speedup |
| --- | ---: | ---: | ---: | ---: |
| Existing Gauss prospective archive, used for development | 80 | 74 / 31 / 55 | 0/160 | 1.74–1.79× |
| Separate saved Gauss pair archive | 64 | 60 / 23 / 45 | 0/128 | 1.78× |
| Earlier nominated weak-carrier challenges from Gauss | 18 | 0 / 14 / 22 | 0/36 | 1.78× |
| First 40 visits of each of two geographic simulations | 80 | 125 / 33 / 2 | 0/160 | 1.80× |

None of these short slices had enough repeated evidence for continuation to publish a factor. The component test supplies six consecutive same-channel observations and verifies the history crosses its selection threshold on the correct lane. The weak-carrier slice is an exact comparison to ALGO08v2 rather than a new count of scientifically confirmed satellite identities. All 124 returned second-scan factors across the four panels were retained in the same order and with the same measurements. [Ordered output digests, counts and CPU and wall timings](receiver-results.json)

## Measured costs

The profile ran two repeats on the same 80 stereo visits. Counts are summed for both repeats of one build, and rows beneath timing are its child stages. Cancellation includes buffer copy, template rotation, per-block amplitude fit and signed residual quantization. The verifier includes the fractional gate and its integer timing stencil.

| Stage | Calls per arm | ALGO08v2 CPU (s) | Experimental CPU (s) |
| --- | ---: | ---: | ---: |
| Full native factor call | 320 | 2.348 | 1.317 |
| Timing scans | 492 | 1.535 | 0.889 |
| Input conversion | 492 | 0.074 | 0.075 |
| FIR | 492 | 0.261 | 0.117 |
| Frame covariance and modes | 492 | 0.157 | 0.158 |
| Timing search | 492 | 0.382 | 0.142 |
| Carrier FFT search | 492 | 0.275 | 0.149 |
| Coarse refinement | 1,968 | 0.302 | 0.200 |
| Independent pilot confirmation | 2,846 | 0.083 | 0.047 |
| Pilot cancellation | 172 | 0.143 | 0.121 |
| Verifier input load | 172 | 0.039 | 0.037 |
| Fractional verifier plus integer stencil | 282 | 0.631 | 0.270 |

There were 86 second scans per 160 lanes. Even a free test that skipped every residual would remove only 86 of 246 timing scans plus their cancellation. At least 55 of those 86 scans returned a distinct verified second factor, and a candidate can support later lane history even when it loses the current visit's selection. Saved full-recording receipts from five DS26 recordings show 21,160 two-factor lanes out of 35,075 with any exported factor. In the earlier one-scan replacement, the causal rule retained 17 of 18 nominated recoveries, yet compact v5 initially produced four of five fixes. An orbit-support retry recovered the fifth. The all-five fitted median was 857 m versus 560 m for two scans with causal support. Those comparisons use the same physical installation. [Residual-search design and DS30 cost shares](../single-core-directions.md)

The largest remaining native costs are the fractional verifier, coarse refinement and the frame covariance plus both scout FFT searches. A later verifier experiment can compute the five integer timing offsets together while keeping each offset's correlation and reduction order. A reduced residual search needs an independent check for a weaker carrier outside the retained proposals and complete history/owner comparisons. None of these avenues has a measured saving here.

## Reproduce

The native builds start from the digest-checked `native/algo08v2` source recipe. The timing experiments used GCC 15.2.0, FFTW 3.3.10 and CPU 2 of the Intel Core Ultra 9 285K on Gauss. The experimental binary retains the production receiver ABI and can be passed to an isolated acquisition caller as its `binary` argument. The deployed build and assets were only read.

| Build | Receiver builder flags | Binary SHA-256 |
| --- | --- | --- |
| Released comparator | Pinned ALGO08v2 build | `f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809` |
| FFT, early group and FMA | `--no-crop --no-reuse --no-avx2` | `509f149630005a8d6850a0bc9a891297d375f30df93982b355827647ba4be9dc` |
| Publication experiment's receiver | `--no-crop --no-pack-refine` | `ab7b4765b9c393d1e5d1cbcda7f0208f84b503f321e262331e0c80bba7202462` |
| Final receiver | Defaults | `107909cc17e994950f7ffb2dce215114959565d5874122d958a6480132c242a5` |

The first intermediate build returned equal factors on all 160 lanes at 1.39–1.40× native CPU. The publication experiment froze the second intermediate build, which returned equal factors on 160 lanes at 1.57–1.60×. The initial global AVX2 reduction changed 86 positive factors despite equal counts and rank/epoch choices. Its largest observed shifts were 0.000417 Hz, 8.11×10⁻⁸ samples and 5.49×10⁻⁹ in an exact-pilot score, at 1.46–1.48× native CPU. Packing the latter coarse refinement blocks into four tap-reduction chains also changed the 86 factors because the release summed those blocks serially. Packing adjacent offsets instead preserved the per-offset order and produced the final measured parity.

Run from the repository root using the repository's Python environment. The receipts bind the indexed input metadata with I/Q hashes, both binary digests, the digest of ordered factors and continuation decisions, and paired per-repeat timings.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_assets=/opt/leo-algo08/current/assets
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental

algo08_one_core() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src \
    timeout 80s "$algo08_python" "$@"
}

mkdir -p "$algo08_work"
algo08_one_core -m "$algo08_native.receiver_build" "$algo08_work/receiver-final-candidate.so"
algo08_one_core -m "$algo08_native.receiver_build" "$algo08_work/receiver-stock-profile.so" \
  --no-fftw --no-early-gate --no-avx2 --no-fma --no-reuse --profile
algo08_one_core -m "$algo08_native.receiver_build" "$algo08_work/receiver-final-candidate-profile.so" --profile

algo08_one_core -m "$algo08_native.receiver_benchmark" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  "$algo08_assets/cancellation-factors.so" "$algo08_work/receiver-final-candidate.so" \
  --assets "$algo08_assets"
algo08_one_core -m "$algo08_native.receiver_benchmark" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  "$algo08_work/receiver-stock-profile.so" "$algo08_work/receiver-final-candidate-profile.so" \
  --assets "$algo08_assets" --repeats 2
algo08_one_core -m "$algo08_native.receiver_benchmark" \
  /srv/bulk/leo-dev/ds26-single-scan-20261120/pair-holdout-iq.zip \
  "$algo08_assets/cancellation-factors.so" "$algo08_work/receiver-final-candidate.so" \
  --assets "$algo08_assets" --repeats 1
algo08_one_core -m "$algo08_native.receiver_benchmark" \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  "$algo08_assets/cancellation-factors.so" "$algo08_work/receiver-final-candidate.so" \
  --assets "$algo08_assets" --repeats 1
algo08_one_core -m "$algo08_native.receiver_benchmark" \
  /tmp/leo-regional-qZJKBw4W/public/panel.json \
  "$algo08_assets/cancellation-factors.so" "$algo08_work/receiver-final-candidate.so" \
  --assets "$algo08_assets" --simulated-panel --visits 40
algo08_one_core -m pytest -q tests/pipeline_eval/test_experimental_receiver.py
```
