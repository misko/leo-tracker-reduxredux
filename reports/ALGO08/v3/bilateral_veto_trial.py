"""Price the fixed single-receiver terminal veto probe on two saved packets."""

import argparse
from hashlib import sha256
from pathlib import Path
from statistics import mean
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve, write
from dense_full_short_crossover import file_sha
from dense_geographic_trial import host
from cold_track_row_transfer import GEOGRAPHIC
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection
from incremental_layout_trial import FROZEN
from regional_track_scores import TrackScores
from regional_track_trial import assignment


ORDER = {"dense": ("stock", "one", "one", "stock"),
         "south-far": ("one", "stock", "stock", "one")}


def stage(kernel, tracks, reader, causal, region, library, arm):
    from bilateral_veto_disproof import RECEIVER, disprove
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    both, partial = [], []
    record = {}

    def evaluate(prepared, catalogue, offer):
        start = process_time()
        points, base, meta = kernel._prepare_probe_scores(prepared, catalogue, offer)
        record["shared_setup_cpu_s"] = process_time() - start
        decision = None
        if arm == "one":
            try:
                scorer = TrackScores(library, base, only_receiver=RECEIVER)
            except ValueError:
                record["subset_unavailable"] = True
            else:
                record["partial_tracks"] = len(scorer.tracks)

                def witness(point):
                    row = scorer(dict(point))
                    partial.append(row)
                    return row["receiver_scores"][str(RECEIVER)]

                decision = disprove(points, offer.width_km, witness)

        if decision is None:
            scorer = TrackScores(library, base)

            def score(point):
                row = scorer(dict(point))
                both.append(row)
                return row["receiver_scores"]

            decision = evaluate_terminal(points, offer.width_km, score)
            record["stock_native"] = scorer.native
            record["stock_fallbacks"] = scorer.fallbacks
        return dict(decision, **meta)

    with geographic_projection(GEOGRAPHIC) as projection, patch.object(kernel, "evaluate_veto", evaluate):
        cpu, wall = process_time(), perf_counter()
        result = regional_bound_guard.causal_probes(tracks, reader, region, catalogue=causal, terminal_only=True)
        duration, elapsed = process_time() - cpu, perf_counter() - wall
    record.update(arm=arm, cpu_s=duration, elapsed_s=elapsed, stock_points=len(both), partial_points=len(partial),
                  projection=dict(projection), result=result)
    return record, both, partial


def compare(case, kernel, tracks, reader, causal, region, library, control):
    from bilateral_veto_disproof import RECEIVER
    from leo.contracts.digests import canonical_digest

    runs = [stage(kernel, tracks, reader, causal, region, library, arm) for arm in ORDER[case]]
    stock, expected, _ = next(item for item in runs if item[0]["arm"] == "stock")
    lookup = {tuple(point["xy_km"]): point for point in expected}
    for row, both, partial in runs:
        result = row["result"]
        if row["projection"].get("original_fallback") or row.get("stock_fallbacks") or row.get("subset_unavailable"):
            raise ValueError("A tested score fell back to the Python likelihood or projection")
        if result["would_withhold"] != control["would_withhold"]:
            raise ValueError("Published regional decision failed to reproduce")
        if both and (result != stock["result"] or both != expected
                     or any(result.get(k) != control.get(k) for k in ("stop", "probes_evaluated", "complete"))):
            raise ValueError("Stock fallback changed the complete ordered rows or terminal result")
        for p in partial:
            original = lookup.get(tuple(p["xy_km"]))
            if original is not None and (p["receiver_scores"] != {str(RECEIVER): original["receiver_scores"][str(RECEIVER)]}
                    or any(v != original["owners"][k] for k, v in p["owners"].items())):
                raise ValueError("Single-receiver score or owner changed")
        if partial and not both and any(tuple(p["xy_km"]) not in lookup for p in partial):
            raise ValueError("A disproof used a point absent from the original decision")
        row.update(stock_rows_sha256=canonical_digest(both) if both else None,
                   single_receiver_rows_sha256=canonical_digest(partial) if partial else None)
    means = {arm: {name: mean(row[name] for row, _, _ in runs if row["arm"] == arm)
                   for name in ("cpu_s", "elapsed_s", "shared_setup_cpu_s")} for arm in ("stock", "one")}
    return dict(runs=[row for row, _, _ in runs], means=means, stock_decision=stock["result"],
                saved_cpu_s=means["stock"]["cpu_s"] - means["one"]["cpu_s"])


def run(case, library, output):
    machine = host()
    if file_sha(library) != TRACK_SCORES_SHA:
        raise ValueError("Expected the reviewed regional likelihood library")
    publication, specification = configuration()
    from dense_geographic_projection import checked_runtime
    from leo.contracts.digests import canonical_digest
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    archive, path, pin, offer, control = assignment(case)
    root = Path(archive["root"])
    if archive_identity(root) != archive or file_sha(path) != pin.removeprefix("sha256:"):
        raise ValueError("Saved causal archive or detector changed")
    original = read(path)
    if canonical_digest(original) != pin:
        raise ValueError("Saved detector canonical digest differs")
    kernel, _ = checked_runtime()
    normal = algo08_position.solve
    record = {}

    class ProofFinished(Exception):
        pass

    def intercept(native, reader, assets, region):
        if region.document() != offer:
            raise ValueError("Unexpected supplied region")
        with handoff(reader) as (live, _, _):
            def proof(prepared, view, *_args, **_kwargs):
                tracks = prepared["tracks"]
                causal = live.match(tracks, reader)
                if causal is None or list(view.center) != offer["center"] or view.width_km != offer["width_km"]:
                    raise ValueError("Missing original prepared catalogue or offer")
                record.update(compare(case, kernel, tracks, reader, causal, view, library, control))
                raise ProofFinished()

            with patch.object(v5_core, "infer", proof):
                return normal(native, reader, assets, region)

    with patch.object(algo08_position, "solve", intercept):
        try:
            solve(publication, specification, original, root, offer)
        except ProofFinished:
            pass
    if not record:
        raise ValueError("Regional scorer did not run")
    files = [Path(__file__), Path(__file__).with_name("regional_track_scores.py"),
             Path(__file__).with_name("bilateral_veto_disproof.py"), Path(kernel.__file__)]
    write(output, dict(case=case, machine=machine, graph="installed", archive=archive, offer=offer,
                       native_pin=pin, aperture_selection="unfiltered", specification="sha256:" + FROZEN,
                       library=TRACK_SCORES_SHA, geographic_library=GEOGRAPHIC_SHA,
                       driver={f.name: sha256(f.read_bytes()).hexdigest() for f in files}, **record))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=tuple(ORDER))
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    run(**vars(parser.parse_args()))
