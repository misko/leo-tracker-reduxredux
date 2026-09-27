# Isolate native final symbol selection

Build a separate native library with only GLRT_SYMBOL_DIVERSITY changed from
one to zero. Keep frozen libraries, profile, guard and controllers unchanged.
This is a mechanism diagnostic, not yet an application-equivalent detector:
blind nuisance removal, fractional timing and other numerical differences remain.

First compare raw guided scores at integer timing with the application's
conditioned_glrt64_score on generated noise and known pilots, both rates and
edges. Include early-only and late-only support to ensure the intended region
changes. Use the same input, acquired CFO and aperture. Record actual error
against a fixed 1e-5 absolute score tolerance and 1 Hz CFO tolerance; failures
are diagnostic failures, not a reason to silently loosen the tolerances.
Test the final probe/RX1 and input immutability. No recorded holdout IQ is read.

If compatible scoring is established, evaluate a separate controller on the
original development/control sets before selecting a new discovery schedule.
Final qualification requires fresh disjoint recorded evidence. Pure-tone and
multisignal behavior must pass before promoting any raw-score confirmation.
