# Raw timing scout using three-frame coherence

The blind scout recovered **0 of 16 missed capture-era targets** through the real wide detector. Its top 16 came within two samples of zero missed targets and within 20 samples of one. The fixed-budget hinted detector kept the target positive in all eight retained controls, including seven native winners. It displaced one unrelated gated candidate on the designated receiver of DS29-0519 visit 732. No positioning run was attempted. [Stage figure](stage.pdf) · [Per-visit outcomes](stage.csv)

| Epoch proposals on saved IQ | Missed targets within 2 | Missed targets within 20 | Retained controls within 2 | Retained controls within 20 |
| --- | ---: | ---: | ---: | ---: |
| Wide stock top four | 0/16 | 0/16 | 8/8 | 8/8 |
| Coherence top four | 0/16 | 0/16 | 3/8 | 3/8 |
| Coherence top 16 | 0/16 | 1/16 | 3/8 | 3/8 |
| Shifted sham top four | 0/16 | 0/16 | 0/8 | 0/8 |
| Shifted sham top 16 | 0/16 | 0/16 | 0/8 | 0/8 |

The nearby result was DS29-0519 visit 157, receiver 0, at 10.325 samples. This experiment supplied only the leading coherence rank to the real hinted ABI. The stock detector used its ordinary four-center budget throughout, so a stock top 16 is unmeasured. In the separately measured privileged known-epoch experiment on the same 16 misses, the native detector recovered 14 gated targets. [Known-epoch intervention](../oracle-start/README.md) · [Machine-readable qualification](qualification.json)

## What the scout measures

The lower and upper edge sequences use bins 528–535 and 488–495, respectively. The same 300-symbol pilot repeats without a prescribed frame-index sign change. At 10 MS/s the rounded 750 Hz frame starts have three rounding residues, and starts three frames apart differ by exactly 40,000 samples. For an ideal stationary edge pilot, its lag product equals the edge-template power times a common complex factor for that frame pair. Taking a magnitude after correlating absorbs a constant unknown carrier rotation, including alternating global frame signs. Each rounding residue has its own complex fold. The difference between known and symbol-rolled power correlations asks whether a repeat matches the published edge pattern. The multiplication also mixes noise and interference from both frames, and a visit with only two live frames offers no usable pilot pair. [Qin et al., §VII](https://arxiv.org/html/2602.02627v1#S7) · [Verified template and lag receipt](templates.json)

The signed strong and weak plants, and the alternating-sign plants, all reached the top four within two samples on both receivers and both edges. The zero input produced no proposals. The two-frame plants produced zero near-epoch proposals, although the original wide detector recovered both plants on both receivers. Gaussian noise and CW produced proposals in all their lanes. The real GLRT admitted no candidates on zero, noise or lower-edge CW. Upper-edge CW admitted four candidates on each receiver in both stock and raw-hinted arms. That interferer is a false positive of the original native gate and remains one with the scout. [All synthetic controls](controls.csv) · [Full synthetic native payloads](controls.json.gz)

## Authenticated boundary and cost

All 24 preselected visits from DS26-0162, DS26-0237, DS29-0082 and DS29-0519 were admitted. The reader checked manifest, IQ payload hash, global visit and sample counter, and matched each window’s actual edge to the archive. Both receivers' stock native factors reproduced the complete archived wide controls byte for byte. The existing ABI with absent hints reproduced every public stock field apart from timing. The measured raw hint on each physical receiver replaced at most its fourth scout center. The original CFO grid, refinement and native gate were used. [Frozen protocol](PROTOCOL.md) · [Authenticated roster](input-lock.json.gz) · [Result seals](prediction-lock.json)

| Host time after reading dual-RX CI16 | Median CPU | P90 CPU | Median wall |
| --- | ---: | ---: | ---: |
| Original wide detector | 17.24 ms | 20.20 ms | 17.55 ms |
| Coherence conversion, search and ranking | 10.12 ms | 11.47 ms | 10.28 ms |
| Coherence plus hinted detector, paired by visit | 27.59 ms | 30.88 ms | 27.78 ms |

Four scout calls per visit gave 96 measurements. The summed boundary pairs the first scout call with the corresponding native call on each visit. This is host x86, CPU 4 at nice 10, with single-threaded numerical libraries and cached template transforms. Warm allocation peaked at 9.87 MiB during the isolated scout on each signed strong plant, excluding input and cached templates. The sum exceeds the 20 ms visit duration before archive reading, tracking or positioning. No device or new RF was used.

## Reproduction

The input lock contains the exact adopted roster and the frozen measurement source digests. Restore the roster into a fresh local scratch directory, then use the published stock and hinted native paths in the ABI build lock. Reusing the four compressed case receipts and the synthetic receipt instead of running `replay` and `synthetic` permits plotting without reading any IQ.

```sh
report=reports/2026_11_19_receiver_screening/track-recovery/frame-coherence
work=$(mktemp -d)
gzip -dc "$report/input-lock.json.gz" > "$work/plan.json"
for case_id in DS26-0162 DS26-0237 DS29-0082 DS29-0519; do
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 4 nice -n 10 \
        python -m tools.pipeline_eval.qualification.frame_coherence_eval \
        replay --work "$work" --case "$case_id"
done
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 4 nice -n 10 \
    python -m tools.pipeline_eval.qualification.frame_coherence_eval synthetic --work "$work"
python -m tools.pipeline_eval.qualification.frame_coherence_results --work "$work"
```

Publishing writes the local result files and seal. Replay times naturally differ across runs.
