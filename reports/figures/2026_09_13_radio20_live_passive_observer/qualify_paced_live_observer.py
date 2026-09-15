"""Two bounded saved-IQ ARM replays on serial-bound .20; opens no RX buffer."""

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

if len(sys.argv) != 3:
    raise SystemExit("usage: qualify_paced_live_observer.py NEW_OUTPUT DEPLOYMENT_RECEIPT")
OUTPUT = Path(sys.argv[1])
DEPLOYMENT = Path(sys.argv[2])


def main():
    OUTPUT.mkdir(exist_ok=False)
    evidence = dict(
        scope="paced_saved_iq_arm_live_observer_no_rx_no_native_io",
        new_rf_samples=0,
        live_tracking_qualified=False,
        status="started",
        cases={},
    )
    save = lambda: (OUTPUT / "operator.json").write_text(json.dumps(evidence, indent=2) + "\n")
    plan, profile = g.deployment_identity(DEPLOYMENT, serial=ENDPOINT[0], host=ENDPOINT[1])
    manifest = json.loads((EVIDENCE / "paced-original-seed-input-v1/manifest.json").read_text())
    payload = {
        "probe": (EVIDENCE / "paced-live-observer-arm-v1").read_bytes(),
        "refs": (EVIDENCE / "direct-references.ci16").read_bytes(),
        "bank": (EVIDENCE / "coarse-bank.ci16").read_bytes(),
    }
    hashes = {k: hashlib.sha256(v).hexdigest() for k, v in payload.items()}
    assert hashes["refs"] == "78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2"
    assert hashes["bank"] == "d9f3452e45180c560a200bb76c9bfe2d7c46b17560fd46495ea74c50f50547f0"
    evidence["payload_sha256"] = hashes
    evidence["inputs"] = manifest
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
        return subprocess.run([*ssh, command], input=data, capture_output=True, timeout=40)

    authority = LocalCaptureAuthority(
        Path("/srv/bulk/leo/control"),
        (RadioResource("radio_pluto_5d4d", ENDPOINT[0], "ip:" + ENDPOINT[1]),),
    )
    try:
        lease = authority.claim(
            ("radio_pluto_5d4d",),
            task_id="paced20-live-observer-arm-v1",
            task_kind=CaptureTaskKind.QUALIFICATION,
        )
    except Exception as error:
        evidence.update(status="admission_refused", error=str(error))
        save()
        raise
    remote = "/tmp/gli-paced-" + uuid.uuid4().hex
    evidence["remote_directory"] = remote
    with lease, acquire_radio_lock(ENDPOINT[0]):
        transport = b.BoundSshBootstrapTransport(
            interface=None,
            host=ENDPOINT[1],
            password=PASSWORD.read_text().strip(),
            known_hosts_file=EVIDENCE / "radio20.known_hosts",
        )
        certain = False
        try:
            evidence["before"] = g.attest_tx_safe_idle(
                transport,
                plan,
                serial=ENDPOINT[0],
                host=ENDPOINT[1],
                layout=profile.return_iio_layout,
            )
            memory = run("cat /proc/meminfo")
            memory.check_returncode()
            available = next(
                int(line.split()[1])
                for line in memory.stdout.decode().splitlines()
                if line.startswith("MemAvailable:")
            )
            assert available > 120000
            evidence["memory_available_kib"] = available
            run("mkdir " + shlex.quote(remote)).check_returncode()
            for name, data in payload.items():
                run("cat > " + shlex.quote(remote + "/" + name), data).check_returncode()
                checked = run("sha256sum " + shlex.quote(remote + "/" + name))
                checked.check_returncode()
                assert checked.stdout.decode().split()[0] == hashes[name]
            run("chmod 700 " + shlex.quote(remote + "/probe")).check_returncode()
            for name in ("positive", "control"):
                root = OUTPUT / name
                root.mkdir()
                case = evidence["cases"][name] = {"status": "started"}
                iq = (EVIDENCE / "paced-original-seed-input-v1" / f"{name}.ci16").read_bytes()
                assert (
                    len(iq) == 25000000
                    and hashlib.sha256(iq).hexdigest() == manifest[name]["sha256"]
                )
                run("cat > " + shlex.quote(remote + "/iq"), iq).check_returncode()
                checked = run("sha256sum " + shlex.quote(remote + "/iq"))
                checked.check_returncode()
                assert checked.stdout.decode().split()[0] == manifest[name]["sha256"]
                directory = remote + "/" + name
                run("mkdir " + shlex.quote(directory)).check_returncode()
                save()
                print(json.dumps({"phase": "paced_replay", "case": name}), flush=True)
                result = run(
                    shlex.join(
                        [
                            remote + "/probe",
                            remote + "/refs",
                            remote + "/bank",
                            remote + "/iq",
                            str(manifest[name]["source_window"]),
                            directory,
                        ]
                    )
                )
                (root / "stdout.json").write_bytes(result.stdout)
                (root / "stderr.txt").write_bytes(result.stderr)
                case["exit_code"] = result.returncode
                case["artifacts"] = {}
                for artifact in (
                    "worker.jsonl",
                    "worker.iq.ci16",
                    "grids.u32",
                    "observer.jsonl",
                    "observer.iq.ci16",
                ):
                    data = run("cat " + shlex.quote(directory + "/" + artifact))
                    data.check_returncode()
                    (root / artifact).write_bytes(data.stdout)
                    case["artifacts"][artifact] = {
                        "bytes": len(data.stdout),
                        "sha256": hashlib.sha256(data.stdout).hexdigest(),
                    }
                result.check_returncode()
                case["result"] = json.loads(result.stdout)
                case["status"] = "complete"
                save()
            certain = True
            evidence["status"] = "replay_complete_review_pending"
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
                if certain:
                    files = [remote + "/" + n for n in (*payload, "iq")]
                    files += [
                        remote + "/" + case + "/" + n
                        for case in ("positive", "control")
                        for n in (
                            "worker.jsonl",
                            "worker.iq.ci16",
                            "grids.u32",
                            "observer.jsonl",
                            "observer.iq.ci16",
                        )
                    ]
                    run(
                        "rm -f "
                        + shlex.join(files)
                        + " && rmdir "
                        + shlex.join([remote + "/positive", remote + "/control", remote])
                    ).check_returncode()
                    evidence["temporary_files_removed"] = True
            finally:
                save()
    print(json.dumps({"status": evidence["status"], "cases": evidence["cases"]}), flush=True)


if __name__ == "__main__":
    main()
