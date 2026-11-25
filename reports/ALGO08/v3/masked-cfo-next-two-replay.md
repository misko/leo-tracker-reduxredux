# Rank 66–67 saved half-shrink replay

The [frozen next-two protocol](held-cfo-next-two-protocol.md) enrolls
only DS30-0442 and DS30-0212. The [adapter](masked_cfo_next_two_replay.py)
binds each original authority and offer to the existing DS30-0218
worker, capsule, scientific verifier and signed owner observer. The
DS30-0218 source and historical artifacts retain their original hashes.
The next-two plans bind the pinned enrollment census, original capture
accession identity, and actual historical request authority independently.
[Census](measurements/held-cfo-next-two.json)

- **DS30-0442, rank 66.** Both official acquisition rows verified.
  The signed request archive has 49 exact bodies and 87,646,559 bytes.
  The first enrolled body had zero bytes resident by privileged
  `cachestat`. This is a custody refusal for the fixed panel. The
  cache-only check read zero payload bytes and created no stage or solver
  child. The accession identity `b89714b4…` and historical request
  identity `58f67db5…` both remain recorded.
  [Sealed refusal](measurements/0442-cache-custody.json)
- **DS30-0212, rank 67.** The sealed census names exactly 50 donor
  bodies with archive SHA-256 `a1b0110c…`. The worker requires the
  unchanged official request and both verified acquisition rows before
  it may hash any staged bodies. It uses the already staged DS30-0218
  and DS30-0086 donor roots, verifies all bodies and links them into a
  fresh private tmpfs stage.

The independent CPU3 no-solve proof on the known signed DS30-0019
fixture sealed at `8b555c427e51f89e8579f132d7c1e6d70a84db84da2f9ee0dad35601da081aac`
in `/dev/shm/leo-next-two-capsule-probe01/probe/capsule-ready.json`.
The true installed source, namespace, descriptor, read-only inputs and
network denial verified. The worker reported 47 causal bodies and zero
acquisition, waveform reads or fits. Twenty-four component tests passed.

Run from this research checkout as `leo` with the installed release
Python after the field state permits staging. `PANEL` is one fresh path
below `/dev/shm`.

```bash
python -IB reports/ALGO08/v3/masked_cfo_next_two_replay.py status
python -IB reports/ALGO08/v3/masked_cfo_next_two_replay.py prepare "$PANEL" --case DS30-0212
```

`prepare` verifies the exact donor bodies and both CPU3 no-solve
preflights. The printed readiness seal binds
`$PANEL/DS30-0212/panel-readiness.json`, which gives `ORDINARY_READY` and
`CORRECTED_READY`. The controller and verification run on CPU3. Each
scientific child runs on its own official deferral, under the shared
nonblocking lease on CPU2, with a 24-second cap and at least 26 seconds
remaining before retry. A declined passive watch can wait for a fresh
deferral while the original driver remains live. A launched worker does
not retry. This path keeps the original scientific timer and adds a
separate GNU `time` resource record inside the worker namespace.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
taskset -c 3 nice -n 15 ionice -c 3 python -IB reports/ALGO08/v3/masked_cfo_next_two_replay.py watch "$PANEL" --case DS30-0212 --cell ordinary --pin "$ORDINARY_READY" --driver-pid "$PID"
taskset -c 3 nice -n 15 ionice -c 3 python -IB reports/ALGO08/v3/masked_cfo_next_two_replay.py watch "$PANEL" --case DS30-0212 --cell corrected --pin "$CORRECTED_READY" --driver-pid "$PID" --ordinary-gate-pin "$ORDINARY_GATE"
python -IB reports/ALGO08/v3/masked_cfo_next_two_replay.py score "$PANEL" --pin "$PAIR_VERIFIED_BEFORE_SURVEY"
```

The first watch prints the ordinary parity gate digest after verifying
scientific parity against the official original successor. The second
watch verifies both closed publications and stops at the held survey
boundary, printing the pair digest. The score command rechecks the
0442 refusal, exact field pair pins and both saved publications before
opening the held survey. A genuine withhold or zero-edit publication
remains part of its original case.
