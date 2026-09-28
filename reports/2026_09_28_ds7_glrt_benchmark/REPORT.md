# DS7 GLRT speed and evidence recovery

This experiment compares complete GLRT dwell analyses on identical saved IQ. It uses no RF and makes no production pipeline changes. SOL implemented the experimental methods; Terra independently implemented scientific scoring and audited provenance and causality.

## Scope and measurement

The frozen, metadata-selected development cohort has 28 consecutive 120 ms dual-RX visits from four DS7 recordings: 16 at 2.5 MS/s and four each at 5, 7.5 and 10 MS/s. Each method processes all eleven overlapping 20 ms probes on both receivers. Two chronological replays reset causal state between repeats. Scientific counts use unique visits from repeat zero; repeat one checks reproducibility and contributes timing, not additional scientific sample size.

Timing includes CI16 conversion and complete detector analysis, including failed local attempts and blind retries. It excludes reading/decompressing files, output serialization, waterfall generation, downstream Doppler analysis, and publication. These are server x86 measurements on an Intel Core Ultra 9 285K with the native acquisition backend, not PLUTO ARM measurements. Serial methods use one pinned core and one numerical-library thread. Four-worker timing includes IPC and shared-memory handling; its CPU figure sums parent and worker CPU, while startup is reported separately.

Reported runtime is the mean of the per-visit median across two repeats. The mixed-rate average weights the actual cohort (16/4/4/4), not an assumed deployment rate distribution. This is a shared host; timings are descriptive, not statistically established performance guarantees. Short concurrent parallel startup smokes during the first serial repeat are disclosed in `PARALLEL.md`; the full parallel replay starts after both serial repeats finish.

## What equivalence means

- **Exact output:** the full serialized scientific result equals the frozen original result.
- **Positive hypothesis recovery:** one-to-one recovery of the original positive candidate hypotheses within 2 microseconds and 8 kHz, in the same visit, receiver, and probe. Multiple hypotheses may describe the same physical signal.
- **Confirmed detection recovery:** recovery through matched identities of the original receiver/visit confirmations, requiring fresh positive evidence on separated probes. This does not establish exact scores or precise Doppler equivalence.

The original yields 1,154 positive hypotheses, 437 positive receiver/probes, and 42 confirmed receiver/visits. DS7 has already been explored, so this is development evidence, not an untouched holdout or independent physical truth. Unmatched candidate positives are reported as extras, not false alarms.

## Methods

1. **Original:** frozen pre-optimization acquisition and pilot-scoring modules, eight candidates per probe.
2. **Exact optimized:** bounded pilot-geometry caching and heap-based acquisition peak selection; full eight-candidate search remains.
3. **Two candidates:** exact optimized code with the candidate limit reduced from eight to two. All probes remain; alternative hypotheses can disappear.
4. **Prior CFO plus fallback:** previous fresh confirmation supplies a causal per-target/per-receiver CFO prior, expiring after three seconds. Search narrows to ±20 kHz around that prior but retains the full timing grid and eight candidates. If any seeded receiver fails fresh confirmation, rerun the entire dwell blind. No reference outputs or future visits enter state.
5. **Four workers:** the full exact optimized workload distributed across four persistent processes, followed by the original chronological decision fold. This tests window-level parallelism, not a newly vectorized GLRT kernel.

## Measured results

All 280 evaluations completed without failure; every method reproduced its own full scientific output exactly on the second replay. Direct source hashes remained unchanged. A final check also matched all 34 supplementary runtime-lock entries, including the native binary. The four-worker pool closed normally and all four worker PIDs were absent after completion. Its separate creation latency was 1.230 seconds; worker CPU accounting uses 10 ms operating-system ticks. All 26 benchmark method, scoring, and runner tests passed. Terra independently checked raw-row denominators, repeatability, and summary arithmetic.

| Method | Cores | CPU ms/dwell | Elapsed ms/dwell | Elapsed speedup | Exact full outputs | Positive hypotheses recovered | Confirmations recovered |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original | 1 | 3,801.9 | 3,818.3 | 1.00× | 28/28 | 1,154/1,154 (100%) | 42/42 |
| Exact optimized | 1 | 3,657.7 | 3,680.3 | 1.04× | 28/28 | 1,154/1,154 (100%) | 42/42 |
| Two candidates | 1 | 3,124.7 | 3,136.6 | 1.22× | 0/28 | 697/1,154 (60.4%) | 42/42 |
| Prior CFO + fallback | 1 | 3,415.5 | 3,443.6 | 1.11× | 17/28 | 904/1,154 (78.3%) | 42/42 |
| Exact four workers | 4 | 3,941.1 | 1,085.3 | 3.52× | 28/28 | 1,154/1,154 (100%) | 42/42 |

Serial CPU reductions versus original are 3.8%, 17.8%, and 10.2%, respectively. Four workers reduce latency but increase aggregate CPU by 3.7% versus original (7.7% versus exact optimized).

### Priority: 2.5 MS/s

| Method | CPU ms/dwell | Elapsed ms/dwell | CPU reduction | Positive hypotheses recovered | Confirmations recovered |
|---|---:|---:|---:|---:|---:|
| Original | 1,214.3 | 1,224.5 | — | 761/761 (100%) | 32/32 |
| Exact optimized | 1,152.3 | 1,170.3 | 5.1% | 761/761 (100%) | 32/32 |
| Two candidates | 795.8 | 797.2 | 34.5% | 478/761 (62.8%) | 32/32 |
| Prior CFO + fallback | 1,132.3 | 1,142.4 | 6.8% | 562/761 (73.9%) | 32/32 |
| Exact four workers | 1,244.2 | 344.1 | −2.5% | 761/761 (100%) | 32/32 |

Positive receiver/probe recovery is 301/323 for two candidates and 322/323 for local fallback. Neither approximate method therefore preserves every positive probe even though all 32 confirmations survive. Four-worker elapsed speedup is 3.56× at this rate.

### All supported rates

Each cell gives elapsed milliseconds per dwell / positive-hypothesis recovery. Original reference counts are 761, 166, 56, and 171 hypotheses respectively. All methods recover every original confirmation at every rate; the higher-rate cohorts have only four visits each.

| Method | 2.5 MS/s | 5 MS/s | 7.5 MS/s | 10 MS/s |
|---|---:|---:|---:|---:|
| Original | 1,224 / 100% | 3,342 / 100% | 7,055 / 100% | 11,433 / 100% |
| Exact optimized | 1,170 / 100% | 3,176 / 100% | 6,603 / 100% | 11,302 / 100% |
| Two candidates | 797 / 62.8% | 2,751 / 53.0% | 5,727 / 76.8% | 10,289 / 51.5% |
| Prior CFO + fallback | 1,142 / 73.9% | 3,027 / 87.3% | 6,557 / 100% | 9,951 / 82.5% |
| Exact four workers | 344 / 100% | 986 / 100% | 1,893 / 100% | 3,342 / 100% |

## Interpretation and next work

Exact optimization is the safe foundation. Reducing candidates gives a larger 2.5 MS/s CPU saving, but it must be evaluated against the intended downstream evidence requirement: preserving a visit confirmation does not preserve the original candidate set.

Prior-guided search is promising but this first conservative version often has little work to skip. Across the cohort it takes 13 cold blind routes, accepts 11 local routes, and retries four locally attempted dwells blind. All four retries occur at 2.5 MS/s. At that rate its total saving is only modestly better than the exact optimization. This experiment does not narrow timing or eliminate probe windows.

Local search produces 217 unmatched extra positive hypotheses. Among all matched candidates, its maximum CFO difference is 7,666.3 Hz and maximum GLRT margin difference is 0.40849. Therefore recovered confirmations must not be interpreted as numerical or downstream Doppler equivalence. The prior follows the latest qualifying pair and can select a different alias branch. Its state key assumes stable target configuration within a session; deployment would need configuration identity and reset semantics.

The next useful experiments are: (a) profile and optimize the remaining full-search native acquisition work while requiring exact recovery; (b) evaluate two-candidate search on a larger stratified corpus with downstream Doppler/association scoring; and (c) test multiple causal CFO hypotheses, timing prediction, and periodic full discovery to improve local-search savings without silently losing new emitters. Freeze each candidate configuration before evaluating a new cohort.

Do not infer real-time capacity by dividing a 120 ms dwell by these server detector times alone. Deployment needs the actual adaptive dwell arrival rate and combined capture, decoding, analysis, and publication CPU budget. The prior PLUTO benchmark has a different reduced workload.

## Reproduction and evidence

Run from the repository root. The installed runtime is used only to read saved visits through its public read-only storage port; the benchmark runs against this checkout.

```bash
sudo -n nice -n 19 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_28_ds7_glrt_benchmark/prepare.py extract --plan reports/2026_09_28_ds7_glrt_benchmark/plan.json --output /tmp/leo-ds7-glrt-replay
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 19 .venv/bin/python reports/2026_09_28_ds7_glrt_benchmark/run.py --inputs /tmp/leo-ds7-glrt-replay --output /tmp/ds7-glrt-serial
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 19 .venv/bin/python reports/2026_09_28_ds7_glrt_benchmark/run_parallel.py --inputs /tmp/leo-ds7-glrt-replay --output /tmp/ds7-glrt-parallel
.venv/bin/python reports/2026_09_28_ds7_glrt_benchmark/summarize.py /tmp/ds7-glrt-serial /tmp/ds7-glrt-parallel --output /tmp/ds7-glrt-summary.json
.venv/bin/python -m pytest -q reports/2026_09_28_ds7_glrt_benchmark/test_methods.py reports/2026_09_28_ds7_glrt_benchmark/test_methods_parallel.py reports/2026_09_28_ds7_glrt_benchmark/test_run.py reports/2026_09_28_ds7_glrt_benchmark/test_scoring.py
```

Use new output directories for each run. `plan.json` seals the cohort and parameters; `inputs.json` binds payload hashes and source counters. Only selected saved chunks were read and verified, not the entire DS7 corpus. `SPEC.md` and `SCORING.md` define the protocol; `AUDIT.md` records causal/provenance limits. `runtime-lock.json` supplements run-header direct-source hashes with a during-run attestation of native and transitive sources, not a retrospective guarantee of pre-attestation history. Full per-call results and terminal receipts remain in `run-01/` and `parallel-01/`; `summary.json` is the machine-readable comparison.
