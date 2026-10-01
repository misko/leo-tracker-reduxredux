# Adaptive CFO alias-context default

The default `cfo-trajectories` PNG now retains all four channel panels and adds
half an alias period above and below the canonical CFO interval. The canonical
boundaries are ±113.636364 kHz; the displayed bounds are ±227.272727 kHz.
Shaded exterior bands contain copies shifted by exactly ±227.272727 kHz.
They do not add observations, candidate associations, or tracking evidence.

This changes presentation only. Artifact names, persisted overview contracts,
analysis configuration, tracking configuration and already-sealed PNGs remain
unchanged. Both firmware and host adaptive overview entry points share this
renderer. A job with an existing sealed overview returns that overview; future
overview publications use the new style.

## Scoped production installation

Adaptive workers use runtime release
`47e2705e437722daa5e6d6bb1c252d54b7a21dbc`. The scoped installation copies its
installed `leo` package into a new root-owned snapshot under
`/opt/leo-adaptive-cfo-alias/FULL_SOURCE_COMMIT/src/leo`, excluding bytecode caches,
then substitutes only `presentation/adaptive_hop_analysis.py` from the tested
source commit. Before staging, the installed renderer is checked byte for byte
against its baseline Git source. The staging manifest records the baseline,
source revision, renderer hash and hashes for every file in the snapshot.

The adaptive-worker template receives a final `zzzz-cfo-alias-context.conf`
drop-in setting `PYTHONPATH` to that snapshot's `src` directory. Its existing
Python executable, dependency environment and command remain unchanged. Only
the adaptive analysis workers are restarted. Capture, API, publication and
general processing services are not restarted. No RF collection is used for
qualification; validation renders sealed metrics from
`scan-fw-d44b363970d434a2` with the production Python runtime.

Verification checks the effective environment and running processes of all
adaptive workers, plus the imported renderer location under the `leo` account.
To revert this scoped renderer update, remove only that drop-in, reload systemd
and restart the adaptive analysis workers. Existing published figures remain
immutable in either direction.
