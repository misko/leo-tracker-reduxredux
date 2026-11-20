# Portable five-refresh compact v5

The portable adapter reproduced both DS26-0036 endpoints and conditional Doppler RMS exactly against a fresh ordinary compact-projector invocation. Both runs used 3,395 native observations, 94 fitted tracks, three initial fits and the same cavity offer decision. The adapter ran in isolated filesystem and network namespaces, with native documents and TLE collections supplied as inputs. [Authentic roof comparison](roof-parity.json) · [Source lock](source-lock.json)

| Roof calibration arm | Latitude | Longitude | Conditional Doppler RMS |
|---|---:|---:|---:|
| Zero | 37.8530548313 | −122.4994030410 | 74.760915847 Hz |
| Fitted | 37.8521000704 | −122.4989606504 | 74.682297513 Hz |

## Required inputs

The native document supplies a qualified detector packet, RF and channel metadata, receiver identifiers and fractional GLRT candidates. The hardware start counter and sample rate place each probe on the measurement clock. The before-and-after UTC readings set its midpoint and causal cutoff. Monotonic and realtime readings let the frozen adapter check clock steps. A last counter and native provenance carry capture extent and status. The shared TrackConfig matches both archived survey configurations. The public tile supplies the search center and width. The adapter uses that center for the sky screen by default. The roof parity run passes the historical independent screen explicitly, keeping both geographic settings matched to stock.

The original policy needs a sequence of prior Space-Track collections. It builds the nominal and previous-orbit models from the past 48 h and the signed phase-history forecast from genuine successive TLE epochs from the past 72 h. The forecast uses orbital-update disagreement before acquisition. The native packet supplies the receiver noise estimate. The specific roof session used 38 collections, 27 distinct snapshot payloads, 1,524 genuine previous-orbit records and 5,765 causal forecast transitions. The public archive port verifies each opened TLE payload against its bound digest. [Protocol](PROTOCOL.md) · [Adapter](../../../tools/pipeline_eval/variants/portable_v5.py)

The adapter calls the existing five-refresh initial search and compact projection through the paired cavity decision. The frozen numerical source, native LP64 backend, compact kernel and configurations are unchanged. The synthetic transfer uses a clock envelope from the simulator's public hardware schedule, with a ±5 ms bracket. Its native input and actual causal TLE history are independent of the hidden geographic labels.

## Blind transfer

Two new multi-channel scenes shared the real Space-Track collection from 2026-11-14 at 05:37 UTC as the generating catalogue, with 35 causal collections and 23 distinct payloads available for inference. The worker received the full native packet and one containing or omitted 25 km offer. The solver re-screened the sky around that offer and recomputed the phase forecast. The returned site screened 1,606 orbits and generated 9,413 pre-observation phase-history transitions. [Authentic history manifest](authentic-history.json) · [Prospective source lock](synthetic-source-lock.json)

| Case | Offer-center error (km) | Returned position error in km, zero / fitted | First-pass status |
|---|---:|---:|---|
| Site 1, containing | 9.795 | 0.527 / 0.483 | Both returned |
| Site 2, containing | 9.766 | — | Timed out |
| Site 1, omitted | 80.549 | — | Timed out |
| Site 2, omitted | 89.818 | — | Timed out |

At the returned site, conditional Doppler RMS was 23.7457 Hz with zero calibration and 23.7445 Hz with fitted calibration. The position improved by 43 m. The containing fix took 86.43 s on the shared host. The other three workers reached their 180 s first-pass cap. These timeouts leave omitted-region rejection unqualified. [Transfer scores](synthetic-scores.csv) · [Matched predictions](matched-tile.jsonl.gz) · [Omitted predictions](omitted-tile.jsonl.gz)

The remaining-budget retries prioritized the second containing site and the first omitted offer. Both used byte-identical input packets from the published seed and reached their 195 s limits. The first-pass cohort stays sealed. [Retry receipts](retry.json)

The history control replayed the authentic roof packet with only its latest causal snapshot. Both calibration arms returned unavailable without a position. The response records the distinct-history requirement. [Single-snapshot control](missing-history.json)

## Reproduce

After the runs, Ruff reordered the imports in the live adapter and worker. The source copies under `as-executed-source/` match the original lock byte for byte. The test suite checks that the syntax trees differ only in import ordering. Both versions resolved the same 205 frozen module paths in the isolated worker and returned identical decisions on the authentic single-snapshot input. All 18 existing evidence hashes matched after the edit. [Import check](import-equivalence.json) · [Measured adapter source](as-executed-source/portable_v5.py.txt) · [Measured worker source](as-executed-source/portable_v5_worker.py.txt)

The parity command uses the local authenticated frozen numerical source and the original archived roof input. The snapshot setting replays the measured import order. The transfer command verifies the parity-checked source before generating sites. Add `--seed-hex` with the seed from `synthetic-labels.json` to reproduce the published geometry and candidate inputs.

```sh
export LEO_PORTABLE_V5_SOURCE_SNAPSHOT="$PWD/reports/2026_11_19_receiver_screening/portable-v5/as-executed-source"
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.portable_v5_trials \
  --scratch /tmp/portable-v5-parity --report /tmp/portable-v5-report --cpus 4 5
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.portable_v5_transfer \
  --scratch /tmp/portable-v5-transfer --report /tmp/portable-v5-report --cpus 4 5
.venv/bin/python -m tools.pipeline_eval.qualification.portable_v5_transfer \
  --score --report /tmp/portable-v5-report
.venv/bin/python -m tools.pipeline_eval.qualification.portable_v5_figures \
  roof --report /tmp/portable-v5-report
.venv/bin/python -m tools.pipeline_eval.qualification.portable_v5_figures \
  transfer --report /tmp/portable-v5-report
```
