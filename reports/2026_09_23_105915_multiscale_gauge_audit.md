# 105915 multiscale phase gauge audit

This audit concerns the existing continuous 105915 IQ only.  Splitting the
same IQ into shorter chunks tests estimator information loss and coordinate
handling; it does not simulate an analogue retune.

| Mechanism | Code path | Invariant test |
|---|---|---|
| Pilot coherent sum | `correlate_pilot_symbols` forms a source/RX/symbol correlation; `coherent_pilot_frames` derotates symbols then sums them | Sum after each source/RX carrier derotation, then form RX products and the source double difference. Forming the RX product first mixes sources and is not equivalent. |
| Nominal NCO | `correlate_pilot_symbols` removes `2π f (n-reference)/Fs`; `restore_receiver_relative_phase` restores it to the declared common sample | Re-run identical synthetic IQ with a changed chunk start/reference. After adding the nominal phase to the same physical center, the double difference is unchanged. |
| Locally fitted residual | `fit_linear_phasor` reports phase at its supplied center | Reference a fitted residual frequency to a declared center and restore `+2π δf(t_c-t_ref)` exactly once. A free fitted phase intercept is the observation and must not be subtracted to align chunks. |
| Source timing | 105915 has different A/B epochs but paired receiver timing | Transport A and B independently to one actual `t_c`; equal frame starts are unnecessary. Treat timing uncertainty as a transport uncertainty. |
| Common receiver phase | `simultaneous_double_difference` computes `high * conj(low)` at common support | Add a phase jump `q_r` to both sources in receiver `r`: DD is invariant. Add source-dependent `q_rk`: DD changes. |
| Filtering | chunk filters may have startup and delay transients | Use known linear/zero-phase treatment and discard the same physical boundary duration in every arm; never filter through a random train/held boundary. |

For source (k), receiver (r), retain the measured complex coefficient after
template fitting as (a_{rk}^{local}).  With demodulation
`exp(-j ψ_hist,rk) exp(-j 2π δf_rk(t-t_ref))`, its raw-centre gauge is

\[
a_{rk}(t_c)=a_{rk}^{local}
 \exp\{j[\psi_{hist,rk}(t_c)+2\pi\delta f_{rk}(t_c-t_{ref})]\}.
\]

The ordinary-​\(2\pi\) double difference is
\[
\arg[(a_{1A}a_{0A}^*)(a_{1B}a_{0B}^*)^*].
\]

Mode A can use frozen historical carrier/epoch models.  Mode B can refit
residual CFO and timing from random training frames inside a chunk, provided it
does not introduce a free chunk phase alignment and applies the stated
transport on held frames.  A short chunk naturally has fewer pilot symbols and
weaker CFO/timing information.  It becomes a software phase reset only when
the estimator discards the local reference or normalizes away the fitted
coefficient phase.

These invariants establish coordinate correctness.  They do not show that a
real adaptive retune preserves receiver-chain phase or frequency response.
