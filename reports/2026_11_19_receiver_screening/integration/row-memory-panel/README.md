# Row-major compact v5 at 512 MiB on four capture-era recordings

All four capped workers were killed by the memory controller before publishing either calibration arm. The previous ordinary DS29-0082 completion still qualifies for that recording. The four new cases span both datasets and the historical lower and upper runtime strata, with the same capture-era GLRT factors, causal catalogue, original tile and CPU assignment as the earlier complete timing pairs. [Position charts](charts/index.html) · [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

| Recording | CPU | Capped service wall / CPU (s) | Last completed or entered stage | Original launcher wall (s) | Compact cavity launcher wall (s) |
|---|---:|---:|---|---:|---:|
| DS26-0026 | 20 | 111.682 / 104.897 | Residual screen returned | 368.86 | 88.15 |
| DS26-0146 | 21 | 75.843 / 70.844 | Signed context entered | 360.91 | 115.64 |
| DS29-0174 | 22 | 73.541 / 70.322 | Signed context entered | 412.57 | 83.28 |
| DS29-0316 | 23 | 92.071 / 85.035 | Family nomination returned | 408.55 | 131.34 |

The four services reported `oom-kill`, 512M peak memory charge and 0B swap. The timing columns use different completed boundaries. Compact published at cavity and original finished its late inference and reporting. The capped intervals ended at service failure. The matched historical original and compact arms each returned four fixes; the capped geographic and conditional RF cells are null. [Resources by timing scope](resources.csv) · [Both-arm calibration scores](scores.csv)

The live monitor treated `io.stat` as mandatory. This user cgroup exposes process I/O and memory counters but lacks `io.stat`. The frozen controller and run logs prove the cap outcomes. They leave worker RSS, anonymous versus file-cache charge, per-case physical scratch bytes and full live counter histories unmeasured. The scorer reclassifies those original launcher rows from `unavailable` to the actual out-of-memory failure using the hashed terminal service record. It preserves the original attempt and full log for every case. The updated live monitor accepted the same cgroup controls on a short non-scientific probe, with `io.stat` optional. The four failed scientific attempts were each executed once. [Preserved attempts](attempts.jsonl.gz) · [Launcher used for these attempts](as-executed-launcher.py)

## Workload at the failure boundaries

| Recording | Input tracks / observations | Completed coarse family passes | Late scratch boundary |
|---|---:|---:|---|
| DS26-0026 | 110 / 3,964 | 18 | First ECEF bank and residual screen returned |
| DS26-0146 | 120 / 3,646 | 0 | Signed context entered before the first ECEF write |
| DS29-0174 | 128 / 4,018 | 0 | Signed context entered before the first ECEF write |
| DS29-0316 | 137 / 4,148 | 26 | Nomination returned before the first ECEF write |
| Ordinary DS29-0082 | 70 / 2,044 | 15 | Both 11,185-row ECEF banks and TEME audit completed |

For the four failed workers, track and observation counts come from the matched compact timing control's input inventory. Per-pass regional satellite row counts were available for the completed ordinary case at 1,680 rows. The failed logs provide family-pass counts and stage boundaries. [Workload records](workload.json) · [Ordinary cap comparison](../../deployment/recovery-reads/README.md)

The signed stage still constructs whole selected-observation design matrices and refits both calibration arms when the signed gate qualifies. Its width and mean arrays also span the regional catalogue. The 64-row family nomination bounds the geometry tiles, while keeping regional score and alias arrays, complete per-family candidate receipts and a dense held-family covariance. The later ECEF screen bounds per-sweep read memory; the first ECEF bank and residual output are still alive when residual evaluation returns. Three failures preceded any late bank write, so late-bank page cache cannot explain those three. Earlier file cache and process RSS are both plausible contributors to the total memory charge. The markers delimit the failure windows and leave the triggering allocation unresolved. [Sampled signed widths](../../../../tools/pipeline_eval/variants/v5_signed_context_memory.py) · [Tiled nomination](../../../../tools/pipeline_eval/variants/v5_nomination_memory.py) · [Row-major sweeps](../../../../tools/pipeline_eval/variants/v5_recovery_reads.py)

## Rebuild the sealed scores and charts

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.row_memory_panel \
  --published --out /tmp/row-memory-panel
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence /tmp/row-memory-panel --out /tmp/row-memory-figures
.venv/bin/pytest -q tests/pipeline_eval/test_row_memory_panel.py
```

For a fresh host qualification, choose a new local report directory and a new local runs directory. Use `tools.pipeline_eval.qualification.row_memory_replay seal` then `run` with those paths. The archived scoring command uses the sealed result, historical timing archives and the repository freeze.
