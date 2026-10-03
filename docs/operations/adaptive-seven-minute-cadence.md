# Automatic adaptive capture cadence

## October 2 v0.60 deployment and native low-rate policy

Radio .20 now runs `v0.60-plutoplus-spf-adaptive-native-fastlock`, installed
through PPU's guarded LAN flash procedure. Each scheduling slot selects native
**1.25 MS/s with 25% probability**, otherwise **2.5 MS/s**. Both use protocol
v3, manual 40 dB gain, 120 ms active/quiet visits, five-minute captures, and the
existing three-minute wait after completion. The low-rate path uses 500,000
transport samples per block, as required by the release qualification; 2.5 MS/s
retains 1,000,000. Target centers are unchanged. This is probabilistic selection,
not a fixed repeating sequence of four scans.

The installed runner is
`8a85f9fafcf5db1b8af1f8ce598d42d61bf6a6d1731bc9b3bae3f1de4e88073d`,
with PPU source `a491b1ca7ee021e3e0e19a8c98becd2c9b1dae8b`.
Native low-rate records use new plan/receipt, geometry, timing, IQ manifest,
history-item, and history-page versions. Existing published versions remain
closed. The API and UI display the real 1.25 MS/s source rate. Scientific
analysis of that rate remains unqualified: the UI states this explicitly and
the queue logs `unsupported_native_1p25_rate` rather than submitting it to
an incompatible analyzer. Raw dual-RX IQ is retained for subsequent analysis.

The bounded ten-second .20 test `scan-fw-189c7fe0ef6e62cc` delivered all 73
planned visits, with zero errors/skips/invalid/cancelled visits. Each visit
contains 150,000 samples per receiver; total raw IQ is 87,600,000 bytes.
This real archive passed import and is visible through the live v2/v3 API.
No hardware qualification claim is inferred for the scientific detector.

PPU verified protected regions, written FIT, reboot, returned serial/version,
SSH key rotation, and TX-safe state. Its receipt is
`54e738fc-dcde-4d37-91b6-9ea13f718d94`, retained with private deployment evidence
under `/home/mouse9911/release-evidence/v060-radio20`.
The published DFU SHA-256 is
`521ab9d36ade7ff4f278e699be6c080a7e7af1b7353de7d62189300caea7fb20`.

The reader/UI deployment at `/opt/leo-native-low-rate/a644cd4b778e` preserves
the installed sparse-publication recovery checks, queue capture-date gate,
and web baseline `4d7a403f9b3e135a98e01daad763aabd49aa81e2`. File hashes are
recorded in its `overlay-files.json`. The `leo-native-low-rate-readers.conf`
drop-in is installed on publication and queue services, and
`leo-native-low-rate-api.conf` on the API, as `zzzzz-native-low-rate.conf`.
The final repository formatting is semantically identical to the tested
deployed Python overlay. Validation: 60 import/queue/API tests on that overlay,
34 scheduling/qualification tests with the deployed PPU, 43 UI regression tests
on the preserved live UI baseline, and a successful TypeScript/production build.

Earlier policy changes below are historical.

## October 2 fixed sample rate

The timer now waits **three minutes after each capture finishes**, replacing
the ten-minute catch-up gap. The obsolete `zzz-catch-up-gap.conf` override is
removed when installing the updated `zz-seven-minute.conf` timer drop-in.
Five-minute captures continue at 2.5 MS/s, for roughly eight-minute cycles plus
setup and finalization. The boot delay remains the base timer's two minutes.

All future adaptive captures use **2.5 MS/s only**, including manual invocations
of the cadence runner; other sample-rate overrides are rejected. The installed
runner digest is
`e437833b8508caf0d8d8c2b8e7b77f87ed8bed4adc13852a963b0666e18410e3`.
All 15 component tests pass, including the RF-free dry run against the deployed
acquisition runtime. The service configuration applies at its next scheduled
activation. Five-minute captures, 120/120 ms dwells, gain, edge selection, and
the spool-space guard remain unchanged. The initial rate-only change preserved
the ten-minute catch-up gap; the subsequent timer update above replaces it.

## October 1 operator policy

The October 1 runner selected **10 MS/s or 2.5 MS/s with equal probability** and
always uses **120 ms active / 120 ms quiet dwells**. Manual 40 dB gain, five-minute
captures, independent edge choice, unique activation IDs and two-minute gaps
remain. Before opening RF it requires free spool space for the full uncompressed
dual-RX capture plus 2 GiB headroom; a low-space attempt is deferred without
starting a capture. This prevents the observed ENOSPC loop but is not a disk
reservation against unrelated concurrent writers. The selected rate is not
changed to fit available space.

The installed runner digest is
`8eeaf27ebfe88f37b36975c7fe1530cc861716df467e8a648ea8678d4fe32d91`.
Fifteen scheduling, identity, space-budget and dry-run tests pass. New capture
pose companions use `gauss-r20-lt3d-004b-20261001-v1` (LT3D-004B; software RX0
west and RX1 east). The first October 1 restart was bounded to 30 minutes.
At 04:43 UTC the operator explicitly authorized continuous adaptive capture;
the timer was enabled for ongoing operation and boot activation, with no
automatic end-of-window stop. Each capture still lasts five minutes followed
by a two-minute gap, subject to the free-space guard.

The following records the earlier cadence and policy for historical reference.

Installed on 2026-09-27 for radio `192.168.1.20` using the existing
`leo-v052-adaptive.service` and enabled `leo-v052-adaptive.timer`.

Each activation captures both receivers for 300 seconds. The timer waits 120
seconds after the service finishes before starting another capture. Setup and
file finalization add overhead to the nominal seven-minute cycle. The timer also
starts scanning after boot. As of 2026-09-28, sample-rate selection gives 10 MS/s
a 50% probability and divides the other 50% uniformly among 2.5, 5, and 7.5 MS/s
(one-sixth each). Choices remain deterministic per radio and seven-minute slot;
these are probabilities rather than guaranteed proportions in every short run.
Manual 40 dB gain and uniform active-dwell selection remain unchanged. Explicit
`--sample-rate` overrides still take precedence.

The repository drop-ins are `deploy/systemd/leo-adaptive-seven-minute.service.conf`
and `deploy/systemd/leo-adaptive-seven-minute.timer.conf`. They are installed as
`zz-seven-minute.conf` in the respective service and timer drop-in directories.
The service uses the immutable copy of `tools/run_adaptive_capture_cycle.py` at
`/opt/leo-adaptive-cadence/59359bf6f25c3aa63be22b541d0ad84d48c0ccd0b593e1aa599e2d5860787532/run_adaptive_capture_cycle.py`.
The directory name is the runner's SHA-256 digest.

Recording IDs incorporate the systemd invocation ID, with a random UUID fallback
for manual invocation. Separate activations within the same scheduling slot
cannot collide. Immediate service retries are disabled; the timer supplies the
next attempt after the two-minute gap. The service has a 390-second timeout and
retains the acquisition lock to prevent overlapping captures.

Weighted-policy validation: all 16 radio-free tests in
`tests/cli/test_adaptive_capture_cycle.py` pass against the deployed acquisition
package, including all probability branches, a 12,000-slot distribution check,
manual overrides, unique recording identities, and capture dry-run checks.
The updated runner applies on the next scheduled service activation.

The 14 scheduling tests run without the optional acquisition package:

```sh
python -m pytest -q -m 'not hardware' tests/cli/test_adaptive_capture_cycle.py
```

The two `hardware`-marked tests require the acquisition runtime but never open
a radio. Run the complete file against the installed runtime with:

```sh
PYTHONPATH=/opt/leo-v058-adaptive/1e7bebed663bc2178a1b91af5b98eb55bc97dc84/src /home/mouse9911/gits/pluto-plus-utils-feature-103/.venv/bin/python -m pytest -q tests/cli/test_adaptive_capture_cycle.py
```

Original cadence installation validation: eight radio-free tests passed.
Systemd unit verification
passed. The existing capture was allowed to finish successfully at 01:08:55 UTC;
systemd scheduled the next activation at 01:10:55 UTC. The timer automatically
started the new runner at 01:10:56 UTC with `--duration-ms 300000`; its process was
confirmed running and the timer remained enabled.

Inspect using `systemctl status leo-v052-adaptive.timer leo-v052-adaptive.service`
and `systemctl list-timers leo-v052-adaptive.timer --all`.

To restore the previous cadence, stop only the timer, remove the two
`zz-seven-minute.conf` drop-ins, reload systemd, and restart the timer. Do not stop
an active capture merely to change scheduling.
