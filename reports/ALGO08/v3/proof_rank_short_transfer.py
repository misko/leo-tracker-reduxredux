"""Check the reviewed proof-owner cold-rank union on two saved short captures."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, read, solve, write
from dense_geographic_trial import elapsed, host, now


HERE = Path(__file__).resolve().parent
CASES = ("physical", "south-inside")
GEOGRAPHIC = Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so")
TRACK_ASSET_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
REVIEWED_RANK_PIN = "297dd1fd485f4d439a9060b6661036094909bf8343bea533f6ace972185872a6"
SOURCE_PINS = {
    "full-short-DS30-0016-raw.json.gz": "945fd3ffccf8e773b64aca7c53242c1432564b48d027eaf730240d7e96b6a297",
    "full-short-south.json": "607b25b2352393103db2f05d5fe8f36ae2a7dafbc04b1328d7db792516cfd356",
    "full-short-graph-transfer.json": "1514e56ecbcd198247bec12edf862ab7e33ebd00a0f46805f72389f0fb68e034",
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def receipt(name):
    path = HERE / "measurements" / name
    if digest(path) != SOURCE_PINS[name]:
        raise ValueError(f"The signed development receipt changed at {name}")
    return path


def saved(case):
    from full_short_graph_transfer import inputs
    from full_short_raw import RECIPE_SHA
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    source = "full-short-DS30-0016-raw.json.gz" if case == "physical" else "full-short-south.json"
    receipt(source)
    _, archive, offer_path, path, key, offer = inputs(case)
    archive_dir = Path(archive["root"])
    document = read(path)
    provenance = document["provenance"]
    if (canonical_digest(document) != key or "sha256:" + digest(path) != key
            or provenance["detector_sha256"] != "sha256:" + RECIPE_SHA
            or document["source"].get("qualified") is not True
            or archive_identity(archive_dir) != archive or Algo08Region.parse(read(offer_path)).document() != offer):
        raise ValueError("An authenticated saved short native packet, original offer and causal archive are required")
    return document, archive_dir, offer, dict(native_sha256=key, case=case, packet=str(path),
                                              archive=archive, offer=offer, offer_sha256=digest(offer_path),
                                              receipt_sha256=SOURCE_PINS[source], receiver=provenance["detector_sha256"],
                                              raw_authority=document["source"]["raw_recording_authority_digest"])


def saved_far():
    original = read(receipt("full-short-graph-transfer.json"))["south-far"]
    pair = read(receipt("full-short-south.json"))["cases"]
    proof, = original["early_regional"]
    answer = proof["result"]
    terminal = original["terminal"]
    if (original["route"] != "withheld_early" or original["decision"] != "withheld"
            or terminal["native_sha256"] != pair["containing"]["native_pin"]
            or terminal["native_sha256"] != pair["far"]["saved_digest"]
            or terminal["region"] != pair["far"]["terminal"]["region"]
            or terminal["reason"] != "both_receivers_support_far_exterior" or original["evidence"]["images"]
            or original["solve"]["reduced_grid"] or "geographic_projector" in original["solve"]
            or any(terminal["arms"][arm]["latlon"] is not None for arm in ARMS)
            or not answer["complete"] or not answer["would_withhold"] or answer["probes_evaluated"] != 96
            or set(answer["receivers"]) != {"1", "2"}
            or not all(row["unique_exterior"] for row in answer["receivers"].values())):
        raise ValueError("Expected the sealed installed-graph short southern bilateral withholding before cold ranking")
    return dict(route=original["route"], terminal=terminal, rank_invocations=0, proof=proof,
                projector="released dense geographic projector", solve=original["solve"],
                archive_receipt_sha256=SOURCE_PINS["full-short-graph-transfer.json"])


def costs(timing, proof, selector, fallback):
    def sum_parts(*parts):
        return {key: sum(part[key] for part in parts) for key in ("cpu_s", "elapsed_s")}

    original = sum_parts(*timing["original"].values())
    trial = sum_parts(*timing["reduced"].values(), selector) if "reduced" in timing else selector
    result = dict(original=sum_parts(original, proof), attempted_reduced=sum_parts(trial, proof))
    result["guard_charged"] = sum_parts(trial, original, proof) if fallback else result["attempted_reduced"]
    return result


def ranked_transfer(prepared, region, bound, visited, proof, share, *, first):
    from blind_joint_finish import digest as science_digest
    from leo.analysis.localization_v3.discovery import signature
    from proof_global_rank import compare_top_three, fallback_reason, ranked_scores, reduced_input, select_pool
    from tools.pipeline_eval.variants import v5_core

    labels = list(map(int, prepared["sky"]["bank"]["norad"]))
    start = now()
    slate = select_pool(visited, labels)
    selector = elapsed(start)
    timing, ranks, fallback, sharing = {}, {}, "unusable_proof_pool" if slate is None else None, {}

    def evaluate(kind):
        start = now()
        try:
            source = reduced_input(prepared, slate) if kind == "reduced" else prepared
            working = v5_core.scan_context(source, region, science_digest(prepared["noise"]), bound, "previous")
        finally:
            timing[kind] = dict(scan_setup=elapsed(start))
        start = now()
        try:
            with share(working) as metrics, ranked_scores(v5_core.ranked_initial_nodes) as rank:
                ranks[kind] = rank(working)
            sharing[kind] = metrics
        finally:
            timing[kind]["rank"] = elapsed(start)

    order = (first, "reduced" if first == "original" else "original") if slate is not None else ("original",)
    for kind in order:
        if kind == "original":
            evaluate(kind)
            continue
        try:
            evaluate(kind)
        except (ValueError, ArithmeticError):
            fallback = "invalid_reduced_evidence"
        else:
            fallback = fallback_reason(ranks[kind])

    formatted = {kind: [dict(score=score if isfinite(score) else None,
                             owners=[(component, norad, alias) for component, _, norad, alias in signature(node)])
                        for score, node in ranked] for kind, ranked in ranks.items()}
    original, reduced = formatted["original"], formatted.get("reduced", [])
    if any(row["score"] is None for row in original[:3] + reduced[:3]):
        pair = dict(ordered_assignments=False, score_delta=[], within_score_tolerance=False)
    else:
        pair = compare_top_three(original, reduced)
    exact = all(pair[key] for key in ("ordered_assignments", "within_score_tolerance"))
    selected = {labels[j] for j in slate or []}
    winners = {n for row in visited for n in row["owners"].values() if n is not None}
    eligible = winners.intersection(labels)
    outside = [[(component, norad, alias) for component, norad, alias in row["owners"] if norad not in eligible]
               for row in formatted["original"][:3]]
    return dict(full_roster=len(labels), pool=sorted(selected), pool_in_order=[labels[j] for j in slate or []],
                proof_winners=len(winners), eligible_union_size=len(eligible),
                original_top3_outside_pool=outside, order=order, activated=slate is not None, fallback=fallback,
                selector=selector, timing=timing, sharing=sharing, paid_proof=proof,
                paid_cost=costs(timing, proof, selector, fallback), ranks=formatted, comparison=pair,
                passes_rank_transfer=fallback is None and exact, changed_without_deployable_warning=fallback is None and not exact)


def run(case, binary, output):
    current = host()
    publication, specification = configuration()
    from dense_geographic_projection import checked_runtime
    from early_region import before_fit
    from full_short_run import GEOGRAPHIC_SHA, geographic_projection
    from prepared_exterior import handoff
    from proof_global_rank import __file__ as reviewed_rank
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    native, archive, offer, identity = saved(case)
    if digest(Path(reviewed_rank)) != REVIEWED_RANK_PIN:
        raise ValueError("The reviewed global-union operation changed")
    graph_check = read(receipt("full-short-graph-transfer.json"))[case]
    stock_solve = algo08_position.solve
    share = run_path(str(HERE.parents[2] / "tools/pipeline_eval/variants/algo08_blind_rank.py"))["shared_rank_preparation"]
    extra, regional, visited, proof_costs = {}, [], [], []

    def observed(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or digest(assets / "tracks.json") != TRACK_ASSET_PIN):
            raise ValueError("The expected same-input installed Graph failed its asset binding")
        kernel, _ = checked_runtime()
        prepare = kernel._prepare_probe_scores

        def audit(*args):
            points, scorer, meta = prepare(*args)

            def visit(point):
                row = scorer(point)
                visited.append(dict(row))
                return row

            return points, visit, meta

        def paid(*args, **options):
            start = now()
            report = regional_bound_guard.causal_probes(*args, **options)
            proof_costs.append(elapsed(start))
            return report

        def inspect(prepared, view, bound, _stages, **_opts):
            proof, = proof_costs
            extra["rank"] = ranked_transfer(prepared, view, bound, visited, proof, share,
                                            first="original" if case == "physical" else "reduced")
            return dict(status="withheld", reason="rank_only_audit", arms={arm: {"latlon": None} for arm in ARMS})

        with ExitStack() as scopes:
            projector = scopes.enter_context(geographic_projection(binary))
            live, counts, _ = scopes.enter_context(handoff(reader))
            scopes.enter_context(patch.object(kernel, "_prepare_probe_scores", audit))
            scopes.enter_context(patch.object(v5_core, "infer", before_fit(inspect, reader, paid, regional, live.match)))
            decision, packet, policy = stock_solve(document, reader, assets, region)
        if packet is not None:
            raise ValueError("The rank-only study must never compute a fitted result or grid")
        extra.update(projection=dict(projector), catalogue=dict(counts))
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, specification, native, archive, offer)
    same_proof = graph_check["early_regional"][0]["result"]
    early, = regional
    if (archive_identity(archive) != identity["archive"] or identity["native_sha256"] != graph_check["terminal"]["native_sha256"]
            or json.loads(json.dumps(early["result"])) != same_proof or extra["projection"]["calls"] != len(visited)
            or extra["projection"].get("original_fallback") or extra["catalogue"].get("catalogue_handoff") != 1
            or result["reason"] != "rank_only_audit"):
        raise ValueError("The unchanged full-catalogue geographic proof or rank-only stop did not reproduce")
    write(output, dict(**extra, host=current, identity=identity, early=early, visited=visited,
                       fused_projector_sha256=GEOGRAPHIC_SHA, stop=result["reason"],
                       source_sha256={"proof_global_rank.py": REVIEWED_RANK_PIN, Path(__file__).name: digest(Path(__file__)),
                                      "proof-rank-short-transfer-protocol.md": digest(HERE / "proof-rank-short-transfer-protocol.md")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=(*CASES, "south-far-receipt"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--binary", type=Path, default=GEOGRAPHIC)
    args = parser.parse_args()
    if args.case == "south-far-receipt":
        host()
        write(args.output, saved_far())
    else:
        run(args.case, args.binary, args.output)
