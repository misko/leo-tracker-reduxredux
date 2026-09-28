# Fixed donor-center diagnostic

Before computing its distance, freeze the diagnostic to exactly the inherited
`geographic_prior_center_deg` in `config/ds7/baseline-wave2-ready-v1.json`.
No coordinate, radius, offset, averaging rule or parameter is fitted or chosen
from reference error. Use the unchanged DS7 evaluator's horizontal metric and
minted pose authority.

This is a coordinator-only, post hoc context check of the already exposed
initialization. It is not an observation-based fit or a substitute for the
full88 evaluation. Do not feed its reference distance or coordinates to model
workers or alter any frozen model. Record source hashes and the exact inherited
center in the receipt so the amount of prior location information is visible.
