# Longitude controls for four-offer Doppler localization

Short CFO arcs with unknown per-track offsets can match unrelated passes by
chance. A winner among four offers can therefore have adequate endpoint
prediction but weak evidence that it is geographically informative. Longitude
rotations retain offer latitudes, relative tile layout, the visibility model,
track timing and waveform structure. They challenge the offered winner with
equally budgeted searches through unrelated parts of the same causal sky.

## Frozen decision

Run the archived arc endpoint receiver on the four original offers. If its
region check passes, challenge its held endpoint score with the 19 nonidentity
rotations in the cyclic group of order 20 around Earth's polar axis. Rotate all
offers by the same multiple of 18 degrees. Use the same 25 km square, training
samples, shortlist caps, grid, fit and endpoint evaluation for every tile. A
rotation's statistic is the maximum held score from any nominated tile with
training and held scores of at least 0.25 and held support of at least three
distinct catalogue objects. The original winner must exceed every rotated
statistic by more than the existing numerical tie tolerance. A tie or stronger
control vetoes region acceptance and publication. Stop at the first veto. A
veto does not change the nominated coordinates. Keep the original lead,
position boundary, and other gates. This rule can only reduce publication.

If the offered longitude phase were exchangeable within this group under a
no-location null, a strict maximum would have a one-sided rank probability at
most 1/20. Orbital state, actual passage geometry and offer construction can
violate this exchangeability. Nearby missing offers can carry genuine Doppler
evidence, and the controls probe longitude at the offered latitudes. Evaluate
the missing-offer error empirically and treat 1/20 as a conditional nominal
rank. A veto indicates competing predictive evidence. It does not locate the
receiver at the control tile. No thresholds are fit to the qualification data.

The original receiver subtracts a per-track constant and fits a training CFO
offset. A constant RF-dependent calibration cancels at the track's fixed RF
in the original and rotated trials. Use identical predictions in the `c0` and
`fitted_c` arms and verify equality. Report held frequency RMS independently of
position errors.

## Qualification

Generate a fresh 40-acquisition synthetic panel using the unchanged receiver
holdout generator and a new cryptographic seed. Keep the seed, truth, and
generation provenance separate from the predictor. Freeze source hashes
before generation. Predict the 80 paired fresh queries and the frozen
`transfer124` queries before opening scorer inputs. Report each panel by
present/missing condition and scene or acquisition class. Report region
acceptance, false region acceptance, position publication, false publication,
within-5-km count, and published and forced error distributions. Compare against
the original arc receiver on identical inputs and report control work. Use at
most three CPU workers on cores 17–19, with one numerical thread per worker.
Maximum extra work is 76 tile nominations and one causal propagation per
eligible query. No RF is collected.
