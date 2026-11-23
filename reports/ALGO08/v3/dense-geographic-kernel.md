# Fused dense projection for the geographic proof

The fused projector cut the paired DS30-0008 geographic probe stage from **6.589 to 2.187 CPU s**. The complete saved live solve took **30.064 CPU s**, compared with **33.677 s** in the archived matched live control. Both calibration arms, all 4,440 owner and role rows per arm, the complete objective grid and recorded path stayed exact. The saved southern omitted offer retained its bilateral withholding decision before fitting.

## What the kernel does

The released geometry preparation, conservative horizon screen, full causal catalogue prior, probe lattice, stopping logic and Python track likelihood remain in use. Each call streams all original eligible satellite-time cells in one AVX2 loop over the existing contiguous prepared arrays. The loop forms slant range, signed Doppler and phase-tangent derivative, and emits the sign of vertical divided by range. Only that sign enters the scorer's whole-track horizon test. It replaces angle construction and temporary dense arrays without introducing a second visibility shortlist or indexed orbit gathers.

At 3.145 million cells per dense probe, the returned arrays occupy about 53.46 MB, down from 75.48 MB for the three binary64 outputs, before counting the original projection's temporary arrays. The kernel binds only the pinned geographic scorer. Noncontiguous, unsupported or invalid projected geometry uses the ordinary projection. The Gauss build used GCC 15.2.0 with vectorization confirmed at 32 bytes and floating-point contraction disabled. Compiler time was 0.09 CPU s and source verification and binding took about 1.25–1.27 ms per process. They are outside the probe and solve clocks. No native fallback occurred in either accepted replay.

## Paired probe evidence

Each case rebuilt the same geometry once and evaluated the original and native scorer with the same early terminal scheduler. The dense case ran control first and the southern case ran native first. The clock includes track scoring and aggregation. Projection time is a subset of the native arm, and geometry preparation is measured separately.

| Saved offer | Original catalogue / projected orbits | Visited probes | Dense cells | Shared geometry CPU s | Probe CPU s, original → native | Native projection CPU s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 containing | 11,177 / 771 | 25 | 78,622,725 | 2.302 | 6.589 → 2.187 | 0.445 |
| Southern omitted | 10,937 / 856 | 96 | 21,694,464 | 0.217 | 1.445 → 0.672 | 0.205 |

All visited coordinates and track owner labels matched in order. The largest absolute change in a receiver or pooled score was **2.98×10⁻¹³** dense and **7.47×10⁻¹³** southern. Comparing full frequency arrays on the first and last visited probes in each offer gave largest errors of **6.26×10⁻⁹ Hz** in frequency and **3.31×10⁻¹⁰ Hz/s** in phase derivative, and zero horizon-sign differences over 6.74 million audited cells. These are empirical errors from representative arrays and every visited proof score in the two saved cases.

The dense proof stopped at the same `inside_score` after 25 probes. The southern proxy evaluated all 96 and both receivers independently chose the same exterior point at `(-62.5, 0.0)` km, with 50 km clearance. Both gains matched within **6.39×10⁻¹³**. The installed early terminal route withheld with `both_receivers_support_far_exterior` without calling the fit. This reproduces the sealed long-primary omission proxy.

## Complete dense saved solve

| Whole saved solve | CPU s | Elapsed s | Early proof CPU s | Owners, zero / fitted | RF RMS Hz, zero / fitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Archived live control | 33.677 | 33.728 | 10.040 | 4,440 / 4,440 | 128.822 / 128.753 |
| Live fused projector | 30.064 | 30.147 | 6.331 | 4,440 / 4,440 | 128.822 / 128.753 |

All 179 grid points and their scores, final coordinates, complete owner sets, published path, objective replay and fit route matched exactly. The complete run saved 3.613 CPU s against the archived control. Its live early proof includes the preparation work measured separately in the paired probe trial. The measurement uses one new complete replay against a pinned archived control, with no raw acquisition or publication-render time. The earlier visibility-first route reached the same geographic decision but took 19.817 CPU s in this proof. [Original live profile](live-inference-profile.md)

Fourteen component and adjacent tests passed. [Frozen protocol](dense-geographic-kernel-protocol.md) · [Summary and provenance](measurements/dense-geographic-kernel.json) · [Complete saved receipts](measurements/dense-geographic-kernel.json.gz) · [Runner](dense_geographic_trial.py)
