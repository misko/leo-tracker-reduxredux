"""Continue unstarted s050 fits after a memory-headroom pause; never rerun fits."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
frozen = json.loads((HERE / "input-seal.json").read_text())["sha256"]
for name, digest in frozen.items():
    if name.endswith(".py") or name in {
        str((HERE / "plan.json").relative_to(ROOT)),
        str((HERE / "PROTOCOL.md").relative_to(ROOT)),
    }:
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
original = HERE / "runs/DS8_late_4_s050/fit/southeast/launch.json"
template = json.loads(original.read_text())["command"]
for unit in plan["units"]:
    if unit["strength"] != "s050":
        continue
    for start in unit["starts"]:
        label = start["label"]
        folder = HERE / "runs" / unit["unit_id"] / "fit" / label
        if folder.exists():
            assert (folder / "exit-code.txt").is_file(), (
                f"Unfinished job requires inspection: {folder}"
            )
            seal = json.loads((folder / "seal.json").read_text())["sha256"]
            for path in folder.iterdir():
                if path.is_file() and path.name != "seal.json":
                    assert (
                        hashlib.sha256(path.read_bytes()).hexdigest()
                        == seal[str(path.relative_to(ROOT))]
                    )
            continue
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available = int(mem["MemAvailable"].split()[0]) * 1024
        assert available >= 5 * 1024**3, "Insufficient headroom; process not launched"
        paths = [
            HERE / n
            for n in (
                "PROTOCOL.md",
                "prepare.py",
                "plan.json",
                "input-seal.json",
                "run.py",
                "launch.py",
                "partial_timing.py",
                "receiver_filter.py",
                "continue_s050.py",
                "continuation-s050.json",
            )
        ]
        paths += [
            ROOT / "tools" / n
            for n in (
                "ds789_covariance_position.py",
                "ds789_correlated_residual.py",
                "ds7_fast_baseline_adapter.py",
                "ds7_baseline_adapter.py",
            )
        ]
        for item in unit["group"]["inputs"]:
            for artifact in item["artifacts"]:
                path = Path(artifact["path"])
                assert (
                    "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
                )
                paths.append(path)
        bindings = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        }
        command = template.copy()
        command[5] = str(folder / "resources.txt")
        command[-3], command[-1] = unit["unit_id"], label
        assert command[-2] == "fit" and command[-4] == str(HERE / "run.py")
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "launch.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "sha256": bindings,
                    "available_bytes": available,
                    "administrative_continuation": "continue_s050.py after memory-headroom pause",
                },
                indent=2,
            )
        )
        with (folder / "terminal.log").open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
        for path in folder.iterdir():
            if path.is_file():
                bindings[str(path.relative_to(ROOT))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
        print(unit["unit_id"], "fit", label, result.returncode, flush=True)
