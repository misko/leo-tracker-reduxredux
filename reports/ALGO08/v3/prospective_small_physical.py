"""Assign or passively admit one physical DS30 case without touching waveform bytes."""

import argparse
import csv
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROSTER = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac")
ROSTER_PINS = {
    "panel.json": "147886973a6419baa925263c02e7b8d37e13737c94518bba69a023f47389d399",
    "final/decision.json": "26ac73f584b58150b1205ccfb848b0317af322d5389c0b4e8eaf18c0a178f1f1",
    "final/recordings.csv": "8535781f2ed67016fe42c6ff820f503e9876c1b0f356f3cf2d9c1b6e8d216aa2",
}
TESTED = ("DS30-0008", "DS30-0016", "DS30-0057", "DS30-0227")
CASE = "DS30-0316"
PAIR_PIN = "334790daefa5a26511aa72328ecd2dc3124a92c826257df9019f8afa793415ed"
CASE_BINDING = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings") / f"{CASE}.json"
BINDING_PIN = "0bc6c621b75a118a3afbd969373d0ac352eb8fc6f9c9fc494faa274b7ed6e578"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
CACHE_LIB = Path("/tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so")
CACHE_PIN = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
MAX_FULL_STALL = 10.
FROZEN = "6053e48b5"


def checked(path, expected):
    contents = path.read_bytes()
    if sha256(contents).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Saved authority differs ({path})")
    return contents


def ranked_cases(complete, exclusions, lower, upper, limit=3):
    return sorted((issued, case) for case, issued in complete.items()
                  if lower <= issued <= upper and case not in exclusions)[:limit]


def selection():
    panel, decision, model = (checked(ROSTER / name, pin) for name, pin in ROSTER_PINS.items())
    assigned = [row["case"] for row in json.loads(panel)["cases"]]
    outcomes = json.loads(decision)
    pins = outcomes["pair_sha256"]
    rows = [row for row in csv.DictReader(StringIO(model.decode())) if row["build"] == "candidate"]
    if len(assigned) != 100 or len(set(assigned)) != 100 or set(pins) != set(assigned) or len(rows) != 100 or {
            row["case"] for row in rows} != set(assigned):
        raise ValueError("Final named v3 decision and original DS30 assignment disagree")
    complete = {}
    for row in rows:
        if row["decision"] != "complete":
            continue
        case = row["case"]
        pair = json.loads(checked(ROSTER / "publications" / case / "pair.json", pins[case]))
        if pair["candidate_specification_digest"] != "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f":
            raise ValueError(f"Completed case uses a different original named specification ({case})")
        receipt = pair["runs"]["candidate"]["receipt"]
        if receipt["decision"] != "complete" or type(receipt["window_count"]) is not int:
            raise ValueError(f"Completion differs from the sealed original receipt ({case})")
        complete[case] = receipt["window_count"]
    initial = ranked_cases(complete, TESTED, 400, 3000)
    next_after_exclusions = ranked_cases(complete, TESTED, 400, max(complete.values()), limit=1)
    if initial or next_after_exclusions != [(3042, CASE)] or pins[CASE] != PAIR_PIN:
        raise ValueError("Replay differs from the frozen two assignment decisions")
    ordered = sorted((issued, case, pins[case]) for case, issued in complete.items())
    return dict(assigned=len(assigned), completed=len(complete), roster_sha256=ROSTER_PINS,
                tested=TESTED, range=[400, 3000], assigned_original=initial,
                completed_in_original_range=ranked_cases(complete, (), 400, 3000),
                amendment_only=next_after_exclusions, census_sha256=sha256(json.dumps(ordered).encode()).hexdigest())


def full_stall(document):
    full, = (line for line in document.splitlines() if line.startswith("full "))
    return float(dict(s.split("=", 1) for s in full.split()[1:])["avg10"])


def issues(payloads, indexes, pressures):
    reasons = []
    for label, item in (("payload", payloads), ("index", indexes)):
        if (item["unavailable"] or item["members"] != item["observed_members"]
                or not item["observed_file_pages"]):
            reasons.append(f"{label}_page_observation_incomplete")
        elif item["cached_pages"] != item["observed_file_pages"]:
            reasons.append(f"{label}_pages_missing")
    if any(not 0 <= full_stall(sample) <= MAX_FULL_STALL for sample in pressures):
        reasons.append("full_io_stall_above_10_percent")
    return reasons


def observe():
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    cpu, nice = sorted(os.sched_getaffinity(0)), os.getpriority(os.PRIO_PROCESS, 0)
    ionice = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    if cpu != [2] or nice < 15 or "prio 7" not in ionice:
        raise RuntimeError("Run the passive input observation in the authorized low-priority Gauss slot")
    binding = json.loads(checked(CASE_BINDING, BINDING_PIN))
    case = binding["case"]
    pair = json.loads(checked(ROSTER / "publications" / CASE / "pair.json", PAIR_PIN))
    recorded = pair["runs"]["candidate"]
    checked(Path(pair["region"]), OFFER_PIN)
    asserted = [(Path("/srv/bulk") / m["path"], "sha256:"+m["sha256"]) for m in case["recording"]["segments"]]
    prior = [(Path(m["path"]), m["sha256"]) for m in pair["cache_observation"]["manifests"]]
    original = Path(pair["recording"])
    if case["id"] != CASE or case["raw_authority"] != recorded["raw_authority"] or asserted != prior:
        raise ValueError("Amendment differs from the archived raw authority or manifest order")
    session, digest, inventory = FastScanStore(Path("/dev/shm")).inventory(original, verify_windows=False)
    live = [(Path(m["path"]) / "manifest.json", m["manifest_digest"]) for m in inventory["segments"]]
    if (inventory["window_count"] != 3042 or live != asserted or session != recorded["receipt"]["session_id"]
            or session != case["session_id"]):
        raise ValueError("Original sealed inputs differ from the prospective assignment")
    checked(CACHE_LIB, CACHE_PIN)
    query, sizes = load_query(CACHE_LIB), os.sysconf("SC_PAGE_SIZE")
    members, indexes, decoded_bytes = [], [], 0
    for path, pin in live:
        reader = ShortWindowReader(path.parent)
        if reader.manifest_sha256 != pin:
            raise ValueError("Original member manifest changed before observation")
        for chunk in reader.manifest.chunks:
            members.append((reader.path, chunk.payload_relative_path, chunk.compressed_bytes))
            indexes.append((reader.path, chunk.index_relative_path, chunk.index_bytes))
            decoded_bytes += chunk.uncompressed_bytes
    pressure = Path("/proc/pressure/io")
    before = pressure.read_text()
    payload_state = cache_snapshot(members, sizes, query)
    index_state = cache_snapshot(indexes, sizes, query)
    after = pressure.read_text()
    problems = issues(payload_state, index_state, (before, after))
    return dict(case=CASE, issued=3042, amended=True, admission="blocked" if problems else "admitted",
                reasons=problems, original_recording=str(original), session=session, inventory=digest,
                raw_authority=recorded["raw_authority"], manifests=[dict(path=str(p), sha256=h) for p,h in live],
                pair_sha256=PAIR_PIN, signed_binding_sha256=BINDING_PIN, original_offer_sha256=OFFER_PIN,
                archive=pair["archive"], causal_orbit_cutoff_ns=binding["orbit_cutoff_ns"],
                authoritative_historical_counts=recorded["receipt"]["counts"],
                pressure_before=before, pressure_after=after, max_full_stall_pct=MAX_FULL_STALL,
                payloads=payload_state, indexes=index_state, page_size=sizes, cache_library_sha256=CACHE_PIN,
                compressed_bytes=sum(x[2] for x in members), index_bytes=sum(x[2] for x in indexes),
                decoded_bytes=decoded_bytes, cpu=cpu, nice=nice, ionice=ionice,
                waveform_calls=0, raw_launches=0, frozen=FROZEN)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("selection", "observe"))
    args = parser.parse_args()
    result = selection() if args.mode == "selection" else observe()
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
