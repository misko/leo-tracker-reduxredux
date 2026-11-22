# A frame covariance gate for the primary receiver pass

The prespecified primary gate passed the initial triage. It skipped 17 of 60 prospective physical lanes and saved **8.5–10.1% native CPU** there. Both gate arms reproduced all **146 ordered factor tuples** across 256 lanes, including all 43 residual factors. The residual gate skipped six residual searches and fell short of the 5% prospective CPU requirement. The primary result supports a bounded independent confirmation with the same thresholds. Its qualification remains limited to the saved panels. [Prespecified test](receiver-covariance-protocol.md) · [Per-lane results and timings](measurements/receiver-covariance.json.gz)

| Saved panel | Lanes | Frozen factors, primary / residual | Primary skips / calls | Primary CPU saved | Residual skips / calls | Residual CPU saved |
|---|---:|---:|---:|---:|---:|---:|
| Prospective DS29 | 60 | 32 / 19 | 17 / 60 | 8.5% to 10.1% | 1 / 32 | −2.6% to 3.9% |
| Disjoint DS26 weak-carrier challenges | 36 | 36 / 22 | 0 / 36 | −0.1% to 1.9% | 5 / 36 | 0.1% to 6.0% |
| Northern simulation | 80 | 23 / 2 | 0 / 80 | −0.6% to 1.4% | 0 / 25 | −2.9% to 2.2% |
| Southern simulation | 80 | 12 / 0 | 0 / 80 | −0.3% to 1.0% | 0 / 12 | −2.1% to 1.7% |

The percentages compare two order-alternating repeats with the unrestricted arm of the same instrumented binary. The unrestricted arm reproduced the genuine packed `950c2b94` binary's factors and continuation vote results on every lane. None of these sparse saved slices produced a selected continuation in any arm. The two simulation prefixes exercised geographic variation and the active primary gate fired only on the physical prospective recording group. The 17 prospective primary skips were 11, five and one across its three recordings. [Input assignments, factor tuples and vote results](measurements/receiver-covariance.json.gz)

The primary gate changes the prospective native totals from 239.4 to 215.2 ms and 229.5 to 210.1 ms. Frame covariance through eigendecomposition consumed 9.1–9.4% of the measured unrestricted native CPU there, and the whole prefix through that point consumed 23.4–23.9%. Every gate arm pays for input conversion, FIR decimation and covariance on each reached pass. The residual arm also pays for the full primary scan and signed cancellation before it can test the statistic. The small timing changes in rows with zero skips show repeat variability. [Timing instrumentation](../../../tools/pipeline_eval/variants/experimental/receiver_covariance_probe.inc)

### What the gate measures

The largest and leading-pair eigenvalue shares were compared with the 95th percentiles of seeded white Gaussian noise processed by the actual receiver. The cutoffs were 0.078894 and 0.155840 for the lower edge, and 0.078795 and 0.155825 for the upper edge. The nearest factor-producing weak-carrier primary pass cleared one cutoff by only 0.97% relative, and the nearest factor-producing weak residual cleared one by 0.095%. The cutoffs remained as declared for every input.

The spectral bound limits absolute projections of the centered and normalized quarter-rate frame matrix. The detector ranks local relative scores and verifies signed fractional factors on the original samples. The covariance shares therefore serve as a statistical noise screen. The earlier periodicity trial used a maximum pairwise normalized correlation over separate raw blocks and lost many physical factors. Neither the earlier method nor the current measurement supplies a general zero-loss bound. [Earlier periodicity trial](cost-checks.md) · [Spectral bound and planted two-carrier tests](../../../tests/pipeline_eval/test_experimental_receiver_covariance.py)

### Reproduction

The genuine frozen packed SHA-256 was `950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13`. The instrumented build hash was `313416b4bbc2eaf65f4c2d20f4ddc0c606b212c322d91a1a4e2eadd00b9ad5a8`. On Gauss, use the frozen release's Python and assets. Each command ran under the shared Gauss lock on CPU 2 with one numerical thread and low CPU and I/O priority. Three targeted component tests passed.

```sh
module=tools.pipeline_eval.variants.experimental.receiver_covariance_trial
python -m "$module" build "$probe"
python -m "$module" compare "$receiver_950c" "$probe" "$assets" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  "$weak_carrier_archive" "$public_panel" > receiver-covariance.json.gz
python -m pytest -q tests/pipeline_eval/test_experimental_receiver_covariance.py
```
