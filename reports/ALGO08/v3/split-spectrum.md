# Split-frame uncertainty for the signed 12 ms primary

The even–odd spectrum difference failed the two-cohort quality screen. Increasing split disagreement went with **slightly smaller** short-to-full CFO differences on dense DS30-0008, and **slightly larger** differences on the weak DS26 clips. Both rank correlations had magnitude below 0.09. The short receiver's exact-minus-rolled margin also failed the paired RMS criterion in one cohort. These bounded replays give no measured benefit for adding a split-frame uncertainty weight. [Frozen protocol](split-spectrum-protocol.md) · [Sealed retrospective score](measurements/split-spectrum-score.json.gz)

| Existing 20 ms counterpart | Dense DS30-0008 | Weak DS26 |
| --- | ---: | ---: |
| Stereo clips with a short primary call | 40 | 18 |
| Lanes called / published | 80 / 35 | 36 / 34 |
| Same-primary matched lanes / distinct visits | 31 / 23 | 30 / 18 |
| Both issue, outside counterpart tolerances | 4 | 4 |
| Short-minus-full signed CFO median / RMS | +19.80 / 91.94 Hz | +11.98 / 61.73 Hz |
| Median absolute short-minus-full CFO | 67.56 Hz | 31.49 Hz |
| Kendall τb, absolute split difference vs. absolute CFO difference | −0.084 | +0.057 |
| CFO RMS, lower / upper half of absolute split difference | 94.02 / 89.67 Hz | 58.15 / 65.12 Hz |
| Kendall τb, weaker ordinary margin vs. absolute CFO difference | +0.080 | +0.090 |
| CFO RMS, stronger / weaker half of ordinary margin | 82.34 / 101.18 Hz | 64.09 / 59.28 Hz |

The retrospective reference is the existing installed rank-zero factor, joined by clip ID, antenna, and exact physical IQ SHA-256. A counterpart also has to agree within two wrapped samples and 250 Hz. The discrepancy is a repeatability comparison between overlapping apertures. The 20 ms CFO and the two within-12 ms estimates share scout information or IQ and are not independent ground truth. The 61 matched observations include paired antennas, and the bounded panels reuse development clips. The table reports descriptive associations without confidence claims or population calibration. No orbit, position, survey or archived factor value entered the diagnostic. [Installed comparator](scout-readout.md) · [Per-lane score states](measurements/split-spectrum-score.json.gz)

## Resolution and cost

All 69 fractional checks had one distinct exact-template peak under the frozen 1% ambiguity rule. The two halves nevertheless selected the same discrete bin on **26 of 35 dense** and **29 of 34 weak** checks. Fifteen of the 16 sub-bin diagnostic differences at or below 70 Hz shared their integer winner. In a noiseless 64-symbol control, ±35 Hz at the middle of a bin gives **0 Hz** on the integer grid. Moving the same 70 Hz difference across the half-bin boundary gives **443.892 Hz**. Three-bin interpolation gives **70.356 Hz** and **69.433 Hz**, respectively. On the measured panels the continuous split discrepancy medians were **139.44 Hz dense** and **122.17 Hz weak**. Single-bin equality is therefore too coarse to rank variation on the scale of the prior approximately 70 Hz physical-aperture discrepancy. The interpolation resolves the control and still fails the quality screen. [Sealed split spectra summaries and controls](measurements/split-spectrum-trace.json.gz)

| Measured native CPU per issued lane | Dense | Weak |
| --- | ---: | ---: |
| Ordinary release, median of three paired repeats | 0.957 ms | 1.152 ms |
| Release plus trace, median of three paired repeats | 0.970 ms | 1.175 ms |
| Paired increase, median [range] | 1.34% [0.90–1.77%] | 2.26% [1.28–4.62%] |
| Python peak/rank extraction, amortized across issued lanes | 0.114 ms | 0.229 ms |

The resident native clocks include the full signed primary call and trace reset. The trace reuses the ordinary eight frame power FFTs and adds even/odd accumulation plus four extra spectrum finishes, one for each half and each template. Peak/rank extraction uses the four normalized spectra and is charged separately. There are no additional IQ reads, trials, fitted phases or reruns in the timed trace arm. The parity audit calls the original verifier entry separately to read its flags. All factor tuples reproduced byte for byte for three interleaved repetitions of each lane, and all compared flags agreed. Forty-five dense and two weak lanes had no scout confirmation. Each confirmed lane reached a fractional result with both templates and eight origins. [Build, flags and paired clocks](measurements/split-spectrum-trace.json.gz)

## Related receiver experiments

The earlier held-block scout readout nominated a replacement CFO and score from a different pilot-symbol aperture and changed which factors survived. This tap uses the existing exact and rolled verification apertures, keeps the same published factors, and asks only whether the independent frame subsets conditionally agree. The common scout and integer stencil use those same origins and can carry a common error into both halves. Interleaving limits the equal-weight centroid separation to 1.333 ms. Slope and unequal frame power can still affect the split. The separate effective-epoch audit estimated a short-to-full centroid correction and found small effects on physical captures. This study changes no timestamp. The continuation-quality study tested a prospective variance weight from causal neighboring measurements and found weak coverage. Split spectra are available without neighboring visits, but coverage by itself provides no calibrated weight. [Held-block readout](scout-readout.md) · [Effective epoch](short-primary-epoch.md) · [Continuation weighting](continuation-quality.md)

## Reproduction

The relinker authenticates and reproduces the original release binary, then rebuilds one verifier object using the archived 12 ms stencil include. An initial trace build resolved the full-aperture stencil include and failed factor parity. The authenticated short include fixed that compile-path error before the trace was sealed. An initial dense outcome lookup used sparse cadence factors and had only one rank-zero counterpart. The final scorer uses the already saved installed all-visit factors for both panels and joins exact CI16 digests. Neither correction changed the frozen metric or clip roster.

Use a writable local bulk work directory. The physical signed archive requires the existing archive-readable `leo` account. The same scope, release assets, scratch paths, and original 18-clip ZIP are pinned in the trial and build receipts. Set the five numerical thread variables and `OMP_THREAD_LIMIT` to one, and run each command under `flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2`.

1. Run `python -BPs -m reports.ALGO08.v3.split_spectrum_build NEW_BUILD`.
2. Run `python -BPs -m reports.ALGO08.v3.split_spectrum_trial observe NEW_BUILD/build.json WEAK_ZIP NEW_TRACE.json.gz`.
3. Seal the trace with SHA-256. Run `python -BPs -m reports.ALGO08.v3.split_spectrum_trial score NEW_TRACE.json.gz TRACE_SHA256 NEW_SCORE.json.gz`.

The committed trace was sealed at `63c114293`, before the all-visit outcome join, with SHA-256 `5ff3bb04368a461979a2840074e37164b82bce78d8eb1d12c68e407f565da39d`. The final score SHA-256 is `2c3e0f045a02755376992ab691ebc0583729459a340f291590a6f740d6ea64f5`. Four component tests check quantization, continuous resolution, circular wrap, ambiguity, blank spectra and tie-safe rankings. [Tests](../../../tests/pipeline_eval/test_split_spectrum.py)
