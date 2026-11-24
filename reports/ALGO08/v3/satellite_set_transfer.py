"""Compare sealed satellite assignment evidence, then score the fixed DS30 transfer."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from first30_native_agreement import read_case
from signed_cfo_time_readout import canonical, document


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
FIRST30 = "2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
FIRST37 = "df6dc59b1d41aec62d4a2127618023096ebe72b990b43887166fc4e9de8c3254"
REFERENCE = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
ARMS, METHODS = ("c0", "fitted_c"), ("installed", "successor")
INSTALLED_MATCHES = {
    "DS30-0086": "b6f0afe62a52313dd8b5aaddcbdb1cfb6f1bd14349752ed9bf2929f2ed7bf6f9",
    "DS30-0220": "9d5baed1b5bac3791cda0340af30c9ea3123ab4ad719112e50ca4a9417e495ce",
}


def ledger(folder, capture, count, expected):
    path = folder / "rows-with-relocations.jsonl"
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError("The preregistered field export changed")
    grouped = defaultdict(dict)
    for line in raw.splitlines():
        row = json.loads(line)
        if row["verified_pair"] is not True:
            continue
        case, role, path = row["case"], row["algorithm"], Path(row["attempt"])
        if role in grouped[case] or path.is_absolute() or ".." in path.parts or path.name != "result.json":
            raise ValueError("Unexpected assigned result path")
        grouped[case][role] = (capture / path, row)
    if len(grouped) != count or any(set(pair) != set(METHODS) for pair in grouped.values()):
        raise ValueError("The fixed panel does not have the required verified pairs")
    start = lambda case: min(row["child_started_unix_ns"] for _, row in grouped[case].values())
    return {case: grouped[case] for case in sorted(grouped, key=start)}


def roster(rows, detail):
    map_ = {oid: norad for oid, norad, _ in rows}
    result = Counter(map_.values())
    if (len(rows) != len(map_) or len(map_) != detail["associated_points"]
            or len(result) != detail["satellites"] or canonical(map_) != detail["owner_sha256"]):
        raise ValueError("Assignment row readback differs from official owner digest or count")
    return result


def set_evidence(old_count, new_count, old_digest, new_digest, old=None, new=None):
    if old is not None and new is not None:
        a, b = set(old), set(new)
        return dict(relation="same" if a == b else "changed", proof="both_exact_rosters", gap=len(a ^ b)/len(a | b),
                    common=len(a & b), dropped=sorted(a-b), added=sorted(b-a))
    if old_digest == new_digest:
        if old_count != new_count:
            raise ValueError("Equal owner maps contradict unequal set counts")
        return dict(relation="same", proof="equal_owner_map_hash", gap=0., common=old_count)
    if old_count != new_count:
        return dict(relation="changed", proof="unequal_cardinalities",
                    jaccard_lower_bound=abs(old_count-new_count)/max(old_count, new_count))
    return dict(relation="unresolved", proof="equal_count_unequal_owner_hash", jaccard_lower_bound=0.)


def named_rows(case, result):
    reported = result["evidence"].get("owner_rows")
    if reported:
        return reported
    if case == "DS30-0049":
        seal = document(MEASUREMENTS / "ds30-0049-saved-crossover.json.gz", "76ffa1841268d1f9dd8348a3549c8927655653abdcc804697b6a36f00aebf8ce")
        if seal["cells"]["installed-installed"]["native_sha256"] != result["native_sha256"]:
            raise ValueError("Earlier exact control used another installed packet")
        return seal["ordered_owner_rows"]["installed-installed"]
    if case in INSTALLED_MATCHES:
        pin = document(MEASUREMENTS / f"field-installed-packet-saved-{case[-4:]}.json", INSTALLED_MATCHES[case])
        if pin["native_sha256"] != result["native_sha256"] or not all(pin["exact_owner_map"].values()):
            raise ValueError("Saved owner evidence is not the original map")
        ref = pin["source_artifacts"]["candidate_worker"]
        path = Path(ref["path"])
        return document(path, ref["sha256"])["ordered_owners"] if path.exists() else None
    return None


def assignment_features(case, pair):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    saved = {}
    for method, (path, row) in pair.items():
        result = document(path, row["attempt_result_sha256"])
        if result["algorithm"] != method or result["outcome"] != row["outcome"]:
            raise ValueError("The sealed result disagrees with the field ledger")
        saved[method] = result
    if saved["installed"]["raw_identity"] != saved["successor"]["raw_identity"]:
        raise ValueError("The comparison does not share a signed source")
    arms, manifests = {}, {}
    outcomes = {method: result["outcome"] for method, result in saved.items()}
    feature = dict(outcomes=outcomes, arms=arms)
    if set(outcomes.values()) != {"complete"}:
        return feature, saved
    owner_sets = {}
    for method, (path, row) in pair.items():
        pub = path.parent / "publication"
        result = saved[method]
        evidence = result["evidence"]
        manifest = FastStandardAnalysisStore(pub).detail(evidence["receipt"]["run_id"])
        if (manifest["state"] != "complete" or manifest["input_sha256"] != result["native_sha256"]
                or manifest["terminal_sha256"] != row["terminal_sha256"]
                or manifest["raw_authority"] != result["raw_identity"]["raw_authority_sha256"]
                or evidence["owners"] != {arm: entry["owner_sha256"] for arm, entry in manifest["arms"].items()}):
            raise ValueError("Assignments are detached from the paired publication")
        manifests[method] = manifest
        if method == "successor":
            witness = document(pub / "exact-named-raw-witness.json")
            if witness["evidence"]["detail"]["terminal_sha256"] != manifest["terminal_sha256"]:
                raise ValueError("Candidate owner witness has another terminal")
            rows = witness["evidence"]["owner_rows"]
        else:
            rows = named_rows(case, result)
        owner_sets[method] = {arm: roster(rows[arm], manifest["arms"][arm]) for arm in ARMS} if rows else {}
    for arm in ARMS:
        old, new = (manifests[method]["arms"][arm] for method in METHODS)
        a, b = (owner_sets[method].get(arm) for method in METHODS)
        relation = set_evidence(old["satellites"], new["satellites"], old["owner_sha256"], new["owner_sha256"], a, b)
        share_loss = (old["associated_points"]/manifests["installed"]["glrt_points"]
                      -new["associated_points"]/manifests["successor"]["glrt_points"])
        effective = sum(b.values())**2/sum(x*x for x in b.values())
        arms[arm] = dict(relation, satellite_count=[old["satellites"], new["satellites"]],
                         satellite_count_loss=old["satellites"]-new["satellites"], owner_share_loss=share_loss,
                         owner_count=[old["associated_points"], new["associated_points"]],
                         track_count=[old["tracks"], new["tracks"]], candidate_effective_count=effective,
                         negative_candidate_effective_count=-effective,
                         installed_exact_rows=a is not None, charted_exact_rows=b is not None)
    return feature, saved


def native_feature(case, pair, saved, old_census):
    packet = old_census[case] if case in old_census else read_case(case, pair)[0]
    expected = {"installed": saved["installed"]["native_sha256"], "mixed": saved["successor"]["native_sha256"]}
    if packet["native_sha256"] != expected:
        raise ValueError("Native support belongs to a different pair")
    counts = packet["counts"]
    return {scope: {key: counts[scope].get(key, 0) for key in
                    ("installed_peaks", "mixed_peaks", "matched", "installed_only_lanes", "mixed_only_lanes")}
            for scope in ("anchor", "short")}


def distance_m(left, right):
    a, b = map(radians, left)
    c, d = map(radians, right)
    h = sin((a-c)/2)**2 + cos(a)*cos(c)*sin((b-d)/2)**2
    return 12_742_017.6 * asin(sqrt(min(1., h)))


def crossing(before, after, limit):
    good_left, good_right = (x is not None and x <= limit for x in (before, after))
    return "stable" if good_left == good_right else "gain" if good_right else "loss"


def score(case, feature, saved, references):
    site = references.get(case)
    for arm in ARMS:
        if site is None:
            continue
        endpoints = [saved[method]["evidence"]["arms"].get(arm, {}).get("latlon") for method in METHODS]
        a, b = (distance_m(site, p) if p is not None else None for p in endpoints)
        result = feature["arms"].setdefault(arm, {})
        result.update(errors_m=[a,b], excess_m=b-a if a is not None and b is not None else None,
                      coverage={str(limit): crossing(a, b, limit) for limit in (1000, 2000)})
        if all(p is not None for p in endpoints):
            result["endpoint_displacement_m"] = distance_m(*endpoints)


def kendall(pairs):
    c = d = tx = ty = 0
    for (x, y), (u, v) in combinations(pairs, 2):
        cross = (x-u)*(y-v)
        c += cross > 0
        d += cross < 0
        tx += x == u and y != v
        ty += x != u and y == v
    scale = sqrt((c+d+tx)*(c+d+ty))
    return dict(n=len(pairs), tau_b=(c-d)/scale if scale else None, concordant=c, discordant=d)


def summarize(ordered):
    arms = {arm: [row["arms"].get(arm, {}) for row in ordered.values()] for arm in ARMS}
    return {arm: dict(relations=dict(Counter(r.get("relation", "no_shared_fix") for r in rows)),
                      observed_both_rosters=sum(r.get("proof") == "both_exact_rosters" for r in rows),
                      rho={name: kendall([(r[name], r["excess_m"]) for r in rows if r.get("excess_m") is not None])
                           for name in ("satellite_count_loss", "owner_share_loss", "negative_candidate_effective_count")},
                      coverage={key: {tag: [case for case, row in ordered.items()
                                            if row["arms"].get(arm, {}).get("coverage", {}).get(key) == tag]
                                      for tag in ("gain", "loss")} for key in ("1000", "2000")})
            for arm, rows in arms.items()}


def evaluate(capture, first, held=None, prior=None):
    first_cases = ledger(first, capture, 30, FIRST30)
    old_census = {}
    if held is None:
        pairs = first_cases
        native = document(MEASUREMENTS / "first30-native-agreement.json.gz", "c9f14a2380f5d1fc58cefdeaf03ff40368b73f1f5beefc921f0a84d016863ed8")
        old_census = {row["case"]: row for row in native["cases"]}
    else:
        first_receipt = json.loads(prior.read_bytes())
        if first_receipt["ledger_sha256"] != FIRST30 or len(first_receipt["cases"]) != 30:
            raise ValueError("Finish the preregistered first-30 readout before reading the held cases")
        entire = ledger(held, capture, 37, FIRST37)
        for case, pair in first_cases.items():
            if case not in entire or any(entire[case][m][1]["attempt_result_sha256"] != pair[m][1]["attempt_result_sha256"] for m in METHODS):
                raise ValueError("The first-30 control changed in the held ledger")
        pairs = {case: pair for case, pair in entire.items() if case not in first_cases}
    records, signed = {}, {}
    for case, pair in pairs.items():
        records[case], signed[case] = assignment_features(case, pair)
        records[case]["native"] = native_feature(case, pair, signed[case], old_census)
    source = document(HERE.parents[1] / "2026_11_21_ds30_full/reference-audit.json", REFERENCE)
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in source["cases"] if r["authority_eligible"] and r["sealed_metadata_digests_verified"]}
    for case, feature in records.items():
        score(case, feature, signed[case], refs)
    return dict(ledger_sha256=FIRST37 if held else FIRST30, reference_sha256=REFERENCE,
                case_order=list(records), cases=records, summary=summarize(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("first30", type=Path)
    parser.add_argument("--first37", type=Path)
    parser.add_argument("--first30-receipt", type=Path)
    a = parser.parse_args()
    if (a.first37 is None) != (a.first30_receipt is None):
        parser.error("Held analysis needs the frozen 37-pair rows and completed first-30 receipt")
    print(json.dumps(evaluate(a.capture, a.first30, a.first37, a.first30_receipt),
                     indent=2, sort_keys=True, allow_nan=False))
