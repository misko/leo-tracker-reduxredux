# Cross-band, leave-NORAD receiver-drift screen

Use original screen indices 0,4,8,12,16,20,24,28 and conditional source pairs
from the frozen CFO audit. Match receivers by visit at identical RF and require
timestamps within 0.1 ms. Training and evaluation rows must respectively have
both original masks training or both held; mixed rows do not enter either.
Each pair needs six training rows. Differences are RX1 minus RX0 in native Hz,
wrapped modulo 1/4.4 microseconds.

For each target NORAD, exclude that identity across all RF bands from donors.
Represent each donor NORAD by the median of its pair-level median training time
and circular offset center; each identity has one vote. Require three donors.
Fit a Theil-Sen line (median pair slope, donor time separations >=1 second),
after unwrapping donor offsets about their circular medoid. Reject slopes above
20 native Hz/s, matching the earlier differential-drift safety bound.

Compare the target's own constant training offset with the donor slope plus a
target-specific constant fitted by training median. This isolates transferable
drift from constant receiver/source offsets. Apply the slope only within the
donor training-center time range; otherwise retain the constant prediction.
Report every eligible pair, unsupported fallback and held absolute circular
error. Average gains within target NORAD, then within scan. Advancement needs
positive mean and median scan gain and at least five of eight scan wins; missing
evaluation scans count as non-wins. No position fitting is authorized by this
measurement gate alone: common receiver drift remains unidentifiable.

All frequency fits use training observations only. The source identities were
selected by the existing training-position model, so this is conditional held
measurement validation, not authenticated association or independent site
validation. Read no geographic reference and use no new IQ or orbit data.
