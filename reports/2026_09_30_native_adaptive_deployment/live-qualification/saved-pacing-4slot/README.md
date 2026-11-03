# Saved-IQ queue-four acceptance

The scanner queue change is limited to the CLI default: one detector worker
now has four pending entries. It does not change the detector library, detector
ABI, executor, or candidate science. The scanner component burst test admits
exactly five of seven rapid visits (one running plus four pending), emits two
explicit drops, and observes queue high-water four. Its source SHA-256 is
`3067cb1528a0527765f9d421bdcd6d26e10b26e72ae58a4af0cc04cf52154091`.

Existing C9 saved-IQ evidence already uses the required executor geometry:
`leo-paced MANIFEST 120 10 4 1` means independent 120 ms arrivals, ten rounds
of eight DS9 inputs, four pending queue entries, additive fractional mode and
one detector worker. `runtime/paced-with-location.jsonl` completed 80/80 with
no rejection while a one-worker full-catalogue scorer ran. The installed
qualified detector shared object has SHA-256
`6951287cd82009ad79e76bb6293ac18f5f3c4bb4c16bfa865131e5629b114e44`.

That evidence validates the unchanged executor and detector under saved-data
contention. It does not prove live scanner losslessness. A new ARM paced run is
therefore unnecessary for the queue-four code change. Root may run the
following saved-data-only command after packaging to produce a release-local
receipt; it performs no RF acquisition:

```sh
release=/mnt/glrtbench/native-adaptive/releases/91df0781fb158853e047
inputs=/mnt/glrtbench/native-adaptive/benchmarks/default-regression-20260930
work=/mnt/glrtbench/native-adaptive/benchmarks/queue4-saved-acceptance-20260930
location_fixture=/mnt/glrtbench/native-adaptive/benchmarks/complete-ds9-f55517a03696d56b/native-e2.loc1
mkdir -p "$work"
head -n 8 "$inputs/paired80.tsv" >"$work/paced8.tsv"
sha256sum \
  "$release/libleo-adaptive-detector.so" \
  "$release/leo-paced" \
  "$release/leo-native-adaptive-replay" \
  "$release/leo-location" >"$work/artifact-sha256.txt"
nice -n 19 "$release/measure-run" 75 \
  "$release/leo-location" score "$location_fixture" 1 \
  >"$work/location.json" 2>"$work/location.stderr" &
location_pid=$!
"$release/measure-run" 30 \
  "$release/leo-paced" "$work/paced8.tsv" 120 10 4 1 \
  >"$work/paced.jsonl" 2>"$work/paced.stderr"
paced_status=$?
wait "$location_pid"
location_status=$?
"$release/measure-run" 20 \
  "$release/leo-native-adaptive-replay" \
  --manifest "$inputs/paired80.tsv" --fractional-epoch \
  >"$work/replay.jsonl" 2>"$work/replay.stderr"
replay_status=$?
printf 'paced=%s location=%s replay=%s\n' \
  "$paced_status" "$location_status" "$replay_status" >"$work/status.txt"
```

Copy the outputs into a new report subdirectory; do not overwrite prior
evidence. Then verify queue behavior, exact candidate fields, parsed location
output and release hashes on the host:

```sh
.venv/bin/python \
  reports/2026_09_30_native_adaptive_deployment/live-qualification/saved-pacing-4slot/verify.py \
  --release reports/2026_09_30_native_adaptive_deployment/release.json \
  --paced NEW_REPORT/paced.jsonl \
  --replay NEW_REPORT/replay.jsonl \
  --reference-replay reports/2026_09_30_native_adaptive_deployment/ds9/hotfix-arm/final-release.jsonl \
  --location NEW_REPORT/location.json \
  --reference-location reports/2026_09_30_native_adaptive_deployment/location/complete-scan-native-arm-score.json \
  --output NEW_REPORT/summary.json
```

The verifier deliberately keeps command provenance separate because paced
stdout does not encode its queue-capacity argument. Preserve the exact command
or shell transcript with any new output. Exact candidate equality confirms the
frozen native implementation; it does not establish server candidate parity.
