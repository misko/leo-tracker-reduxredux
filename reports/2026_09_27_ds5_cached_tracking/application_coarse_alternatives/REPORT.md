# Coarse-grid alternatives result

Neither concrete rounded-template alternative accelerates the production
AVX2/FMA coarse grid. Both preserve the component science within the frozen
tolerance, but direct `np.correlate` is 2.1–3.6 times slower and the batched FFT
is 5.5–11 times slower.

The experiment used the production 11-row CFO grid, the actual rounded complex128
Qin template, 12 production anchor symbols, and complete 20 ms receiver probes.
The correlation alternative ran one valid short FIR per symbol/CFO pair. The FFT
alternative reused one probe FFT and processed a 12-CFO kernel bank one symbol at
a time. Both then applied the same frame/epoch fold, support, energy normalization,
and output layout.

| Rate | Production AVX2 | NumPy correlation | Correlation relative speed | NumPy FFT | FFT relative speed |
|---|---:|---:|---:|---:|---:|
| 2.5 Msps | 26.072 ms | 95.117 ms | 0.274x | 286.941 ms | 0.091x |
| 5 Msps | 102.402 ms | 219.196 ms | 0.467x | 568.000 ms | 0.180x |

These are median process CPU times from one warmup and three cyclically
counterbalanced repetitions on P-core 0 with numerical thread counts fixed to
one. The complete bounded run took 9.3 seconds.

Random, zero, and injected Qin-pilot fixtures were evaluated at both rates. Peak
indexes matched exactly for every CFO row. Maximum map error was 7.8e-16 across
all fixtures and variants, far below the frozen 1e-10 tolerance. This validates
the formulations as close numerical variants, but does not make them bit-exact.

The frozen promotion gate required a 10x stage CPU speedup at both rates. Neither
variant approached it, so the experiment stopped before saved-IQ application
calls. No acquisition-identity or scanner-decision claim is made from the
component fixtures. The result supports the source audit: 11- and 22-sample
kernels are short enough that production's fused direct AVX2 loop beats generic
correlation and FFT machinery.

This closes generic rounded-template convolution/GEMM-style correlation and FFT
as routes to 10x for the existing coarse statistic. Further large gains require
less repeated application work, a different statistic with separately frozen
detection gates, or changes above this component boundary.

Frozen evidence:

- `design.json`: `14a4211410b98895d6765173eb7bb41da663d06fca8e7753946b78ff5cc55535`
- `alternatives.py`: `1ec1834020b53a6a2f38be218cdca69389f6b3df45ca2d9a084781da162b5e2c`
- `run_experiment.py`: `7cd697138c6a82cee8c4deaa25af84422d6e9e3a97bbcd26771d0c93a21a2c18`
- `source_lock.json`: `08269edea98173f04e4a7f6a6ff4efe9de81c207346f8705ef3feada838d313d`
- `results.json`: `935cc7dd7896552cb2d32b36f2147138449a04aba9796dd17c7ff07e4e1d72df`
