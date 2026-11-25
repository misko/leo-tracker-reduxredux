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
INPUT_AUDIT = "sha256:87e6c389cc4dccafb204ada3def360343514d283d65418ee3211817d9a57b5c5"
ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
ORIGINAL = Path("/srv/bulk/leo-dev/ds30-full-20261121")
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


def roster_digest(names):
    return digest(json.dumps(names, sort_keys=True, separators=(",", ":")).encode())


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
                              manifest_roster_sha256=roster_digest(names))
    return receipts, pooled


def signed_suffixes(pooled, cutoff, expected):
    """Use the same exact ordered suffix and strict cutoff as the 0218 custody port."""
    prior = sorted(name for name in pooled if int(name.split("-", 1)[0]) < cutoff)
    return [prior[i:] for i in range(len(prior)) if
            roster_digest({name: pooled[name] for name in prior[i:]}) == expected]


def catalogue_authority(entry, pooled, historical):
    directory = CAMPAIGN/"cases"/entry["case"]
    path, request_path = directory/"authority.json", directory/"input.json"
    if not path.is_file() or not request_path.is_file():
        return dict(state="original_input_authority_pending")
    if any(p.resolve(strict=True) != p or p.stat().st_dev != CAMPAIGN.stat().st_dev
           for p in (path, request_path)):
        raise ValueError("Original request authority is outside the admitted metadata filesystem")
    body, request_body = path.read_bytes(), request_path.read_bytes()
    authority = json.loads(body)
    request = json.loads(request_body)
    archive_path = ORIGINAL/"snapshot/inputs"/entry["case"]/"tle"
    if (authority["recording"] != entry["recording"] or authority["window_count"] != entry["window_count"]
            or request["historical_binding_sha256"] != historical["binding_sha256"]
            or request["expected_admitted"] != historical["usable_visits"]
            or request["archive"] != str(archive_path)
            or request["authority"] != authority or request["authority_sha256"] != digest(body)
            or any(authority[key] != value for key, value in request["expected"].items())):
        raise ValueError("Original input authority changed frozen recorded identity")
    cutoff, archive = authority["causal_cutoff_utc_ns"], authority["archive_sha256"]
    matches = signed_suffixes(pooled, cutoff, archive)
    return dict(state="metadata_match_only" if len(matches) == 1 else "no_unique_exact_donor_view",
                authority_sha256=digest(body), request_sha256=digest(request_body),
                original_input_metadata_bytes=len(body)+len(request_body), signed_cutoff_ns=cutoff,
                historical_binding_sha256=request["historical_binding_sha256"],
                historical_request_raw_authority_sha256=authority["raw_authority_sha256"],
                matches_accession_digest=authority["raw_authority_sha256"] == entry["manifest_raw_authority_sha256"],
                original_archive_path=str(archive_path), signed_archive_sha256=archive, exact_suffix_matches=len(matches),
                matched_names=len(matches[0]) if len(matches) == 1 else None)


def bulk_mount():
    """Read the mount table only. Do not stat the original archive path."""
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        options, filesystem = line.split(" - ", 1)
        fields = options.split()
        if fields[4] == "/srv/bulk":
            kind, source, *_ = filesystem.split()
            return dict(target=fields[4], device=fields[2], source=source, filesystem=kind)
    return None


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
    donors, pooled = donor_inventory()
    times = sorted(int(name.split("-", 1)[0]) for name in pooled)
    planned = {entry["case"]: entry for entry in plan["cases"]}
    audit = json.loads(checked(ROOT/"reports/2026_11_21_ds30_full/input-audit.json", INPUT_AUDIT))["bindings"]
    for case in selected:
        nominal = int(datetime.fromisoformat(case["nominal_capture_start_utc"]).timestamp())*10**9
        case["temporal_donor_screen_only"] = dict(before_capture_label=sum(t < nominal for t in times),
                                                  at_or_after_capture_label=sum(t >= nominal for t in times),
                                                  newest_prior_donor_ns=max((t for t in times if t < nominal), default=None))
        case["catalogue_custody"] = catalogue_authority(planned[case["case"]], pooled, audit[case["case"]])
    space = os.statvfs(RAM)
    print(json.dumps(dict(plan_sha256=PLAN, export_sha256=EXPORT, export_seal_sha256=SEAL,
                          ordinary_ledger_sha256=seal["ledger_snapshot_sha256"],
                          historical_input_audit_sha256=INPUT_AUDIT,
                          last_pre_enrollment_case=ANCHOR, previously_tested_originals=sorted(PRIOR),
                          cases=selected, catalogue_manifests=donors, union_catalogue_names=len(times),
                          original_backing_mount=bulk_mount(),
                          tmpfs_available_bytes=space.f_bavail*space.f_frsize,
                          custody_checked_at_utc=datetime.now(timezone.utc).isoformat(),
                          catalogue_body_reads=0, packet_reads=0, survey_reads=0, slot_started=False),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
