# Off-grid conditioned frequency transfer: 480 synthetic calls

Preparation only until parent publishes the source-hashed protocol. No recording,
RF, orbit, positioning or receiver-reference inputs. No universal error weights
will be fitted from this experiment.

Use the same actual native conditioned scorer and signal construction as
[120](../2026_10_09_position_error_iter120/SYNTHETIC_PROTOCOL.md), with acquired
CFO, true epoch and fractional offset zero. Inject the complex ramp
`exp(+2*pi*i*f*n/Fs)` into the signal **before addition of receiver noise**.
Multiplying by the on/off support mask commutes with that ramp; noise is
neither masked nor frequency-shifted.

Frozen factorial design:

- `Delta = 1/(512*4.4e-6)` Hz; injected `f/Delta = [-.4,-.2,0,.2,.4]`.
- Signal multipliers `[.25,1]`; unchanged complex receiver noise RMS1.
- One turn-off at `[.00015,.001,.020]` seconds in a 20 ms, 2.5 MS/s lower-edge
  pilot; no signal-energy normalization or extra orientation experiment.
- Sixteen **new** seeds122000..122015, reused across cells to preserve identical
  noise. Thus 5×2×3×16 = **480** calls, one single-thread process.
- Admission: exact minus control >=.025 only. No host .175 floor, acquisition
  success or fractional bracketing predicate is asserted by these calls.

All phase offsets are strictly inside the nearest-bin-zero cell. The ordinary
nearest-bin rounding explanation predicts bin0 and error `-f`; any nonzero
returned bin is an extra-bin error relative to that ideal, not a physical
227 kHz alias. Preserve estimated frequency, injected frequency, error, bin,
exact/control/margin, admission and time for every row. Summarize each cell's
admission with Wilson95 intervals, unconditional and admitted-only bin-error
histograms, signed bias/RMS and runtime. Undefined admitted-only metrics stay
undefined; no filtering of poor cells, replacement seeds or outcome tuning.

Compare matched noise seeds across phases and support levels descriptively.
Within each cell the16 seeds are independent; between-cell results are
correlated. No formal multiple-testing rejection threshold or model promotion
gate is declared. The question is whether errors look like ordinary rounding,
or support/amplitude/phase-dependent peak mistakes incompatible with a simple
fixed symmetric grid-error mixture. An outcome cannot calibrate blind detection,
operational uncertainty, realistic fading/occultation or position error.

Before execution, four source-only signal tests verify zero-phase bitwise
parity with120, both ramp signs, unrotated/unmasked noise, and commutation with
the support mask. They make no native estimator calls. Source hashes and an
exclusive start claim precede build/run. A crash after claim is explicit
incomplete evidence and cannot trigger an automatic rerun. The compiled build
receipt/library hash are retained; no binary publication is required.
