# Receiver screening position errors

Roof plots compare each study on its scheduled recordings against all four original v5 options. Matched stock fits use the inputs and solver boundary described on each page. Blank rows retain failed or withheld attempts in the denominator. Diagnostic estimates appear only when a receiver saved one.

Wrong-region and independent-site results have their own figures. V5 enters only the paired original-tile comparisons. A false published point remains visible.

## Roof comparisons

**Fitted calibration** · [PDF](fitted_c/modifications.pdf) · [Per-sample CSV](fitted_c/modifications.csv)

- [Shared receiver clock on ten matched recordings](fitted_c/joint_clock_model-matched.png)
- [Track-sized early Doppler projections](fitted_c/v5_track_projection.png)
- [Embedded Schur fit on two roof recordings](fitted_c/embedded_schur_fit.png)
- [Full-roof position accuracy on 135 recordings](fitted_c/full-receiver-comparison-roof135.png)
- [Full-epoch Q10 GLRT with a paired v5 position fit](fitted_c/dense_q10.png)
- [Archived IQ through ordinary GLRT and joint orbits](fitted_c/iq_to_joint.png)
- [Shared receiver clock on two ordinary detector donors](fitted_c/native_joint_clock_model-ordinary-donors.png)
- [Native smooth oscillator on 135 roof recordings](fitted_c/native_clock_full-roof.png)
- [Full native joint orbit replay](fitted_c/native_joint_full-roof.png)
- [Causal per-orbit phase width on the common owner mask](fitted_c/orbit_prior_history.png)
- [Fixed 2.5 s phase width on the common owner mask](fitted_c/orbit_prior_equal.png)
- [Privileged owner oracle · Common mask · lean owners and matched aliases](fitted_c/owner-oracle-common-lean-owners.png)
- [Privileged owner oracle · Common mask · v5 owners and matched aliases](fitted_c/owner-oracle-common-v5-owners.png)
- [Privileged owner oracle · Full v5 conditional mask · lean exact fit](fitted_c/owner-oracle-full-v5-lean.png)
- [Privileged owner oracle · Common mask · v5 owners and compact clock/prior](fitted_c/owner-oracle-common-v5-clock.png)
- [Privileged owner oracle · Full v5 conditional mask · compact clock/prior](fitted_c/owner-oracle-full-v5-clock.png)
- [Privileged owner oracle · Full v5 conditional mask · compact diagonal noise](fitted_c/owner-oracle-full-v5-diagonal.png)
- [Sparse native GLRT tracks with the matched joint orbit fit · primary](fitted_c/native_simple_tracks-primary.png)
- [Sparse native GLRT tracks with the matched joint orbit fit · confirmation](fitted_c/native_simple_tracks-confirmation.png)
- [Fixed training assignments on all 135 roof recordings](fitted_c/native_train_update-roof.png)
- [Reuse the causal orbital bank in complete v5 reassociation](fitted_c/v5_recovery_bank_reuse.png)

**Zero calibration** · [PDF](c0/modifications.pdf) · [Per-sample CSV](c0/modifications.csv)

- [Shared receiver clock on ten matched recordings](c0/joint_clock_model-matched.png)
- [Track-sized early Doppler projections](c0/v5_track_projection.png)
- [Embedded Schur fit on two roof recordings](c0/embedded_schur_fit.png)
- [Full-roof position accuracy on 135 recordings](c0/full-receiver-comparison-roof135.png)
- [Full-epoch Q10 GLRT with a paired v5 position fit](c0/dense_q10.png)
- [Archived IQ through ordinary GLRT and joint orbits](c0/iq_to_joint.png)
- [Shared receiver clock on two ordinary detector donors](c0/native_joint_clock_model-ordinary-donors.png)
- [Native smooth oscillator on 135 roof recordings](c0/native_clock_full-roof.png)
- [Full native joint orbit replay](c0/native_joint_full-roof.png)
- [Causal per-orbit phase width on the common owner mask](c0/orbit_prior_history.png)
- [Fixed 2.5 s phase width on the common owner mask](c0/orbit_prior_equal.png)
- [Privileged owner oracle · Common mask · lean owners and matched aliases](c0/owner-oracle-common-lean-owners.png)
- [Privileged owner oracle · Common mask · v5 owners and matched aliases](c0/owner-oracle-common-v5-owners.png)
- [Privileged owner oracle · Full v5 conditional mask · lean exact fit](c0/owner-oracle-full-v5-lean.png)
- [Privileged owner oracle · Common mask · v5 owners and compact clock/prior](c0/owner-oracle-common-v5-clock.png)
- [Privileged owner oracle · Full v5 conditional mask · compact clock/prior](c0/owner-oracle-full-v5-clock.png)
- [Privileged owner oracle · Full v5 conditional mask · compact diagonal noise](c0/owner-oracle-full-v5-diagonal.png)
- [Sparse native GLRT tracks with the matched joint orbit fit · primary](c0/native_simple_tracks-primary.png)
- [Sparse native GLRT tracks with the matched joint orbit fit · confirmation](c0/native_simple_tracks-confirmation.png)
- [Fixed training assignments on all 135 roof recordings](c0/native_train_update-roof.png)
- [Reuse the causal orbital bank in complete v5 reassociation](c0/v5_recovery_bank_reuse.png)

## Wrong regions and new sites

**Fitted calibration** · [PDF](fitted_c/transfer.pdf) · [Per-sample CSV](fitted_c/transfer.csv)

- [Shared receiver clock with the correct tile omitted](fitted_c/joint_clock_model-wrong-offer.png)
- [Ordinary GLRT and joint orbits with the correct tile omitted](fitted_c/iq_to_joint_missing_tile.png)
- [Native smooth oscillator with omitted tiles](fitted_c/native_clock_full-omitted.png)
- [Native joint with nine omitted tiles](fitted_c/native_joint_full-omitted.png)
- [Held region support with development-calibrated noise](fitted_c/tile_region_empirical-fresh.png)
- [Development-calibrated region support on hard offers](fitted_c/tile_region_empirical-replay.png)
- [Local Doppler region support at two new sites](fitted_c/tile_region_support-fresh.png)
- [Local region support on known hard offers](fitted_c/tile_region_support-replay.png)
- [Sparse native GLRT tracks with the matched joint orbit fit · transfer](fitted_c/native_simple_tracks-transfer.png)
- [Fixed training assignments with the correct region omitted](fitted_c/native_train_update-omitted.png)

**Zero calibration** · [PDF](c0/transfer.pdf) · [Per-sample CSV](c0/transfer.csv)

- [Shared receiver clock with the correct tile omitted](c0/joint_clock_model-wrong-offer.png)
- [Ordinary GLRT and joint orbits with the correct tile omitted](c0/iq_to_joint_missing_tile.png)
- [Native smooth oscillator with omitted tiles](c0/native_clock_full-omitted.png)
- [Native joint with nine omitted tiles](c0/native_joint_full-omitted.png)
- [Held region support with development-calibrated noise](c0/tile_region_empirical-fresh.png)
- [Development-calibrated region support on hard offers](c0/tile_region_empirical-replay.png)
- [Local Doppler region support at two new sites](c0/tile_region_support-fresh.png)
- [Local region support on known hard offers](c0/tile_region_support-replay.png)
- [Sparse native GLRT tracks with the matched joint orbit fit · transfer](c0/native_simple_tracks-transfer.png)
- [Fixed training assignments with the correct region omitted](c0/native_train_update-omitted.png)
