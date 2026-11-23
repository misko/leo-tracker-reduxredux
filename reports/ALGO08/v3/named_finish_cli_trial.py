"""Compare both settings of the portable final-fit switch on one authenticated saved fix."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from aperture_trial import archive_identity, read, write
from dense_geographic_trial import host
from empty_bootstrap import RELEASE, checked
from full_short_physical import environment
from joint_publication import artifacts
from short_raw_diagnostic import measure, pairs
from weak_cairo_combined import JOB, JOB_SHA


HERE = Path(__file__).resolve().parent


def run(root):
    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a private tmpfs output")
    job = json.loads(checked(JOB, JOB_SHA))
    if archive_identity(Path(job["archive"]["root"])) != job["archive"]:
        raise ValueError("Changed causal archive")
    root.mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    runs = {}
    for enabled in (True, False):
        mode = "named-finish" if enabled else "ordinary"
        target = root / mode
        command = [python, "-IB", HERE / "cumulative_grid_projection.py", "worker", JOB, "combined", target]
        if enabled:
            command.append("--named-survivor-finish")
        clock = measure(command, env, target)
        write(root / (mode + "-clock.json"), clock)
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
        worker = read(target / "cumulative-grid-worker.json")
        pub = worker["receipt"]
        terminal, = (target / "fast-scan-automatic-work").glob("*/terminal.json")
        terminal_doc = json.loads(checked(terminal, pub["terminal_sha256"].removeprefix("sha256:")))
        if (worker["waveform_calls"] or worker["handoffs"] != 1 or pub["decision"] != "complete"
                or terminal_doc["native_sha256"] != job["native"] or pub["session_id"] != job["session"]
                or pub["region"] != read(Path(job["region"])) or bool(worker["named_survivor_finish"]) != enabled):
            raise ValueError("Saved publication differs from the enrolled input or requested option")
        science = pairs.evidence(target, pub, clock["started_unix_ns"], read_only=True)
        media = artifacts(target, pub)["images"]
        if len(media) != 8 or science["raw_authority"] != job["authority"]:
            raise ValueError("Incomplete scientific publication")
        runs[mode] = dict(clock=clock, receipt=pub, science=science, media=media, finish=worker["named_survivor_finish"])
    # Survey joins only after both complete results have been checked.
    from triage_bounds import REFERENCE, REFERENCE_SHA256, distance_km
    ref, = (r for r in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if r["dataset_label"] == "DS30-0016" and r["authority_eligible"] and r["sealed_metadata_digests_verified"])
    truth = [ref["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    for result in runs.values():
        result["errors_km"] = {arm: distance_km(truth, state["latlon"]) for arm, state in result["science"]["arms"].items()}
    files = ("unified_short_bootstrap.py", "cumulative_grid_projection.py", "isolated_salvage.py", "named_survivor_fit.py")
    write(root / "result.json", dict(machine=machine, request_sha256=JOB_SHA, runs=runs,
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in files}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
