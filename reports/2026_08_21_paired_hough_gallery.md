# Paired receiver-path Hough gallery

## Root cause

The Standard graph has no paired Hough transform product. Each `path-alternate-tracks`
job consumes the exact receiver-path `standard.pilot-scan` product and publishes a
receiver-path-scoped `standard.alternate-cfo-track-bank` JSON product plus a
`standard.alternate-cfo-tracks-png` presentation product. `paired-presentation`
instead consumes the four registered path presentations and publishes the five
established aggregate PNGs (waterfall, pilot methods, raw CFO, de-aliased CFO, and
final CFO).

This separation was already preserved by the catalog and API. A paired subject
detail projects its exact `receiver_path_expansions`, and the named PNG endpoint
resolves `cfo-alternate` against an exact child receiver-path scope. It correctly
returns no artifact for the paired scope itself.

The omission was in `web/src/StandardAnalysis.tsx`: the generic named-artifact list
included `cfo-alternate` only when the selected subject was itself a receiver path.
The combined paired tab did not compose the child paths already present in its API
detail.

## Design

The paired tab now renders the exact child `cfo-alternate` PNGs in a two-column
gallery (a 2x2 layout for the normal four-path topology, collapsing to one column on
narrow screens). Every image and download link names its receiver path and targets
that child subject's immutable artifact endpoint. The panel explicitly states that
the images are independent receiver-path products and that no joint or cross-radio
Hough result is inferred.

No analyzer, product contract, schema, catalog model, endpoint, or persisted public
contract changed.

## Verification

- Standard DAG/product, API, and presentation tests: 39 passed.
- Application projection/presentation tests: 19 passed.
- Full React suite: 45 passed.
- Targeted React gallery suite: 6 passed.
- Production web build: passed.
- Ruff check and format check on changed Python: passed.
- A production Playwright assertion now runs the real four-path Standard worker,
  verifies all four paired-gallery images have nonzero natural width, and rejects
  any HTTP 5xx or page error.

The production Playwright test could not be executed in this workstation session:
the configured local `leo_tracker` PostgreSQL role lacks `CREATE SCHEMA` permission.
The server failed before app startup, without touching capture data, QNAP, or a live
service. CI supplies the isolated `leo_test` database and exercises this test.
