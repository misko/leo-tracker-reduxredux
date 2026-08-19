# WP11 post-soak operator runbook

This is the supported order for the first hardware campaign. Run it only after
the soak gate passes. The browser remains read-only. All commands below use the
centered RX1 profile `starlink-ch4-lower-2p5m-60s-rx1-centered-v1`.

## 1. Preflight

Set `LEO_DATABASE_URL`, `LEO_BULK_ROOT`, `LEO_QUALIFICATION_ROOT`,
`LEO_CAPTURE_EVIDENCE_ROOT`, `LEO_LEGACY_EVIDENCE_ROOT`, and
`LEO_PIPELINE_RELEASE_ID`. Every root must already exist on local storage; QNAP
is rejected. Confirm both radios and the profile, then publish the config from
the deployed release:

```console
leo acquire doctor --json
leo acquire profiles validate starlink-ch4-lower-2p5m-60s-rx1-centered-v1 --json
leo process wp11 config \
  --output /srv/bulk/leo/qualification/wp11-configs/wp11-config.json --json
```

An exact config retry is idempotent; different existing bytes are a conflict.

## 2. Centered calibration

For each radio separately, assign at least three session IDs and predeclare them
before any dwell:

```console
leo process calibration predeclare --plan-id cal-radio-a-001 --radio-id radio_pluto_5d4d \
  --session cal-a-01 --session cal-a-02 --session cal-a-03 --json
leo acquire once --profile starlink-ch4-lower-2p5m-60s-rx1-centered-v1 \
  --radio radio_pluto_5d4d --session-id cal-a-01 --tag CALIBRATION --json
```

Repeat the capture for every predeclared session, then use the exact `plan.logical_uri`
and `plan.digest` returned by `predeclare`:

```console
leo process calibration queue --plan-uri PLAN_URI --plan-digest PLAN_DIGEST --json
leo process worker --worker-id wp11-calibration-a --max-jobs 3 --json
leo process calibration promote --plan-uri PLAN_URI --plan-digest PLAN_DIGEST \
  --promotion-id cal-radio-a-p001 --calibration-id cal-radio-a-v001 \
  --calibration-set-id cal-radio-a-set-v001 --json
leo process calibration show cal-radio-a-p001 --json
```

Repeat for radio B. Do not use acceptance-session IQ as calibration evidence.
An insufficient promotion is a stop condition; there is no zero-offset fallback.

## 3. Acceptance capture: exact 10 + 10 + 10

Capture ten radio-A-only sessions, ten radio-B-only sessions, and ten paired
sessions. Every acceptance capture must include `--tag ACCEPTANCE`; never add
`CALIBRATION`.

```console
leo acquire once --profile starlink-ch4-lower-2p5m-60s-rx1-centered-v1 \
  --radio radio_pluto_5d4d --session-id accept-a-01 --tag ACCEPTANCE --json
leo acquire once --profile starlink-ch4-lower-2p5m-60s-rx1-centered-v1 \
  --radio radio_pluto_19f2 --session-id accept-b-01 --tag ACCEPTANCE --json
leo acquire once --profile starlink-ch4-lower-2p5m-60s-rx1-centered-v1 \
  --radio radio_pluto_5d4d --radio radio_pluto_19f2 \
  --session-id accept-pair-01 --tag ACCEPTANCE --json
```

After all 30 sessions, run `leo acquire audit-capture-modes` with exactly ten
repetitions of each session option and publish `--receipt` directly beneath
`LEO_CAPTURE_EVIDENCE_ROOT`. Use the receipt's typed canonical digest returned
by the command—not `sha256sum` of formatted JSON—as the WP11 capture digest.

## 4. Campaign execution

Create the immutable plan, generate legacy receipts before jobs exist, queue,
run the ordinary worker, then finalize:

```console
leo process wp11 create --campaign-id wp11-001 \
  --capture-uri qualification://capture/CAPTURE_RECEIPT \
  --capture-digest CAPTURE_CANONICAL_DIGEST \
  --config /srv/bulk/leo/qualification/wp11-configs/wp11-config.json --json
leo process wp11 legacy wp11-001 --json
leo process wp11 queue wp11-001 --json
leo process worker --worker-id wp11-acceptance-001 --max-jobs 80 --json
leo process wp11 finalize wp11-001 --json
leo process wp11 show wp11-001 --json
```

`legacy --ordinal N` supports bounded restart from ordinal 0 through 39. Run
legacy ordinals serially because the frozen oracle uses a global qualification
lock. The full command reads and verifies compressed IQ, holds one 600 MB RX1
dwell in the local spool at a time, unlinks it before oracle execution, and
leaves only the immutable receipt. `queue` refuses incomplete legacy evidence.

The 30 runs contain 80 jobs: 20 independent sessions with two stages and 10
paired sessions with four stages. Any nonzero command exit, failed worker job,
missing calibration, release drift, receipt conflict, or inconclusive/failing
final result is a stop condition. Nothing in this workflow deletes or mutates
QNAP data.
