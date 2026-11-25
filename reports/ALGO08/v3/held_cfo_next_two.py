"""Enroll the next fixed half-shrink transfer cases without decoding outcomes."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re


PLAN = "sha256:9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
EXPORT = "sha256:3fb2f2999401ce551d8c5fa0b2cebc14caec7246ffcbfd14f387a8f1422cb182"
SEAL = "sha256:5e16c85c52144c55c6f1a88dffc3a1fe70724df891bd3ae6f7e1b6e3187bdee7"
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
RAM = Path("/dev/shm")
BUILDS = ("installed", "successor")
ANCHOR = "DS30-0218"
PRIOR = frozenset(("DS30-0049", "DS30-0086", "DS30-0019", "DS30-0274", ANCHOR))
DONORS = {
    "DS30-0086": ("leo-v3-cfo-epoch-0086-saved01/catalogue.json", (),
                  "68bfd52bcac791477997d6da402835d830f82172268f847d66dfa5fc8e2755f9"),
    "DS30-0255": ("leo-v3-unseen-saved-0255-result01/admission.json", ("archive_sources",),
                  "b42e9b53d303e78270d8f34a866452bc2d3d28ea7bc99b4c86589a699bdbd1a1"),
    "DS30-0289": ("leo-v3-nomination-handoff-0289-local01/admission.json", ("archive", "names"),
                  "3529ba6f682917b200af0353b273efbfbb76fbb85a56602cfdcf7d693ca8e259"),
    "DS30-0274": ("leo-v3-held-shrink-0274-stage02/stage/catalogue.json", (),
                  "26ea5340883005750006e6afe13281ebbdf221d9dc511fc7585360eda723d809"),
    "DS30-0049": ("leo-v3-cfo-epoch-0049-saved01/catalogue.json", (),
                  "9d0788aa7b7698d26600b52a5a4439b43b00b08860fa03b2a25b5534ea625a66"),
    "DS30-0218": ("leo-v3-0218-prospective01/stage/catalogue.json", (),
                  "778f535225c1df2c1a270e42b100c283597eadba069c1090124c84dfacb55c94"),
    "DS30-0402": ("leo-v3-saved-0402-pair-01/admission.json", ("archive", "files"),
                  "fed3760d61bb9cb1d4ee2eb98ee5e36490db6d706451a1eda99220f287be9453"),
}
LABEL = rb'"case":"(DS30-[0-9]{4})"'
ROLE = rb'"algorithm":"(installed|successor)"'
VERIFIED = rb'"verified_pair":(true|false)'
TLE_NAME = re.compile(r"([1-9][0-9]*)-([0-9a-f]{64})\.tle")


def digest(body):
    return "sha256:"+sha256(body).hexdigest()


def checked(path, pin):
    body = path.read_bytes()
    if digest(body) != "sha256:"+pin.removeprefix("sha256:"):
        raise ValueError(f"Enrollment metadata digest changed at {path.name}")
    return body


def field(raw, expression):
    values = re.findall(expression, raw)
    if len(values) != 1:
        raise ValueError("Expected one canonical enrollment metadata field")
    return values[0].decode()


def role_status(lines):
    roles = {}
    for raw in lines:
        role = field(raw, ROLE)
        if role in roles:
            raise ValueError("Ambiguous enrolled build")
        roles[role] = dict(verified_pair=field(raw, VERIFIED) == "true", export_line_sha256=digest(raw))
    if set(roles) != set(BUILDS) or len({status["verified_pair"] for status in roles.values()}) != 1:
        raise ValueError("Both original builds must identify the same pair status")
    return roles


def select(plan, export, *, previous=PRIOR, after=ANCHOR, rank=65):
    """Use immutable order and verification flags only. Never decode result objects."""
    planned = {entry["case"]: entry for entry in plan["cases"]}
    smoke = plan["smoke"]
    if (len(planned) != len(plan["cases"]) or len(smoke) != len(set(smoke)) or not set(smoke) <= planned.keys()):
        raise ValueError("Ambiguous original order")
    ordered = [*smoke, *(name for name in planned if name not in smoke)]
    if ordered[rank-1] != after:
        raise ValueError("The held-transfer start does not agree with execution rank")
    index = defaultdict(list)
    for raw in export.splitlines():
        index[field(raw, LABEL)].append(raw)
    if index.keys() != planned.keys():
        raise ValueError("The sealed export and frozen enrollment labels differ")
    if any(not role_status(index[name])["installed"]["verified_pair"] for name in ordered[:rank]):
        raise ValueError("Expected a fully verified pre-enrollment prefix")
    chosen = []
    for position, case in enumerate(ordered[rank:], rank+1):
        roles = role_status(index[case])
        if case in previous or roles["installed"]["verified_pair"]:
            continue
        entry = planned[case]
        keys = ("case", "assigned_rank", "case_id", "window_count", "raw_identity_sha256",
                "manifest_raw_authority_sha256", "order", "recording_state")
        capture_label = "-".join(Path(entry["recording"]).name.split("-")[2:4])
        nominal = datetime.strptime(capture_label, "%Y%m%d-%H%M%S")
        chosen.append({key: entry[key] for key in keys} | dict(
            execution_rank=position, nominal_capture_start_utc=nominal.replace(tzinfo=timezone.utc).isoformat(),
            roles=roles))
        if len(chosen) == 2:
            return chosen
    raise ValueError("The plan lacks two unverified untouched original cases")


def catalogue_names(document):
    if isinstance(document, dict):
        entries = ((name, meta["sha256"] if isinstance(meta, dict) else meta) for name, meta in document.items())
    else:
        entries = ((meta["filename"], meta["sha256"]) if isinstance(meta, dict) else (meta, None) for meta in document)
    names = {}
    for key, declared in entries:
        name = Path(key).name
        match = TLE_NAME.fullmatch(name)
        if not match or name in names or (declared is not None and declared.removeprefix("sha256:") != match[2]):
            raise ValueError("Invalid or conflicting timestamped catalogue name")
        names[name] = match[2]
    return names


def donor_inventory():
    receipts, pooled = {}, {}
    for case, (relative, fields, pin) in DONORS.items():
        path = RAM/relative
        if path.resolve(strict=True) != path or path.stat().st_dev != RAM.stat().st_dev:
            raise ValueError("Expected the documented direct tmpfs donor manifest")
        document = json.loads(checked(path, pin))
        for key in fields:
            document = document[key]
        names = catalogue_names(document)
        pooled.update(names)
        times = sorted(int(name.split("-", 1)[0]) for name in names)
        receipts[case] = dict(manifest=str(path), manifest_sha256="sha256:"+pin, names=len(times),
                              oldest_ns=times[0], newest_ns=times[-1],
                              manifest_roster_sha256=digest(json.dumps(names, sort_keys=True,
                                                    separators=(",", ":")).encode()))
    return receipts, sorted(int(name.split("-", 1)[0]) for name in pooled)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    plan = json.loads(checked(CAMPAIGN/"plan.json", PLAN))
    seal = json.loads(checked(args.snapshot/"rows-with-relocations-seal.json", SEAL))
    if seal["combined_sha256"] != EXPORT or seal["plan_sha256"] != PLAN:
        raise ValueError("The combined export seal changed")
    export = checked(args.snapshot/"rows-with-relocations.jsonl", EXPORT)
    selected = select(plan, export)
    donors, times = donor_inventory()
    for case in selected:
        nominal = int(datetime.fromisoformat(case["nominal_capture_start_utc"]).timestamp())*10**9
        case["temporal_donor_screen_only"] = dict(before_capture_label=sum(t < nominal for t in times),
                                                  at_or_after_capture_label=sum(t >= nominal for t in times),
                                                  newest_prior_donor_ns=max((t for t in times if t < nominal), default=None))
        case["official_authority_present_at_check"] = (CAMPAIGN/"cases"/case["case"]/"authority.json").is_file()
    space = os.statvfs(RAM)
    print(json.dumps(dict(plan_sha256=PLAN, export_sha256=EXPORT, export_seal_sha256=SEAL,
                          ordinary_ledger_sha256=seal["ledger_snapshot_sha256"],
                          last_pre_enrollment_case=ANCHOR, previously_tested_originals=sorted(PRIOR),
                          cases=selected, catalogue_manifests=donors, union_catalogue_names=len(times),
                          tmpfs_available_bytes=space.f_bavail*space.f_frsize,
                          catalogue_body_reads=0, packet_reads=0, survey_reads=0, slot_started=False),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
