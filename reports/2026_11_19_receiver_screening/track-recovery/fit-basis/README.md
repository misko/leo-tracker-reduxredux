# Fuse compact discovery moments on complete wide factors

The optional overlay evaluates the receiver and orbital-phase sufficient statistics in one track pass. On three complete recorded wide-factor pairs, it reduced CPU in that calculation by 31.7–42.5%. Both calibration arms returned exact geographic coordinates, conditional RF RMS, frequency objectives and decisions. Whole-worker CPU and wall increased on these pairs, so the measured speedup applies to the moment calculation.

## Measured repeated work

Stock compact v5 calculates the centered measured-minus-projected residual for each track and satellite. Immediately afterward it gathers the same projected orbit columns, computes the same residual again and centers it again to form the cross term with the phase derivative. The complete wide profiles recorded 13 calls to each function. DS26-0237 spent 3.876 s in the first pass and 3.850 s in the second. DS29-0082 spent 1.496 and 1.576 s respectively. Its generic linear solves occupied 0.156 s in that profile. [Profiler measurements](profile-summary.json)

The overlay uses the same projected frequency and knot-column indices in both sets of moments. For residual \(z=y-qf\) and derivative \(h=q\,\partial_\phi f\), it computes the original \(\sum(h-\bar h)(z-\bar z)\) alongside the original residual and phase moments, retaining each method's separate time-centering arithmetic. The two compact entry points supply zero frequency corrections. A nonzero or signed-zero correction retains the original uncorrected residual for the phase calculation. Candidate order, alias handling, clock model, priors and search budgets follow the original functions.

The stock and fused passes both scale as the number of satellite-observation pairs. The fused pass removes one frequency gather, residual construction and centering per projected row set. It retains only track-local scratch and the same scan-wide output fields. It also keeps the frequency residual live while forming derivative moments in that track. The charged peak and worker RSS were lower on the three measured pairs. [Installed source diff](installed-change.patch) · [Input and executable seal](source-lock.json)

## Real candidate proof before position runs

Before candidate inference, a separate stock shadow verified every one of the 20 moment fields byte-for-byte for three live inventories on each development recording. The inventories covered 19,839,882 satellite-observation pairs. They included the fresh discovery and receiver-smooth exploration inputs. The shadow used the same 512 MiB and zero-swap cap. DS29-0127 was held from both the optimization design and the shadow. [Exact witness receipts](candidate-witness.json) · [Fixed protocol](PROTOCOL.md)

## Matched position services

| Recording | Moment CPU, stock → fused | Whole process CPU, stock → fused | Whole wall, stock → fused | Charged peak, stock → fused | Projection calls, stock → fused |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | 7.648 → 5.227 s | 75.65 → 80.59 s | 77.26 → 82.17 s | 303.61 → 301.59 MiB | 5,924 → 5,027 |
| DS29-0082 | 3.355 → 1.929 s | 36.59 → 37.11 s | 37.13 → 38.95 s | 273.66 → 259.02 MiB | 2,494 → 2,117 |
| DS29-0127, held | 5.978 → 3.871 s | 49.32 → 51.89 s | 51.14 → 52.69 s | 286.13 → 284.46 MiB | 4,558 → 3,869 |

The full pairs used the same CPU within each case, one numerical thread, 512 MiB physical cap, zero swap and a 210 s deadline. Both methods ran the same lightweight timing probe. Fresh stock matched the earlier sealed wide controls exactly on all three cases. Full wall included process launch, native-factor preparation, inference and output. Candidate work dropped by 13 repeated projected reads per track in each case. [Resources and work counters](resources.csv) · [Both-arm parity](parity.json)

| Recording | Geographic error, zero / fitted | Conditional RF RMS, zero / fitted |
| --- | ---: | ---: |
| DS26-0237 | 0.382 / 0.323 km | 92.538 / 92.427 Hz |
| DS29-0082 | 2.489 / 2.346 km | 84.421 / 84.248 Hz |
| DS29-0127, held | 0.756 / 0.721 km | 75.833 / 75.902 Hz |

Whole-process CPU would break even if the extra CPU outside the timed moment calculation stayed below the savings of 2.42, 1.43 and 2.11 s. The actual outside differences were +7.36, +1.94 and +4.68 s. These are differences between measured runs, with their causes unresolved. Both native binaries match the earlier phase-release package, and the installed default profiles retain their original source. [Both-arm error and frequency scores](scores.csv) · [Development and held figures](figures.json)
