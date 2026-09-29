"""Stage saved IQ and run the maintained native qualification client on CPU0."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import shlex
import subprocess
import tarfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def connection(args):
    prefix = ["sudo", "-n", "sshpass", "-f", str(args.password_file)]
    options = ["-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-o",
               "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]

    def remote(command, timeout=300):
        return subprocess.check_output([*prefix, "ssh", *options, args.target, command],
                                       text=True, timeout=timeout)

    def upload(source, destination):
        subprocess.run([*prefix, "scp", "-O", *options, str(source),
                        f"{args.target}:{destination}"], capture_output=True,
                       timeout=240, check=True)
        assert remote("sha256sum " + shlex.quote(destination)).split()[0] == digest(source)

    return remote, upload


def stage(args):
    panel = json.loads((HERE / "panel.json").read_text())
    local = HERE / "local"
    local.mkdir(exist_ok=True)
    root = "/mnt/glrtbench/headroom-" + digest(HERE / "panel.json")[:12]
    payloads = {}
    cases = []
    for item in panel["selected"] + panel["compatibility"]:
        c = item["context"]
        source = args.inputs / c["file"]
        assert digest(source) == c["sha256"]
        values = np.load(source, allow_pickle=False)
        assert values.dtype == np.int16 and values.shape == (c["rate_hz"] * 120 // 1000, 2, 2)
        raw = values.tobytes()
        name = hashlib.sha256(raw).hexdigest() + ".ci16"
        payloads[name] = raw
        names = {}
        for role, template in item["templates"].items():
            path = args.oracle / template["file"]
            assert digest(path) == template["sha256"]
            names[role] = template["sha256"] + ".c128"
            payloads[names[role]] = path.read_bytes()
        cases.append({**item, "raw_file": name, "template_files": names})
    groups = []
    rng = random.Random(panel["seed"])
    for rate in (2500000, 5000000, 7500000, 10000000):
        for edge in ("lower", "upper"):
            subset = [c for c in cases if c["context"]["rate_hz"] == rate
                      and c["context"]["target"]["edge"] == edge]
            batch_size = 16 if rate == 2500000 else 4
            for offset in range(0, len(subset), batch_size):
                group = subset[offset:offset + batch_size]
                if not group:
                    continue
                group_id = f"{rate}-{edge}-{offset:03d}"
                rows, mapping = [], []
                for repeat in range(panel["rounds"] if rate == 2500000 else 2):
                    order = list(range(len(group)))
                    rng.shuffle(order)
                    for i in order:
                        item = group[i]
                        seq = len(rows)
                        rows.append("\t".join(map(str, (seq, rate, 120, 120,
                            root + "/" + item["template_files"]["exact"],
                            root + "/" + item["template_files"]["control"],
                            root + "/" + item["raw_file"]))))
                        mapping.append({"sequence": seq, "repeat": repeat, "case": item})
                manifest = group_id + ".tsv"
                payloads[manifest] = ("\n".join(rows) + "\n").encode()
                groups.append({"id": group_id, "manifest": manifest, "rate_hz": rate,
                               "unique_dwells": len(group), "calls": mapping})
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()}
    payloads["inputs.sha256"] = "".join(f"{h}  {n}\n" for n, h in hashes.items()).encode()
    bundle = local / "inputs.tar"
    with tarfile.open(bundle, "w") as archive:
        for name, value in payloads.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))
    save(HERE / "execution-panel.json", {"panel_sha256": digest(HERE / "panel.json"),
         "remote_root": root, "files": hashes, "groups": groups})
    remote, upload = connection(args)
    remote("mkdir -p " + shlex.quote(root))
    upload(bundle, root + "/inputs.tar")
    remote("cd " + shlex.quote(root) + " && tar -xf inputs.tar && sha256sum -c inputs.sha256", 240)
    print("staged", len(cases), "unique saved dwells in", len(groups), "groups", flush=True)


def run(args):
    panel = json.loads((HERE / "execution-panel.json").read_text())
    remote, upload = connection(args)
    root = panel["remote_root"]
    output = HERE / "local" / args.label
    output.mkdir(parents=True, exist_ok=True)
    identity = {"execution_panel_sha256": digest(HERE / "execution-panel.json"),
                "binary_sha256": digest(args.binary), "receipt_sha256": digest(args.receipt),
                "runner_sha256": digest(Path(__file__)),
                "label": args.label, "profile_enabled": not args.no_profile,
                "thermal_sensor": "xadc", "thermal_raw_offset": -2219,
                "thermal_scale_millidegrees": 123.040771484}
    binding = output / "binding.json"
    if binding.exists():
        assert json.loads(binding.read_text()) == identity
    else:
        save(binding, identity)
    executable = root + "/bench-" + identity["binary_sha256"][:16]
    upload(args.binary, executable)
    remote("chmod +x " + shlex.quote(executable))
    for group in panel["groups"]:
        if args.primary_only and group["rate_hz"] != 2500000:
            continue
        path = output / (group["id"] + ".jsonl")
        if path.exists():
            continue
        command = [executable, "--manifest", root + "/" + group["manifest"],
                   "--thermal-path", "/sys/bus/iio/devices/iio:device1/in_temp0_raw",
                   "--thermal-offset", "-2219", "--thermal-scale", "123.040771484"]
        if args.no_profile:
            command.append("--no-profile")
        started = time.monotonic()
        result = remote(shlex.join(command), 300)
        rows = [json.loads(line) for line in result.splitlines()]
        assert rows[0]["kind"] == "setup" and rows[-1]["kind"] == "summary"
        assert len(rows) == len(group["calls"]) + 2
        path.write_text(result)
        save(output / (group["id"] + ".transport.json"), {
            "ssh_wall_seconds": time.monotonic() - started,
            "scope": "transport wall, not device deadline time"})
        print(args.label, group["id"], len(group["calls"]), "calls complete", flush=True)
    save(output / "manifest.json", {**identity, "files": {
        p.name: digest(p) for p in sorted(output.glob("*.jsonl"))}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--target", default="root@192.168.1.15")
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--oracle", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--no-profile", action="store_true")
    parser.add_argument("--primary-only", action="store_true")
    args = parser.parse_args()
    (stage if args.action == "stage" else run)(args)
