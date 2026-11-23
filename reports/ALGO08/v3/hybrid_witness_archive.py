"""Evaluate the frozen hybrid admission predicate on sealed DS23 diagnostics."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import pre_signed_hybrid as hybrid


EVIDENCE = Path("2026_10_22_ds23_family_cavity_full_assessment/evidence")
CAVITY = Path("2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23/position")
SOURCE_SIZE_LIMIT = 150_000_000
HYBRID_PIN = "5085a1e334a15ad2baa6991276c52785f86c724bca7c57988c6b8325d04a9298"
SOURCE_PINS = {
    "ledger": (EVIDENCE/"evaluation.json", "9b5130552b945e81a4caf405cbdd2d202452143ae3104cc6fc20756322ce1986"),
    "publication": (EVIDENCE/"publication_receipt.json", "9dce6e8cc9131c960a276e28fef9358bf0428afeefc7d22741728b7920cb791d"),
    "pilot": (EVIDENCE/"random20_protocol.json", "a12e7f9121ae9179745b1256265575b5b4ff13b5c7d3fc213370177e55f9b11c"),
    "engineering": (EVIDENCE/"engineering_evaluation.json", "efc964dd09644535b8e7d73559f70e1ffa1cac9506620be3e5092ae76cc3f88d"),
    "recovery": (Path("2026_10_20_ds23_combined_recovery_full/protocol.json"),
                 "6f47edd36d71307d7928e8c330fc45442bc02a7c1ae2b1fc608810b93c2410c4"),
    "signed": (Path("2026_10_20_ds23_signed_recoveries/evaluation_audit.json"),
               "f82b37093e897e7c6ce1e0dbd3bb9c7afb69547a90c5e81cd84bcabad9cf1997"),
}
HELD = {
    "tested_alternatives": ("DS23-0023", "DS23-0192", "DS23-0347", "DS23-0317", "DS23-0047", "DS23-0323", "DS23-0360", "DS23-0353"),
    "zero_trials": ("DS23-0094", "DS23-0196", "DS23-0021", "DS23-0168", "DS23-0077", "DS23-0312", "DS23-0300", "DS23-0321"),
}


class MissingFields(ValueError):
    """A saved record cannot support the original predicate."""


class Archive:
    def __init__(self, reports, limit=SOURCE_SIZE_LIMIT, external=()):
        self.reports = reports.resolve(strict=True)
        self.external = tuple(path.resolve(strict=True) for path in external)
        self.total = 0
        self.limit = limit
        self.sources = {}

    def read(self, relative, pin=None):
        path = (self.reports/relative).resolve(strict=True)
        allowed = path.is_relative_to(self.reports) or (
            pin is not None and any(path.is_relative_to(root) for root in self.external))
        if not allowed or path.suffix != ".json":
            raise ValueError(f"Expected a saved JSON beneath a declared evidence root: {relative}")
        expected_size = path.stat().st_size
        if self.total + expected_size > self.limit:
            raise ValueError("Saved diagnostic reads exceed their declared byte cap")
        with path.open("rb") as stream:
            data = stream.read(expected_size)
        digest = sha256(data).hexdigest()
        if len(data) != expected_size or pin is not None and digest != pin:
            raise ValueError(f"Saved diagnostic disagrees with its seal: {relative}")
        self.total += len(data)
        self.sources[str(relative)] = digest
        return json.loads(data)


def relative_reports(value):
    parts = Path(value).parts
    if "reports" not in parts or ".." in parts:
        raise ValueError("Legacy diagnostic path requires a literal reports directory")
    suffix = parts[parts.index("reports")+1:]
    return Path(*suffix)


def enroll(ledger, excluded):
    arms = defaultdict(dict)
    for row in ledger["rows"]:
        case, rule, arm = row["case"], row["policy"], row["arm"]
        if arm in arms[case, rule]:
            raise ValueError("Archived adoption ledger repeats one calibration arm")
        arms[case, rule][arm] = row
    cases = ledger["evaluated_case_ids"]
    for case in cases:
        for rule in ("equal_assignment_priors", "incumbent_sticky_prior"):
            pair = arms[case, rule]
            if (set(pair) != set(hybrid.ARMS) or pair["c0"]["accepted"] != pair["fitted_c"]["accepted"]
                    or pair["c0"]["replacements"] != pair["fitted_c"]["replacements"]):
                raise ValueError("Archived adoption lacks matching calibration arms")
    positive = [case for case in cases if arms[case, "incumbent_sticky_prior"]["c0"]["accepted"]]
    equal = {case for case in cases if arms[case, "equal_assignment_priors"]["c0"]["accepted"]}
    with_trials = {row["case"] for row in ledger["trials"]}
    pools = {"tested_alternatives": set(cases) & with_trials, "zero_trials": set(cases) - with_trials}
    selections = {}
    for tag, pool in pools.items():
        pool -= equal | excluded
        ranked = sorted(pool, key=lambda case: sha256(f"ds23-hybrid-witness-controls-v1:{tag}:{case}".encode()).digest())
        selections[tag] = dict(pool=len(pool), cases=ranked[:len(HELD[tag])])
    return dict(positive=positive, equal_prior_only=len(equal-set(positive)), held=selections), arms


def validate_stock(position, earlier, adopted):
    selected = position["selected"]
    if (not position["accepted"] or not selected or not selected["paired_valid"]
            or not selected["replacements"] or selected["replacements"] != adopted["replacements"]
            or position["selection_gain"] <= position["search_penalty"]
            or selected["arms"] != position["policy_arms"] or position["baseline_arms"] == position["policy_arms"]
            or position["original_mask"] != earlier["mask"]):
        raise ValueError("The positive case lacks the actual adopted replacement and its earlier pair")
    return dict(replacements=selected["replacements"], selection_gain=position["selection_gain"],
                stock_penalty=position["search_penalty"],
                earlier_endpoints={a: position["baseline_arms"][a]["endpoint_east_north_km"] for a in hybrid.ARMS},
                selected_endpoints={a: position["policy_arms"][a]["endpoint_east_north_km"] for a in hybrid.ARMS})


def classify(earlier_route, signed, ordinary, region):
    if earlier_route is not None:
        return "retains_competition"
    if signed["selection"]["qualified"]:
        return "qualified_warm_pair_unobserved"
    if signed["accepted"] or signed["policy_arms"] != ordinary:
        raise ValueError("Unqualified signed history changed the original ordinary pair")
    if not hybrid.interior_pair(signed["policy_arms"], region):
        return "retains_competition"
    return "skips_competition_before_packet_evidence"


def case_details(archive, sources, case, *, adopted=None):
    recovery = sources["recovery"]
    directory = relative_reports(recovery["input_roots"][case])/case
    old = archive.read(directory/"algo02_result.json", recovery["baseline_sha256"][case])
    region = SimpleNamespace(half_width_km=old["box_width_km"]/2)
    signed_ref = sources["signed"]["evidence"][case]
    selected = {}
    if adopted is not None:
        position = archive.read(CAVITY/f"{case}.json", sources["positions"][case])
        selected = validate_stock(position, old, adopted["c0"])
        selected.update(error_delta_km={arm: row["policy_error_km"]-row["original_error_km"]
                                       for arm, row in adopted.items()})

    audit = {}
    family = old | {"mask": np.asarray(old["mask"], bool)}
    # The frozen guard itself short-circuits before touching these arrays when the
    # history output failed predictive admission or its ordinary pair fails.
    tracklist, norads, conservative = [], {}, {}
    if old["linear_paired_valid"] and old["linear_entries"] and hybrid.interior_pair(old["policy_arms"], region):
        if adopted is None:
            baseline = archive.read(directory/"result.json", old["baseline_sha256"])
            node = baseline["final_node"]
        else:
            node = position["baseline_node"]
        conservative = {"final_node": node}
        prepared = archive.read(directory/"preparation_receipt.json")
        tracklist = archive.read(directory/"tracks.json", prepared["files_sha256"][f"{case}/tracks.json"])
        widths = {row["key"]: len(row["times"]) for row in tracklist}
        curves = [row for row in node["seed"]["rows"] if row["active_curvature"]]
        if (len(curves) != len(old["confidence"])
                or any(widths[row["component"]] != len(row["times_s"]) for row in curves)
                or sum(widths[row["component"]] for row in curves) != len(old["mask"])):
            raise MissingFields("Original Graph widths, mask and confidence do not form the named ordered layout")
        norads = {row["candidate_index"]: row["candidate_norad"] for row in curves}
        norads.update({row["candidate_index"]: row["norad"] for row in old["linear_entries"]})
    scan = SimpleNamespace(tracks=tracklist, norads=norads, search_region=region)
    route = hybrid.eligible(scan, conservative, family, audit)
    if route == "unrecognized_named_curved_layout":
        raise MissingFields(audit.get("unsupported_witness", route))
    signed_info = {}
    if adopted is not None or route is None:
        signed = archive.read(relative_reports(signed_ref["path"]), signed_ref["sha256"])
        if signed["baseline_arms"] != old["policy_arms"]:
            raise ValueError("Frozen signed record changes the earlier admitted pair")
        if adopted is not None and position["baseline_arms"] != signed["policy_arms"]:
            raise ValueError("Actual competitive incumbent does not match the original signed record")
        signed_info = dict(qualified=signed["selection"]["qualified"], historical_adopted=signed["accepted"])
    outcome = classify(route, signed if signed_info else None, old["policy_arms"], region)
    return dict(earlier_reason=route, disposition=outcome, witness=audit, signed=signed_info, selected=selected)


def run(reports, external=()):
    if sha256(Path(hybrid.__file__).read_bytes()).hexdigest() != HYBRID_PIN:
        raise ValueError("Loaded hybrid guard differs from dd8a871df")
    archive = Archive(reports, external=external)
    sources = {name: archive.read(path, pin) for name, (path, pin) in SOURCE_PINS.items()}
    excluded = set(sources["pilot"]["cases"]) | {row["case"] for row in sources["engineering"]["rows"]}
    selection, rows = enroll(sources["ledger"], excluded)
    if (len(selection["positive"]) != 9 or selection["equal_prior_only"] != 65
            or any(tuple(selection["held"][name]["cases"]) != values for name, values in HELD.items())):
        raise ValueError("Frozen evaluation, challenge or held roster changed")
    sources["positions"] = {row["case"]: row["position_sha256"]
                            for row in sources["publication"]["case_result_sha256"]}

    def observed(case, sticky):
        try:
            return case_details(archive, sources, case, adopted=rows[case, "incumbent_sticky_prior"] if sticky else None)
        except (FileNotFoundError, KeyError, MissingFields) as error:
            return dict(disposition="missing", reason=str(error))

    groups = {"sticky_adopted": {case: observed(case, True) for case in selection["positive"]}}
    groups.update({label: {case: observed(case, False) for case in data["cases"]}
                   for label, data in selection["held"].items()})
    summary = {name: dict(rows=len(data), early_eligible=sum(r.get("earlier_reason", False) is None for r in data.values()),
                          dispositions=dict(Counter(r["disposition"] for r in data.values())),
                          early_rejections=dict(Counter(r["earlier_reason"] for r in data.values() if r.get("earlier_reason"))))
               for name, data in groups.items()}
    return dict(frozen_hybrid="dd8a871dffbff8d2231b346f9018a9f9c846ac78", hybrid_source_sha256=HYBRID_PIN,
                selection=selection, summary=summary, cases=groups, source_sha256=archive.sources,
                saved_json_bytes=archive.total, fits=0, waveform_reads=0, publications=0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--reports", type=Path, required=True, help="Root of archived reports tree")
    cli.add_argument("--external-json-root", type=Path, action="append", default=[],
                     help="Allow digest-pinned diagnostic symlinks beneath this directory")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    result = run(args.reports, args.external_json_root)
    with args.output.open("x") as destination:
        json.dump(result, destination, indent=2, sort_keys=True, allow_nan=False)
        destination.write("\n")
