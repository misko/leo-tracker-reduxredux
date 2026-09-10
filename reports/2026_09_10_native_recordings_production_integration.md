# Native recording production integration

This intermediate application release integrates the native recording CLI,
registry, API and browser view onto production development base
`9982c792230cb12c7cdf85123b75acb5a0da3e9c`. The original native refinement
worktree predates deployed adaptive scanner features and must not replace the
application wholesale. This branch preserves those features and adds the five
reviewed recording commits from the native worktree.

The recording view exposes retained native measurements and original runtime
outcomes. It does not qualify acquisition, original native IQ, physical
precision, sustained operation or Doppler accuracy. Radio commissioning and
the prepared controller/native-IQ operators remain separate release work.

Production-composition tests exercise both the default registry and an explicit
registry setting. They use the real application factory and routes, refuse
PostgreSQL connections, discover a publication added after startup, preserve
its failed runtime outcome, and expose later artifact damage as unavailable.
Two type annotations fix full-source type-check failures in the native bundle
hash map and variable-length CSV column list without changing persisted V1
contracts or numerical behavior.

Evidence under `/srv/bulk/leo/glrt-deployment-20260909`:

- `native-production-integration-v1.xml`: 69 passing production composition,
  native API and recording CLI tests.
- `native-production-mypy-v2.log`: all 473 source files pass with the locked
  development and hardware dependency groups installed.
- Integration UI run: 74 passing tests across App, NativeRecordings,
  AdaptiveAnalysisPanel, AdaptiveHopPanel and ScannerGlrtPanel; TypeScript and
  Vite production build pass.

Deployment must use the ordinary full-release path: this delta adds contracts,
operations and CLI modules outside the API-only fast boundary. Staging is
permitted for a clean local HEAD and does not select or restart production.
Cutover still requires publication on main, exact-revision test evidence and
the release qualification enforced by the deployment front door. No selector,
service or radio change is claimed by these integration tests.
