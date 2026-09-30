"""Bounded replay of two existing stored visits using the unchanged recovery script."""

import hashlib
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / "2026_09_29_ds10_signal_extension"
RUNTIME = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def main():
    rows = json.loads((BASE / "local/rows.json").read_text())
    eligible = [r for r in rows if r["dataset"] == "DS10" and r["rate"] == 10000000
                and r["edge"] == "lower" and r["tier"] == "control_supported_candidate"
                and r["norad_id"] != 63400]
    selected, identities = [], set()
    for row in sorted(eligible, key=lambda r: -r["pilot"]):
        if row["norad_id"] not in identities:
            selected.append(row)
            identities.add(row["norad_id"])
        if len(selected) == 2:
            break
    assert len(selected) == 2
    script = PRIOR / "paired_recovery.py"
    plan = dict(selection="Top pilot-qualified lower-edge 10MS/s DS10 strong candidates, "
                          "two distinct IDs other than 63400; no selection on early signs",
                script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
                targets=selected, recording_seconds_per_receiver_per_visit=.120,
                timeout_seconds_per_visit=240)
    output = BASE / "local/paired-extension.json"
    output.write_text(json.dumps(plan, indent=2) + "\n")
    results = []
    for row in selected:
        name = f"{row['unit']}-v{row['visit']}"
        folder = PRIOR / "local/paired" / name
        summary = folder / "summary.json"
        if summary.exists():
            state = "reused_existing_summary"
        elif folder.exists():
            state = "abstain_existing_incomplete_output"
        else:
            command = ["sudo", "-n", "-g", "leo", "env", "OPENBLAS_NUM_THREADS=1",
                       "OMP_NUM_THREADS=1", RUNTIME, "-I", str(script),
                       "--unit", row["unit"], "--visit", str(row["visit"]),
                       "--receiver", str(row["receiver"])]
            with (BASE / f"local/{name}-recovery.log").open("w") as log:
                try:
                    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=240, check=False)
                    state = f"exit_{completed.returncode}"
                except subprocess.TimeoutExpired:
                    state = "timeout_no_restart"
        record = dict(visit=name, candidate=row["norad_id"], state=state,
                      summary_path=str(summary))
        if summary.exists():
            data = json.loads(summary.read_text())
            record.update(summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest(),
                          qualified_frames=len(data["qualified_frames"]),
                          header=data["header"].get("matched"))
        results.append(record)
        plan["results"] = results
        output.write_text(json.dumps(plan, indent=2) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
