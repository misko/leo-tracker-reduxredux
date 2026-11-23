# A quadratic point estimate from archived geographic mixture maps

All six fixed local quadratic fits had a strictly concave maximum inside their sampled neighborhood. Interpolation improved position error on the India omission by **0.915 km** and increased it on the other five offers. It made exactly the same six side decisions as the discrete maximum. Both methods identified two of three omissions and marked one containing offer as exterior. The measured transfers supply no advantage over the discrete point as a general seed or near-face diagnostic. [Frozen protocol](geographic-peak-protocol.md) · [Scored receipts](measurements/geographic-peak-summary.json)

| Original public offer | Reference clearance km | Discrete error km | Interpolated error km | Interpolated clearance km | Original fit error km, zero / fitted `c` |
|---|---:|---:|---:|---:|---:|
| India, containing | +3.576 | 0.452 | 0.728 | +2.861 | 1.017 / 0.751 |
| India, omitted | −1.500 | 1.628 | **0.713** | −2.202 | 1.580 / 1.534 |
| North, containing | +0.100 | 0.002 | 1.577 | +1.559 | 0.106 / 0.141 |
| North, omitted | −0.100 | 0.197 | 1.590 | +1.370 | 0.123 / 0.118 |
| South, containing | +0.100 | 0.197 | 0.257 | −0.057 | 0.817 / 1.101 |
| South, omitted | −0.100 | 0.002 | 0.258 | −0.257 | 0.817 / 1.102† |

Clearance is positive inside the original offered square. The north omission stayed falsely inside. The south containing offer stayed falsely outside by 57 m. The India omission estimate was also closer to the reference than either of its matched fitted positions. The two near-face north fits were closer than their interpolations. The dagger marks the previously published v3 positions for the same southern omitted waveform and offer, with a different detector document. The other five rows use original fits bound to the same detector bytes and offer as the score maps. The receipts also preserve both same-offer India full-catalogue arms and the published v3 arms for all four mirrored offers, with packet identity recorded separately. [Original India numerical comparison](india-regional-diagnostic.md) · [Published same-waveform near-face fits](geographic-jackknife.md)

The estimator selected the best of all 96 pooled scores and fitted the 12 nearest points, including the winner. It used the original local east–north frame and ran the same finite-design, concavity and hull checks on every offer. No fallback was used. The scorer opened the survey references after the six estimates sealed. It independently matched all 576 coordinate and score rows, pooled and receiver values, owner records, and catalogue witnesses to their original evidence digests. The estimator uses evidence from the same RF recording as the fitted locations. This comparison covers three previously studied recordings and measures seed error at a fixed point, prior to any optimization from that seed. [Original score archive and provenance](geographic-rf-fold.md) · [Complete estimate and comparison records](measurements/geographic-peak.json.gz)

## Cost of having all scores available

The released terminal rule on these same archived receiver scores finished after **25 lattice evaluations on five offers and 26 on the India omission**. Each stopped at `inside_score` and kept its candidate. An interpolation that starts from terminal-only evidence would need **70 or 71 additional evaluations per offer**, taking the evaluated coordinates to 96 in every case. The prior complete passes cost **0.788 to 1.365 CPU seconds per offer**, including orbit geometry for the probes and the archived per-track score readout. The offline mathematical interpolation cost **0.211 to 0.958 CPU milliseconds**. This experiment reads already paid scores. It measures additional score counts without projecting an incremental runtime from them. [Per-offer clocks and original terminal replay](measurements/geographic-peak-summary.json)

## Reproduce

Run the estimator first and score the resulting sealed JSON independently. Both commands read only the pinned archived score and reference receipts. All 32 focused and adjacent tests passed. [Estimator](geographic_peak.py) · [Separate scorer](geographic_peak_score.py) · [Tests](../../../tests/pipeline_eval/test_geographic_peak.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
here="$PWD/reports/ALGO08/v3"
out=$(mktemp -d /var/tmp/geographic-peak.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 30s \
    env PYTHONPATH="$here:$PWD/src:$PWD" OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    "$release/venv/bin/python" -BPs "$@"
}
gauss "$here/geographic_peak.py" "$out/estimates.json"
gauss "$here/geographic_peak_score.py" "$out/estimates.json" "$out/summary.json" "$out/full.json.gz"
```
