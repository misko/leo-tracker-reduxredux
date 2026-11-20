# Preserve the four stock timing regions and add a fifth

The union preserved all **7,067 stock coarse peak keys** before top-eight selection and nominated **1,151 extra keys** on 36 saved visits. The shared top-eight kept **102** slots from extra epochs. The union recovered **7/24** archived physical misses and retained **8/8** previous matches, the same target counts as fourth-center replacement. It added four gate-positive candidates over replacement on this panel. [Stage chart PNG](center-union.png) · [PDF](center-union.pdf) · [Paired timing CSV](timing.csv) · [Qualification](qualification.json)

## Search support and final gates

The native detector evaluates the full 21-bin coarse CFO grid in every stock time region and in the independent FFTW hint's clipped ±1 neighborhood. Only previously uncovered epochs add cells. An original epoch keeps its original regional comparisons and local refinement. A novel epoch tests its observed neighbors. The two peak sets enter the same top-eight ordering and suppression, coarse score threshold, fine search and fractional confirmation. New nominations can occupy slots that would have gone to stock peaks. The stock public entrypoints are unchanged. [Protocol](PROTOCOL.md) · [Source-bound ABI witness](abi-witness.json)

All 36 scheduled visits processed. The schedule includes 24 primary, eight confirmation and four fixed windows from DS26-0168 and DS29-0604. Both receivers used the rank-one FFTW proposal. An absent hint reproduced the complete native stock output on every visit. With the hint present the union retained the entire original peak-key set, added 141 unique epoch instances across 60/72 receiver lanes, and retained 474 stock-origin and 102 extra slots out of 576. [Fixed raw visit lock](source-lock.json.gz) · [Lower-band receipts](lower.json.gz) · [Upper-band receipts](upper.json.gz)

| Real saved-IQ evidence | Stock wide | Replace fourth | Union |
| --- | ---: | ---: | ---: |
| Gate-positive candidates | 161 | 195 | 199 |
| Gate-positive candidates matched to stock | 161 | 161 | 161 |
| Archived physical misses recovered | 0/24 | 7/24 | 7/24 |
| Previously matched targets still recovered | 8/8 | 8/8 | 8/8 |

The gate comparison uses one-to-one epoch/CFO matching with the existing alias tolerance. The physical target counts use the archived unfolded CFO with the two-sample and 1 kHz tolerances. Union matched all 195 replacement positives and added four unmatched records. These totals come from a selected detector panel and leave open whether either hint preserves every stock positive over a complete recording.

## Complete detector cost and controls

| Three rotated repeats on each of 36 visits | Stock wide | Replace fourth | Union |
| --- | ---: | ---: | ---: |
| Complete CPU p50 / p95 (ms) | 15.964 / 18.498 | 19.570 / 22.302 | 19.635 / 22.847 |
| Complete wall p50 / p95 (ms) | 16.754 / 23.892 | 20.484 / 43.663 | 20.459 / 52.461 |
| Coarse-only CPU p50 (ms) | 1.791 | 1.810 | 1.942 |
| Complete calls ≤20 ms wall | 88/108 | 45/108 | 46/108 |

CPU and wall include the actual FFTW scout for both hint deployments. The measured whole-call boundary is already-loaded CI16 through full decoded candidate output on x86 host CPU 0. Both hinted paths recovered the single-frame target on 4/4 receiver–sideband pairs while stock recovered 0/4. The strong, weak, alternating-sign and two-family physical targets survived all three paths. Empty and seeded Gaussian controls gave zero positive records. The upper-edge pure tone produced 8, 6 and 8 gate-positive records for stock, replacement and union, without a planted pilot. [Control outcomes](qualification.json)

## Opt-in native interface

The installed stock ABI-1 release and FFTW sidecar remain distinct. The union library exports `leo_native_glrt_analyze_center_union_v1` as an extra function. Use `tools.pipeline_eval.variants.center_union.DifferentialUnionCall` with the qualified `FftScout` for the same raw-service boundary. The candidate SHA-256 is `3d1d1451b151b36dbcd6750326396bbfe6a1b0c5bd5b79e7555676ad65ba2342`. The feature gate matched stock science and preserved every stock peak key on two authentic sidebands before whole-IQ handoff. [Release receipt](release.json) · [Build receipt](build-receipt.json) · [Feature gate](feature-gate.json) · [Evidence hashes](evidence-lock.json)

```sh
python -m tools.pipeline_eval.qualification.center_union_build \
  --stock /path/to/wide-runtime/stock/libleo-adaptive-detector.so \
  --work /var/tmp/receiver-center-union-local
python -m tools.pipeline_eval.qualification.center_union_results \
  --out /var/tmp/receiver-center-union-figures
```

The chart and CSV regenerate from the sealed local receipts. This study ends at the detector and leaves geographic scoring to complete-waveform qualification.
