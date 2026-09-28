# Pagination deployment

Deployed API revision `e55fe6149f45842c53167a48b61f3e0eb2c31c39` on 2026-09-27.
It applies only the pagination cache and scan-selection fixes onto the previous
live API revision `e1a24b200d4bb68d4f38484dc591e9b9616a2e70`.

The standard immutable release builder verified source identity, installed
runtime, browser build, and sealed release metadata. The component selector
helper changed only `current-api`; the API restart helper reported healthy
after 5153 ms. Acquisition remained on PID 1490541 through the cutover.

Validation: 85 backend tests, 33 adaptive browser component tests, lint, and the
production frontend build passed. Chromium on the live UI measured a previously
unseen next page at 2131 ms, Previous at 77 ms, and revisiting Next at 77 ms.
The selected scan remained `scan-fw-851486cc2a1acd99` throughout navigation.
A final warm live API request returned in 34.8 ms. Earlier initial requests
during warmup took 5.78 s and 2.50 s; cold loads still do manifest validation.

Rollback: select the previous API revision with `select-component-release api`
and run `restart-current-api`. Worker and acquisition selectors were unchanged.
