"""Run one frozen export stage, preserving success, failure and resource receipts."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("unit")
parser.add_argument("stage", choices=("observations", "banks"))
args = parser.parse_args()
plan = json.loads((HERE / "plan.json").read_text())
matches = [r for r in plan["captures"] if r["unit_id"] == args.unit]
if len(matches) != 1:
    raise ValueError("unit not in frozen panel")
row = matches[0]
for source in plan["sources"]:
    assert hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() == source["sha256"]
receipt = HERE / "receipts" / args.unit / args.stage
receipt.mkdir(parents=True, exist_ok=False)
output = HERE / "exports" / args.unit
output.mkdir(parents=True, exist_ok=True)
python = RELEASE / ".venv/bin/python"
environment = subprocess.check_output(
    ["sudo", "-n", str(python), str(HERE / "environment.py")], text=True
)
parsed = json.loads(environment)
assert all(str(RELEASE) in v["path"] for v in parsed["modules"].values())
(receipt / "environment.json").write_text(environment)
arguments = [
    "--plan",
    str(HERE / "plan.json"),
    "--session",
    row["session_id"],
    "--output",
    str(output / ("observations.json" if args.stage == "observations" else "banks")),
]
if args.stage == "banks":
    arguments.extend(["--banks", "--tracks", str(output / "observations.json")])
command = [
    "sudo",
    "-n",
    "/usr/bin/time",
    "-v",
    "-o",
    str(receipt / "resources.txt"),
    "timeout",
    "--kill-after=5s",
    "60s" if args.stage == "observations" else "120s",
    "prlimit",
    "--as=4294967296",
    "nice",
    "-n",
    "19",
    "env",
    "OPENBLAS_NUM_THREADS=1",
    "OMP_NUM_THREADS=1",
    "MKL_NUM_THREADS=1",
    str(python),
    str(ROOT / "tools/ds7_export_baseline.py"),
    *arguments,
]
paths = [
    Path(__file__),
    HERE / "environment.py",
    HERE / "PROTOCOL.md",
    HERE / "plan.json",
    HERE / "prepare.py",
    ROOT / "tools/ds7_export_baseline.py",
]
if args.stage == "banks":
    paths.append(output / "observations.json")
with (receipt / "launch.json").open("x") as stream:
    json.dump(
        {
            "command": command,
            "unit_id": args.unit,
            "stage": args.stage,
            "sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
            },
        },
        stream,
        indent=2,
    )
with (receipt / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
(receipt / "exit-code.txt").write_text(str(result.returncode) + "\n")
print(
    json.dumps({"unit_id": args.unit, "stage": args.stage, "exit_code": result.returncode}),
    flush=True,
)
raise SystemExit(result.returncode)
