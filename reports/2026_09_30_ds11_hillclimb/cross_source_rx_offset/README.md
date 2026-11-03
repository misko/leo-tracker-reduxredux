# Same-time, same-RF cross-source receiver-offset support

The frozen diagnostic is unsupported: none of the eligible target pairs has
the required three other conditional satellite identities at the same RF with
at least six shared training visits. This is a data-support result, not a
rejection of a shared receiver-path offset model.

Of 604 exported cross-receiver pairs, 101 have fewer than six common training
visits. Of the remaining 503, 453 have no eligible donor identity and 50 have
one. None has two or three. No prediction errors or position fits are produced,
and the support threshold is retained.

A posthoc descriptive inspection of scan16 finds all 16 eligible receiver pairs
have native RX1-minus-RX0 offsets between -20,706.08 and -19,625.18 Hz. The
conditional NORAD67103 pair is -19,807.35 Hz. These pairs span several selected
NORAD identities and RF bands; they are not all simultaneous. This consistency
argues against treating the target pair's approximately 20 kHz offset alone as
evidence of a wrong association. It does not establish common emitter identity,
measure a calibrated hardware oscillator offset, or validate a drift model.

The repository's capture profile includes an LNB frequency-conversion stage
(`src/leo/contracts/profile.py`), while the DS7 receiver-clock plan explicitly
leaves physical SDR-versus-LNB state sharing unresolved. A presumed common SDR
clock therefore cannot justify forcing the two complete RF paths to equal CFO.
No deployment-specific oscillator topology was independently verified here.

The diagnostic reads existing training-derived CFOs and verifies their saved
provenance digests. Two tests pass for circular wrapping/medoids and donor
identity/support isolation. Execution completes successfully in under one
second. `outcome.json` binds the exact input, protocol, executable and tests.
The original IID endpoint already used these target observations, so even a
supported leave-source result would not constitute independent validation.

A future cross-band or sequential receiver-offset model would need a separate
protocol and controls for units, drift and source-specific signal differences.
The existing DS7–9 differential-drift and frequency-fusion failures remain
relevant; this support audit does not justify repeating those fits unchanged.
