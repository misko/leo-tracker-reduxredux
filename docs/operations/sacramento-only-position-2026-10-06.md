# Sacramento-only adaptive positioning

Deployed source `f8ba2d1a1` on 2026-10-06 at approximately 03:25 UTC.
New adaptive TLE positioning searches only Sacramento (250 km radius).
The V3 contract and storage namespace preserve published V1/V2 contracts;
the WebUI falls back to historical V2 results when V3 is pending.

The WebUI table and map title report the selected estimate's horizontal error
in kilometres against the configured receiver reference
(37.84903264307456, -122.4856541910174). This reference is used after fitting,
not as a search input. V3 requires errors for selected and finest estimates.

Validation: 43 component Python tests and 11 frontend tests passed; the
production frontend build and targeted Ruff checks passed. Rendering tests
cover both the new single-panel map and historical two-panel maps.

Production files and previous module copies are pinned under
`/opt/leo-sacramento-only/f8ba2d1a1`. Worker and API overlays link to the
changed modules. The API drop-in `zzzzzzzzzzzz-sacramento-only.conf` selects
the new frontend. All 19 previously running adaptive worker services were
gracefully stopped and restarted to load the V3 completion check.

Live verification: the V3 endpoint returns pending for an existing V2-only
session; its V2 endpoint still returns complete. The served frontend bundle
contains the V3 endpoint and Reference error column. API and all 19 worker
services are active. The queue resumed with six tracking and four analysis
jobs leased, with zero expired adaptive leases. A full new V3 scientific
search had not completed at this verification point.

Rollback requires stopping the adaptive workers, restoring the worker/API
module copies from the pinned `backup` directories, removing the new API
drop-in, reloading systemd and restarting the API and the same worker
instances. Preserve all V3 products; older versions ignore that namespace.
