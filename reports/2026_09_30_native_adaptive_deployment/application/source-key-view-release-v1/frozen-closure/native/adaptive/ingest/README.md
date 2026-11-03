# Scanner observation ingress

`project_event` translates scanner v2 candidate events into the public physical
`Observation` contract. It requires an invocation generation, input/analysis
digests, a measured `Timebase`, and an explicit target map connecting attested
tuner profiles to sky RF, channel and edge. It rejects mismatched profile IDs/frequencies,
expired timing, out-of-visit probes and invalid fractional scores. Incomplete or
nonpassing candidates remain unavailable; queue drops are not observations.

Post-recall CRC must be nonzero but need not equal the prepared profile CRC:
v0.59 Fast Lock may update its ALC byte. The local source validates immutable
profile content; keep each original scanner event as its attestation provenance.
Recordings lacking persisted CRCs require the explicit `historical_metadata`
authority and zero CRCs on both target and event. This replay-only declaration
does not attest a live device; the default `live_attested` mode rejects it.

The scanner v2 probe stride is 120 ms with a 20-ms analysis window. Event callback
arrival and detector completion timestamps are deliberately irrelevant to UTC.
Invoke this short translation from the serialized sink, then hand observations
to a bounded background queue. Tracking and search must run on their state owner,
never inside the acquisition callback. This library does not own a worker or
start a radio. Caller-owned immutable invocation identity is mandatory because
scanner v2 events themselves have no generation field.

Build/run the component test:

```sh
bash native/adaptive/ingest/build.sh /tmp/leo-ingest
/tmp/leo-ingest/test-ingest
```

The required DS9 replay test consumes the same explicit TSV as `leo-project`.
Export it from the frozen fixture with `tools/native_adaptive_projection_check.py`
using its `--export-input` argument, then run:

```sh
/tmp/leo-ingest/test-ds9-ingest < /path/to/projection-input.tsv
```

It tests all 24,681 records and 11,747 retained observations against direct native
projection, including IDs, UTC support, CFO, uncertainty and moments. Replay
reconstructs the persisted historical timing bracket and uses zero additional
drift/resolution, preserving its recorded uncertainty. This is a handoff test,
not a new live clock measurement or server-detector equivalence test.

`SANITIZE=1` enables ASan/UBSan. `ARM=1 CXX=...` builds PLUTO+ CPU-only tests.
