# Incremental rescue on stock-negative receivers

The incremental detector recovered 8 of 24 known pilot targets previously missed by stock. It preserved all 35 stock-positive receiver rows byte for byte and recovered 9 of 37 stock-negative lanes. Complete dual-receiver wall time was 23.47 ms at p50 and 32.34 ms at p95. The 20 ms gate was met in 31 of 108 trials. These timings cover saved CI16 through native output on the Intel Core Ultra 9 285K host. [Detector chart](incremental-rescue.pdf) · [Per-call timings](timing.csv) · [Receiver lanes](lanes.csv)

| Policy | Gated candidates | Prior misses recovered | Prior matches retained | CPU p50 | Wall p50 | Wall p95 | Wall ≤20 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stock wide | 161 | 0/24 | 8/8 | 16.25 ms | 17.03 ms | 21.51 ms | 97/108 |
| Full four-region rescue | 191 | 7/24 | 8/8 | 33.11 ms | 34.21 ms | 46.82 ms | 24/108 |
| Incremental rescue | 196 | 8/24 | 8/8 | 22.78 ms | 23.47 ms | 32.34 ms | 31/108 |
| One-region sham | 161 | 0/24 | 8/8 | 19.73 ms | 20.17 ms | 26.41 ms | 51/108 |

The detector runs the stock native search first on each receiver. A stock lane qualifies when any complete fractional candidate passes margin ≥0.025. Positive lanes bypass the scout. Each negative lane can request one independent FFTW timing center. The detector clips its ±1 neighborhood to the frame and skips the entire proposal if any requested epoch overlaps stock. It reuses the CI16 preparation and fine FFT plan, evaluates exactly one new region at all 21 coarse CFOs, and applies the original fine and fractional gates. The entire stock row survives every failed donor gate. Three archived misses occurred on lanes with another qualifying stock candidate, so the rescue deliberately skipped those lanes. [Protocol](PROTOCOL.md) · [Native ABI witness](abi-witness.json)

All 36 scheduled dual-receiver visits were processed on their archived timings and antennas. The 32 target-bearing visits are enriched for stock misses, with four additional windows carrying waveform measurements only. There were 36 evaluated secondary regions after one overlap skip, totaling 108 epochs or 2,268 coarse epoch/CFO cells. The full rescue reused the same rank-one scout proposal on the same eligible receiver but reran the four-region detector and charged both receivers, for 672 secondary epochs or 14,112 cells. The paired median full-to-incremental saving was 11.17 ms wall and 10.28 ms CPU. Stock was 6.35 ms faster than incremental rescue by paired median wall time. [Qualification data](qualification.json) · [Source lock](source-lock.json.gz)

Zero and Gaussian controls returned zero gated candidates. Both rescue paths gated 14 candidates across the one-frame controls. Stock and the sham gated zero there. The upper-sideband CW interference control kept its existing eight gated candidates across all policies. The sham used one deterministic epoch per eligible lane with no FFTW scout charged. Candidate totals may include several hypotheses for one physical target. Physical target counts use the original unfolded CFO. [Lower-sideband payloads](lower.json.gz) · [Upper-sideband payloads](upper.json.gz)

## Reproduce

The feature gate binds the detector, FFTW sidecar and six waveform witnesses. `incremental_rescue_build` accepts `--stock` with the authenticated 21-bin stock wide `.so`. It builds offline from the portable wide capsule and existing FFTW scout source, with GCC, `gcc-ar` and the FFTW development libraries. The optional C entry is `leo_native_glrt_analyze_incremental_v1`. The ordinary wide exports stay available. [Feature gate](feature-gate.json) · [Build receipt](build-receipt.json) · [Portable stock source](../../track-recovery/wide-release/README.md)

Regenerate the chart and CSVs from the sealed payloads without the raw archive.

```sh
python -m tools.pipeline_eval.qualification.incremental_rescue_results --out /path/to/local/output
```

The detector stage ends at public native candidate output. Whole-recording position outcomes and device-level resource measurements have separate evidence boundaries. [Stage seal](evidence-lock.json)
