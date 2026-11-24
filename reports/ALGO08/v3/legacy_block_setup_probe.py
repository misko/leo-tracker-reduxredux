"""Stop both approved raw entries at receiver construction, before any waveform access."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch


def measured(entry, argv):
    sys.path.insert(0, str(entry.parent))
    sys.path.append(str(entry.parents[3]))
    import empty_bootstrap as boot
    from legacy_block_raw_entry import parser, run as basic

    if entry.name == "legacy_block_all_entry.py":
        from legacy_block_all_entry import run
    elif entry.name == "legacy_block_raw_entry.py":
        run = basic
    else:
        raise ValueError("Expected one of the existing frozen entry choices")
    args = parser().parse_args(argv)
    if not args.recording.is_dir() or any(args.recording.iterdir()):
        raise ValueError("The preload probe requires an empty scratch recording")
    original = boot.load_runtime
    entry_modules = set(sys.modules)
    captured = {}

    def forbid(event, call):
        if event == "open" and isinstance(call[0], (str, bytes)) and str(call[0]).endswith(".ci16.zst"):
            raise ValueError("Setup-only probe cannot open original encoded data")

    class ReachedScanner(Exception):
        pass

    def clock(start):
        return dict(elapsed_s=perf_counter()-start[0], cpu_s=process_time()-start[1])

    def booted():
        start = perf_counter(), process_time()
        result = original()
        captured["release_startup"] = clock(start)
        captured["after_release"] = sorted(set(sys.modules)-entry_modules)
        captured["receiver_preparation_start"] = perf_counter(), process_time()
        return result

    def stop(*_args, **_kwargs):
        captured["through_scanner_boundary"] = clock(begin)
        captured["from_release_to_scanner"] = clock(captured.pop("receiver_preparation_start"))
        captured["added_before_scanner"] = sorted(set(sys.modules)-entry_modules-set(captured["after_release"]))
        captured["scientific_loaded"] = [name for name in boot.SCIENTIFIC_IMPORTS if name in sys.modules]
        raise ReachedScanner

    sys.addaudithook(forbid)
    begin = perf_counter(), process_time()
    try:
        with patch.object(boot, "load_runtime", booted), patch.object(boot, "staged_scanner", stop):
            run(args)
    except ReachedScanner:
        if captured["scientific_loaded"] or args.output.exists():
            raise ValueError("The setup probe must stop before science or durable publication")
        return captured
    raise ValueError("The actual worker did not reach the intended setup boundary")


def probe_roster(root):
    tiny = Path("/dev/shm/leo-v3-legacy-block-0107-result01")
    large = Path("/dev/shm/leo-v3-legacy-all-0016-result02")
    with (tiny/"admission.json").open("rb") as stream:
        base = json.load(stream)["commands"]
    with (large/"admission.json").open("rb") as stream:
        complete = json.load(stream)["commands"]["indexed"]
    root.mkdir(mode=0o700)
    (root/"empty-recording").mkdir()
    plan = json.loads((tiny/"maps/custody.json").read_bytes())
    for row in plan["members"]:
        if not row["map"]:
            raise ValueError("The source setup probe requires the previously committed literal map")
        row["map_kind"] = "literal"
    custody = root/"custody.json"
    custody.write_text(json.dumps(plan, sort_keys=True))
    for row in plan["members"]:
        (root/row["map"]).hardlink_to(tiny/"maps"/row["map"])
    complete[complete.index("--legacy-map-custody")+1] = str(custody)
    complete[complete.index("--legacy-map-custody-sha256")+1] = "sha256:"+sha256(custody.read_bytes()).hexdigest()
    for _, flag in enumerate(("--archive", "--region", "--archive-sha256")):
        complete[complete.index(flag)+1] = base["ordinary"][base["ordinary"].index(flag)+1]
    out = {}
    for name, command in (("ordinary", base["ordinary"]), ("literal", base["indexed"]), ("all_member", complete)):
        command[command.index("--recording")+1] = str(root/"empty-recording")
        command[command.index("--output")+1] = str(root/"unused-output")
        out[name] = [command[3], "-IB", str(Path(__file__).resolve()), command[5], *command[6:]]
    return out


def compare(root):
    roster = probe_roster(root)
    order = ("ordinary", "literal", "all_member", "all_member", "literal", "ordinary")
    out = []
    for name in order:
        start = perf_counter()
        result = subprocess.run(roster[name], check=True, capture_output=True, text=True, timeout=12)
        out.append(dict(name=name, process_wall_s=perf_counter()-start, pre_scanner=json.loads(result.stdout)))
    if (root/"unused-output").exists():
        raise ValueError("Setup comparisons must produce no publication")
    (root/"result.json").write_text(json.dumps(dict(order=order, runs=out, command=roster,
                                                     waveform_opens=0, starts_solver=False), indent=2)+"\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--compare":
        compare(Path(sys.argv[2]))
        sys.exit(0)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("entry", type=Path)
    cli.add_argument("argv", nargs=argparse.REMAINDER)
    options = cli.parse_args()
    print(json.dumps(measured(options.entry, options.argv)))
