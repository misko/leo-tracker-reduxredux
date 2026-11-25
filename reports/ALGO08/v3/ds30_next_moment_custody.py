"""Enroll one original DS30 recording using authenticated metadata and resident donors."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter_ns, process_time_ns


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import held_cfo_next_two as meta  # noqa: E402


PROTOCOL = "d8adfd587022657d4ab64e7f1383e7e486b495022d205ce021f6b37186316a28"
STEM = "ds30-next-moment-fast-enrollment"
RANKS = range(70, 74)
STAGES = (*(Path("/dev/shm")/name for name in (
    "leo-v3-cfo-epoch-0086-saved01", "leo-v3-unseen-saved-0255-result01",
    "leo-v3-nomination-handoff-0289-local01", "leo-v3-held-shrink-0274-stage02/stage",
    "leo-v3-cfo-epoch-0049-saved01", "leo-v3-0218-prospective01/stage",
    "leo-v3-mask-cfo-next-two01/DS30-0212/stage", "leo-v3-cfo-epoch-0019-saved01",
    "leo-held-anchor-selected-dense-01", "leo-v3-saved-0155-pair-01",
    "leo-v3-saved-0316-pair-01", "leo-v3-saved-0402-pair-01",
    "leo-v3-raw-cfo-0016-result03", "leo-v3-short-raw-0180-01",
    "leo-v3-causal-0138-stage01", "leo-v3-nomination-handoff-0419-local01",
    "leo-v3-exact-grid-0138-active01", "leo-v3-ds30-0163-ready01", "leo-v3-raw-cfo-0016-result02")),
    Path("/tmp/leo-v3-0280-moment-extended01/field/stage"))
ACQUISITION = rb'"acquisition_verified":(true|false)'
RESULT_PIN = rb'"attempt_result_sha256":"(sha256:[0-9a-f]{64})"'
STAGE_PART = Path("tle/archive/space-track")


def digest_rows(path, expected):
    return json.loads(meta.checked(path, expected))


def complete_pair(directory, lines):
    """Only read pair-level acquisition flags and file digests, never result objects."""
    role_flags = meta.role_status(lines)
    pair_path = directory/"pair.json"
    if not all(ready["verified_pair"] for ready in role_flags.values()) or not pair_path.is_file():
        return None
    body = pair_path.read_bytes()
    pair = json.loads(body)
    pins = {meta.field(line, meta.ROLE):meta.field(line, RESULT_PIN) for line in lines}
    if (pair["state"] != "observed_pair" or pair["verified_pair"] is not True
            or pins != pair["attempt_result_sha256"]
            or any(meta.field(line, ACQUISITION) != "true" for line in lines)):
        raise ValueError("The field pair and both acquisition rows do not bind identical results")
    return dict(sha256=meta.digest(body), attempts=pins, generation=pair["generation"],
                authority_sha256=pair["authority_sha256"])


def documented_donors():
    names, census = {}, {}
    tmpfs = {root.stat().st_dev for root in (Path("/dev/shm"), Path("/tmp"))}
    for stage in STAGES:
        pool = stage/STAGE_PART
        if not pool.is_dir():
            census[str(stage)] = None
            continue
        if pool.resolve() != pool or pool.stat().st_dev not in tmpfs:
            raise ValueError("A documented donor is outside its staged tmpfs")
        entries = sorted(path for path in pool.iterdir()
                         if meta.TLE_NAME.fullmatch(path.name) and not path.is_symlink() and path.is_file())
        census[str(stage)] = len(entries)
        for path in entries:
            names.setdefault(path.name, []).append(path)
    return names, census


def exact_window(names, cutoff, expected):
    prior = sorted(name for name in names if int(name.split("-", 1)[0]) < cutoff)
    for lo, hi in combinations(range(len(prior)+1), 2):
        view = {name:meta.TLE_NAME.fullmatch(name)[2] for name in prior[lo:hi]}
        if meta.roster_digest(view) == expected:
            return view
    return None


def resident_roster(view, donors):
    # util-linux fincore observes page residency without reading payload.
    candidates = [path for name in view for path in donors.get(name, ())]
    if not candidates:
        return {}, sorted(view)
    result = json.loads(subprocess.check_output([
        "fincore", "--json", "--bytes", "-o", "FILE,RES,SIZE", *map(str, candidates),
    ]))["fincore"]
    if [Path(row["file"]) for row in result] != candidates:
        raise ValueError("Residency did not account for every documented donor candidate")
    files = {}
    for row, path in zip(result, candidates, strict=True):
        if 0 < row["size"] <= row["res"]:
            files.setdefault(path.name, dict(path=str(path), bytes=row["size"], sha256=view[path.name]))
    return files, sorted(view.keys()-files.keys())


def archive_view(path, names, authority):
    cutoff, expected = authority["signed_cutoff_ns"], authority["signed_archive_sha256"]
    if path is None or not path.is_file():
        return exact_window(names, cutoff, expected), None
    filesystem = path.stat().st_dev
    if (path.resolve() != path or not any(path.is_relative_to(root) and filesystem == root.stat().st_dev
            for root in (Path("/tmp"), Path("/dev/shm"), meta.CAMPAIGN))):
        raise ValueError("The optional roster must be a direct local metadata file")
    body = path.read_bytes()
    view = meta.catalogue_names(json.loads(body))
    if meta.roster_digest(view) != expected or any(int(name.split("-", 1)[0]) >= cutoff for name in view):
        raise ValueError("The local catalogue manifest differs from the exact signed causal roster")
    return view, meta.digest(body)


def selection_for(rows):
    """Pending older metadata blocks selection. Completed custody refusals do not."""
    for row in rows:
        if row["disposition"] == "eligible":
            return row["case"], "enrolled"
        if row["disposition"].startswith("pending"):
            return None, "pending"
    return None, "all_four_custody_unavailable"


def census(rosters=None, previous=None):
    start, cpu = perf_counter_ns(), process_time_ns()
    meta.checked(HERE/f"{STEM}-protocol.md", PROTOCOL)
    campaign = meta.CAMPAIGN
    plan = digest_rows(campaign/"plan.json", meta.PLAN)
    historical = digest_rows(meta.ROOT/"reports/2026_11_21_ds30_full/input-audit.json", meta.INPUT_AUDIT)
    by_name = {row["case"]:row for row in plan["cases"]}
    order = [*plan["smoke"], *(case for case in by_name if case not in plan["smoke"])]
    export = (campaign/"rows.jsonl").read_bytes()
    donors, inventories = documented_donors()
    if previous is not None and (previous["source_plan_sha256"] != meta.PLAN
            or previous["protocol_sha256"] != PROTOCOL or previous["state"] != "pending"
            or [row["execution_rank"] for row in previous["ranks"]] != list(RANKS)):
        raise ValueError("Only a prior sealed pending check can resume the same four-case window")
    exclusions = {row["case"]:row for row in (previous or {}).get("ranks", ())
                  if row["disposition"].startswith("custody_unavailable")}
    rows = []
    for rank in RANKS:
        name = order[rank-1]
        enrolled = by_name[name]
        row = {k:enrolled[k] for k in ("case", "case_id", "assigned_rank", "window_count", "raw_identity_sha256",
                                       "manifest_raw_authority_sha256", "recording_state")}
        row["execution_rank"] = rank
        lines = [line for line in export.splitlines() if meta.field(line, meta.LABEL) == name]
        point = complete_pair(campaign/"cases"/name, lines)
        if name in exclusions:
            if point != exclusions[name]["official_pair"]:
                raise ValueError("An original completed pair changed after its custody exclusion")
            rows.append(exclusions[name])
            continue
        row["official_pair"] = point
        authority = meta.catalogue_authority(enrolled, {}, historical["bindings"][name])
        row["catalogue_custody"] = authority
        if authority["state"] == "original_input_authority_pending":
            row["disposition"] = "pending_original_input_authority"
        else:
            path = rosters/f"{name}.json" if rosters is not None else None
            view, pin = archive_view(path, donors, authority)
            row["local_roster_manifest_sha256"] = pin
            cutoff = authority["signed_cutoff_ns"]
            row["documented_causal_donor_names"] = sum(int(key.split("-", 1)[0]) < cutoff for key in donors)
            if point and point["authority_sha256"] != authority["authority_sha256"]:
                raise ValueError("The official completed pair uses a different authority")
            if view is None:
                row["disposition"] = ("custody_unavailable_exact_roster" if point else "pending_exact_roster")
            else:
                files, missing = resident_roster(view, donors)
                row["missing_or_nonresident"] = missing
                authority["exact_archive_names"] = list(view)
                authority["matched_names"] = len(view)
                row["resident_roster"] = files
                row["resident_bytes"] = sum(item["bytes"] for item in files.values())
                row["disposition"] = ("custody_unavailable_residency" if point else "pending_resident_custody") if missing else "eligible"
        rows.append(row)
    selected, state = selection_for(rows)
    return dict(protocol_sha256=PROTOCOL, selector_sha256=meta.digest(Path(__file__).read_bytes()),
                source_plan_sha256=meta.PLAN, field_export_sha256=meta.digest(export),
                date_utc=datetime.now(timezone.utc).isoformat(), ranks=rows, selected=selected, state=state,
                staged_catalogue_locations=inventories, source_tle_payload_reads=0,
                survey_reads=0, numerical_children=0, custody_wall_ns=perf_counter_ns()-start,
                custody_cpu_ns=process_time_ns()-cpu)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--rosters", type=Path, help="Optional private copies of exact authenticated roster metadata")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-pin")
    args = parser.parse_args()
    if bool(args.previous) != bool(args.previous_pin):
        parser.error("Pass the prior census and its exact SHA-256 together")
    previous = None if args.previous is None else digest_rows(args.previous, args.previous_pin)
    result = census(args.rosters, previous)
    result["prior_check_sha256"] = args.previous_pin
    with args.destination.open("x") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")
    print(meta.digest(args.destination.read_bytes()))


if __name__ == "__main__":
    main()
