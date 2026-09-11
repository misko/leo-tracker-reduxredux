# Why better timing does not always lower the reported CFO RMS

Better pilot alignment can help CFO estimation, but the current pipeline has
another source of error after acquisition: the residual frequency grid. The
earlier statements that 5 Msps does not consistently improve CFO should not be
read as evidence that its timing benefit has no value.

This diagnostic reuses the paired sample-rate experiment. It selects the same
59 successfully recovered **pure time-shift** cases across both rates and both
GLRT grids, at acquisition steps 500/100 Hz. No frequency rotation was imposed.
It asks how much the estimated CFO nevertheless changes when the waveform is
shifted in time. This is different from the earlier test that imposes a CFO
change and scores its recovery.

| Input rate | GLRT grid | Delay-recovery RMS | Unintended CFO-change RMS |
|---|---:|---:|---:|
| Filtered 2.5 Msps | 512 | 24.84 ns | 46.60 Hz |
| Native 5 Msps | 512 | 9.39 ns | 48.74 Hz |
| Filtered 2.5 Msps | 8192 | 24.77 ns | 9.18 Hz |
| Native 5 Msps | 8192 | 9.38 ns | 3.75 Hz |

At grid 512, the timing benefit coexists with similar CFO sensitivity. At grid
8192, the native 5 Msps path also has substantially lower CFO sensitivity to
the imposed time shifts. This is evidence consistent with the intuition that
better alignment can help once the frequency correction is sufficiently fine.
It does not establish that timing alone causes all of the rate difference:
the filtered copy also has reduced bandwidth, and success selection remains
conditional. It does not measure absolute frequency accuracy.

A concrete 5 Msps example makes the bottleneck visible. The waveform was
delayed by 32.977 ns. The 512-grid estimator recovered 24.717 ns of that delay,
an error of -8.260 ns. No frequency shift was imposed, but its CFO moved by
343.625 Hz. The same rank-zero acquisition candidate was selected before and
after the delay.

```text
Final CFO = acquisition CFO + residual GLRT correction

512-grid change:
    -100.267 Hz + 443.892 Hz = +343.625 Hz

8192-grid change:
    -100.267 Hz +  83.230 Hz =  -17.037 Hz
```

The acquisition estimate is formed using integer timing, before fractional
GLRT refinement. The initial CFO estimate can therefore change when the
waveform's fractional alignment changes. The final GLRT must correct it, and
a 443.9 Hz grid can make that correction jump too far. Both grids achieve
similar fractional timing in this example; the finer frequency correction
accounts for the much smaller CFO change.

This example was selected post hoc as the largest delay-induced CFO change
among the supported native 5 Msps, 500/100/512 cases. It illustrates an observed
failure mechanism, not the typical error. Median absolute unintended CFO
changes in the common cases are only 0.87–1.54 Hz across the four rows, so a
small number of larger changes matter greatly to RMS. Every error is retained.

There are three distinct limits to the interpretation:

- Delay recovery measures response to an imposed change; shared absolute
  timing biases can cancel. The 9.4 ns result is not absolute timing jitter.
- The rate comparison changes digital sampling and retained bandwidth
  together. It does not isolate an ADC-rate effect.
- Real-track cubic RMS includes acquisition errors, association problems,
  receiver/transmitter behavior and model mismatch. A coarser estimate can
  conceal variation and appear closer to a cubic without being more accurate.

The next causal test would hold each IQ waveform fixed, sweep a controlled
timing error, and compare CFO errors against an independently known CFO,
using both frequency grids. That would establish how much of total frequency
error is timing-limited, separately from translation consistency.

[Numerical diagnostic](diagnostic.json) binds the parent summary by SHA-256
and preserves the exact example estimates and frequency decomposition. This
is a derived diagnostic; no additional recording or raw-IQ replay was run.
