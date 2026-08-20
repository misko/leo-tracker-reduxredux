# Standard offline runtime benchmark

This benchmark replays one sealed local capture. It does not contact radios,
the live catalog, or QNAP.

## Frozen input

- Corpus root: `/srv/bulk/leo/test-corpus/trial-132-four-path-v1`
- Session: `production-24h-20260819-01-trial-00000132`
- Manifest digest:
  `sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d`
- Inventory: `stream-0/RX0`, `stream-0/RX1`, `stream-1/RX0`,
  `stream-1/RX1`
- Duration: 60 seconds per path at 2.5 MHz

The corpus is a protected local copy. Benchmark output must use a new local
directory for every invocation. Never point output beneath `/mnt/qnap01`.

## Full-capture command

Run with live acquisition and production workers stopped. Replace the output
suffix for every replay because the harness publishes create-only artifacts.

```bash
sudo -u leo env \
  PYTHONPATH=src \
  LEO_REAL_CORPUS_ROOT=/srv/bulk/leo/test-corpus \
  /usr/bin/time -v .venv/bin/python -c "import json,pathlib,runpy,time; ns=runpy.run_path('tests/analysis/test_standard_real_corpus_e2e.py'); out=pathlib.Path('/tmp/leo-standard-v2-offline-UNIQUE'); started=time.perf_counter(); result=ns['_run_full_chain'](out); print(json.dumps({'elapsed_seconds':time.perf_counter()-started,'paths':[(x['stream_id'],x['receiver_id'],x['trajectory_count']) for x in result['path_summaries']],'paired_digest':result['paired_report']['report_digest']},sort_keys=True))"
```

The harness deliberately uses one inner scientific worker. Independent path
work is the outer concurrency boundary, matching the production policy that
the database scheduler owns parallelism.

## Reviewed baseline — 2026-08-20

- Code: `92b83ec094b2eeae6e7e105cee3439b8e13206cf`
- Science wall time: 657.765482 seconds
- Process wall time: 658.13 seconds
- User CPU: 1,500.18 seconds
- System CPU: 265.64 seconds
- Mean CPU utilization: 268 percent
- Peak RSS: 1,857,420 KiB
- Voluntary context switches: 191,140,805
- Artifact bytes: 93,713,630
- Artifact SHA-256:
  `7b55fefc1a9799c402938894adee77413aefeedeae692c120decf98fd8ec1a76`
- Path trajectory counts: 6, 6, 9, 6
- Probes per path: 1,200
- Path and paired status: `partial`, because 4,800 of 9,600 bounded
  candidates per path are intentionally omitted
- Paired report digest:
  `sha256:8f1a65de86c23a0b4b5edd3b45a5e4a86618b9ed90f4d8ef64a69a82a6ca438d`
- Reviewed golden summary comparison: pass at the frozen absolute and relative
  floating-point tolerances

## Parallelism result

A four-second prefix took 21.561 seconds with one inner worker and 13.141
seconds with four. However, the full four-path replay with four inner workers
exceeded the baseline after 11:58, reached 2,856,844 KiB RSS, and accumulated
325,609,535 voluntary context switches. It was terminated without publication.

Therefore production uses one inner detector worker per claimed job and up to
20 independent worker processes. OpenBLAS, OpenMP, and MKL are pinned to one
thread in the worker unit. This policy is frozen in commit `920d75b` and keeps
the scheduler, rather than nested libraries, in control of machine-wide
parallelism.

## Acceptance for every optimization

1. Run the bounded one-path/one-second real-corpus gate first.
2. Require the frozen one-second golden comparison to pass.
3. Run one full capture only after the bounded gate improves.
4. Require exact path inventory and probe counts, trajectory counts 6/6/9/6,
   degrees 1/2/3, candidate-only claim fences, and reviewed floating-point
   summary parity.
5. Record wall time, user/system CPU, mean CPU, peak RSS, context switches,
   artifact size/hash, and the exact code revision.
6. Do not refresh a golden merely because an optimized implementation differs.

