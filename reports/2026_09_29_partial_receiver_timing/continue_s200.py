"""Administrative continuation of s200 fits/audits; no completed job is rerun."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
phase = sys.argv[1]
assert phase in ("fit", "held")
plan = json.loads((HERE / "plan.json").read_text())
frozen = json.loads((HERE / "input-seal.json").read_text())["sha256"]
for name, digest in frozen.items():
    if name.endswith(".py") or name in {
        str((HERE / "plan.json").relative_to(ROOT)),
        str((HERE / "PROTOCOL.md").relative_to(ROOT)),
    }:
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
template_folder = "fit/origin" if phase == "fit" else "held"
template = json.loads(
    (HERE / "runs/DS7_early_4_s010" / template_folder / "launch.json").read_text()
)["command"]
assert template[-2] == phase and template[-4] == str(HERE / "run.py")


def verify_completed(folder):
    assert (folder / "exit-code.txt").is_file(), f"Unfinished job requires inspection: {folder}"
    seal = json.loads((folder / "seal.json").read_text())["sha256"]
    for path in folder.iterdir():
        if path.is_file() and path.name != "seal.json":
            assert (
                hashlib.sha256(path.read_bytes()).hexdigest() == seal[str(path.relative_to(ROOT))]
            )


for unit in plan["units"]:
    if unit["strength"] != "s200":
        continue
    parent = HERE / "runs" / unit["unit_id"]
    starts = [s["label"] for s in unit["starts"]]
    if phase == "held":
        runs = []
        for label in starts:
            folder = parent / "fit" / label
            verify_completed(folder)
            code = int((folder / "exit-code.txt").read_text())
            runs.append(
                {
                    "start": label,
                    "exit_code": code,
                    "result": json.loads((folder / "result.json").read_text())
                    if code == 0
                    else None,
                }
            )
        eligible = [r["result"] for r in runs if r["result"] and r["result"]["qualified"]]
        selected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        selection = {"runs": runs, "qualified_starts": len(eligible), "selected": selected}
        selection_path = parent / "selection.json"
        if selection_path.exists():
            assert json.loads(selection_path.read_text()) == selection
        else:
            with selection_path.open("x") as stream:
                json.dump(selection, stream, indent=2)
        if selected is None:
            continue
        starts = ["selected"]
    for label in starts:
        folder = parent / "fit" / label if phase == "fit" else parent / "held"
        if folder.exists():
            verify_completed(folder)
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
                "receiver_filter.py",
                "partial_timing.py",
                "continue_s200.py",
                "continuation-s200.json",
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
        if phase == "held":
            paths.append(parent / "selection.json")
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
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "launch.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "sha256": bindings,
                    "available_bytes": available,
                    "administrative_continuation": "continue_s200.py after memory-headroom pause",
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
        print(unit["unit_id"], phase, label, result.returncode, flush=True)
