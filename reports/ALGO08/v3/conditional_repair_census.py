"""Locate archived two-arm repair refusals without interpreting survey scores."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import zlib


ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = "reports/ALGO08/v3/measurements/"
MAX_BYTES = 12_000_000
JOINT_REFUSAL = "repair_original_joint_pair_gate"
CAP_REFUSAL = "repair_rejection_cap"
REASONS = re.compile(rb'"reason":\s*"(repair_(?:original_joint_pair_gate|rejection_cap|'
                     rb'unqualified_region|unqualified_orbital_support|insufficient_calibration_support))"')
ARMS = ("c0", "fitted_c")


def reason_mentions(body):
    return Counter(reason.decode() for reason in REASONS.findall(body))


def stored(revision):
    git = ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT)]
    entries = subprocess.check_output([*git, "ls-tree", "-r", "-l", revision, "--", DIRECTORY], text=True)
    counts, hits = Counter(), []
    with subprocess.Popen([*git, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as blobs:
        for line in entries.splitlines():
            info, name = line.split("\t", 1)
            _, kind, oid, size = info.split()
            if kind != "blob" or not name.endswith((".json", ".json.gz")):
                continue
            if int(size) > MAX_BYTES:
                counts["oversize_blob"] += 1
                continue
            blobs.stdin.write(oid.encode() + b"\n")
            blobs.stdin.flush()
            _, _, size = blobs.stdout.readline().split()
            body = blobs.stdout.read(int(size))
            if blobs.stdout.read(1) != b"\n":
                raise ValueError("Truncated Git blob")
            if name.endswith(".gz"):
                body = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(body, MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                counts["oversize_document"] += 1
                continue
            counts["checked"] += 1
            if reasons := reason_mentions(body):
                hits.append(dict(file=name.removeprefix(DIRECTORY), sha256=sha256(body).hexdigest(), reasons=reasons))
    return dict(revision=revision, counts=counts, mentions=hits)


def case_hint(path):
    hints = set(re.findall(r"(?<!\d)\d{4}(?!\d)", path.parts[0]))
    return "DS30-" + hints.pop() if len(hints) == 1 else None


def readout(arms):
    keys = ("curved_points", "compatible_curved_points", "linear_points", "compatible_linear_points",
            "final_phase_change_s", "east_north_km", "failed_curved", "failed_linear")
    if set(arms) != set(ARMS):
        return None
    return {arm: {key: arms[arm][key] for key in keys} for arm in ARMS}


def attempt_evidence(attempt):
    result = {key: attempt.get(key) for key in ("decision", "reason", "pair_passes")}
    repair = attempt.get("repair")
    if repair is not None:
        result["repair"] = {key: repair[key] for key in ("status", "reason", "attempted_refits", "rejection_counts")}
        result["repair"]["finish"] = readout(repair.get("finish", {}))
        if repair["status"] == "rejected":
            result["first_finish"] = readout(attempt.get("finish", {}))
    return result


def sealed_by(path, digest, stage):
    for parent in path.parents:
        if parent == stage:
            return None
        seal = parent / "prediction-seal.json"
        if seal.is_file() and seal.resolve().is_relative_to(stage) and seal.stat().st_size <= MAX_BYTES:
            body = seal.read_bytes()
            if json.loads(body).get(str(path.relative_to(parent))) == digest:
                return sha256(body).hexdigest()
    return None


def staged(stage):
    results, counts = [], Counter()
    for path in sorted(stage.glob("leo-v3-*/**/risk-route.json")):
        relative = path.relative_to(stage)
        if "reports" in relative.parts or not path.resolve().is_relative_to(stage):
            continue
        if path.stat().st_size > MAX_BYTES:
            counts["oversize"] += 1
            continue
        body = path.read_bytes()
        digest = sha256(body).hexdigest()
        counts["checked"] += 1
        attempts = [attempt_evidence(attempt) for solve in json.loads(body)["solves"]
                    for attempt in solve.get("lean_attempts", [])]
        results.append(dict(path=str(relative), case_hint=case_hint(relative), sha256=digest,
                            prediction_seal_sha256=sealed_by(path, digest, stage), attempts=attempts))
    return dict(counts=counts, files=results)


def physical_refusals(results):
    """Keep recorded case hints and the signed diagnostic evidence for each refusal."""
    return [(row["case_hint"], row["path"], attempt) for row in results["files"] if row["case_hint"] is not None
            for attempt in row["attempts"] if attempt.get("repair", {}).get("status") == "rejected"]


def census(revisions, stage):
    tracked = [stored(revision) for revision in revisions]
    routes = staged(stage)
    refusals = physical_refusals(routes)
    return dict(schema="leo.research.conditional-repair-transfer-census.v1", tracked=tracked, resident_routes=routes,
                route_case_hints=sorted({row["case_hint"] for row in routes["files"] if row["case_hint"] is not None
                                         and any(a["decision"] is not None for a in row["attempts"])}),
                completed_joint_refusal_hints=sorted({case for case, _, a in refusals
                                                       if a["repair"]["reason"] == JOINT_REFUSAL}),
                early_cap_refusal_hints=sorted({case for case, _, a in refusals
                                                if a["repair"]["reason"] == CAP_REFUSAL}),
                fresh_solver_workers=0, acquisition_bodies_read=0, tle_bodies_read=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", nargs="+")
    args = parser.parse_args()
    print(json.dumps(census(args.revision, Path("/dev/shm")), indent=2, sort_keys=True, allow_nan=False))
