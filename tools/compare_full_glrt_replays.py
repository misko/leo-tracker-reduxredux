"""Compare every native window and hypothesis in two frozen full-scan replays."""

import argparse
import json
import math
from pathlib import Path

import profile_algo07_full_glrt as full


def read(path):
    return json.loads(path.read_text())


def differences(left, right, path=""):
    """Require matching types and exact finite leaves; retain diagnostic paths."""
    if type(left) is not type(right):
        yield path
    elif isinstance(left, dict):
        if left.keys() != right.keys():
            yield path + "/keys"
        for key in sorted(left.keys() & right.keys()):
            yield from differences(left[key], right[key], path + "/" + str(key))
    elif isinstance(left, list):
        if len(left) != len(right):
            yield path + "/length"
        for index, (a, b) in enumerate(zip(left, right, strict=False)):
            yield from differences(a, b, path + f"/{index}")
    elif (isinstance(left, float) and (not math.isfinite(left) or not math.isfinite(right))
          or left != right):
        yield path


def argument(command, flag):
    if command.count(flag) != 1:
        raise ValueError(f"Expected one {flag} in replay command")
    return command[command.index(flag) + 1]


def trial(snapshot, root, frozen_hash, document):
    launch, timing, result = (read(root / name) for name in
                              ("launch.json", "timing.json", "result.json"))
    if not (timing["successful_execution"] and timing["exit_code"] == 0
            and not timing["timed_out"] and timing["manifest_unchanged"]
            and timing["reference_after"]["verified"] and result["exact"]):
        raise ValueError("Replay did not finish with verified inputs and published parity")
    if launch["manifest_sha256"] != frozen_hash:
        raise ValueError("Replay used another frozen reference")
    command = launch["command"]
    if Path(argument(command, "--input")).resolve() != snapshot / "input.json":
        raise ValueError("Replay used another input")
    if Path(argument(command, "--output")).resolve() != root:
        raise ValueError("Replay output identity differs")
    if int(argument(command, "--workers")) != result["workers"]:
        raise ValueError("Worker count differs from launch")
    source = Path(argument(command, "--source-root")).resolve(strict=True)
    bound = {Path(row["path"]) for row in read(snapshot / "frozen.json")["files"]}
    runtime = {p for p in (source / "src").rglob("*") if p.is_file()
               and p.suffix in (".py", ".so")}
    if not runtime or not runtime <= bound or snapshot / "input.json" not in bound:
        raise ValueError("Replay implementation or input is not frozen")
    tasks = {f"visits-{t['offset'] + t['start']:06d}.json": t
             for t in full.spans(document["inventory"])}
    rows = result["ranges"]
    if len(rows) != len(tasks) or {r["path"] for r in rows} != set(tasks):
        raise ValueError("Incomplete or duplicated range inventory")
    if {p.name for p in (root / "windows").iterdir()} != set(tasks):
        raise ValueError("Unexpected window files")
    windows, receipts = {}, {}
    for name, task in tasks.items():
        path = root / "windows" / name
        payload = read(path)
        receipts[name] = full.PROFILE.digest(path)
        if payload["task"] != task:
            raise ValueError("Task differs from frozen segment inventory")
        expected = list(range(task["offset"] + task["start"], task["offset"] + task["stop"]))
        if [w["visit"] for w in payload["windows"]] != expected:
            raise ValueError("Missing, reordered or duplicated native windows")
        for window in payload["windows"]:
            visit = window["visit"]
            if window["result"]["visit"] != visit or not window["published_candidates_exact"]:
                raise ValueError("Native result identity or published parity differs")
            windows[visit] = window["result"]
    processed = sum(w["status"] == "processed" for w in windows.values())
    expected_processed = len({p["visit_index"] for p in document["expected_probes"]})
    if not (len(windows) == result["windows"] == result["expected_windows"]
            and processed == result["processed"] == result["expected_processed"]
            == expected_processed):
        raise ValueError("Window summary differs from actual evidence")
    return dict(launch=launch, timing=timing, result=result, windows=windows,
                file_sha256=receipts, runtime=str(source))


def compare(snapshot, baseline, candidate, *, baseline_snapshot=None):
    snapshot, baseline, candidate = (p.resolve(strict=True)
                                     for p in (snapshot, baseline, candidate))
    if baseline == candidate:
        raise ValueError("Two independent trial directories are required")
    manifest = snapshot / "frozen.json"
    verified = full.PROFILE.verify(manifest)
    if not verified["verified"]:
        raise ValueError("Frozen evidence changed")
    frozen_hash = full.PROFILE.digest(manifest)
    document = read(snapshot / "input.json")
    baseline_snapshot = (baseline_snapshot.resolve(strict=True)
                         if baseline_snapshot is not None else snapshot)
    baseline_manifest = baseline_snapshot / "frozen.json"
    baseline_verified = full.PROFILE.verify(baseline_manifest)
    if not baseline_verified["verified"]:
        raise ValueError("Frozen baseline evidence changed")
    baseline_hash = full.PROFILE.digest(baseline_manifest)
    if list(differences(document, read(baseline_snapshot / "input.json"))):
        raise ValueError("Baseline and candidate input documents differ")
    a = trial(baseline_snapshot, baseline, baseline_hash, document)
    b = trial(snapshot, candidate, frozen_hash, document)
    mismatches = list(differences(a["windows"], b["windows"]))
    matched = (baseline_snapshot == snapshot
               and a["result"]["workers"] == b["result"]["workers"]
               and all(a["launch"][key] == b["launch"][key] for key in
                       ("executable", "python", "host", "thread_settings", "cprofile_enabled",
                        "script_sha256")))
    receiver_count = sum(len(w["receivers"]) for w in a["windows"].values())
    candidates = sum(len(r["candidates"]) for w in a["windows"].values() for r in w["receivers"])
    return dict(schema_version=1, exact=not mismatches, mismatch_count=len(mismatches),
                first_mismatches=mismatches[:30], windows=len(a["windows"]),
                receiver_results=receiver_count, all_candidates=candidates,
                matched_timing_configuration=matched,
                wall_speedup=(a["timing"]["wall_seconds"] / b["timing"]["wall_seconds"]
                              if matched and not mismatches else None),
                manifest_sha256=frozen_hash, frozen_verification=verified,
                baseline_manifest_sha256=baseline_hash,
                baseline_frozen_verification=baseline_verified,
                reused_baseline_snapshot=baseline_snapshot != snapshot,
                baseline={k: v for k, v in a.items() if k not in ("windows", "result")},
                candidate={k: v for k, v in b.items() if k not in ("windows", "result")},
                localization_replayed=False, production_modified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("snapshot", "baseline", "candidate", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--baseline-snapshot", type=Path,
                        help="Reuse identical frozen inputs for parity only; withhold timing ratio")
    args = parser.parse_args()
    result = compare(args.snapshot, args.baseline, args.candidate,
                     baseline_snapshot=args.baseline_snapshot)
    full.PROFILE.write_new(full.PROFILE.destination(args.output), result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("baseline", "candidate")}))
    if not result["exact"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
