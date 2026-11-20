# Marginal Doppler track offsets

This comparison isolates the frozen v5 constant-offset scale `BIAS = 1000.0` in native Hz from `leo/analysis/research/retained_track_likelihood.py`. The reference specifies each merged carrier component's zero-mean Gaussian offset independently. This replay applies that prior once per anonymous Graph track. A Graph track can cover a different set of samples from a merged v5 component. The replay retains native joint's original correlated noise, point support, robust weights, clock, phase and CFO alias branches.

The matched fit compares 1,000 Hz with zero variance. Both run from the same trained and pooled orbit assignments, aliases, and starting states in each calibration setting. Substituting a constant Gaussian offset of variance `σ²` augments each track covariance by `σ²11ᵀ`. In the whitened coordinates, the implementation scales the single constant direction by `1 / sqrt(1 + σ²‖W1‖²)`. The projection keeps the original bounded parameter dimension. The robust weight applies to the integrated whole-track criterion. The final geometry comparison uses the original training-to-pooled reference and gate thresholds.

Held tracks have their identities and aliases selected once under the common stock `c = 0` training state. Each receiver estimates its shared parameters from the separate training tracks. Held loss integrates an independent zero-mean offset over the entire held track and includes its covariance determinant penalty. The reported raw RF RMS measures the same unadjusted physical residual for both models, before subtracting any track offset.

## Recorded results

The sealed roster has four fixed diagnostic roof cases, six outcome-blind roof recordings selected by an identifier hash with three per dataset, and three real archived omitted-tile offers selected by a hash. All 26 worker runs measured both calibration settings. All 13 pairs matched their native factors, catalogue, tile, Graph projection and exact training, held and final owner/alias digests. The experiment used CPU 0, 7 or 17 with paired runs alternating order and the same 512 MiB address-space cap.

| Cohort | Calibration | Published in both methods | Published horizontal error median, zero → 1,000 Hz | Held marginal loss per point median, zero → 1,000 Hz |
| --- | --- | ---: | ---: | ---: |
| Four diagnostic roof cases | `c = 0` | 2/4 | 1.692 → 0.505 km | 18.153 → 6.329 |
| Four diagnostic roof cases | fitted `c` | 2/4 | 1.329 → 0.531 km | 18.032 → 6.326 |
| Six salted roof cases | `c = 0` | 6/6 | 1.262 → 0.895 km | 8.185 → 2.189 |
| Six salted roof cases | fitted `c` | 6/6 | 0.929 → 0.909 km | 7.693 → 2.194 |
| Three omitted offers | `c = 0` | 0/3 | — | 32.435 → 3.050 |
| Three omitted offers | fitted `c` | 0/3 | — | 33.757 → 3.044 |

Both models withheld DS26-0197 and DS29-0316 for weak geometry. DS26-0277's omitted query moved from weak held support to weak geometry and still withheld. The broad prior also lowered predictive loss for the wrong offers. On the six salted cases its median raw final RF RMS increased from 170.4 to 302.1 Hz at `c = 0` and from 128.6 to 279.3 Hz with fitted `c`. Geographic outcomes, raw residuals and predictive losses have separate columns in the [per-recording scores](per-recording.csv). Both roof charts include all four original v5 options. The omitted chart uses the exactly matched archive offers with their own denominators.

An initial worker batch reached a JSON serialization error when returning a NumPy integer support count. The sealed results come from the rerun of the same planned case pairs after conversion to a JSON integer. The [preflight failures](preflight-failures.json.gz), [source lock](source-lock.json) and [prediction lock](prediction-lock.json) record the two stages.

## Reproduce

```sh
report=reports/2026_11_19_receiver_screening/refinement/marginal-offset
python -m tools.pipeline_eval figures --panel screening --evidence "$report" --arm both --out /tmp/marginal-offset-figures
```

For a fresh paired replay, supply the frozen native archive and native-joint worker bundle.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 0,7,17 \
  python -m tools.pipeline_eval.qualification.marginal_offset \
  --work /tmp/marginal-offset-work --out /tmp/marginal-offset-evidence
python -m tools.pipeline_eval.qualification.marginal_offset_results --report /tmp/marginal-offset-evidence
```
