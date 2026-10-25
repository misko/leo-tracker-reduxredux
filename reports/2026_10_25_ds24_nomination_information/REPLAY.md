# Published evidence and replay limits

This is a compact research record: new code/tests, frozen protocols, source
ownership inventory, generated target draws and diagnostic results, covariance
arrays, independent audits, tables and figures. The publication manifest lists
the exact supplied bytes. No production algorithm or accepted association is
changed. There are no new position fits, IQ reads or RF recordings.

The original DS24 fast-scan inputs are stored in the shared
`/srv/bulk/leo/research/ds25-20261024` research directory. That directory name
does not make these scans DS25 recordings. Information ranking uses the exact
0010–0013 reference-node identities, aliases, masks and saved RF endpoints,
plus previously reconstructed full accepted-ID ledgers. Its
[inventory](information/inventory.json) and
[protocol](information/protocol.json) bind those files, original tracking/noise
products, causal orbit banks/history and reused research sources. The original
full tracks, banks and prior runtime are not duplicated in this report.

The [nomination protocol](nomination/PROTOCOL.md) documents the narrower
conditional generator: new physical/unresolved CFO curves on two inherited
source layouts, conditioned on real parent calibration. It does not reproduce
GLRT selection, the complete robust parent hierarchy, a population of arbitrary
source layouts or actual RF clutter. It does not certify identity probabilities.
Its frozen input/generator/observation bindings are retained with the new
outputs; catalogue truth is never supplied to ordinary nomination.

Earlier source construction and covariance conventions are described in the
immutable [phase/shape and later-panel report](https://github.com/misko/leo-tracker-reduxredux/blob/a3ae6254d2dee7dc25e794eac06279fee9631c03/reports/2026_10_25_ds24_phase_shape_validation/README.md)
and [causal identity/component report](https://github.com/misko/leo-tracker-reduxredux/blob/a3ae6254d2dee7dc25e794eac06279fee9631c03/reports/2026_10_25_ds24_identity_components/README.md).
Full dependencies are referenced by path/hash and those earlier reports rather
than republished as another runtime capsule. A hash binds bytes; it does not
supply them or make an unavailable archive reconstructible.

Numerical execution uses the repository `.venv/bin/python`, NumPy/SciPy,
`src` and `tools` on `PYTHONPATH`, the original research modules and
`/tmp/algo03-feasible-deps`. Use one BLAS/OMP/MKL thread per worker. Information
ranking used one worker; catalogue nomination permits at most two. Each branch
has its own 600 s numerical budget, frozen failure rules and matching independent
preflight. The source scripts and protocols retain their exact original paths;
they refuse output overwrite. Re-execution needs complete matching external
inputs, a fresh output location and a separately declared bounded run. Merely
opening or packaging the report does not authorize a rerun.

`information/ranking.py` exports the complete local Gaussian old/new designs and
sufficient statistics. `audit/information_terminal.py` can independently replay
the conditional information and joint nuisance elimination from those arrays
without orbit propagation. `information/summarize.py` reads sealed numbers only.
These checks do not turn the local Gaussian design approximation into nonlinear
phase-mixture information, calibrated confidence or position accuracy.

The publication supports inspection of the saved evidence and its numerical
audits. It is **not a standalone full scientific-input/runtime restoration**.
All 24 DS24 development cases and the eight RX1V later cases are exposed; the
present four scans are development diagnostics, never an untouched validation
panel. The operational reference remains unchanged.
