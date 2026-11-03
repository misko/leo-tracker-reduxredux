# Gradient checks near the difficult R100-02 solution

The original-measurement T1-AT cone-off fitted-c continuation remained unconverged after its extra optimizer budget. Its saved point is 3,999.26 m from the roof, with checked KKT residual 83.22. This is not a verified minimum.

Central finite differences were evaluated in the solver's scaled coordinates at steps 0.001, 0.0001, and 0.00001. The sampled coordinates cover east, north, both receiver offsets and drifts, common timing, and the RF coefficient. These are local sampled checks, not a proof about every derivative or every point. No tested pair changed visibility masks.

| Coordinate | Analytic derivative | Numeric derivative at step 0.00001 |
| --- | ---: | ---: |
| East position | -4.096989 | -4.096989 |
| North position | 7.400702 | 7.400702 |
| Scaled nuisance coordinate 2 | 34.259492 | 34.259493 |
| Scaled nuisance coordinate 3 | 7.198310 | 7.198311 |
| Scaled nuisance coordinate 4 | -52.029807 | -52.029806 |
| Scaled nuisance coordinate 5 | -3.106749 | -3.106748 |
| Common timing | 83.221950 | 83.221944 |
| RF coefficient | -15.098850 | -15.098850 |

The largest sampled gradient agrees with finite differences. Total satellite time shifts range from -17.95 to +16.58 seconds, inside the ±20 second bounds. The preceding Fisher continuation was still making downhill progress when its 60-second budget ended. These observations argue against an obvious local derivative error or a visibility-mask jump as the explanation for this saved fit; they do not establish that the associations or physical model are correct.

The saved source is `/srv/bulk/leo/recent-v16-rates-20261006/factorial-v1/continuation-v1/R100-02/original/T1AT/off/fitted-c.json`. The objective is reconstructed from its linked baseline input arrays. Position derivatives use the same ENU-to-geographic-coordinate Jacobian as the optimizer. Subsequent experiments preserve this state and the original baseline rather than overwriting either.
