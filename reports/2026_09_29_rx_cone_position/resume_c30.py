"""Administrative continuation after launcher 143; never rerun an existing fit."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
unit_id = "DS9_middle_4_c30"
folder = HERE / "runs" / unit_id / "fit/baseline"
assert not (folder / "exit-code.txt").exists()
assert not (folder / "seal.json").exists()
launch = json.loads((folder / "launch.json").read_text())
result = json.loads((folder / "result.json").read_text())
assert result["unit_id"] == unit_id and result["start"] == "baseline"
assert result["phase"] == "fit"
assert (folder / "resources.txt").read_text().endswith("\tExit status: 0\n")
assert (folder / "terminal.log").read_text().endswith(f"{unit_id} fit baseline complete\n")
bindings = launch["sha256"].copy()
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
recovery = {
    "launcher_session": 56034,
    "launcher_exit_code": 143,
    "cause": "Not established",
    "live_process_check": "No launch.py/run.py/time child remained in process listing",
    "completed_child": f"{unit_id}/fit/baseline",
    "child_exit_code_source": "GNU time resources.txt Exit status: 0",
    "terminal_completion_line": f"{unit_id} fit baseline complete",
    "action": "Recover missing exit receipt and seal; do not rerun completed child",
    "remaining": [
        f"{u['unit_id']}/{s['label']}"
        for u in plan["units"]
        if u["strength"] == "c30"
        for s in u["starts"]
        if not (HERE / "runs" / u["unit_id"] / "fit" / s["label"]).exists()
    ],
}
assert len(recovery["remaining"]) == 12
with (folder / "recovery.json").open("x") as stream:
    json.dump(recovery, stream, indent=2)
with (folder / "exit-code.txt").open("x") as stream:
    stream.write("0\n")
for path in folder.iterdir():
    if path.is_file():
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
bindings[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(
    Path(__file__).read_bytes()
).hexdigest()
with (folder / "seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Recovered completed child receipt; no refit", flush=True)

for unit in plan["units"]:
    if unit["strength"] != "c30":
        continue
    for start in unit["starts"]:
        label = start["label"]
        folder = HERE / "runs" / unit["unit_id"] / "fit" / label
        if folder.exists():
            assert (folder / "seal.json").exists()
            assert (folder / "exit-code.txt").exists()
            continue
        assert f"{unit['unit_id']}/{label}" in recovery["remaining"]
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available = int(mem["MemAvailable"].split()[0]) * 1024
        assert available >= 5 * 1024**3
        folder.mkdir(parents=True, exist_ok=False)
        paths = [
            HERE / n
            for n in (
                "PROTOCOL.md",
                "prepare.py",
                "plan.json",
                "input-seal.json",
                "run.py",
                "launch.py",
                "cone_position.py",
                "cones.py",
                "resume_c30.py",
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
        command = [
            "sudo",
            "-n",
            "/usr/bin/time",
            "-v",
            "-o",
            str(folder / "resources.txt"),
            "timeout",
            "--kill-after=5s",
            "180s",
            "prlimit",
            "--as=4294967296",
            "nice",
            "-n",
            "19",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python",
            str(HERE / "run.py"),
            unit["unit_id"],
            "fit",
            label,
        ]
        expected = launch["command"].copy()
        expected[5] = str(folder / "resources.txt")
        expected[-3], expected[-1] = unit["unit_id"], label
        assert command == expected, "Continuation must preserve original command and limits"
        (folder / "launch.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "sha256": bindings,
                    "available_bytes": available,
                    "administrative_continuation": "resume_c30.py; original launcher exit 143",
                },
                indent=2,
            )
        )
        with (folder / "terminal.log").open("x") as stream:
            process = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        (folder / "exit-code.txt").write_text(str(process.returncode) + "\n")
        for path in folder.iterdir():
            if path.is_file():
                bindings[str(path.relative_to(ROOT))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        (folder / "seal.json").write_text(json.dumps({"sha256": bindings}, indent=2))
        print(unit["unit_id"], "fit", label, process.returncode, flush=True)
