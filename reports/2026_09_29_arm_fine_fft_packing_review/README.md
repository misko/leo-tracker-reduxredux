# Fine FFT packing review

This is a bounded source and evidence review of the `wave3_combined` fine
estimator. It adds no implementation and ran no ARM work.

## Actual transform input

For every selected acquisition frame, `sources/fine_precision.h` constructs

```
x_frame[k] = samples[start + k] * conj(exact[k])
```

on the selected symbols, zero fills the other positions, and executes one
single-precision complex-to-complex FFT. Both operands are complex and there is
no conjugate symmetry constraint on `x_frame`. The configured transform lengths
remain 5000, 10000, 15000, and 20000, and the preferred frame budget produces
two independent complex inputs. The control template is not transformed by the
fine estimator; it is used later by conditioned/final scoring.

## Why the usual packing identity does not apply

The standard identity that packs two real sequences as `z = a + i*b` recovers
their transforms from `Z[k]` and `conj(Z[-k])`. It depends on each original
transform having Hermitian symmetry. A fine input here is general complex data,
so its N-point transform has 2N independent real values. Two frames therefore
have 4N real degrees of freedom, while one N-point complex FFT returns only 2N.
One same-size transform cannot recover both spectra exactly.

Splitting one input into real and imaginary parts and applying that identity is
another formulation of one ordinary complex FFT, not a reduction. Splitting
two complex frames requires four real sequences. Likewise, interleaving the two
complex frames into one 2N-point complex transform needs even/odd separation
and twiddle recombination; it changes the problem to a larger transform rather
than halving the arithmetic.

There is also no exact/control transform pair to pack at this stage. The source
forms only the exact-template product above. Packing exact and control would add
a transform that the current fine estimator does not perform.

## Concrete exact option already measured

`reports/2026_09_29_arm_batched_fine_fft` implemented the feasible backend
packing: an FFTW `plan_many` batch of the two independent complex transforms.
Its component test compared every output bin with separate transforms at all
four production lengths. This preserves all math and can save dispatch or
improve scheduling, but cannot reduce the mathematical transform count.

The measured cohort rejected it:

| build | mean fine FFT time |
|---|---:|
| final-reuse ARM control, 4 cases | 296.455 ms |
| batched ARM, same 4-case protocol | 306.418 ms |
| final-reuse host control, 704 cases | 12.089 ms |
| batched host, same 704-case protocol | 23.229 ms |

The evidence is in
`reports/2026_09_29_arm_subsecond/{arm4,host704}-batched-fine-radius2/summary.json`
and the corresponding final-reuse summaries. The ARM result is about 3.4%
slower in the fine stage; the host result is about 92% slower.

## Qualification

There is no exact two-real-sequence packing opportunity in the current fine
FFT because its inputs are independent complex sequences. The only concrete
exact packing opportunity is backend batching, and the existing implementation
and measurements reject it for this target. A real-to-complex decomposition
could still be benchmarked as a different backend kernel, but it requires two
real transforms per complex frame plus splitting and reconstruction; it does
not reduce transform count and has no source-level reason to beat the measured
complex FFT.
