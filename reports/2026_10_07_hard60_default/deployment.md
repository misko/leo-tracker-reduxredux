# Hard60 rollout receipts

The implementation and experiment report are prepared in an isolated checkout
from remote main 55a5a419dffdfc23d14dda2b159797542d263b63. The existing research
checkout is preserved. This file is updated with final production verification
after cutover; preparation checks alone are not deployment evidence.

## Prepared change

The standard adaptive tracking queue now requires scanner-regional-position-v2,
whose single method is V16 under the named hard60-v1 policy. Published V1
contracts and namespaces remain unchanged. The V2 API adds a digest-bound PNG
route; the WebUI prefers V2 and explicitly labels historical V1 fallback.

The worker policy is σrelative=2 s, σcommon=3 s, hard ±60 Hz/s stage-specific
added slopes, nearest-measured edge priorities, 40/20/10/5 km, 400 points,
three regions, and stationary-only final selection. Both final c arms remain.

## Qualification completed before cutover

- 115 affected Python tests passed using the production Python 3.14 interpreter
  in the initial component run. Subsequent tests and the deployment gate are
  recorded below when complete.
- 51 affected WebUI tests passed; TypeScript and the production Vite build passed.
- All 64 saved Hard60 search orders reproduced exactly.
- 54 frozen final states matched the original likelihood and gradient within
  the declared 1e-6 absolute tolerances.
- Six same-start coarse fits reproduced saved objective values exactly.
- The new numerical kernel is built into the Python package; no report folder
  imports, runtime compilation or silent numerical fallback are used.
- A saved N29 capture replay is running through the complete CLI/input/TLE/search/
  publication path in an isolated output root. No new RF is being collected.

## Scope and rollback

The staging operation copies the effective immutable worker and API source trees,
applies only the reviewed role-specific delta, and records inherited/replaced file
hashes. Existing files being replaced were checked byte-for-byte against the
reviewed main base. The API's built UI is staged alongside those sources.

Cutover changes only the final analysis-worker, queue and API drop-ins. Workers
retain their existing SIGINT cancellation/requeue behavior, scratch roots,
concurrency limits and capture admission cutoff. The capture service/timer and
database schema are unchanged.

Rollback removes this rollout's Hard60 selector drop-ins, reloads systemd, and
restarts the same affected analysis/API services. Earlier selectors remain.
Retain all V2 products and digest-scoped checkpoints; V1 readers ignore them.
No data deletion is part of rollback.
