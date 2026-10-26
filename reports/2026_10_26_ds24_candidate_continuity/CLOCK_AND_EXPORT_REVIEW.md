# Epoch continuity must use device time

This is a source/contract review before the new recorded persistence outcomes.
The original DS24-0011 export and deployed producer remain unchanged.

`src/leo/processing/fast_scan.py`, in `tracking_input`, maps each native
window's `sample_start` to `valid_start_counter`, sets `probe_start_ms=0`, and
sets `payload_start_sample=visit*window_samples`. The latter is an index in
packed payload data; it excludes guard intervals and retune gaps. It must not
be used as a device-time coordinate. The historical deployed producer has the
same mapping. `src/leo/analysis/research/public_tracking_points.py` independently
constructs start = valid_start_counter + round(probe_start_ms*fs/1000), verifies
integral probe support, and uses the device counter for observation identity
and the midpoint timestamp.

The historical `leo/analysis/starlink/fast_scan_scores.py` samples at
epoch_sample + round(frame*fs/750) + relative_symbol_sample + fractional_offset.
Thus a positive fractional epoch adds to the acquisition-window time. For
same-receiver continuity, the appropriate nominal circular frame coordinate is

    local_epoch = integer_epoch_sample + fractional_epoch_offset_samples
    start = valid_start_counter + round(probe_start_ms*fs/1000)
    phase = ((start - origin) + local_epoch) mod (fs/750)

Use the source's declared common device origin. At integer fs, evaluating
the counter remainder as `((start-origin)*750) % fs / 750` before adding
local_epoch preserves integer arithmetic and avoids cancellation of large
absolute counters. Do not add a midpoint offset: the epoch is relative to the
window start, while CFO observations conventionally use its midpoint.
Changing the common origin rotates all phases by a constant and must not
change same-lane path membership. The exact period is fs/750, not its rounded
integer value. At 10 MS/s the period is 13,333⅓ samples.

This construction preserves the nominal frame phase measured by the detector.
It does not prove the transmitter clock is constant or that physical sources
cannot change timing. A fitted drift or an unresolved discontinuity must
remain possible. Neither local epoch nor an epoch/CFO-coherent path by itself
establishes a satellite identity. Avoid cross-receiver registration in this
first within-lane inventory.

The saved tracking candidates contain rank, integer/fractional epoch, final
fractional CFO, exact/control scores, margin and gate state. They omit
acquired CFO and the separate refinement residual. The numerical synthetic
outputs contain those additional fields, but the recorded adapter must not
invent them or derive them from the winning final value. Preserve unavailable
fields as null and use only common available fields for a transferable policy.

The prior nearby-peak inventory retains 501 alternative records. Their CFO
separation could reflect alternate refinements of one signal. Before looking
at the distribution, root declares a descriptive readback: for every one of
those 501 saved pairs, compute distance to the nearest nonzero integer multiple
of the deployed 443.8920454545 Hz refinement-bin spacing; report counts within
1, 5 and 25 Hz, all distances and the full histogram. Do not call these counts
a calibrated false-source rate, change the persistence gate based on them, or
assert that bin alignment proves one physical source. This readback does not
read IQ, run the detector, or select a satellite or position.
