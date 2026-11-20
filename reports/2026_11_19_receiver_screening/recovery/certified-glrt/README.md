# Certified coarse GLRT recovery

The fixed tap-prefix bound could eliminate **zero of 21,504 sampled coarse cells** at 11, 22, 33 or 40 of 44 taps. Exact guarded-acquisition reuse also saved no work on these visits. It preserved all 16 public payloads byte for byte and retained all 22 original integer and fractional positives, including their CFO, epoch, raw margin and rank. The two capture configurations also matched on empty, noise, and the off-lattice faint pilot controls. The study supports keeping the existing Q10 detector.

## Groupwise decision bound

With unit-norm reference `h`, fixed observed IQ norm `||x||`, and any processed tap prefix `P`, the normalized coarse contribution is at most

```text
(|dot(x[P], conj(h[P]))| + ||x[remaining]|| ||h[remaining]||) / ||x||
```

Each remaining term includes the same trial CFO phase, whose modulus is one. The upper bound averages these terms across the same supported anchors and frames as the original detector. The audit compares against the realized exact eighth retained score. This threshold is optimistic because a streaming search would need enough exact peaks to establish it. The observed cutoffs were 0.16991 to 0.17421. At each fixed tap boundary the bound remained above the cutoff on every measured cell. The full-score calculation put all sampled cells below the cutoff. The sample spans all 21 CFOs at 128 stratified raw epochs for each of eight receiver acquisitions. Each of the direct kernel's four real dot sums is bounded by the appropriate IQ and template norms. Their combined binary32 rounding allowance is conservatively below `2e-5` after normalizing and taking the magnitude. The diagnostic adds that allowance before declaring any cell below the cutoff.

## Exact reuse

The adapter shares repaired coarse rows, the exact NMS output, and fine FFT results only inside one guarded acquisition scope. It validates the IQ and template bytes, frequency bits, geometry and peak-selection arguments. A component test forces an identical nested retry to exercise both hits. In the real held trials neither hit occurred. The extra producer acquisitions switched to a different fallback-anchor geometry. A shared tone-basis implementation across that separate boundary would require storage or eager folding for both anchor sets.

| Paired held CPU | Q10 | Scoped reuse | Change |
| --- | ---: | ---: | ---: |
| Coarse | 12.380 s | 12.508 s | 1.03% more |
| Full detector | 25.556 s | 25.618 s | 0.25% more |

The adapter allocated up to 5,653,272 additional bytes for immutable IQ, template and coarse-row snapshots in the measured receiver scope. Timings pool two alternating runs per visit on CPU 12. One position worker began while the second capture's held audit was running. The CPU timing and zero reuse counters describe the intervention, and wall time reflects that shared-core scheduling as well.

## Partial-IQ position confirmation

The fresh DS26-0036 v5 fit uses the actual held detector outputs for eight raw visits and 16 receiver rows. The other 6,757 valid visits use archived detections. The matched control is the independently computed original-archive fit from the Q10 trial, verified against its preserved digest, the identical underlying capture archive and the causal catalogue. The fresh and control native input digests are distinct. Prepared observations, tracking arcs, final owners and numeric outputs agree exactly in both calibration arms.

| Calibration arm | Position error | Conditional RF RMS | Frequency score |
| --- | ---: | ---: | ---: |
| `c = 0` | 1.278365 km | 74.760916 Hz | 25,232.145635 |
| Fitted `c` | 1.208143 km | 74.682298 Hz | 25,232.285586 |

[Fresh position](positions.jsonl.gz) · [Matched archive control](control-positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

[Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Qualification](qualification.json)
