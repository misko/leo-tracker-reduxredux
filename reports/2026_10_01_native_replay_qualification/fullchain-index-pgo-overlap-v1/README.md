# Lossless combined replay with downstream work below 300 seconds

On PLUTO+ 192.168.1.15, the complete previous-scan downstream chain finishes in
**297.978384 seconds**, concurrently with paced recorded-IQ GLRT/projection.
All 2,215 dwells and **16,191 positive observations** match the frozen control,
with zero rejected or failed dwells. Observation and support checkpoints are
byte-identical. Detector queue peak is **11/16** and maximum arrival-to-finish
latency is **1.553675 seconds**.

| Concurrent workload/stage | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Seed generation | 3.818102 | 3.794546 | 9,928 |
| Track reconstruction | 4.101743 | 4.076205 | 10,536 |
| In-memory conversion, orbit, search, associations | 290.016674 | 276.601569 | 151,588 |
| Whole downstream chain | 297.978384 | 284.513661 | 151,588 |
| Concurrent paced GLRT/projection | 300.853220 | 286.482418 | 55,204 |

The detector duration includes the 299.861-second arrival span, initialization,
final drain and checkpoint publication. It is not 300.853 seconds of detector
compute. This process-per-scan experiment does not establish gapless execution
across scan boundaries. RSS values are process peaks, not aggregate samples.

Seed and track checkpoints, all 400 search scores and final association JSON
are byte-identical to the existing controls. The independent host search
comparison passes its unchanged 1e-9 Hz tolerance (maximum difference
5.684342e-13 Hz). Native tracking still differs from server tracking; matching
these controls does not establish identical server memberships or positions.
Search still exhausts its 400-point budget, not global convergence.

Two changes were combined: the GLRT archive from `../ungated-glrt-pgo-v2/`
and the optional satellite-ID index from `../catalogue-index-v1/`. Relative to
the preceding in-memory overlap, downstream wall time decreases by 4.406372
seconds and GLRT CPU by 5.752468 seconds. These single trials do not isolate
the contribution of each change or establish a statistical improvement.
Search breadth, input data, priorities, and queue capacity are unchanged.

The 2.021616-second downstream margin is narrow. **Sustained 300-second cadence
remains unqualified.** Next test successive releases against one fixed
monotonic origin, preserving queued work across boundaries and accounting for
output publication and downstream backlog. Repeating this recording would be
a load test, not a genuine longer-history scientific fixture or live-RF test.

`protocol.json` pins deployed inputs and executables; `chain.sh` gives the
bounded downstream commands. `artifacts/` preserves binaries and build logs,
and `source/` plus `source-sha256.json` preserve changed source provenance.
The PGO archive SHA256 is
`b2d26282e79664d278a0180a7c8421c75f6f719ae3b128563561ce4edd886971`.
Build the detector with `native/adaptive/bench/build-recorded.sh` using the
frozen detector headers, that archive, and the same FFTW libraries as the
preceding qualified detector. The indexed session uses
`LEO_RESEARCH_IMMUTABLE_ORBIT`, `LEO_RESEARCH_CAPPED_SEARCH`,
`LEO_RESEARCH_SCORE_WARM_START`, and `LEO_RESEARCH_WARM_ID_INDEX`, linked to the
existing vector-bank128 PGO location archive. Default builds remain unchanged.

Execute with `PYTHONPATH=src python tools/run_arm_overlap.py REPORT_DIRECTORY`
after staging the pinned payloads in a fresh diagnostic directory. Existing
output paths deliberately prevent rerunning over evidence. Evaluate with
`evaluate_recorded_pacing.py`, `compare_projection_subset.py`, and
`compare_regional_results.py`; the resulting JSON receipts are included here.
`chain-comparison.json` records the complete downstream comparisons.
Host location component checks and 31 harness/comparison/PGO-recipe tests pass.
IQ stays on ARM; only evaluation products are retrieved after execution.
