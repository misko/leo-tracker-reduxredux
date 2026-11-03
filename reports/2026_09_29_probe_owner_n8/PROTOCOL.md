# Probe-level ownership with surviving track histories

Use the same 24 scans (balanced N8 set 0 per DS7/DS8/DS9) and verified quality sidecars. Resolve each probe source_group_id once: choose the eligible track with greatest ORIGINAL training-observation count, tie by track ID. No candidate margin, held signal values, reference coordinate or fit outcome enters ownership. Use all-point source identities for conflicts, preserving training/held labels.

Remove only losing observations, slicing times, frequencies, masks and candidate-state arrays together. Retain all other observations of each track. Apply the existing minimum support rule (at least two training and one held observation); explicitly ledger tracks that fail after pruning. Do not reassign their ownership in a second pass. Record unrepresented source groups after support exclusions. Keep every scan or fail explicitly if a scan has no remaining tracks.

Fit the unchanged q=0.2 contrast mixture with the original six cold/grid starts and gates. Compare against the saved all-track and hard whole-track source-consistent fits. Held comparisons evaluate every parameter vector on exactly the SAME probe-owner observation support. Report geographic distance only after selection and full observation/track coverage. This is a deterministic selection control, not a soft alternative-observation likelihood or blind validation.

Per-dataset cap 180 seconds, BLAS1. No RF, IQ reads, archived-input edits or production changes. Preserve all failed starts and support exclusions.
