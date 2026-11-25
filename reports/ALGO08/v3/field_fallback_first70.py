"""Extend the frozen fallback accounting to the first 70 verified pairs."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
from statistics import median

from .ds30_oracle_routing import CAMPAIGN, PLAN, digest, frozen_order
from .ds30_routing_first64 import CASE_KEY, SURVEY_KEY, restricted_json
from .field_fallback_budget import METRICS, clock, route_times, summarize
from .full_successor_score import ARMS, BUILDS, PINS, REFERENCE, VERIFIED, outcomes_summary, paired_rows


HERE = Path(__file__).resolve().parent/"measurements"
EXPORT = "sha256:d1581f38c524439e1e64215ed98e8fc6b36b054e2994c7a0fd1840a26d84334a"
SEAL = "sha256:b462fcfb8eb0a274abc2df0214ec08d99be3b77d1cf8ca412e3b3774a8b3ccdc"
INTAKE = "sha256:5d7b3624bca9f1d808cb0bee044fcadb7c4593054da771d8c57dc0dd1456de3c"
ROUTING = "sha256:6958f0a428eeb70ca147aa19c595a834298f1e613ae0776a07e448f230406b10"
PRODUCER = "sha256:122de8ddfdf498f6f372f6f3896387b6ede886b4b136c180aa3e45f4da783c03"
DENSE = "sha256:0def2c61024e8691af4fff27182c77044acd7c2dd7263796821a0a3a427582b5"
WITNESS_BOUND = 1_250_000
METADATA_BOUND = 65_536
REVIEWED_WITNESS = "DS30-0312"
ARCHIVED_FALLBACK = "DS30-0003"
PARTS = {"observed": (), "skip_failed_proposal": ("rejected",), "free_named_fallback": ("fallback",),
         "both_free": ("rejected", "fallback")}


class Reads:
    def __init__(self):
        self.bytes = Counter()

    def load(self, path, group, pin=None, *, cap=METADATA_BOUND, raw=False):
        with path.open("rb") as stream:
            if path.stat().st_size > cap:
                raise ValueError(f"Stage evidence exceeds its declared byte bound at {path}")
            data = stream.read(cap+1)
        self.bytes[group] += len(data)
        if len(data) > cap or pin is not None and digest(data) != pin:
            raise ValueError(f"Sealed bytes or input bound changed at {path}")
        return data if raw else json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def enrollment(snapshot, read):
    plan = read.load(snapshot/"plan.json", "snapshot", PLAN, cap=250_000)
    seal = read.load(snapshot/"rows-with-relocations-seal.json", "snapshot", SEAL)
    source = read.load(snapshot/"rows-with-relocations.jsonl", "snapshot", EXPORT, cap=1_400_000, raw=True)
    order = frozen_order(plan)
    if (seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT
            or [e["case"] for e in order[63:65]] != ["DS30-0282", "DS30-0218"]
            or [e["case"] for e in order[69:71]] != [ARCHIVED_FALLBACK, "DS30-0036"]):
        raise ValueError("Expected the exact sealed original first-70 prefix")
    entries = {row["case"]: row for row in order[:70]}
    rows = {}
    for record in restricted_json(source.splitlines(), CASE_KEY, entries):
        row = json.loads(record)
        label = row["case"], row["algorithm"]
        entry = entries[row["case"]]
        if (label in rows or row["algorithm"] not in BUILDS or row["build_sha256"] != PINS[row["algorithm"]]
                or not row["verified_pair"] or not row["acquisition_verified"] or row["outcome"] not in VERIFIED
                or row["actual_order"] != entry["order"] or row["first"] != entry["order"][0]
                or any(row[k] != entry[k] for k in ("assigned_rank", "case_id", "order", "raw_identity_sha256",
                                                     "manifest_raw_authority_sha256"))
                or row.get("relocation_proof_sha256") != seal["proofs"].get(row["case"])):
            raise ValueError("Selected result does not match the frozen original enrollment")
        rows[label] = row, digest(record)
    if len(rows) != 140:
        raise ValueError("The selected prefix must supply all 140 original arms")
    return entries, rows


def scored_pairs(entries, rows, snapshot, reading):
    old = reading.load(HERE/"ds30-routing-first64.json.gz", "sealed_studies", ROUTING)
    first = list(entries)[:64]
    if first != [r["case"] for r in old["measurements"]]:
        raise ValueError("The sealed first-64 accuracy enrollment differs")
    matched = []
    for row in old["measurements"]:
        case = row["case"]
        pair = []
        for role in BUILDS:
            scored = row[role]
            exported, pin = rows[case, role]
            if (pin != scored["export_line_sha256"]
                    or any(scored[k] != exported[k] for k in (*METRICS, "attempt_result_sha256", "terminal_sha256",
                                                             "outcome", "timing_scope"))):
                raise ValueError("A first-64 measured arm changed in the current export")
            pair.append(dict(case=case, **scored,
                             **{arm+"_rf_rms_hz": exported["arms"][arm]["rf_rms_hz"] for arm in ARMS}))
        matched.append(tuple(pair))
    new = {case: value for case,value in entries.items() if case not in first}
    survey = reading.load(snapshot/"reference-audit.json", "six_case_survey", "sha256:"+REFERENCE,
                          cap=330_000, raw=True)
    candidates = survey.split(b'"cases":[', 1)[1].rsplit(b'],"prediction_lock_sha256":', 1)[0]
    refs = {}
    for body in restricted_json(re.split(rb',(?=\{"acquisition_time_policy":)', candidates), SURVEY_KEY, new):
        row = json.loads(body)
        if row["dataset_label"] in refs:
            raise ValueError("Duplicate authorized reference row")
        point = row["reference"] if row["authority_eligible"] else None
        refs[row["dataset_label"]] = [point["latitude_deg"], point["longitude_deg"]] if point is not None else None
    if refs.keys() != new.keys():
        raise ValueError("The final six original reference rows are incomplete")
    assigned = {case: dict(case_id=row["case_id"], raw_authority=row["manifest_raw_authority_sha256"],
                           physical_content=row["raw_identity_sha256"], release_100=row["historical_first100"],
                           reference=refs[case], recording_state=row["recording_state"])
                for case,row in new.items()}
    matched.extend(paired_rows([rows[c, role][0] for c in new for role in BUILDS], assigned))
    return matched


def compact_route(boot, receipt, outcome):
    if boot["route"] == "authenticated_installed_graph_ineligible" and outcome == "withheld":
        return "before_solver"
    if boot["route"] != "history_risk_installed":
        raise ValueError("Unknown compact charted receiver/solver entry")
    recipe = boot["solver_recipe"]
    if recipe["specification_solver"] != "screened-tiled-finish":
        raise ValueError("The nominal screened-nomination contract changed")
    mode = recipe["history_risk"]["choice"]
    if mode == "named":
        return "direct_named"
    if mode == "lean" and outcome == "complete" and isinstance(receipt["screened_nomination"], dict):
        # An ordinary successful named execution always calls the screened
        # selector. The signed lean branch constructs its own cold finalists.
        return "lean_then_fallback" if receipt["screened_nomination"] else "lean_complete"
    raise ValueError("Compact receipt cannot prove this solver route")


def collected_routes(pairs, rowbook, campaign, snapshot, reading):
    first = reading.load(HERE/"first30-after-intake.json.gz", "sealed_studies", INTAKE)
    first64 = reading.load(HERE/"first64-producer-transfer.json.gz", "sealed_studies", PRODUCER)
    archived_routes = {row["case"]: row for row in first["cases"]}
    if len(first["cases"]) != 30 or set(archived_routes) != {a["case"] for a,_ in pairs[:30]}:
        raise ValueError("The original first-30 route evidence is different")
    producer = {row["case"]: row for row in first64["rows"]}
    routes, binds = {}, {}
    for a, b in pairs[:30]:
        case_receipt = archived_routes[b["case"]]
        if (case_receipt["pins"]["result"] != b["attempt_result_sha256"]
                or case_receipt["installed_result"] != a["attempt_result_sha256"]):
            raise ValueError("The original first-30 paid result changed")
        stage = case_receipt["phases"]
        route = {metric: {name: stage["solver"][metric][old] for name,old in (
                    ("rejected", "rejected_proposal"), ("fallback", "ordinary_fallback"))} for metric in METRICS}
        routes[b["case"]] = dict(route=stage["route"], reason=stage["reason"],
                                 solve={k: stage["outer"][k]["solve"] for k in METRICS},
                                 **{piece: {k: route[k][piece] for k in METRICS} for piece in ("rejected","fallback")})
        binds[b["case"]] = dict(witness="sha256:"+case_receipt["pins"]["scientific"], source="sealed_first30")

    reviewed = None
    for _, b in pairs[30:]:
        case = b["case"]
        row, _ = rowbook[case,"successor"]
        result_path = (campaign/row["attempt"]).resolve(strict=True)
        if result_path != campaign/row["attempt"] or not result_path.is_relative_to(campaign):
            raise ValueError("Only original dedicated-NVMe selected receipt paths are permitted")
        attempt = reading.load(result_path, "compact_attempt", row["attempt_result_sha256"])
        pub = result_path.parent/"publication"
        prior = producer.get(case, {}).get("pins", {})
        eligible_pins = {k: "sha256:"+prior[k] if k in prior else None for k in ("marker","raw")}
        marker = reading.load(pub/"algo08v3-successor-release.json", "compact_marker", eligible_pins["marker"])
        boot = reading.load(pub/"unified-short-bootstrap.json", "compact_boot", eligible_pins["raw"])
        if (any(row[k] != attempt[k] for k in (*METRICS, "algorithm", "outcome", "authority_sha256", "generation"))
                or marker["build_sha256"] != row["build_sha256"] or marker["authority_sha256"] != row["authority_sha256"]
                or marker["decision"] != row["outcome"] or marker["terminal_sha256"] != row["terminal_sha256"]
                or boot["native_sha256"] != attempt["native_sha256"]
                or marker["receipt"] != attempt["evidence"]["receipt"]):
            raise ValueError("Compact route evidence belongs to a different original")
        selected = compact_route(boot, marker["receipt"], row["outcome"])
        zero = dict.fromkeys(METRICS, 0.)
        route = dict(route=selected, rejected=zero, fallback=zero, reason=None)
        if case in producer:
            route["archived_solve_wall_s"] = producer[case]["solver"]
        proof = dict(source="original_compact_route")
        if selected == "lean_then_fallback":
            if case == ARCHIVED_FALLBACK:
                archived = reading.load(snapshot/"ds30-0003-witness-attribution.json", "sealed_studies", DENSE)
                if (archived["case"] != case or archived["original_attempts"] != {
                        role: rowbook[case,role][0]["attempt_result_sha256"] for role in BUILDS}):
                    raise ValueError("The sealed 0003 stage does not bind both original attempts")
                fit = archived["fit"]
                route.update(solve=clock(fit["published_solve"]), rejected=clock(fit["lean"]),
                             fallback=clock(fit["paid_ordinary"]),
                             reason=fit["rejection"])
                proof = dict(source="sealed_0003_attribution", witness="sha256:"+archived["witness_and_reports"]["witness"]["sha256"])
            elif case == REVIEWED_WITNESS:
                reviewed = pub/"exact-named-raw-witness.json", "sha256:"+prior["scientific"], row, attempt["native_sha256"]
                continue
            else:
                raise ValueError("A new unresolved fallback needs its own budgeted stage receipt")
            if (route["route"] != selected or
                    any(route["rejected"][k]+route["fallback"][k] > route["solve"][k]+1e-6
                        or route["solve"][k] > b[k] for k in METRICS)):
                raise ValueError("Expected non-overlapping nested fallback clocks")
        routes[case], binds[case] = route, proof
    if reviewed is None:
        raise ValueError("The prespecified fallback no longer has its original compact marker")
    path, pin, row, native = reviewed
    if path.resolve(strict=True) != path:
        raise ValueError("Witness must be its original dedicated-NVMe publication file")
    witness = reading.load(path, "full_witness", pin, cap=WITNESS_BOUND)
    detail = witness["evidence"]["detail"]
    if detail["terminal_sha256"] != row["terminal_sha256"] or detail["input_sha256"] != native:
        raise ValueError("Fallback witness does not bind the paid compact result")
    route = route_times(witness, row["outcome"])
    if route["route"] != "lean_then_fallback" or any(route["solve"][k] > row[k] for k in METRICS):
        raise ValueError("Original detailed witness differs from the compact route or paid enclosure")
    routes[REVIEWED_WITNESS] = route
    binds[REVIEWED_WITNESS] = dict(source="one_bounded_original_witness", witness=pin)
    return routes, binds


def wall_results(records):
    stock = [a["elapsed_s"] for a,_,_ in records]
    result = {}
    for name, pieces in PARTS.items():
        other = [b["elapsed_s"]-sum(r[p]["elapsed_s"] for p in pieces) for _,b,r in records]
        result[name] = dict(installed_s=sum(stock), installed_median_s=median(stock),
                            successor_s=sum(other), successor_median_s=median(other), at_half=sum(
                                2*b <= a for a,b in zip(stock, other, strict=True)))
    return result


def run(snapshot, campaign):
    read = Reads()
    entries, rows = enrollment(snapshot, read)
    pairs = scored_pairs(entries, rows, snapshot, read)
    routes, binds = collected_routes(pairs, rows, campaign, snapshot, read)
    records = [(a,b,routes[a["case"]]) for a,b in pairs]
    classes = Counter(route["route"] for route in routes.values())
    all_results = summarize(records)
    return dict(plan=PLAN, export=EXPORT, seal=SEAL, cases=list(entries), routes=routes, bindings=binds, counts=classes,
                all=all_results, wall_totals=wall_results(records),
                by_route={label: summarize([r for r in records if r[2]["route"] == label]) for label in sorted(classes)},
                accuracy={role: outcomes_summary([pair[i] for pair in pairs], entries) for i,role in enumerate(BUILDS)},
                report_read_bytes=dict(read.bytes), report_read_bytes_total=sum(read.bytes.values()),
                permitted_full_witness_bytes=WITNESS_BOUND)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("snapshot", type=Path)
    cli.add_argument("--campaign", default=CAMPAIGN, type=Path)
    args = cli.parse_args()
    print(json.dumps(run(args.snapshot, args.campaign), sort_keys=True, allow_nan=False, indent=2))
