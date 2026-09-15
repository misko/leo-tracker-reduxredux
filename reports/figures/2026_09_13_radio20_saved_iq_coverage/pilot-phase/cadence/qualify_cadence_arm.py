"""Bounded saved-IQ compute replay on serial-bound ARM; no radio I/O."""

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/scripts")
from deploy_glrt_iq_tracking20 import EVIDENCE, PASSWORD
from leo.acquisition.authority import LocalCaptureAuthority, RadioResource, CaptureTaskKind
from pluto_plus import bootstrap_firmware as b, glrt_canary as g
from pluto_plus.glrt_iq_tracking_profiles import ENDPOINT
from pluto_plus.radio_lock import acquire_radio_lock


def main():
    output = EVIDENCE / "cadence-arm-v1-results"
    output.mkdir(exist_ok=False)
    build = json.loads((EVIDENCE / "cadence-arm-build-v1.json").read_text())
    files = dict(
        probe="cadence-bench-arm-v1",
        refs="direct-references.ci16",
        training="adjacent-training-v1.txt",
        iq="paced-original-seed-input-v1/positive.ci16",
    )
    payload = {k: (EVIDENCE / v).read_bytes() for k, v in files.items()}
    for name, data in payload.items():
        assert hashlib.sha256(data).hexdigest() == build["payloads"][name]
    for path, sha in build["sources"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
    receipt = EVIDENCE / "deploy60-revisits-v1/receipts/0afb2dfe-42c4-43f7-84eb-0d5d29dfd6cb.json"
    plan, profile = g.deployment_identity(receipt, serial=ENDPOINT[0], host=ENDPOINT[1])
    authority = LocalCaptureAuthority(
        Path("/srv/bulk/leo/control"),
        (RadioResource("radio_pluto_5d4d", ENDPOINT[0], "ip:" + ENDPOINT[1]),),
    )
    remote = "/tmp/adjacent-replay-" + uuid.uuid4().hex
    evidence = dict(
        scope="saved_IQ_adjacent_feedback_ARM_compute",
        new_rf_samples=0,
        native_jobs=0,
        tracking_qualified=False,
        payload_sha256=build["payloads"],
        status="started",
        remote_directory=remote,
        serial=ENDPOINT[0],
        host=ENDPOINT[1],
    )

    def save():
        (output / "operator.json").write_text(json.dumps(evidence, indent=2) + "\n")

    ssh = [
        "sshpass",
        "-f",
        str(PASSWORD),
        "ssh",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(EVIDENCE / "radio20.known_hosts"),
        "-o",
        "ConnectTimeout=5",
        "root@" + ENDPOINT[1],
    ]

    def run(command, data=None):
        return subprocess.run([*ssh, command], input=data, capture_output=True, timeout=30)

    try:
        lease = authority.claim(
            ("radio_pluto_5d4d",), task_id="cadence-arm-v1", task_kind=CaptureTaskKind.QUALIFICATION
        )
    except BaseException as error:
        evidence.update(status="admission_refused", error=str(error))
        save()
        raise
    with lease, acquire_radio_lock(ENDPOINT[0]):
        transport = b.BoundSshBootstrapTransport(
            interface=None,
            host=ENDPOINT[1],
            password=PASSWORD.read_text().strip(),
            known_hosts_file=EVIDENCE / "radio20.known_hosts",
        )
        terminal = False
        try:
            evidence["before"] = g.attest_tx_safe_idle(
                transport,
                plan,
                serial=ENDPOINT[0],
                host=ENDPOINT[1],
                layout=profile.return_iio_layout,
            )
            run("mkdir " + shlex.quote(remote)).check_returncode()
            for name, data in payload.items():
                run("cat > " + shlex.quote(remote + "/" + name), data).check_returncode()
                checked = run("sha256sum " + shlex.quote(remote + "/" + name))
                checked.check_returncode()
                assert checked.stdout.decode().split()[0] == build["payloads"][name]
            run("chmod 700 " + shlex.quote(remote + "/probe")).check_returncode()
            save()
            print("Running bounded saved-IQ ARM feedback replay", flush=True)
            evidence["cases"] = []
            for cadence in (2, 3):
                for offset in range(cadence):
                    completed = run(
                        shlex.join(
                            [
                                remote + "/probe",
                                remote + "/iq",
                                remote + "/refs",
                                remote + "/training",
                                str(cadence),
                                str(offset),
                            ]
                        )
                    )
                    name = f"c{cadence}-o{offset}.jsonl"
                    (output / name).write_bytes(completed.stdout)
                    evidence["cases"].append(
                        dict(
                            cadence=cadence,
                            offset=offset,
                            exit_code=completed.returncode,
                            journal=name,
                            sha256=hashlib.sha256(completed.stdout).hexdigest(),
                            stderr=completed.stderr.decode(),
                        )
                    )
                    save()
                    completed.check_returncode()
            terminal = True
            evidence["status"] = "complete_review_pending"
        except BaseException as error:
            evidence.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            try:
                evidence["after"] = g.attest_tx_safe_idle(
                    transport,
                    plan,
                    serial=ENDPOINT[0],
                    host=ENDPOINT[1],
                    layout=profile.return_iio_layout,
                )
                if "before" in evidence:
                    assert evidence["before"] == evidence["after"]
                if terminal:
                    run(
                        "rm -f "
                        + shlex.join([remote + "/" + name for name in payload])
                        + " && rmdir "
                        + shlex.quote(remote)
                    ).check_returncode()
                    evidence["temporary_files_removed"] = True
            finally:
                save()
    print(evidence["status"], flush=True)


if __name__ == "__main__":
    main()
