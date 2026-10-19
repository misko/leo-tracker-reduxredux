# DBG01 source overlay

These files archive the research tools and tests used by the DBG01 example and
scan-217 follow-up. They are evidence, not imports used by the running repository.
`sha256.json` identifies the captured bytes. Existing ALGO01 scientific fixtures
and source snapshots are unchanged.

For an isolated replay, restore `reports/ALGO01/source_snapshot` into a new
workspace, then overlay the `tools`, `tests` and `src` paths from this directory.
Restore the frozen report inputs at their recorded repository-relative locations;
large radio/orbit archives are local authorities and are not fetched automatically.
Run commands from that workspace root with its configured `.venv` and
`PYTHONPATH=src:tools`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`.
Do not run a tool in place inside this snapshot: scripts derive their repository
root from their own path.

The source overlay includes transitive local research-tool imports where needed.
It does not turn the case-specific scripts into a generic public API. See the
DBG01 specification for which stages are mandatory and how GPS-only diagnostics
are separated from inference. QNAP sources remain read-only.
