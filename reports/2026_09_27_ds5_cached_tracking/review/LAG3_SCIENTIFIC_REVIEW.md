# Scientific review of a lag-3 phase CFO proposal

This review addresses the physical meaning of the proposed lag-3 CFO phase.
It does not benchmark DSP, modify the implementation, open holdout IQ, or
authorize a detector claim.

## Result

Lag 3 removes a carrier **alias** over the declared search interval, but this
does not make its phase an unbiased CFO estimate. The identity is exact only
for a correctly timed, scalar-channel copy of the detector template. Unknown
OFDM data, frequency-selective pilot response, fractional timing, frame-boundary
rounding, mixtures, and a weak correlation all enter as an unknown phase term.
At the required 8 kHz association tolerance, the allowed nuisance phase is only
0.0603 rad at 2.5 Msps and 0.0302 rad at 5 Msps. Synthetic pilot-only success
therefore validates implementation and sign, not physical accuracy.

The implementation must compute phase from a direct native-rate correlation
after native timing refinement. The existing 512-bin rank correlation phase is
not a qualified CFO gauge, and a nonzero magnitude is not a sufficient support
test.

## Exact ideal identity

For lag `L`, let the residual-CFO-free signal be `z[k]`, and let

```
x[k] = A z[k-e] exp(j (omega k + phi)),   omega = 2 pi f / Fs.
```

The observed lag product is

```
pL[k] = x[k+L] conj(x[k])
      = |A|^2 exp(j omega L) z[k+L-e] conj(z[k-e]).
```

The native source builds the template product as
`s[(k+L) mod n] conj(s[k])`
([coarse_differential.h:24](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/coarse_differential.h:24)) and correlates the folded observation with its conjugate
([coarse_differential.h:46](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/coarse_differential.h:46)). Both template and observation have their respective means removed. In the ideal case `z=s`, mean removal commutes with the common
`exp(j omega L)` factor, so the direct correlation is a positive real energy
times `exp(j omega L)`. Constant receive phase and a scalar complex channel
cancel in the lag product.

Thus

```
f_hat = Fs arg(RL) / (2 pi L), modulo Fs/L.
```

For `L=3`, the principal intervals are:

| Rate | Alias period `Fs/L` | Principal interval | Margin beyond +/-400 kHz |
|---|---:|---:|---:|
| 2.5 Msps | 833.333 kHz | +/-416.667 kHz | 16.667 kHz |
| 5 Msps | 1,666.667 kHz | +/-833.333 kHz | 433.333 kHz |

This establishes unique phase unwrapping within `[-400,400] kHz`. It says
nothing about the phase error of `R3`. Near +/-400 kHz at 2.5 Msps, modest
phase error can also cross the principal boundary and produce an approximately
833 kHz wrap.

## The nuisance phase in the real signal model

With timing error, channel distortion, data, or interference, write the direct
correlation as

```
R3 = exp(j 3 omega) C3(e, timing, channel, data, interference).
```

The estimate is then

```
f_hat = f + Fs arg(C3)/(2 pi 3), modulo Fs/3.
```

An 8 kHz CFO error corresponds to only:

| Rate | Maximum `abs(arg(C3))` for 8 kHz |
|---|---:|
| 2.5 Msps | 0.06032 rad = 3.456 degrees |
| 5 Msps | 0.03016 rad = 1.728 degrees |

The shorter physical lag at 5 Msps halves the allowable phase error even though
its alias interval is wider.

The local template generator confirms why `C3` cannot be assumed real. It
decodes 300 published base-4 states on eight edge subcarriers
([templates.py:27](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/starlink/templates.py:27)), synthesizes their complex sum at the receiver sample times
([templates.py:77](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/starlink/templates.py:77)), and explicitly describes the result as a **pilot-only** frame
([templates.py:107](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/starlink/templates.py:107)). It initializes all samples to zero and adds only those eight subcarriers. It does not model unknown data subcarriers or a per-subcarrier channel.

For the captured waveform, all components sharing one carrier CFO still receive
the common `exp(j 3 omega)` factor. But data-data and pilot-data lag products,
and pilot products under unequal subcarrier gains, contribute to `C3`. There is
no finite-window orthogonality in the code that forces their sum to be positive
real. Fifteen repeated frames may average some random data terms, but that is a
statistical hope rather than an identity.

Fractional timing has the same problem. A delay rotates the eight subcarriers by
different phases. The resulting lag-product waveform is no longer the exact
integer template, so its direct correlation can have nonzero argument. The
rank grid makes this material: `n/512` is 6.51 samples at 2.5 Msps and 13.02
samples at 5 Msps, or 2.604 us in either case. Phase must be recomputed after a
native-rate timing refinement, rather than read from the projected rank bin.

Frame geometry introduces another bounded mismatch. Frame starts are rounded
from `frame*Fs/750` in native code
([window_rank.c:209](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:209)) and in the local injection helper
([polynomial_injection.py:154](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/research/polynomial_injection.py:154)). The ideal periods are 3333 1/3 and 6666 2/3 samples, so the discrete starts alternate 3333/3334 or 6667/6666 sample gaps. The existing injection places a separately sampled discrete template at those rounded starts
([trajectory_qin_injection.py:150](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/research/trajectory_qin_injection.py:150)); it does not synthesize a continuously timed transmitter frame across the +/-1/3-sample boundary phases. Also, the differential template wraps its last three samples modulo rounded `n`, while the observed fold reads three subsequent recording samples. Seam cases need an explicit control.

## Code-specific correctness requirements

1. **Use the direct native correlation.** The earlier phase experiment added a
   direct sum of `folded * conj(template)` and used its argument. That is the
   correct gauge to test. The window-rank FFT path computes
   `conjf(X*conjf(D))` followed by another forward FFT
   ([window_rank.c:310](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:310)). Only its magnitude and epoch were qualified; its complex phase has an unproven sign, scale, and shift.
2. **Preserve the lag-product sign.** Native CI16 folding uses
   `imag = ar*bi-ai*br`, which is `b*conj(a)`
   ([ci16_fold.h:51](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/ci16_fold.h:51)). The development sparse lag-3 scout uses the opposite imaginary sign because it discards phase. That scout expression must not be copied into a phase estimator.
3. **Refine timing first.** Recompute `R3` at the retained native timing cell;
   do not reuse the 512-bin projected complex value. Test the circular seam at
   epochs `0`, `1`, `n-2`, and `n-1`.
4. **Expose support.** Return raw complex `R3`, its normalized magnitude, the
   native epoch, and a separate `phase_supported` status. Noise almost always
   produces a nonzero complex sum, so the earlier `magnitude > 0` check is not
   a scientific gate. Freeze any magnitude/contrast gate before reference
   outcomes.
5. **Keep proposal and decision semantics separate.** Noise, tones, and rolled
   controls may still yield a proposal. They must not become detections unless
   unchanged exact/control confirmation passes. An unsupported phase is unknown
   CFO evidence, not absence.

## Bounded synthetic controls

The following fixed vectors are sufficient for the first scientific check; no
large sweep is justified. Run both rates, both edges, and both receiver lanes
where the wrapper has lane-specific addressing.

| Family | Fixed cases | Required interpretation |
|---|---|---|
| Ideal sign and alias | CFO `0`, `+123456.7`, `-123456.7`, `+399000`, `-399000` Hz; global phases `0`, `0.7` rad; two positive amplitudes | Direct `R3` phase has the stated sign; high-SNR CFO error is well inside the later local-refinement radius and never wraps at +/-399 kHz. Amplitude and global phase do not change CFO. |
| Timing | Fractional delay `-0.49`, `-0.25`, `+0.25`, `+0.49` samples, plus integer epochs `0`, `1`, `n-2`, `n-1` | After native timing refinement, CFO remains within 8 kHz and source timing within 2 us, or the proposal is explicitly unsupported. |
| Frame lattice | One discrete-template placement control and one continuous-time 750 Hz restart sampled at the alternating rounded starts | The first checks compatibility with existing fixtures. The second measures the physical +/-1/3-sample boundary bias; they must not be presented as equivalent. |
| Channel | Scalar complex gain; deterministic eight-subcarrier amplitude slope; deterministic mild phase slope; one fixed nonflat stress channel | Scalar invariance must be exact apart from quantization. Each nonflat result reports `arg(C3)` and CFO bias; a claimed physical estimator must meet 8 kHz on the predeclared nonflat cases. |
| Unknown data | Three frozen QAM seeds at three declared aggregate data-to-pilot powers, constructed in the same sampled OFDM band | Report CFO bias and normalized support for every seed. Pilot-only success cannot substitute for this family. |
| Dynamics | Constant CFO and one frozen linear-CFO trajectory spanning 8 kHz over 20 ms | Define truth at the lag estimator's weighted temporal center. Do not compare a 15-frame average to an arbitrary window edge. |
| Specificity | Zero, seeded noise, stationary tone, rolled-17 control pilot | Proposal output may be present, but unsupported phase cannot be promoted and complete exact/control decisions must remain negative for noise/tone/control. |
| Mixtures | Two pilots with declared CFOs; pilot plus stronger stationary tone; two timing-close pilots | A proposal may match either declared pilot within 8 kHz/2 us. A third hypothesis is failure. Do not assign one oracle CFO after observing the result. |

For ideal template cases, build CFO as a continuous phase over the entire
120 ms visit; restarting carrier phase at each frame would erase the condition
being tested. Quantize to CI16 only after summing all declared components and
record clipping counts. The pure-tone differential becomes constant and should
vanish after mean removal; pilot-tone cross terms are why the combined case is
still required.

Freeze case membership, seeds, component powers, channel coefficients, truth
hypotheses, timing/CFO tolerances, and the support rule before running the
proposal. The proposal must then retain the existing development reference
positives and pass the final exact/control controls before any validation or
holdout access. A successful bounded synthetic result establishes only that
lag 3 is implementable under those models; real-IQ retention is still needed
because the local generator omits unknown data and measured channel response.
