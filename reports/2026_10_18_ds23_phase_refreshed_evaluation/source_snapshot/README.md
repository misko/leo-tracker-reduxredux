# Research source snapshot

This is an audit copy of the DS23 experiment's Python source and statically resolved local imports, plus the dataset collectors and frozen graph configuration loaded dynamically. Paths preserve their repository layout. The [digest map](sha256.json) binds each file. No source from the `leo-tracker` or `leo-tracker-redux` reference repositories is used at runtime.

The public adaptive tracking export used the deployed **same-repository** storage port named and hashed in [export_protocol.json](../export_protocol.json). That worktree is needed only to export original adaptive tracking contracts. Numerical analysis then consumes frozen serialized inputs. This is research evidence, not a production installation or a claim that every historical helper's default entrypoint is portable.

`ds23_radio_noise_generation.py` preserves the exact source that generated the sealed radio-noise features. `tools/ds23_radio_noise.py` differs only by two line-wrap formatting changes. All ten feature documents bind to the exact generation source. The final inference source and seven core dependencies match [run_sources.json](../run_sources.json). Preparation receipts retain their earlier source hashes; later additions affect fitting and reporting rather than prepared observation membership.

Tests for membership boundaries, uniform reproducible sampling, archive integrity, scan-owned causal prior paths and radio-only variance estimation are in `tests/analysis/test_ds23_transfer_tools.py`. Related phase, likelihood and retained-track tests are included. From the repository root:

```bash
snapshot=reports/2026_10_18_ds23_phase_refreshed_evaluation/source_snapshot
PYTHONPATH="$snapshot/src:$snapshot/tools" .venv/bin/python -m pytest -q "$snapshot/tests/analysis" --confcutdir="$snapshot"
```

For a full replay, overlay these paths into an isolated checkout, recover DS23's authority from its lossless archive, and provide the checksum-bound scan inputs recorded in the input/causal receipts. Original IQ is not needed for the numerical fit. Full propagated banks and original tracking contracts remain local; published observations, tracks, TLEs, fit archives, scores and figures allow inspection without those larger files. No future TLE, reference GPS or saved endpoint should be supplied to inference. The reference coordinate belongs only to `report_ds23_phase_refreshed.py`.
