"""Continue unstarted audits, preserving selections and original command limits."""

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
template = json.loads((HERE / "runs/DS9_early_8_s050/held/launch.json").read_text())["command"]
for unit in plan["units"]:
    if unit["strength"] != "s050":
        continue
    parent = HERE / "runs" / unit["unit_id"]
    runs = []
    for start in unit["starts"]:
        folder = parent / "fit" / start["label"]
        code = int((folder / "exit-code.txt").read_text())
        seal = json.loads((folder / "seal.json").read_text())["sha256"]
        for path in folder.iterdir():
            if path.is_file() and path.name != "seal.json":
                assert (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    == seal[str(path.relative_to(ROOT))]
                )
        runs.append(
            {
                "start": start["label"],
                "exit_code": code,
                "result": json.loads((folder / "result.json").read_text()) if code == 0 else None,
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
    folder = parent / "held"
    if folder.exists():
        assert (folder / "exit-code.txt").is_file(), (
            f"Unfinished audit requires inspection: {folder}"
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
            "receiver_filter.py",
            "partial_timing.py",
            "continue_held_s050.py",
            "continuation-s050-07.json",
        )
    ] + [selection_path]
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
            assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
            paths.append(path)
    bindings = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    command = template.copy()
    command[5] = str(folder / "resources.txt")
    command[-3] = unit["unit_id"]
    assert command[-2:] == ["held", "selected"] and command[-4] == str(HERE / "run.py")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "launch.json").write_text(
        json.dumps(
            {
                "command": command,
                "sha256": bindings,
                "available_bytes": available,
                "administrative_continuation": "continue_held_s050.py after memory-headroom pause",
            },
            indent=2,
        )
    )
    with (folder / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    (folder / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for path in folder.iterdir():
        if path.is_file():
            bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
    print(unit["unit_id"], "held selected", result.returncode, flush=True)
