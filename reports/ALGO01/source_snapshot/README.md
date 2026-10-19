# Frozen ALGO01 research source

Paths preserve repository layout. The SHA-256 map binds the source-workstation
files at report publication. The collector resolves the static local import
closure of the case tools and included tests, plus dependency declarations.
It is an audit/replay snapshot, not a new installed package or production API.

Overlay `src/`, `tools/` and `tests/` in an isolated checkout for historical
replay; also restore the graph config at its original path and the checksum-bound
case inputs described in the report. Some historical helpers have workstation
default paths; the ALGO01 entrypoints supply case-owned overrides. No large IQ,
tracking contract or propagated bank is embedded here. Read the report's exact
reconstruction prerequisites and separate inference from GPS diagnostics.

Run the included focused tests from this directory with:

```bash
PYTHONPATH=src:tools /path/to/repository/.venv/bin/python -m pytest -q tests/analysis --confcutdir=.
```

Import closure is static; deployment-time ports, archive access and dynamically
loaded file inputs still require the explicit contracts/receipts in the report.
No reference-repository runtime dependency is introduced.
