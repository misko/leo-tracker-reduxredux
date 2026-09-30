# Late-fitted repeating-pattern subtraction

The known tail pattern does not provide a valid direct model of the early
header. Subtracting its late-fitted prediction increases early-region energy.
In a separate held-out late window, subtraction removes nearly all shared
structure in S23, but leaves a reproducible residual in DS9-middle. Allowing
separate gains for each carrier does not explain the latter. This residual is
a target for further modeling, not newly decoded data.

## Method and controls

Read the two hash-verified expanded atlas caches: S23 upper edge, 42 qualified
paired evaluation frames; DS9-middle lower edge, 45. Retain all 28 common data
carriers. State labels come from the existing receiver-checked known-repeat
assay at symbols 194–225. Expand the exact 60-state generator using the existing
compact-carrier tessellation mapping over symbols 2–301.

Fit one complex least-squares gain per receiver and frame on symbols 226–257.
The model is `z = gain * known_state_prediction`; no unknown early observations
enter either the state selection or gain fit. Test subtraction on four earlier
regions and the separate late window 258–289. Repeat using one gain per
receiver/frame/carrier, fitted on the same 32 symbol times.

Shared correlation subtracts each coordinate's mean across frames and then
normalizes the aggregate complex cross-product, taking its real part. This
suppresses static coordinate templates. It weights coordinates by their energy
and is distinct from averaging per-coordinate correlations.

**Subtracting the same wrong prediction from two receivers can itself create
correlation.** Controls therefore mismatch RX1 frames but subtract the same
target-frame prediction from both sides, using each source frame's fitted gain.
All nonzero cyclic frame shifts are evaluated. This preserves shared-subtraction
artifacts in the controls. It is a descriptive safeguard, not a proof that
remaining matched correlation is message content or independent of calibration.

## Results: scalar gain

| Visit / symbols | Raw shared correlation | Residual correlation | Maximum shared-subtraction control | Energy removed, RX0 / RX1 |
|---|---:|---:|---:|---:|
| S23 / 2–7 | 0.261 | 0.431 | 0.241 | −36.3% / −30.0% |
| S23 / 8–33 | 0.336 | 0.434 | 0.187 | −25.8% / −19.8% |
| S23 / 34–129 | 0.307 | 0.168 | 0.057 | 23.3% / 18.5% |
| S23 / 130–193 | 0.292 | 0.034 | 0.013 | 36.5% / 28.8% |
| S23 / 258–289 | 0.285 | 0.007 | 0.008 | 37.9% / 30.3% |
| DS9-middle / 2–7 | 0.457 | 0.588 | 0.269 | −31.2% / −31.0% |
| DS9-middle / 8–33 | 0.533 | 0.574 | 0.172 | −13.5% / −12.8% |
| DS9-middle / 34–129 | 0.502 | 0.324 | 0.033 | 32.9% / 32.5% |
| DS9-middle / 130–193 | 0.494 | 0.252 | 0.005 | 39.9% / 39.0% |
| DS9-middle / 258–289 | 0.491 | 0.246 | 0.006 | 40.0% / 39.0% |

Negative removed energy means subtraction **adds** energy. Thus the larger
early residual correlations are not improved decoding scores. The model is
misapplied there, even though additional matched structure survives the control.

Separate per-carrier gains leave late residual correlation at 0.006 in S23
and 0.246 in DS9-middle; corresponding control maxima are 0.008 and 0.005.
They slightly worsen energy reduction, consistent with fitting additional noise
without explaining the shared lower-edge residual. This rejects only a simple
frequency-dependent gain explanation, not more general channel effects.

## Implications

The early unknown region should not be treated as the known tail pattern with
a different amplitude. Its receiver-reproducible structure remains unexplained.
The lower-edge late residual deserves a separate test for leakage from adjacent
carriers/symbols or another deterministic signal component before assigning
extra bits. A local linear mixture of neighboring known-pattern predictions,
fitted only on late discovery symbols and checked on disjoint symbols, is the
next discriminating model. It could explain shared distortion without inventing
a payload alphabet.

These two visits do not establish a general difference between upper and lower
edges, satellite-specific behavior, or any new plaintext, time, position, or ID
field. Their differing residuals may depend on recording or calibration conditions.

## Reproduction

Run `state_residuals.py` with NumPy and SciPy. It imports the existing generator
and tessellation implementation. Hashes, per-region metrics, gains, coordinates,
state labels, and complex residual arrays are in ignored `local/state-residuals/`.
Original decoded caches are unchanged. The report's energy statistic is
`1 - sum(abs(residual)**2) / sum(abs(observed)**2)`, without centering.

Synthetic tests verify that early observations cannot influence the late gain,
that per-carrier gains transfer on an exact model, and that subtraction of a
shared wrong model can create correlation which the control also detects.
All 21 tests in this research folder and Ruff checks pass. No new RF collection,
download, commit, or deployment was performed.
