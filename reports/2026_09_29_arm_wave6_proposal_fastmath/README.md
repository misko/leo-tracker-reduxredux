# Wave 6 proposal-only fast-math qualification

Physical ARM4 qualification averages **947.167 ms/dwell** versus 960.455 ms
for strict Wave5 v2 (1.38% lower). All 182 candidates and 119/119 standard
hits match on this small target panel, and the owned all-rate unit passes.
This small saving is not included in the preferred exact combination; the
larger host comparison below shows that general candidate equivalence changes.

This experiment begins from sealed `arm_wave5_final/builds-v2`.  Only the
separately compiled `proposal_core.o` receives `-ffast-math`; full search,
conditioned stages, and the FP64 final GLRT retain strict compilation flags.

Fast math can reassociate proposal arithmetic and alter denormal or NaN
behavior.  It is therefore not expected to have exact candidate parity.  The
owned proposal unit exercises zero and full-scale CI16 inputs at all four rates
and repeats top-four selection; normal frame construction exercises unequal
lag tails.  Host704 candidate differences and frozen hit recovery are required
qualification outputs.  ARM execution is not part of this artifact.

Host and sanitizer units passed; the ARM binary cross-built only.  Host704
changed 12 candidate objects in 5 of 15,488 windows and emitted 86,440 rather
than 86,439 candidates, so this is explicitly non-exact.  Its frozen standard
audit nevertheless retained 19,217 of 19,581 reference-positive hits, the same
recovered-hit count as the strict final.  No host timing comparison is used to
predict the ARM result.

The frozen host704 identity comparison found the same 19,217 matched reference
hit identities as strict final-v2: zero lost and zero gained.  All emitted JSON
numeric fields were finite.  The five changed windows contain 11 paired
candidate field changes (coarse/refined epoch, CFO, score, and final values)
plus one inventory addition; `fastmath-identity-qualification.json` records
the compact field counts.  Equal aggregate recovery therefore does not imply
exact numerical behavior.
