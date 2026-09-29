# Exploratory per-rate native coarse gate

This isolated Wave4-derived variant removes a retained candidate after coarse
support validation and before fine refinement, conditioned fallback work, and
final GLRT. It keeps all 22 receiver-window searches and emits the actual,
variable candidate inventory in JSON. The only runtime inputs to the gate are
sample rate and the already-computed finite coarse score.

The frozen-cohort-selected thresholds are 2.5 MHz 0.300 (or 0.312 in the
separate loss-budget variant), 5 MHz 0.150, 7.5 MHz 0.175, and 10 MHz 0.152.
They are exploratory training selections, not a holdout policy.

| host704 variant | emitted candidates | recovered standard hits |
| --- | ---: | ---: |
| `.300` | 97,090 | 19,226 / 19,581 |
| `.312` | 86,439 | 19,217 / 19,581 |

The `.300` audit retains all prior recovered hits; `.312` removes a further
10,651 candidate entries and loses nine recovered hits. These are host
scientific audits, not ARM timing or quality claims.

Build matrices are sealed in `builds/` and `builds-312/`, with manifests
`build-manifest.json` and `build-manifest-312.json`. Host and sanitizer units
cover rate constants, equal threshold, both `nextafter` sides, NaN/infinity,
final reuse, fine budgets, and conditioned moments. `audit.py` and
`audit_312.py` preserve the frozen reference candidate count separately from
the dynamic emitted inventory. Their Python audit tests passed with
`.venv/bin/pytest`.

ARM execution is intentionally not part of this report.
