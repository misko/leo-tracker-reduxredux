# Source-only reference-field dependency audit

This inspection reads source code only, not actual receiver references or errors.
Frozen106 numerical code is unchanged.

The claim “the inference engine reads no reference fields” is too absolute for
the complete legacy loader chain. More accurate: **reference values/errors do
not construct the numerical model, choose starts/banks/winners or qualify fits;
one legacy loader validates an archived error field for artifact consistency.**

## Executed loader dependency

106engine→87audit.reconstruct→85dependencies.load→84evaluate's51cohort_inputs.load.
In [cohort_inputs.py](../2026_10_09_position_error_iter51/cohort_inputs.py#L43),
the `legacy_ds16` branch checks each persisted baseline selected arm against the
pinned old recovery receipt's `arms[arm]["actual"]`. Lines45–52 compare exactly:
`objective`, `selection_score`, **`horizontal_error_m`**, `source_basin`, `satellites`.
The error value is asserted equal; it is not thresholded, minimized, transformed
into a correction or passed to a fit. Nevertheless, changing only that archived
error field can cause an assertion/input failure. It is therefore a provenance
admission dependency, not complete reference nonaccess.

The same loader's branch selection is by frozen `kind`; completion selection is
by stored status/baseline_mode and file availability. These decisions do not
compare reference error. It returns `previous` artifacts, but87reconstruct ignores
that return value (`case, baseline, _`). Legacy DS17/loading helpers construct
RegionalPrior() and banks from prepared observations/causal TLEs, verifying saved
identities. Their reference-bearing document is carried as an artifact; the load
functions do not read reference latitude/longitude to build geometry.

The original old document digest also includes reference fields. Canonical-digest
or full-artifact equality is provenance validation, so changing references changes
admission. It does not make a fixed bank/start adapt toward a known location.

## Numerical use after loading

[87audit.py](../2026_10_09_position_error_iter87/audit.py#L34) chooses the frozen
archived fitted-c region source, selected satellite numbers/calibration and
converged B3/B4/B4W/B5 states. `arm_selected` retrieves the already selected arm;
it performs no sorting by error. Bank pruning uses fitted relative timing; centers
use assignment responsibility and observation times. No reference/error field is
consulted in these choices.106engine then uses the same archived fitted B7 vector
and full clock seed for all four fits, with independent physical/clock KKT and
the predeclared fallback chain. No actual reference value influences that sequence.

Other imported modules contain report functions that evaluate references, but
those functions are not invoked by this reconstruct path. In particular the old
baseline `run()` applies reference coordinates only after selecting its output;
106does not call it. Source presence alone is not proof of an executed dependency.

## Conclusion and future improvement

No reference-guided optimization/selection blocker identified. Disclose the legacy
archived-error equality check and digest-level reference admission dependency.
For future107 loading, use frozen byte/canonical-hash provenance plus inference-only
payload validation instead of fieldwise horizontal_error_m checks. Keep numerical
reconstruction and evaluation authorities separate. Do not modify the frozen106
loader to make this statement cleaner after execution has begun.
