# WP11 operational CLI

`leo process wp11` is an explicit selected campaign lane. It never changes the
Standard/default processing graph.

- `create` verifies an accepted capture receipt and publishes one immutable plan
  binding the campaign ID, exact detector configuration, deployed pipeline release,
  30 sessions, 40 streams, and legacy receipt names.
- `queue` creates one deterministic `evidence_only` native-to-matched run for each
  of the 30 sessions. Exact retries return the same run IDs; differing existing runs
  fail as conflicts.
- The ordinary `leo process worker` can execute these selected jobs. Its dynamic
  wrappers resolve the immutable run binding before delegating to the frozen native
  and matched analyzers. Those wrappers are execution-only and are excluded from
  automatic/default runs.
- `finalize` resolves the 40 sealed matched products and calls the trusted campaign
  production facade. `show` authoritatively re-resolves sealed campaigns and returns
  only the bounded presentation summary and durable references.

Create requires `--config` containing `MatchedPilotAcceptanceConfigV1`. Legacy
receipts are bound as `legacy-<first 16 hex characters of SHA-256(campaign_id)>-NN.json`
for ordered stream ordinals `00` through `39`; they must already exist in the
configured confined legacy evidence root before processing/finalization.

Required local roots are configured with `LEO_QUALIFICATION_ROOT`,
`LEO_CAPTURE_EVIDENCE_ROOT`, and `LEO_LEGACY_EVIDENCE_ROOT`. PostgreSQL uses
`LEO_DATABASE_URL`. QNAP and noncanonical/double-slash aliases are rejected before
storage access.
