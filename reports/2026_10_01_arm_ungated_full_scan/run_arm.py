"""Replay the full saved scan through the already-qualified gate-disabled build."""
import hashlib
import io
import json
import shlex
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SESSION = "scan-fw-f363c7f29141d0b1"
MANIFEST = "sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015"
DEVICE = "/mnt/glrtbench/full-scan-f363-ungated-20261001"
PRIOR = "/mnt/glrtbench/ds9-native-comparison-20260930"
BINARY = "/mnt/glrtbench/missing-long-gate-ablation-20261001/bench-ungated"
KEYS = REPO / "reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts"
SSH = ["sshpass", "-f", "/etc/leo/credentials/scanner-iiod-ssh-password"]
OPTIONS = ["-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=yes",
           "-o", "UserKnownHostsFile=" + str(KEYS)]


def remote(command, timeout=60):
    return subprocess.check_output(SSH + ["ssh"] + OPTIONS + ["root@192.168.1.15", command],
                                   text=True, timeout=timeout)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def main():
    started = time.monotonic()
    output = HERE / "arm"
    output.mkdir(exist_ok=False)
    panel = json.loads((REPO / "reports/2026_09_30_arm_ds9_native_comparison/panel.json").read_text())
    binary = REPO / "reports/2026_10_01_arm_glrt_missing_diagnosis/ungated-build/leo-native-glrt-bench"
    expected = {BINARY: hashlib.sha256(binary.read_bytes()).hexdigest()}
    baseline_inventory = json.loads((REPO / "reports/2026_09_30_arm_full_scan_comparison/arm-v2/inventory.json").read_text())
    for edge, templates in panel["templates"].items():
        for role, item in templates.items():
            expected[f"{PRIOR}/{edge}-{role}.c128"] = item["sha256"]
    installed = remote("sha256sum " + " ".join(map(shlex.quote, expected)))
    for line in installed.splitlines():
        digest, path = line.split()
        assert expected[path] == digest
    (output / "installed-hashes.log").write_text(installed)
    remote("mkdir " + DEVICE)
    store = AdaptiveHopIqStore("/srv/bulk/leo", read_only=True)
    try:
        session = store.inspect(SESSION)
        assert session.manifest_sha256 == MANIFEST
        document = session.manifest.model_dump(mode="json")
        events = document["receipt"]["events"]
        assert [e["visit_index"] for e in events] == list(range(len(events)))
        assert len(events) == 2215
        assert document["receipt"]["plan"]["geometry"]["sample_rate_hz"] == 2500000
        save(output / "capture-manifest.json", document)
        origin = events[0]["valid_start_counter"]
        inventory = []
        with store.reader(SESSION, expected=session) as reader, tempfile.TemporaryDirectory(
                prefix="leo-full-scan-arm-", dir="/var/tmp") as temporary:
            bundle = Path(temporary) / "batch.tar"
            for begin in range(0, len(events), 16):
                assert time.monotonic() - started < 2400, "Replay exceeded bounded 40 minute budget"
                group = events[begin:begin + 16]
                lines, hashes = [], []
                with tarfile.open(bundle, "w") as archive:
                    for event in group:
                        visit_id = event["visit_index"]
                        visit, values = reader.read_visit_ci16(visit_id)
                        assert visit.event.model_dump(mode="json") == event
                        assert values.shape == (300000, 2, 2)
                        assert event["valid_end_counter_exclusive"] - event["valid_start_counter"] == 300000
                        raw = np.asarray(values, dtype="<i2", order="C").tobytes()
                        digest = hashlib.sha256(raw).hexdigest()
                        assert digest == baseline_inventory[visit_id]["raw_sha256"]
                        assert event == baseline_inventory[visit_id]["event"]
                        name = f"visit-{visit_id:06d}.ci16"
                        info = tarfile.TarInfo(name); info.size = len(raw)
                        archive.addfile(info, io.BytesIO(raw))
                        hashes.append(f"{digest}  {name}\n")
                        edge = event["target"]["edge"]
                        lines.append("\t".join(map(str, [len(lines), 2500000, 120, 120,
                            f"{PRIOR}/{edge}-exact.c128", f"{PRIOR}/{edge}-control.c128", f"{DEVICE}/{name}"])))
                        inventory.append({"visit": visit_id, "capture_time_s":
                            (event["valid_start_counter"] - origin) / 2500000,
                            "raw_sha256": digest, "event": event})
                    for name, data in {"batch.tsv": "\n".join(lines) + "\n",
                                       "batch.sha256": "".join(hashes)}.items():
                        encoded = data.encode(); info = tarfile.TarInfo(name); info.size = len(encoded)
                        archive.addfile(info, io.BytesIO(encoded))
                subprocess.run(SSH + ["scp", "-O"] + OPTIONS + [str(bundle),
                    f"root@192.168.1.15:{DEVICE}/batch.tar"], check=True, timeout=180)
                verification = remote(f"cd {DEVICE} && tar -xf batch.tar && sha256sum -c batch.sha256")
                assert verification.count(": OK") == len(group)
                result = remote(f"ulimit -v 220000; {BINARY} --manifest {DEVICE}/batch.tsv", 45)
                path = output / f"batch-{begin:06d}.jsonl"
                path.write_text(result)
                calls = [entry["result"] for line in result.splitlines()
                         if "result" in (entry := json.loads(line))]
                assert [call["sequence"] for call in calls] == list(range(len(group)))
                assert all(len(call["rows"]) == 2 for call in calls)
                save(output / "inventory.json", inventory)
                # Only files this invocation created under its exclusive device directory.
                names = [f"{DEVICE}/visit-{e['visit_index']:06d}.ci16" for e in group]
                remote("rm " + " ".join(map(shlex.quote, names + [DEVICE + "/batch.tar"])))
                print(json.dumps({"completed": begin + len(group), "total": len(events),
                                  "elapsed_s": round(time.monotonic() - started, 2)}), flush=True)
        save(output / "completion.json", {"status": "PASS", "session": SESSION,
            "manifest": MANIFEST, "visits": len(inventory), "elapsed_s": time.monotonic() - started,
            "binary_sha256": expected[BINARY],
            "scope": "Fresh coarse-gate-disabled ARM detector on all original full 120ms dwells; 20ms/RX sparse probes; excludes RF"})
    finally:
        store.close()


if __name__ == "__main__":
    main()
