import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

from selection import ROOT


def selected_batch(selection, start, count):
    if not 1 <= count <= 4 or not 0 <= start < len(selection["selected"]):
        raise ValueError("Use one to four selected scans per bounded batch")
    return selection["selected"][start : start + count]


def verify_finished_fit(directory, existing):
    for name in ("bundle.json", "bundle.npz"):
        current = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if existing["input_sha256"].get(name) != current:
            raise RuntimeError("Existing fit uses different input data")
    for name in ("models.py", "bundle.py", "fast_geometry.py", "fast_tracks.py"):
        current = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        recorded = existing["source_sha256"].get(f"{ROOT.name}/{name}")
        if recorded != current:
            raise RuntimeError("Existing fit uses a different scientific implementation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("export", "fit"))
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=4)
    args = parser.parse_args()
    selection = json.loads((ROOT / "selection.json").read_text())
    try:
        selected = selected_batch(selection, args.start, args.count)
    except ValueError as error:
        parser.error(str(error))
    environment = dict(
        os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1"
    )
    for session in selected:
        directory = ROOT / "scans" / session
        directory.mkdir(parents=True, exist_ok=True)
        if args.phase == "export" and (directory / "bundle.json").exists():
            from bundle import Data

            Data(directory)
            print(
                json.dumps({"session_id": session, "status": "verified existing export"}),
                flush=True,
            )
            continue
        if args.phase == "fit" and (directory / "fits.json").exists():
            existing = json.loads((directory / "fits.json").read_text())
            if existing.get("status") == "finished":
                verify_finished_fit(directory, existing)
                print(
                    json.dumps({"session_id": session, "status": "existing finished fit"}),
                    flush=True,
                )
                continue
            raise RuntimeError("Inspect previous process state before resuming an unfinished fit")
        script = "export_ds11.py" if args.phase == "export" else "run_case.py"
        command = [sys.executable, str(ROOT / script), session]
        started = time.monotonic()
        with (directory / f"{args.phase}.log").open("w") as stream:
            try:
                completed = subprocess.run(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    timeout=70 if args.phase == "export" else 550,
                )
                status = "finished" if completed.returncode == 0 else "failed"
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                status, returncode = "timeout", None
        receipt = {
            "session_id": session,
            "phase": args.phase,
            "command": command,
            "status": status,
            "returncode": returncode,
            "elapsed_s": time.monotonic() - started,
        }
        (directory / f"{args.phase}-process.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
