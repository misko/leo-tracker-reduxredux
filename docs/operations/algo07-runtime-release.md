# Qualified ALGO07 runtime composition

`tools/stage_algo07_runtime.py` packages the runtime-only contraction change
qualified in the November 3 iteration 002 report. It accepts only a full Git
revision, verifies every member of the installed original ALGO07 release against
its pinned release manifest, and checks the committed numerical parity receipts
and exact candidate kernel hash before staging.

The optional `--qualification prepared-calibration` composition additionally
loads the exact geometry and one-position curved-calibration reuse validated in
iterations 003 and 004. It accepts only the eight explicitly listed source
files, verifies their hashes against the committed implementation receipt,
checks their original installed hashes, and requires both complete replay
comparisons, all 16 paired incumbent reconstructions and the 175-case saved
policy audit. The original `contractions` qualification remains available.

The new immutable directory preserves the original release source files and
published manifests. Its explicit differences are:

- the qualified `joint_predictive_families.py` kernel;
- a worker entry point which verifies the complete new composition;
- the integrity verifier itself;
- a byte-identical copy of the original worker under the name
  `algo07_frozen_production_worker.py`;
- the qualification evidence and new composition manifest.

The wrapper delegates to the original worker after replacing its release-specific
integrity check with the complete composition check. This does not change inputs,
search budgets, numerical policy, acceptance, publication contracts, or fallback
behavior. It does not overwrite the old scientific manifests to bless changed
bytes. Python and dependencies reuse the exact tested installed environment.

The service must set `LEO_ALGO07_RUNTIME_MANIFEST_SHA256` to the stager's returned
hash. The entry point rejects a missing pin, changed manifest, unsafe member path,
or changed member before inference, and verifies the inventory again afterward.
It is compatible with the watcher `--worker-root` isolation added in iteration
001. Staging itself does not mutate services. Activate only after an isolated
installed-runtime canary and when the watcher has no active numerical child.
Rollback restores the previous worker root and its matching runtime manifest
pin. Remove the pin only when returning to an original, uncomposed release.
All old numerical releases and published results remain available.
