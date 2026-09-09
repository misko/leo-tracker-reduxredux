# Scanner: frozen dependency build and inactive release verification

September 9, 2026. **A full immutable candidate release is staged, not selected
for production. No radio access, RF collection, firmware or FPGA changes were
performed in this checkpoint.**

## Result

The candidate at
`/opt/leo-tracker/releases/06c1fd88320e899f70f5ccb1df91b4bc76fa29c9`
was built through the production stager with `--scanner-glrt`, frozen Python
dependencies and `--no-editable`. PPU and native libiio were fetched at exact
published Git commits rather than imported from development worktrees. The
stager built the web application, verified installed entrypoints and native
ABI, sealed ownership and the 25-line external metadata inventory, and passed
the published-release validator. Repeating the stage verified the existing
release without rebuilding or changing it.

The previously packaged ARM companion bundle is unchanged. The newly built
host native library and Python binding also match the earlier canary runtime
byte-for-byte, although this release uses Python 3.14.4 and the updated PPU
package. This byte comparison is not a new RF qualification of that combined
Python environment.

| Authority | Exact revision |
| --- | --- |
| Leo candidate | `06c1fd88320e899f70f5ccb1df91b4bc76fa29c9` |
| Installed PPU | `6b577ac229fe4b7b43528ff469dd197f9550e268` |
| Installed host libiio | `a1088b61de3c57762cfed5533e1baf8076a7b726` |
| Packaged ARM provider source | `4323b93a17ff2a0e8954fc5ffd9367a40540bebe` |

The PPU candidate is published on `codex/arm-glrt-host-integration`, and the
libiio candidate on `codex/arm-glrt-frame-integration`. The host libiio commit
is an ancestor of the latter. Installation fetches the exact SHA, never a
moving branch. No main/master merge was performed.

The Python project, lockfile, dependency provenance and component-owned pin
test now agree on the exact PPU revision. Lock regeneration changed only the
two PPU references, with no unrelated package updates. The pin test parses
the lockfile and requires one exact PPU package source, rather than accepting
an arbitrary textual occurrence of the commit.

## Build isolation and first-attempt failure

The build ran in a temporary systemd build unit limited to 200% CPU,
low CPU/IO weights and priority, 6 GiB memory-high and 8 GiB memory-max, with
a 20-minute hard runtime limit. This unit runs the stager; it is not a scanner
or a production service. The successful attempt took approximately 28 seconds
wall time and peaked at 1.5 GiB memory.

The initial unit lacked the Git ownership context inherited by an ordinary
`sudo` invocation. Git rejected the user-owned worktree before a release was
created. The retry supplied a process-local `safe.directory` entry for the
single reviewed source path. No global Git trust configuration changed, and
no ownership or immutable-release checks were disabled. Both attempts' logs
are retained.

The `current`, `current-api` and `current-acquisition` selectors remained on
`39146ee83d00523fbd37ba02179c87a5c241a017`. API and acquisition PIDs remained
3852279 and 3852299, respectively, with their September 7 start timestamps.
No production restart, configuration change or database migration occurred.

## Tests and scope

| Check | Result | What it establishes |
| --- | --- | --- |
| Deployment component | 282 passed | Pin consistency, staging and artifact/metadata checks |
| Scanner tests against installed Python 3.14 packages | 314 passed | Selected CLI, radio adapter, contracts, publication, storage and API paths |
| Web Vitest suite | 139 passed | React/component behavior, not deployed Chromium E2E |
| PPU offline suite, Python 3.13 | 3,399 passed; 1 skipped; 10 deselected | Broad dependency regressions; explicit transmitter oracle unavailable, hardware/browser lanes excluded |
| PPU paired-capture tests, local Python 3.11 | 57 passed | Local reproduction attempt; does not clear the hosted CI failure |

Tests that cover full 300-second metadata inventories use simulated data;
they did not collect RF. The installed-package suite ran as `leo` with
bytecode/cache writes disabled and test output outside the sealed release.
The release validators passed again after these tests. Counts across the PPU
suites overlap and must not be added as independent tests.

The web suite emitted expected jsdom/WebGL-unavailable diagnostics; it is not
a visual rendering certification. The build also reported two moderate npm
audit findings and a large-bundle warning. No forced dependency upgrades were
performed, and those diagnostics are retained in the build log.

## Hosted Python 3.11 CI: confirmed pre-existing, still unresolved

The [candidate CI run](https://github.com/misko/pluto-plus-utils/actions/runs/34417309172)
passed Python 3.12, Python 3.13 and browser jobs. Python 3.11 failed these three
tests in `tests/test_paired_capture.py`:

- `test_real_public_clients_concurrently_record_and_reconcile_full_finite_envelope`
- `test_late_external_cancellation_cannot_be_hidden_by_internal_cleanup[context_after]`
- `test_late_external_cancellation_cannot_be_hidden_by_internal_cleanup[owner_after]`

The [pre-existing main run](https://github.com/misko/pluto-plus-utils/actions/runs/34411241334)
at `4bc2ca6...` failed the same three tests before candidate publication. Its
paired-capture implementation and test file are byte-identical to the
candidate. Both hosted logs report the PIL1 progress queue filling, followed
by cancellation/deadline and incomplete cleanup errors. Thus this is not a
new scanner-branch change to those files. It remains a real failing supported
environment, not a failure that can be ignored because the local run passed.

Inspection shows a bounded progress queue and serialized durable journal
writes shared by concurrent producers. Queue pressure under hosted execution
is a plausible explanation, but its precise scheduling/storage cause has not
been established. No sleeps, enlarged queues, weakened cleanup assertions,
skips or unrelated paired-recorder runtime changes were introduced to make CI
green. That path needs its own reproducible diagnosis before promotion.

## Remaining release gates

The dependency availability and full frozen-build gates are now closed.
Production activation, main/master integration, exact-release qualification,
deployed browser/rollback verification and the outstanding scientific/live
gates remain open. In particular:

- The previous 5 MS/s canary preserved 94.4688% capture duty but fully screened
  only 26.63% of visits; it did not meet the 100 ms every-dwell CPU target.
- The previous adaptive 2.5 MS/s canary preserved 94.1583% capture duty and
  screened every visit, but produced no qualifying positive detections. Live
  positive-signal weighting, cooldown and reacquisition benefit remain unproven.
- A matched no-duty-regression comparison has not passed. Partial-cancel and
  hard-counter-fault terminal recovery limitations remain as previously recorded.
- Further full-length RF tests require new explicit authorization; the existing
  conservative ledger has only 140 guaranteed seconds remaining.

See the [live checkpoint](2026_09_09_radio18_live_startup_checkpoint.md) for
measurements and failed attempts, and the
[bundle checkpoint](2026_09_09_scanner_bundle_release_checkpoint.md) for exact
ARM identities. The [evidence index](evidence/2026_09_09_scanner_frozen_release/index.json)
retains test receipts, build logs, metadata, post-test validators, remote refs
and both CI failure logs. This report does not claim the implementation,
deployment and verification goal is complete.
