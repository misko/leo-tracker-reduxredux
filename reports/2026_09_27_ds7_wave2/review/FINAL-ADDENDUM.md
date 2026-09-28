# Final first-eight audit addendum

This addendum extends the earlier review snapshot without modifying it.

`solver/first8-panel-v1` is now sealed. Every file listed in its seal recomputes
to the recorded digest. Its four new single units and `group8-01` have validated
responses, and the group response binds all eight frozen ready captures with 486
eligible tracks and the two recorded frozen-mask exclusions.

`solver/scan-estimate-index-first8-v1.json` contains exactly the first eight
ready sessions and one scan-estimate artifact for each. The ordered member set
matches `group8-01`. The eight scan estimates exactly match their cited sealed
single-response estimate, convergence flag, boundary flag, and RMS. Full source
paths and hashes are recorded in `scan-estimate-provenance-first8.json`.

No geographic score, reference value, fit, or IQ artifact was used in this
addendum.
