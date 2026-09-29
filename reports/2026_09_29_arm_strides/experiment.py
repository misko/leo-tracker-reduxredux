"""Frozen saved-IQ panel and serial physical-ARM comparison; never opens a radio."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shlex
import subprocess
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SEED = 20260929


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def freeze(args):
    destination = HERE / "panel.json"
    if destination.exists():
        raise RuntimeError("Panel is already frozen")
    manifest = json.loads(args.corpus_manifest.read_text())
    oracle = json.loads((args.oracle / "oracle.json").read_text())
    templates = {(c["context"]["rate_hz"], c["context"]["target"]["edge"]): c["templates"]
                 for c in oracle["cases"]}
    rng = random.Random(SEED)
    selected = []
    for rate, count in ((2500000, 32), (5000000, 8), (7500000, 8), (10000000, 8)):
        candidates = sorted((r for r in manifest["selected"] if r["rate_hz"] == rate),
                            key=lambda r: (r["session_id"], r["visit_index"]))
        for context in rng.sample(candidates, count):
            path = args.inputs / context["file"]
            assert sha(path) == context["sha256"]
            source = np.load(path, allow_pickle=False)
            assert source.dtype == np.int16 and source.shape == (rate * 120 // 1000, 2, 2)
            template = templates[(rate, context["target"]["edge"])]
            for item in template.values():
                assert sha(args.oracle / item["file"]) == item["sha256"]
            selected.append({"context": context, "templates": template,
                             "ci16_sha256": hashlib.sha256(source.tobytes()).hexdigest()})
    save(destination, {"schema": "arm-stride-panel/v1", "seed": SEED,
                       "selection": "whole dwells, deterministic random sample within each rate",
                       "source_manifest_sha256": sha(args.corpus_manifest),
                       "oracle_manifest_sha256": sha(args.oracle / "oracle.json"),
                       "dwell_ms": 120, "strides_ms": [10, 20, 120], "rounds": 2,
                       "selected": selected})


def run(args):
    from leo.contracts.arm_glrt import ArmGlrtConfigurationV1, ArmGlrtInputBindingV1
    from leo.scanner.arm_glrt import validate_native_output

    panel_path = HERE / "panel.json"
    panel = json.loads(panel_path.read_text())
    binary_hash = sha(args.binary)
    destination = HERE / args.output
    destination.mkdir(parents=True, exist_ok=True)
    identity = {"schema": "arm-stride-execution/v1", "panel_sha256": sha(panel_path),
                "binary_sha256": binary_hash, "build_receipt_sha256": sha(args.receipt),
                "runner_sha256": sha(Path(__file__)),
                "target": args.target, "hardware": "PLUTO+ CPU0", "rounds": panel["rounds"],
                "timing_scope": "detector CPU includes preparation/proposals/search; excludes setup, file I/O, serialization, SSH and capture"}
    binding = destination / "binding.json"
    if binding.exists():
        assert json.loads(binding.read_text()) == identity
    else:
        save(binding, identity)
    prefix = ["sudo", "-n", "sshpass", "-f", str(args.password_file)] if args.password_file else []
    options = ["-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-o",
               "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]

    def remote(command, timeout=180):
        return subprocess.check_output([*prefix, "ssh", *options, args.target, command],
                                       text=True, timeout=timeout)

    def upload(source, target):
        subprocess.run([*prefix, "scp", "-O", *options, str(source), f"{args.target}:{target}"],
                       check=True, timeout=120, capture_output=True)
        assert remote("sha256sum " + shlex.quote(target)).split()[0] == sha(source)

    root = "/mnt/glrtbench/strides-" + binary_hash[:12] + "-" + sha(panel_path)[:12]
    remote("mkdir -p " + shlex.quote(root))
    upload(args.binary, root + "/leo-native-glrt")
    remote("chmod +x " + shlex.quote(root + "/leo-native-glrt"))
    if not (destination / "hardware.json").exists():
        save(destination / "hardware.json", {"uname": remote("uname -a"),
                                             "cpuinfo": remote("cat /proc/cpuinfo")})
    uploaded = set()
    rng = random.Random(SEED)
    for index, case in enumerate(panel["selected"]):
        context = case["context"]
        rate = context["rate_hz"]
        modes = [(round_id, stride) for round_id in range(panel["rounds"])
                 for stride in panel["strides_ms"]]
        rng.shuffle(modes)
        pending = [(repeat, stride) for repeat, stride in modes
                   if not (destination / f"{index:03d}-{repeat}-{stride}.json").exists()]
        if not pending:
            continue
        source = args.inputs / context["file"]
        assert sha(source) == context["sha256"]
        values = np.load(source, allow_pickle=False)
        with tempfile.TemporaryDirectory(prefix="leo-strides-") as temporary:
            raw = Path(temporary) / "input.ci16"
            values.tofile(raw)
            assert sha(raw) == case["ci16_sha256"]
            remote_raw = root + f"/input-{index}.ci16"
            upload(raw, remote_raw)
        paths = {}
        for role in ("exact", "control"):
            template = case["templates"][role]
            local = args.oracle / template["file"]
            assert sha(local) == template["sha256"]
            target = root + "/template-" + template["sha256"]
            if target not in uploaded:
                upload(local, target)
                uploaded.add(target)
            paths[role] = target
        for repeat, stride in pending:
            # The production configuration validates and routes the same geometry
            # as the packaged command. Detector implementation is never duplicated.
            cfg = ArmGlrtConfigurationV1(rate_hz=rate, dwell_ms=120,
                                         probe_stride_ms=stride)
            command = [root + "/leo-native-glrt", "--rate-hz", str(rate),
                       "--dwell-ms", "120", "--probe-stride-ms", str(cfg.probe_stride_ms),
                       "--exact-template", paths["exact"], "--control-template", paths["control"],
                       "--input-ci16", remote_raw]
            payload = remote(shlex.join(command)).encode()
            input_binding = ArmGlrtInputBindingV1(
                input_sha256=context["manifest_sha256"],
                ci16_sha256="sha256:" + case["ci16_sha256"], receiver_ids=(0, 1),
                dwells=({"dwell_index": 0, "source_sample_start": context["sample_start_counter"],
                         "channel": context["target"]["channel"], "edge": context["target"]["edge"],
                         "actual_rf_hz": context["target"]["rf_center_hz"] - context["actual_if_offset_hz"]},))
            validated = validate_native_output(
                payload, configuration=cfg, input_binding=input_binding,
                native_binary_sha256="sha256:" + binary_hash,
                exact_template_sha256="sha256:" + case["templates"]["exact"]["sha256"],
                control_template_sha256="sha256:" + case["templates"]["control"]["sha256"])
            output = json.loads(payload)
            save(destination / f"{index:03d}-{repeat}-{stride}.json",
                 {"context": context, "round": repeat, "stride_ms": stride,
                  "binary_sha256": binary_hash, "ci16_sha256": case["ci16_sha256"],
                  "output": output, "validated_result": validated.model_dump(mode="json")})
            print(f"completed dwell={index + 1}/56 round={repeat} stride={stride}", flush=True)
    files = sorted(destination.glob("[0-9]*.json"))
    assert len(files) == len(panel["selected"]) * panel["rounds"] * len(panel["strides_ms"])
    save(destination / "manifest.json", {**identity, "complete": True,
                                         "files": {p.name: sha(p) for p in files}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("--corpus-manifest", type=Path)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", default="local/arm")
    parser.add_argument("--target", default="root@192.168.1.15")
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    (freeze if args.action == "freeze" else run)(args)


if __name__ == "__main__":
    main()
