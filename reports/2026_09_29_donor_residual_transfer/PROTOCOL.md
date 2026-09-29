# Conditional candidate residual-slope transfer diagnostic

Freeze all 25 donor-only fitted groups and nine original eight-scan target
panels. No new position, timing or identity fit. Replay complete training scores,
per-track training/held scores, signal responsibilities and candidate weights.
Export residuals for each candidate with signal responsibility times conditional
training weight >=0.5, retaining excluded tracks and reasons. These are selected
conditional cases, not asserted identities or a replacement mixture likelihood.

Require at least five training observations spanning at least five seconds.
Fit an ordinary training-centered linear residual slope; report canonical
exported Hz/s, not calibrated oscillator units. No clipping or fitted correction
bound is applied in this diagnostic. All offsets use the target's own training
residual mean and time mean, never target held data.

For each target case, use only donor groups whose latest observation precedes
the target recording start. Within each such group and identical receiver/exact
RF, calculate a median slope from the same catalogue candidate and a separate
median from other catalogue candidates. Retain only groups with both types.
Require at least two matched groups, then take the median of group medians for
the satellite-specific and receiver/RF control predictions. Equal group weight
prevents a track-rich recording from dominating the transfer.

Compare baseline zero-slope, satellite-specific slope and receiver/RF control
on the same target cases using median absolute held residual after the identical
training offset. Also export training errors, per-group slopes and group IDs.
This descriptive selected-candidate residual error is not a normalized held
mixture score, geographic improvement or identity probability. Report complete
target denominators and unmatched cases. Do not tune thresholds after outcomes.
No correction proceeds to geography solely from this diagnostic.

Three prelaunch tests verify exact linear transfer, held isolation, short-track
exclusion, strict whole-group chronology and matched RF/group controls. One
fixed-point child per group/panel, sequential, timeout90s, AS4GiB, BLAS1/nice19,
available memory >=5GiB. Preserve failures, no retries. No RF, IQ, propagation,
archive/provider access or production changes.
