# Timing resolution and shared drift: declared comparison

Continue the seed-20260923 random-group dataset. The 23 retrospective-test scans
remain excluded. All prior exposure caveats and conditional candidate/seed
limitations remain. No geographic validation error selects hyperparameters.

## Fractional timing

Compare the existing integer `[-5,5]` second per-track timing profile with bounded
fractional timing. Profile each track's constant frequency offset on its saved
training mask. Use numerical interpolation only after verifying that the
approximation error is small against the relevant frequency signal; check both
boundary cases and injected known fractional timing. The independent preceding
quarter-second state audit found about 0.002 Hz RMS error after CFO removal, but
this does not by itself verify an additional time-profile approximation.

Use the same two complete validation groups (Sep22 18Z, ten scans; Sep23 08Z,
twelve scans) and their first scans. Fit capped 800 Hz and robust 150 Hz spatial
objectives with the same own-window seeds and prior intersection. Preserve all
attempted windows. Save and hash inference before reserved-frequency and
reference-coordinate evaluation. Report train/reserved gains, timing-bound
occupancy, common capped/uncapped metrics and positional errors.

Fractional timing can reduce quantization bias while weakening positional
identifiability. Lower residual alone will not count as an improvement. A local
linear nuisance profile is not a globally certified timing optimum. Report any
remaining approximation error, failed qualification or nonconvergence.

## Shared receiver drift diagnostic

Use up to twelve recordings from the **training** partition only. At fixed
training-derived scan coordinates, select identity/timing/CFO from training
frequency rows. Estimate a shared residual linear slope per scan, and per RX
only if the saved evidence provides reliable RX metadata. Evaluate reserved rows
with these quantities frozen. Keep original model results as the control.

Report slope magnitudes, between-track scatter, reserved prediction change and
metadata coverage. This is a mechanism diagnostic, not an independent location
estimate. Receiver drift, orbital error and wrong association can be confounded;
an apparent common slope does not identify its physical cause.

## Longer-duration evidence availability

Inventory older existing capture metadata without opening track/position outcomes.
Exclude the existing randomized corpus and quarantines, and preserve the future
reserve. Assess whole eight-hour groups by available nominal scans and gaps, not
by geographic fit. This inventory establishes availability only; it cannot
declare untouched data or validate a long-duration model. No new RF collection
or production deployment is included.
