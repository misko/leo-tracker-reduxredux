# Repository collaboration rules

- `leo-tracker` and `leo-tracker-redux` are references and numerical oracles,
  never runtime dependencies.
- Public persisted contracts are immutable within a published major version.
- Components communicate through contracts and narrow ports, never private ORM
  models, constructed storage paths, or another component's implementation.
- Analyzers do not import PostgreSQL, HTTP, CLI, or concrete storage modules.
- QNAP adapters are read-only. No code in this repository may delete, move, or
  rename a path beneath `/mnt/qnap01`.
- Golden scientific fixtures change only through explicit review; do not update
  them merely because a test fails.
- Every component change includes component-owned tests. Hardware, QNAP, and
  PostgreSQL requirements must be explicit test markers, never silent skips.
- Keep the implementation lean. Add infrastructure only in response to a
  measured need that the existing PostgreSQL and local-filesystem design cannot
  meet.
- Use `apply_patch` for hand-written file changes and preserve unrelated work.
- Development must prioritize lean iterations over the existing on-disk radio
  corpus toward truthful QAM, known-pilot, Doppler, and Starlink candidate
  evidence. Do not start, wait on, or disappear into multi-hour radio campaigns.
  Any new RF collection requires explicit user authorization, must be bounded to
  at most 30 minutes, and must not displace recording CLI/UI or re-analysis work.
