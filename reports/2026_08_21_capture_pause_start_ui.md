# Capture pause/start control

## Outcome

The web header now exposes one state-aware **Pause / Start** capture control. It uses the same durable capture authority file and kernel acquisition lock as the CLI and supervisor; the browser does not call systemd or access PostgreSQL directly.

## Semantics

- `POST /api/v1/capture-control/pause` is idempotent and immediately writes the durable `paused` admission desire. It returns `pausing` when a dwell already owns the radio and never cancels that dwell.
- While paused or pausing, the acquisition supervisor does not claim another durable acquisition operation. Pending dwell and scanner rows remain in the acquisition queue.
- `GET /api/v1/capture-control` reports the typed desired and observed state. The first read after the active radio lease drains advances `pausing` to `paused`.
- `POST /api/v1/capture-control/start` is idempotent and reopens admission. The supervisor resumes claiming the preserved queue in its existing order.
- Missing or unreadable authority state produces a bounded `503` response and a disabled UI control, not a server exception or a misleading state.

## Verification

- Authority tests cover non-blocking pause, active-lease drain, durable state, idempotent start/pause, and claim fencing.
- API tests prove the exact two POST exceptions to the otherwise read-only v1 surface, bounded failures, and unchanged acquisition queue contents across pause/resume.
- React tests cover accessible state labels, `aria-pressed`, disabled/pending behavior, and both actions.
- Production-composed Playwright uses an isolated migrated PostgreSQL database and real local capture authority. It proves a queued dwell remains present across pause/resume and records no HTTP 5xx or browser error.
