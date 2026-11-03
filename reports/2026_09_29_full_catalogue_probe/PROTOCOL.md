# Bounded full-catalogue shortlist probe

Select the first frozen outside-pool target by time in each DS7/DS8/DS9 and
the first three bank-eligible tracks by track ID. No residual, posterior or
reference-error selection. Evaluate at the existing N24 location and timing
offset zero only. This is a nine-track local completeness probe, not a new
position fit, integrated-timing test or observer-independent localization.

Reconstruct the exact original catalogue using the bank manifest's baseline
snapshot and provider snapshots via read-only TleArchiveReader. Reproduce
newest-per-object selection and catalogue row identity. Propagate all catalogue
objects at the actual track epochs, then apply the original training-mask
horizon visibility rule. Check retained predictions against the existing bank
at its zero timing node to <1e-6 Hz.

Compare original-export robust top-candidate selection with the current
Student-t4 contrast densities, training and complete track. Report retained
conditional signal likelihood mass, best full-catalogue candidate inclusion,
and q020 signal responsibility under uniform retained-visible versus
full-visible candidate priors. The latter changes normalization and is a
diagnostic, not a drop-in posterior correction. Preserve invalid propagation
counts. Three workers capped at 120 seconds, no RF or archive mutation.
