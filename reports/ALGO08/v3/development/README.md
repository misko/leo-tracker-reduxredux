# ALGO08v3 successor qualification

The comparison starts at sealed raw I/Q and ends at process exit after the terminal result and required publications. The comparator is the installed versioned ALGO08v3 launcher, specification `6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f`. These development experiments use saved recordings and one low-priority core on Gauss.

## Development ledger

| Experiment | Physical evidence | Decision |
|---|---|---|
| Full-member prefetch and orbit-support guard | DS30-0374, 164.41 → 168.61 s. Both arms started cold. They reproduced the same detections, both fitted positions and all eight PNGs. | The orbit-support change has separate value on failures. This combination missed the latency gate. [Pair and limitations](../successor-physical-triage.md) |
| Receiver early stopping, solver layout reuse and regional rejection during fine recovery | DS30-0008, 149.89 → 155.54 s. The prototype ran first with substantially less input cached. Both calibration arms and all PNGs matched. | The measured component opportunities are small relative to the required saving. [Pair and limitations](../bounds-physical-pair.md) |

![Recorded elapsed time and horizontal error for two separate matched experiments](physical-pairs.png)

Each row is a different prototype on one physical recording. The paired error dots coincide horizontally where both builds returned the same location. Errors use the DS30 operator site reference. Pooling these rows would mix different algorithms.

## Cost budget before new raw runs

We projected the frozen ALGO08v3 stage clocks onto the original nested 4- and 16-recording assignments. For each recording the model multiplies acquisition and solver elapsed time by their proposed fractions, then adds the original publication time. The table gives the **minimum acquisition speedup** that satisfies both half-time gates if the solver reaches the indicated speedup.

| Hypothetical solver speedup | First 4 recordings | First 16 recordings |
|---|---:|---:|
| 1× | 5.19× | 5.50× |
| 1.5× | 2.62× | 2.91× |
| 2× | 2.11× | 2.35× |
| 3× | 1.77× | 1.98× |

Historical totals were 403.36 s and 1,715.13 s. Rank 13, DS30-0022, had a timed orbit-interpolation failure and lacks split clocks. Each 16-case projection charges the original 110.77 s in full. A successor that recovers its fix must include the real cost of doing so. Dropping solver time to zero for every split-clock recording, while retaining original acquisition and publication, leaves a 16-recording median paired ratio of **0.7014** and summed ratio of **0.7031**. Actual I/O, cache state, output costs and new decisions can move both gates. [Inputs, per-case assignments and computed fractions](stages.json)

## Frozen scoring rules

1. Use the recorded 4-case prefix and then the 16-case prefix in [the assignment manifest](stages.json). Retain complete pairs from the first four only for the identical frozen implementation and timing boundary. Alternate first build according to the assignments. Record cache residence immediately before each build, charged reads, CPU, elapsed, exit and artifacts. Use a single shared lock across each pair, one pinned core, nice 15, best-effort I/O priority 7 and one numerical thread. Keep failed attempts in the ledger.
2. The timing gates are the median of per-recording candidate/v3 elapsed ratios and the ratio of summed elapsed times. Both must be ≤0.50. Report incomplete pairs explicitly and require complete coverage for a timing verdict. A crash or lost publication cannot qualify as a faster result. A fix must produce all eight readable standard figures, the reported decision, path and grid for the supplied region.
3. Freeze source, native libraries, configuration, fallback thresholds and the complete panel digest before held-out confirmation. Use the existing paired geographic procedure with the installed v3 comparator. Score independently for each site and each calibration arm, fixed-zero and fitted. On containing offers retain baseline fixes with no worse median or P90 horizontal error. On omitted offers count every false publication. Fresh geographic qualification requires containing fixes and withholding on every omitted offer. Report RF-fit RMS separately from position error. Record all-assignment cumulative position errors as well as error among returned positions. [Geographic protocol and scoring](../../single-core-2x/PROTOCOL.md)
4. Keep the blind site's reference and score outside inference. Use independent geographically separated simulated sites, both pilot edges and matched interior, near-face inside/outside and distant offers. Physical DS26, DS29 and DS30 form one geographic site. Physical off-site validation needs separately verified recordings and location authority. Only an integrated candidate with component timing and quality evidence justifies the next raw replay.

The plot and budget can be regenerated from this checkout on Gauss. The command reads the pinned panel and saved receipts without replaying a recording.

```sh
PYTHONPATH=.:src MPLBACKEND=Agg python -m reports.ALGO08.v3.staged_budget \
  /srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/panel.json /tmp/v3-staged-budget
```

For a fresh blind pair, pass `--baseline /opt/leo-algo08/algo08v3/run` to `tools.pipeline_eval.qualification.paired_publication`. It verifies the named launcher and payload and checks the baseline session and decision against its publication marker. During prediction locking, pass `--require-algo08v3` to `tools.pipeline_eval.qualification.score_paired_holdout lock` to bind the comparator alongside the candidate specification. A timed solver failure counts in elapsed statistics and fails the quality verdict.
