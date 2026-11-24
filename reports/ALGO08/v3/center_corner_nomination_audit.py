"""Audit admission and avoidable rank cost from pinned, saved centre/corner receipts."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
BASE = "fb555a633bd6f01b5404f7821e8f283922ad7940"
MEASUREMENTS = "reports/ALGO08/v3/measurements/"
PINS = {
    "blind-rank.json": "718616328e7f1a198638ab02327e7e9011398fe9b92e2bb3dfb3c49aa719e50a",
    "cold-finalist-race.json.gz": "54c51d6e8420d266787d1ab1aa6b2b6fe5c9cba5526d3bba7bf93c5012880e86",
    "cold-exact-budget-profile.json.gz": "bc678254659ac2403bc2d712560a3a69c3ce75e61eabd57535394ae10fbe58dc",
    "catalogue-block-dense-pair.json.gz": "221619809450842843221dcd6dc4b80412d19fd5a661318c447b738bd6c3bf68",
    "catalogue-block-portable-0316.json.gz": "31852bdbfd08905c7827a79c1d015bc380ee9da742b8a0eed47428edc0165536",
    "rank-block-0138.json": "39fe1e32e302a97bec5ed74391cf7bc5b04355e19ae4b6c8eb2078cf70bacae0",
    "history-risk-0016-raw.json.gz": "5b84151697623d67ce43f7ec2ddcf3f9fc488701625754fabb8d6f7a612d23d3",
    "history-risk-0016-omitted.json.gz": "fd8cfe8a08ba896922c148e5050d3561e1f30cc875a9cf5dc7b942f55874d2cf",
    "history-risk-raw.json.gz": "ff335cb69524253255168c93138497639e3342ab615a602d0d502aab873ff75b",
    "named-rank-census.json.gz": "4f98be935f2121f9d5f560a30a8a980c0138f89e945a4e3c53fb9c343ace3a6a",
}
SOURCE_PINS = {
    "tools/pipeline_eval/variants/v5_core.py": "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407",
    "tools/pipeline_eval/variants/algo08_dense_discovery.py": "d8c221ba3240de78b7dad1d657c0c01d425b9384658aa7ed9a7679c28b8439f1",
    "src/leo/analysis/localization_v3/discovery.py": "7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a",
    "reports/2026_11_19_short_receiver/search-budget/README.md":
        "e8535d9b1cd057c302b21db8feca9a968cfdca16d0d9d3cbf1f1bab2a8e9f7d4",
}
OLDER = Path("/home/mouse9911/.cache/initial-discovery-20261113/dev-ranking-only-001/DS26-0102-r0")
OLDER_PINS = {
    "baseline-work.json": "faeb38d625eb9cae1e115c72e6bf507e023a9ce6d1bad7c90a0c07ae056b054b",
    "candidate-work.json": "78399f68840205175cc449b526c6bdc6240c85bfe78918169793e69f3a21f656",
    "baseline/report.json": "94b2bdc016eb24f2b95cc4f25b1f8be1d16da6424ca95402f17e6189436359a0",
    "candidate/report.json": "91db8ec8ac5686741ce26170e65c6937b4a5380f9a7ae5ece3b154db4f35bc70",
}


def pinned(path, expected):
    body = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{BASE}:{path}"])
    if sha256(body).hexdigest() != expected:
        raise ValueError(f"Archived bytes changed: {path}")
    return body


def source_documents():
    for relative, pin in SOURCE_PINS.items():
        pinned(relative, pin)
    available = {}
    for name, pin in PINS.items():
        body = pinned(MEASUREMENTS + name, pin)
        available[name] = json.loads(gzip.decompress(body) if name.endswith(".gz") else body)
    return available


def signature_budget(generated, unique, centres=4):
    """Give deterministic limits without assigning sorted nodes to an anchor."""
    if not 2 <= centres < generated or not 1 <= unique <= generated:
        raise ValueError("Inconsistent nomination population")
    duplicates = generated - unique
    return dict(generated=generated, unique=unique, repeat_slots=duplicates,
                any_two_centre_agreement_possible=duplicates >= 1,
                two_centre_and_first_corner_agreement_possible=duplicates >= 2,
                novel_skipped_at_least_if_two_centres_and_first_corner_agree=(
                    max(0, unique - centres + 1) if duplicates >= 2 else None),
                corner_exclusive_at_least=max(0, unique-centres),
                corner_exclusive_at_least_if_two_centres_agree=max(0, unique-centres+1) if duplicates else None,
                distinct_unseen_if_only_two_identical_centres_paid=unique-1 if duplicates else None)


def subsequent_scope(rank_cpu_s, centres_cpu_s=None, corner_and_alias_cpu_s=None):
    """Free-qualification ceiling after all centres; actual proposal also pays one corner."""
    if rank_cpu_s <= 0:
        raise ValueError("A measured rank or enclosing cold clock is required")
    if centres_cpu_s is None:
        return rank_cpu_s
    if not 0 < centres_cpu_s < rank_cpu_s:
        raise ValueError("Centre clock must be inside the rank scope")
    if corner_and_alias_cpu_s is not None and not 0 < corner_and_alias_cpu_s <= rank_cpu_s-centres_cpu_s:
        raise ValueError("Corner work must be disjoint from the centre work")
    return rank_cpu_s-centres_cpu_s


def corner_origin(rows, centre_budget):
    """A first insertion past the maximum centre budget must come from a corner."""
    if (not 1 <= centre_budget < len(rows)
            or [row["node_index"] for row in rows] != list(range(len(rows)))):
        raise ValueError("Expected the full insertion order before score sorting")
    winning = min(rows, key=lambda row: row["cold_score"])
    if winning["node_index"] < centre_budget:
        return None
    centre_best_lower = min(row["cold_score"] for row in rows[:centre_budget])
    return dict(node_index=winning["node_index"], cold_score=winning["cold_score"],
                centre_score_lower_bound=centre_best_lower,
                improvement_at_least=centre_best_lower-winning["cold_score"])


def archived_origin(root):
    docs = {}
    for name, digest in OLDER_PINS.items():
        body = (root / name).read_bytes()
        if sha256(body).hexdigest() != digest:
            raise ValueError(f"Original insertion-order evidence changed: {name}")
        docs[name] = json.loads(body)
    control, candidate = (docs[f"{mode}-work.json"] for mode in ("baseline", "candidate"))
    rank_policy = candidate["initial_discovery_policy"]
    control_counts, counts = (doc["initial_counts"] for doc in (control, candidate))
    if (not (control["public_store_validated"] and candidate["public_store_validated"])
            or control["initial_discovery_policy"] is not None
            or (rank_policy["seed_policy"], rank_policy["ranking_policy"]) != ("legacy", "warm-center-v1")
            or control["manifest_sha256"] != candidate["manifest_sha256"]
            or control_counts != counts or counts["selected_hypothesis"] != 0):
        raise ValueError("The earlier warm-ranking trace changed more than its ranking option")
    paired = []
    for mode, work in (("baseline", control), ("candidate", candidate)):
        report_path = f"{mode}/report.json"
        report = docs[report_path]
        (row,) = report["results"]
        if (work["report_sha256"] != "sha256:" + OLDER_PINS[report_path]
                or row["status"] != "complete" or row["result_sha256"] != work["result_sha256"]):
            raise ValueError("The earlier opening-order evidence is not bound to a complete saved result")
        paired.append({key: row[key] for key in ("case", "input_sha256", "tle_sha256", "workload_sha256")})
    ranking = candidate["initial_ranking"]
    if paired[0] != paired[1] or len(ranking) != counts["unique_RF_hypotheses"]:
        raise ValueError("Earlier legacy seed provenance or candidate coverage changed")
    origin = corner_origin(ranking, counts["fresh_radio_seed_budget"])
    if origin is None:
        raise ValueError("The earlier direct corner witness disappeared")
    return paired[0] | dict(paths=str(root), pins=OLDER_PINS, ranking=origin, fallback_role="older independent evidence",
                            stock_selected_cold_rank_zero=True, independent_centre_state_available=False,
                            candidates=len(ranking), score_rows=[{k: row[k] for k in ("node_index", "cold_score")}
                                                               for row in ranking])


def clean_rank(ranks, case):
    (rank,) = ranks[case]["control"]["ranks"]
    shared = rank["shared"]
    corner = shared["other_projections"]
    remaining_explorations = shared["fused_passes"] - 1 - corner
    if corner != 4 or remaining_explorations != 8 or rank["counts"]["tracks"] != rank["tracks"]*16:
        raise ValueError("Original cached execution no longer verifies four centres and four corners")
    return dict(**signature_budget(8, rank["hypotheses"]), rank_cpu_s=rank["clocks"]["cpu_s"],
                paid_associations_after_exact_duplicate_reuse=rank["counts"]["tracks"] // rank["tracks"],
                top3_winner=ranks[case]["control"]["chosen"][0]["details"]["branch"],
                unnormalized_state_available=False, origin_order_available=False)


def dense_measurement(documents):
    dense = clean_rank(documents["cold-finalist-race.json.gz"]["runs"], "DS30-0008")
    shared = documents["catalogue-block-dense-pair.json.gz"]["result"]["rank"]
    if shared["ordered_ranks"] != dense["unique"] or not shared["exact_archived_signatures"]:
        raise ValueError("Dense full-catalogue control count changed across timing contexts")
    profile = documents["cold-exact-budget-profile.json.gz"]["stages"]["work"]
    (centres,) = (row for row in profile["profile_rows"] if row["function"] == "fresh_discovery")
    (rank,) = (row for row in profile["profile_rows"] if row["function"] == "ranked_initial_nodes")
    if centres["calls"] != 1 or rank["calls"] != 1:
        raise ValueError("Expected one centre operation within the profiled dense rank")
    total, spent = rank["inclusive_cpu_s"], centres["inclusive_cpu_s"]
    return dense | dict(mixed_profile_rank_cpu_s=total, mixed_profile_centres_cpu_s=spent,
                        mixed_after_centres_gross_upper_cpu_s=subsequent_scope(total, spent),
                        mixed_exact_block_clock=shared["paired"])


def audit(documents):
    dense = dense_measurement(documents)
    race = documents["cold-finalist-race.json.gz"]["runs"]
    weak = clean_rank(race, "DS30-0016")
    south = documents["blind-rank.json"]["cases"]
    south_rank = {}
    for name in ("south-containing", "south-far"):
        row = south[name]
        candidate = row["runs"]["candidate"]
        sharing = candidate["shared_work"]
        if sharing["fused_passes"] != 13 or sharing["other_projections"] != 4:
            raise ValueError("South cadence changed")
        south_rank[name] = dict(**signature_budget(8, row["candidates"]),
                                rank_cpu_s=candidate["rank_clocks"]["cpu_s"], top3_winner=row["cold"]["branch"])

    long = documents["rank-block-0138.json"]
    clock = long["measured_0138"]
    total = clock["enclosing"]["cpu_ns"]/1e9
    centre = clock["scopes"]["centre_nomination"]["inclusive_s"]
    corners = sum(clock["scopes"][name]["inclusive_s"] for name in ("corner_exploration", "corner_alias_construction"))
    exact_0138 = dict(**signature_budget(clock["proposals_before_dedup"], clock["distinct"]),
                     rank_cpu_s=total, centres_cpu_s=centre, full_four_corners_and_alias_cpu_s=corners,
                     after_centres_gross_upper_cpu_s=subsequent_scope(total, centre, corners),
                     all_unique_final_score_cpu_s=clock["post_signature_all_scores_free_upper_cpu_s"],
                     final_rank_order=long["observed_0138"]["final_order"])
    portable = documents["catalogue-block-portable-0316.json.gz"]["result"]
    (medium,) = portable["rank"]["evaluations"]
    exact_0316 = dict(**signature_budget(8, medium["nodes"]), rank_cpu_s=medium["rank"]["cpu_ns"]/1e9)

    contained = documents["history-risk-0016-raw.json.gz"]["runs"]["candidate"]["route"]["history_risk"]
    omitted = documents["history-risk-0016-omitted.json.gz"]["result"]["route"]["history_risk"]
    north = documents["history-risk-raw.json.gz"]["saved_omission"]
    north = north["north-far-saved/exact-named-raw-witness.json"]["value"]["ports"]["history_risk"]
    ports = {}
    for key, doc in (("DS30-0016-original-containing", contained), ("DS30-0016-translated", omitted),
                     ("north-far", north)):
        (attempt,) = doc["lean_attempts"]
        cold = attempt["cold"]
        ports[key] = dict(total_cold_cpu_s=attempt["cold_clocks"]["cpu_s"],
                          distinct_finalists_at_least=len(cold["scores"]), refined_winner=cold["branch"],
                          finalist_route=cold["routing"], chronological_nominations_available=False)
    if not north["boundary_checks"][0]["result"]["would_withhold"] or omitted["boundary_checks"][0]["result"]["would_withhold"]:
        raise ValueError("Archived geographic controls differ")
    named = documents["named-rank-census.json.gz"]["panels"]["100"]
    return dict(
        schema="center-corner-nomination-audit-v1", archive_revision=BASE, source_pins=SOURCE_PINS, receipt_pins=PINS,
        rule=dict(centre_calibrations_paid=4, distinct_input_centres_required=(0, 1),
                  require_first_two_match_complete_state=True, require_selected_parent_match=True,
                  paid_original_corner=(-1, -1), require_corner_match_signed_assignment=True,
                  ordinary_remaining_corner_passes=3, unresolved_ordinary_fallback=True),
        rank_cases={"DS30-0008": dense, "DS30-0016-paid-quadratic": weak, "DS30-0138": exact_0138,
                    "DS30-0316": exact_0316, **south_rank},
        partial_matched_geographic_ranks=ports,
        named_v3_independent_rank_census=dict(fixes=named["decisions"]["complete"], ranks=named["fixed_winners"],
                                               earliest_later=named["earliest_nonzero"]),
        disposition="stop_before_paid_validation", new_rank_runs=0, position_solves=0, raw_reads=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--older-origin", type=Path, default=OLDER)
    args = parser.parse_args()
    result = audit(source_documents())
    result["older_direct_corner_winner"] = archived_origin(args.older_origin)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
