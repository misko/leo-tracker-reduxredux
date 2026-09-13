# Native-10M host adaptive feedback integration checkpoint

The host decision path now has explicit provider/client protocols, single-RX
visit reconstruction, a bounded computation worker and passing saved-IQ timing.
It is **not deployed as the production adaptive scanner**. Leo's versioned
capture-to-publication integration, a compatible release bundle and live canaries
remain required by the [deployment plan](../../docs/architecture/adaptive-single-rx-10m-plan.md).

Only radio `104000bac4950008230026001b440a003a` is selected for operation. This
checkpoint collected no new qualification RF; replays use existing recordings.
The running fixed scanner's recovery is documented in the
[reboot report](../2026_09_13_scanner_reboot_recovery/README.md).

## Protocol and ownership

PPU commit `bcc68f1ec5e1e30e239bd11b6a18d9506d56ae12` adds major-3 HOPR/HOPS/HOPT
and 160-byte HFB1 feedback. Native capture remains 10 MS/s with one physical RX;
RX1 is represented by payload column zero when selected. Legacy fixed and
adaptive V2 codecs remain separate. Full uint64 counters, request identity,
generation, RX, target, source interval and detector/filter identity are checked
before feedback is offered to the provider. The IIO owner thread alone refills,
submits feedback, cancels and closes. Source-ending tail results are explicitly
unapplied; acceptance does not itself prove use by a later HOPS decision.

libiio commit `ab89268c42ae4d2e520e2a0eb1a491e0f459d8dd` adds the owned-buffer
feedback command and binding, provider admission and host policy input for either
physical RX at native 10M. Malformed acknowledgements poison the transport;
ordinary provider errors remain distinguishable. Provider checks include source
order, exact completed visits, source counter extension and the one-second age
bound. Host feedback and the radio GLRT worker cannot both produce observations.

Native and ARM builds completed. These builds are development validation, not
source-pinned release bundles. The current hardware firmware was not reflashed.

## Numerical qualification

`sealed.json`, the build receipt and compressed holdout rows preserve the
previously frozen 161-tap Q15 factor-four filter and all-six-screen/one-blind-
confirmation detector. No threshold, filter or holdout selection was changed.

All 64 reserved dwells match the independent same-coefficient scalar reference.
The longer-filter reference has the same 13 positive candidate outcomes; the
22 unknown-versus-negative differences preserve explicit fractional-boundary
uncertainty. Neither comparator supplies RF ground truth or calibrated recall.

## Paced host replay

Both timing runs replay 2,381 saved native dwells over 300 seconds, arriving
126 ms apart. They verify the frozen input hashes and retain complete rows,
source-bound serialized feedback, queue depth and process peak memory. Each
simulated session keeps a single physical RX. The first replay attempt lacked
read permission to the protected corpus and performed no timed work; the files
were present and were subsequently read with the required local access.

| Measurement | Initial worker, v2 | Final worker, v3 |
| --- | ---: | ---: |
| Duration | 300.001 s | 300.001 s |
| Decisions | 2,381 | 2,381 |
| Mean service time | 32.592 ms | 33.083 ms |
| p99 service time | 37.754 ms | 38.058 ms |
| Maximum feedback age | 127.929 ms | 129.196 ms |
| Outstanding-job high-water mark | 1 of 2 | 1 of 2 |
| Healthy results | all | all |
| Peak RSS growth after corpus loading | 1,536 KiB | 1,772 KiB |

The final replay includes input copying, queueing, filtering, screening,
confirmation **and serialization** in its service-time metric. The first replay
serialized every feedback packet but excluded the small codec duration from that
metric; its source snapshots are retained. Final workspace/template startup was
67.544 ms and is reported separately from steady-state gates. The corpus cache
accounts for most of the roughly 814 MiB process peak; the worker itself retains
at most two CI16 jobs plus its native workspace.

The final worker also queues workspace destruction behind accepted work before
waiting for shutdown, so an expired caller timeout does not leak a workspace
after a delayed job returns. Its bounded-timeout test passes.

Both runs pass the frozen 90 ms mean, 100 ms p99 and one-second feedback-age
limits, with no overload, expired result or queue growth. This is host saved-IQ
timing and wire serialization, not a measurement of live FEEDBACKBUFM round-trip
latency or RF duty under adaptive load.

## Tests and reproducibility

- 1,172 targeted PPU codec, stream, client, backend and legacy tests passed.
  Subsequent owner-thread and backend-factory checks passed in a 25-test run.
- 358 Leo host numerical, qualification, worker and policy tests passed with
  the pinned PPU implementation. Lint checks pass for the changed Python files.
- C protocol and direct-async transport tests passed. The real parser/client/
  provider feedback test passed. Policy checks cover 458,752 mask decisions,
  4,000 threaded decisions and injected faults.
- Python and C request, sidecar and feedback packets match byte for byte for both
  receivers and counters crossing 2^32 and above 2^53.

The final paced command was:

```sh
sudo -n env PYTHONPATH=/home/mouse9911/gits/pluto-plus-utils-single-rx-10m/src \
  /home/mouse9911/gits/leo-tracker-single-rx-10m/.venv/bin/python \
  -m tools.qualify_host_feedback_replay \
  /var/tmp/leo-host-adaptive-20260913-v1 \
  /var/tmp/leo-host-feedback-paced-20260913-v3
```

Output directories are exclusive-create. Compressed row artifacts retain the
original JSONL bytes; their uncompressed hashes appear in the corresponding
summaries. Keep the old run and all boundary outcomes. The remaining release work
must bind the exact numerical implementation, templates, protocol and configuration
before activating feedback on the selected radio.
