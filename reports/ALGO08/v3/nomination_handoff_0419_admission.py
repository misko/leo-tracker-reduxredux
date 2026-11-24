"""Check the frozen second saved-input assignment without scoring or running a solver."""

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from runpy import run_path

from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader

from reports.ALGO08.v3.unseen_saved_holdout import estimated_child_ceiling


HERE = Path(__file__).resolve().parent
CASE = "DS30-0419"
RANK_HASH = "015d6473219fed3585dd3c51586bb9af46f100e7093247d0439538f1f3ef9087"
PAIR_PIN = "7d141aceb32428ab5ca305db68b2b177b9b9ed6ea4c30a2825513dc84b9df44a"
PROTOCOL_COMMIT = "9b1a5dc605a81a69e2c5e798b8d739029bdb3949"
RUNTIME_COMMIT = "3a49c5f1241f935d30f3348eed77c8d3c7e4a919"
TMPFS = (Path("/dev/shm"), Path("/tmp"))
PANEL = Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE
OFFER = Path("/dev/shm/leo-v3-solver-exception-0022-result01/offer.json")
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
HOUR_NS = 3600 * 10**9


def digest(data):
    return sha256(data).hexdigest()


def checked(path, pin):
    body = path.read_bytes()
    if digest(body) != pin:
        raise ValueError(f"Unexpected digest for {path}")
    return json.loads(body)


def enrollment():
    original = run_path(str(HERE / "unseen-saved-assignment.py"))
    roster = checked(original["ROSTER"], original["ROSTER_PIN"])
    pairs = {row["case"]: row["pair_sha256"] for row in roster["rows"]}
    if len(pairs) != len(roster["rows"]) or len(pairs) != 100 or roster["decision_sha256"] != original["DECISION_PIN"]:
        raise ValueError("Expected the original 100-case release roster")
    remaining = pairs.keys() - original["EXCLUDED"]
    ranking = sorted((digest((original["PREFIX"] + case).encode()), case) for case in remaining)
    if len(ranking) != 87 or ranking[0][1] != original["assignment"]()["selected"] or ranking[1] != (RANK_HASH, CASE):
        raise ValueError("The unchanged second rank did not match the preregistration")
    if pairs[CASE] != PAIR_PIN or int(CASE[-4:]) % 2 != 1:
        raise ValueError("The release pair or original worker order changed")
    (row,) = (row for row in roster["rows"] if row["case"] == CASE)
    return dict(case=CASE, rank=2, roster_size=len(ranking), ranking_sha256=RANK_HASH,
                roster_sha256=original["ROSTER_PIN"], release_pair_sha256=PAIR_PIN,
                planned_order=["routed", "installed"], historical_post_detection_s=row["post_s"],
                estimated_worker_ceiling_s=estimated_child_ceiling(row["post_s"]))


def tmpfs(path):
    if not any(path.is_relative_to(root) for root in TMPFS) or path.resolve() != path:
        raise ValueError(f"Expected a direct staged tmpfs path, got {path}")
    return path


def input_binding(pair):
    release = pair["runs"]["candidate"]
    record = release["receipt"]
    work = tmpfs(PANEL / "candidate/fast-scan-automatic-work")
    (native_path,) = work.glob("*/detections.json")
    native_body = tmpfs(native_path).read_bytes()
    native = json.loads(native_body)
    source = native["source"]
    session = source["session_id"]
    inventory_pin = source["input_manifest_sha256"].removeprefix("sha256:")
    inventory_path = tmpfs(PANEL / "candidate/fast-scan-inputs" / f"{session}.json")
    inventory = checked(inventory_path, inventory_pin)
    offer = checked(tmpfs(OFFER), OFFER_PIN)
    terminal = json.loads(tmpfs(work / record["run_id"] / "terminal.json").read_bytes())
    native_pin = digest(native_body)
    issued, admitted = record["window_count"], record["counts"]["processed"]
    manifests = [{"path": str(Path(row["path"]) / "manifest.json"), "sha256": row["manifest_digest"]}
                 for row in inventory["segments"]]
    if (session != record["session_id"] or session != "fast-" + inventory_pin[:32]
            or not source["qualified"] or source["probe_ms"] != 20
            or source["raw_recording_authority_digest"] != release["raw_authority"]
            or terminal["native_sha256"] != "sha256:" + native_pin
            or canonical_digest(terminal) != record["terminal_sha256"]
            or terminal["region"] != offer or record["region"] != offer
            or inventory["window_count"] != issued or native["provenance"]["processed_windows"] != admitted
            or len(source["probes"]) != 2 * admitted or manifests != pair["cache_observation"]["manifests"]):
        raise ValueError("The archived detector, signed inventory, original authority or offer changed")
    return dict(native_sha256=native_pin, native_path=str(native_path), native_bytes=len(native_body),
                inventory_sha256=inventory_pin, inventory_path=str(inventory_path),
                offer_sha256=OFFER_PIN, raw_authority=release["raw_authority"],
                terminal_sha256=record["terminal_sha256"], manifest_count=len(manifests),
                session=session, issued=issued, admitted=admitted, probes=len(source["probes"]),
                factors=sum(len(probe["candidates"]) for probe in source["probes"]),
                cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"])


def directories(path):
    with os.scandir(path) as entries:
        return [Path(entry.path) for entry in entries if entry.is_dir(follow_symlinks=False)]


def archive_roots(roots=TMPFS):
    """Census local named stage directories to two levels, without following links."""
    candidates = set()
    inaccessible = []
    for root in roots:
        for folder in directories(root):
            if not folder.name.startswith(("leo-", "ds30", "ds22", "algo08", "tle-")):
                continue
            try:
                children = directories(folder)
            except PermissionError:
                inaccessible.append(str(folder))
                continue
            candidates.update((folder, folder / "tle", folder / "catalogue", folder / "inputs", folder / "snapshot"))
            for child in children:
                if child.name.startswith(("DS30-", "tle-", "tle_", "staged", "source", "causal",
                                          "input", "result", "archive")):
                    candidates.update((child, child / "tle"))
    stages = []
    for stage in sorted(candidates):
        chain = (stage, stage / "archive", stage / "archive/space-track")
        try:
            if all(not path.is_symlink() and path.is_dir() for path in chain):
                if os.access(chain[-1], os.R_OK | os.X_OK):
                    stages.append(stage)
                else:
                    inaccessible.append(str(stage))
        except PermissionError:
            inaccessible.append(str(stage))
    return stages, sorted(inaccessible)


def available_archive(readers, capture_ns, cutoff_ns):
    chosen = {}
    donors = []
    for reader in readers:
        refs = reader.list_snapshots("space-track")
        selected = [ref for ref in refs if capture_ns - 72 * HOUR_NS <= ref.collected_utc_ns < cutoff_ns]
        for ref in selected:
            chosen.setdefault(ref.path.name, ref)
        donors.append(dict(root=str(reader.root), total=len(refs), in_nominal_window=len(selected),
                           newest_ns=max((ref.collected_utc_ns for ref in refs), default=None)))
    union = dict(sha256=canonical_digest({name: ref.sha256 for name, ref in chosen.items()}),
                 count=len(chosen), bytes=sum(ref.byte_size for ref in chosen.values()),
                 oldest_ns=min((ref.collected_utc_ns for ref in chosen.values()), default=None),
                 newest_ns=max((ref.collected_utc_ns for ref in chosen.values()), default=None))
    return dict(donors=donors, candidate_union=union)


def reduce():
    assignment = enrollment()
    pair = checked(tmpfs(PANEL / "pair.json"), PAIR_PIN)
    bound = input_binding(pair)
    capture = Path(pair["recording"]).name.split("-")[2:4]
    capture_s = datetime.strptime("-".join(capture), "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    roots, inaccessible = archive_roots()
    archive = available_archive((TleArchiveReader(tmpfs(root)) for root in roots),
                                int(capture_s) * 10**9, bound["cutoff_utc_ns"])
    expected = pair["archive"]["snapshots_sha256"]
    matches = archive["candidate_union"]["sha256"] == expected
    archive.update(expected_sha256=expected, match=matches, nominal_capture_name_utc_s=int(capture_s),
                   inaccessible_named_stage_roots=inaccessible,
                   original_backing_root_opened=False, catalogue_payload_bytes_read=0)
    if matches:
        raise ValueError("A matching roster is now available. Authenticate its bodies before worker admission.")
    return dict(schema="leo.research.nomination-handoff-second-admission.v1", assignment=assignment,
                protocol_commit=PROTOCOL_COMMIT, frozen_remediation_commit=RUNTIME_COMMIT,
                unchanged_input_available=bound, catalogue_custody=archive,
                timing_eligible=0 < assignment["estimated_worker_ceiling_s"] < 120,
                disposition="deferred", reason="exact_causal_archive_unavailable_on_local_tmpfs",
                candidate_children=0, installed_children=0, new_rf_captures=0, original_waveform_reads=0,
                scored_cases=0, substituted_cases=0)


if __name__ == "__main__":
    print(json.dumps(reduce(), sort_keys=True, indent=2))
