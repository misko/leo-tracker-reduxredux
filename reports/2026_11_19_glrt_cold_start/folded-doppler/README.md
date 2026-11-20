# Track-free folded Doppler

The global receiver issued one fix on six sealed recordings. That fix was **8,431 km from truth** despite four validated frequency profiles. The offered-tile run issued three fixes at 1.82, 4.02 and 6.38 km. All three improved on the 8.19 km offer center. The same recordings had 0.36–1.32 km error with stored v5 in the `c = 0` arm. The fixed validation rule failed to control false localization over the global site search. [Protocol](PROTOCOL.md) · [Prediction lock](prediction-lock.json)

This receiver starts from passing fractional GLRT carrier peaks, capture UTC and a causal Starlink TLE inventory. It scores whether absolute-frequency residuals repeat modulo 227.273 kHz after subtracting the Doppler of each proposed site and orbit. The accumulator fits a constant residual on its training bins and checks that same orbit and offset on the held bins. Raw points are never assembled into tracks. The global arm uses 768 starting cells and at most 1,284 site evaluations. The offered arm uses the original tile center and searches within 12.5 km. [Receiver](../../../tools/pipeline_eval/variants/folded_doppler.py) · [Accumulator](../../../tools/pipeline_eval/variants/folded_doppler.c)

| Recording | Global decision and error | Global profiles confirmed | Offered-tile decision and error | Tile profiles confirmed | v5 `c = 0` error |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | Withheld, guess 18,158 km | 2 | Issued 4.02 km | 4 | 1.28 km |
| DS26-0122 | Withheld, guess 9,950 km | 2 | Withheld, guess 2.62 km | 4 | 0.75 km |
| DS26-0237 | Issued 8,431 km | 4 | Issued 1.82 km | 4 | 0.36 km |
| DS29-0082 | Withheld, guess 14,347 km | 1 | Withheld, guess 12.83 km | 2 | 0.57 km |
| DS29-0174 | Withheld, guess 11,105 km | 2 | Issued 6.38 km | 3 | 0.89 km |
| DS29-0247 | Withheld, guess 12,800 km | 1 | Withheld, guess 5.12 km | 3 | 1.32 km |

The global false fix achieved a held frequency-support excess score of 15.95 and a 4.88-point lead over separated finalists. In the tile, DS26-0122 achieved 17.40 with four confirmed profiles and was withheld because a separated finalist scored two points higher. DS29-0247 was withheld with a 0.60-point lead. The scores count repeating within-band carrier residuals. The global false fix shows how this can happen at a wrong location when many orbits and offsets are searched. Individual profile offsets, support counts and training and held scores are in the sealed predictions. [Global](global.jsonl.gz) · [Matched tile](matched-tile.jsonl.gz)

The observable fitted offset is a free constant for each exact RF. Adding `c × (RF / GHz − 11.5)` shifts the nuisance offset by the opposite constant. This gives identical frequency scores, hypotheses and coordinate decisions in the `c = 0` and fitted-`c` arms. The data identify the sum of these constants modulo the pilot ambiguity. RMS was left unreported because the method assigns support counts to anonymous raw peaks, with no per-peak satellite labels.

The four synthetic component tests passed. They exercise global and tile recovery within 2 km for an optimistic planted source, random-frequency null rejection, unchanged training offsets after editing held peaks, and the RF-calibration identity. The site was planted near a starting lattice cell, and the synthetic catalogue has four signals with accurate orbital states. On a single pinned Intel host CPU per worker, median timing including input load was 7.68 s globally and 2.71 s in the offered tile. The ranges were 6.36–11.03 s and 2.25–3.79 s. [Tests](../../../tests/pipeline_eval/test_folded_doppler.py)

Run the same paired replay into a fresh directory. Truth is read separately by the suite's comparison. The SHA-256 of the receiver Python file followed by its C kernel is `dd6f48e9509fcbfe526a22ad7bc9484588d441b804d57e9e750b8b487ec7cffa`. [Qualification runner](../../../tools/pipeline_eval/qualification/folded_doppler_trial.py)

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 0-3 .venv/bin/python -m tools.pipeline_eval.qualification.folded_doppler_trial \
  --out /tmp/folded-doppler-replay --cpus 0 1 2 3 \
  --cases DS26-0036 DS26-0122 DS26-0237 DS29-0082 DS29-0174 DS29-0247
```
