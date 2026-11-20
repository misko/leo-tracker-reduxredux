# Cached joint satellite association

Each candidate stores whitened Gram information for raw Doppler residual, east, north, constant, receiver drift and orbital phase. A whole-period integer anchor centers the raw residual before whitening. The constant component is projected out of the remaining features and retained as a scalar so the estimator can subtract the current alias without subtracting two large squared norms. All seven matching passes use these same statistics to compute the original weighted energy, phase impulse and phase information. Alias rounding uses the absolute integer and falls back to the original arithmetic near half-integer ties or severe cancellation. Both runs use the original shared phase prior and bounds, partition, held-track validation, final nonlinear fit and publication policy.

## Recorded outcomes

The fixed panel has eight recorded roof captures and two earlier omitted-tile controls. Each pair starts with identical complete native GLRT factors, causal catalogue, tile, and verified Graph projection. The runs alternate order and repeat twice per query on CPU 23 under the same 512 MiB address-space limit. The scorer also checks the original archived receiver outputs.

All 20 pairs had identical Graph digests, ownership decisions, alias selections at every partition pass, and publication decisions. The largest coordinate change across both calibration settings was 12 µm, including forced coordinates on withheld cases. The largest conditional RF RMS change was 1.31 × 10⁻⁸ Hz. Both methods published five of eight roof cases and withheld both omitted offers. The roof figure includes all four original v5 choices on the same recordings.

| Paired CPU measurement | Stock | Cached | Observed difference |
| --- | ---: | ---: | ---: |
| Matching, including Gram preparation | 0.924 s | 0.848 s | −8.2% |
| Complete native worker | 98.348 s | 97.026 s | −1.34% |

Gram preparation used 0.138 s within the cached total. The measured saving in the changed stage was 0.075 s, about 0.08% of the stock worker CPU. Complete-worker timings varied across pairs, so the stage result is the direct evidence for the optimization. Cached numeric arrays reached 619,704 bytes. None of 15,420 recorded matcher calls fell back. Unit tests exercised both sides of half-integer aliases, exact ties, large integral offsets, and a cancellation case.

[Timing and numerical summary](summary.json) · [All 40 fresh attempt receipts](paired-attempts.jsonl.gz) · [Prediction lock](prediction-lock.json)

## Reproduce

```sh
report=reports/2026_11_19_receiver_screening/refinement/cached-association
python -m tools.pipeline_eval figures --panel screening --evidence "$report" --arm both --out /tmp/cached-association-figures
```

The paired replay uses the frozen native archive and the authenticated stripped native-joint environment. The stock and candidate branches use the same process wrapper, affinity and instrumentation.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 23 \
  python -m tools.pipeline_eval.qualification.cached_association \
  --work /tmp/cached-association-run --out /tmp/cached-association-evidence --cpu 23 --repeat 2
python -m tools.pipeline_eval.qualification.cached_association_results \
  --work /tmp/cached-association-run --report /tmp/cached-association-evidence
```
