"""Test a genuinely reduced cold rank from the paid geographic owner union."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from math import isfinite
from pathlib import Path

from proof_cold_reuse import clocks, now, run


RANK_PIN = "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407"
WRAPPER_PIN = "2a6fb84d59d1fba485d270b38a2a0553b59c1977373520dcce0e3488c6859690"
MINIMUM_ROSTER = 8
SCORE_TOLERANCE = 1e-8


def select_pool(probes, labels):
    owner_union = {owner for probe in probes for owner in probe["owners"].values() if owner is not None}
    indices = [index for index, label in enumerate(labels) if label in owner_union]
    return indices if MINIMUM_ROSTER <= len(indices) < len(labels) else None


def rank_port(original):
    # Keep the original stable sort, uniqueness, fits and their arithmetic, while exposing its computed score.
    if sha256(Path(original.__code__.co_filename).read_bytes()).hexdigest() != RANK_PIN:
        raise ValueError("The released cold-rank source changed")
    source = getsource(original)
    line = '    return [node for _, node in sorted(ranked, key=lambda entry: entry[0])]'
    if source.count(line) != 1:
        raise ValueError("The released rank readout changed")
    env = dict(original.__globals__)
    exec(compile(source.replace(line, '    return sorted(ranked, key=lambda entry: entry[0])'),
                 original.__code__.co_filename, "exec"), env)
    return env[original.__name__]


@contextmanager
def ranked_scores(wrapper):
    # Keep both installed shared-discovery and sparse-rank contexts around the base rank.
    if (wrapper.__qualname__ != "run.<locals>.shared_rank"
            or sha256(Path(wrapper.__code__.co_filename).read_bytes()).hexdigest() != WRAPPER_PIN):
        raise ValueError("Expected the pinned installed shared-rank wrapper")
    cells = dict(zip(wrapper.__code__.co_freevars, wrapper.__closure__, strict=True))
    port = cells["rank"]
    original = port.cell_contents
    port.cell_contents = rank_port(original)
    try:
        yield wrapper
    finally:
        port.cell_contents = original


def reduced_input(prepared, indices):
    import numpy as np

    sky = prepared["sky"]
    bank = {key: (value if key == "time_s" else np.asarray(value)[indices]) for key, value in sky["bank"].items()}
    return dict(prepared, sky=dict(sky, bank=bank))


def fallback_reason(ranked):
    if len(ranked) < 3 or not all(isfinite(row[0]) for row in ranked[:3]):
        return "insufficient_finite_finalists"
    for left, right in zip(ranked[:3], ranked[1:], strict=False):
        if left[0] == right[0]:
            return "rank_tie"
    return None


def compare_top_three(original, proposed):
    left, right = original[:3], proposed[:3]
    same = len(left) == len(right) == 3 and all(
        row["owners"] == other["owners"] for row, other in zip(left, right, strict=True)
    )
    gaps = [other["score"]-row["score"] for row, other in zip(left, right, strict=False)]
    return dict(ordered_assignments=same, score_delta=gaps,
                within_score_tolerance=len(gaps) == 3 and all(abs(x) <= SCORE_TOLERANCE for x in gaps))


def rank_pair(prepared, region, bound, probes, sealed, share_rank):
    from blind_joint_finish import digest
    from cold_finalist_race import audit_overlap
    from leo.analysis.localization_v3.discovery import signature
    from tools.pipeline_eval.variants import v5_core

    labels = list(map(int, prepared["sky"]["bank"]["norad"]))
    start = now()
    slate = select_pool(probes, labels)
    slate_cost = clocks(start)
    paid = sealed["regional"][0]["cpu_s"]
    timings, ranked = {}, {}
    start = now()
    stable_noise = digest(prepared["noise"])
    full_scan = v5_core.scan_context(prepared, region, stable_noise, bound, "previous")
    full_setup = clocks(start)

    def evaluate(scan, setup, name):
        start = now()
        with share_rank(scan) as shared, ranked_scores(v5_core.ranked_initial_nodes) as rank:
            ranked[name] = rank(scan)
        timings[name] = dict(scan_setup=setup, rank=clocks(start), shared=shared)

    evaluate(full_scan, full_setup, "original")
    if audit_overlap([node for _, node in ranked["original"][:3]]) != sealed["attempts"][0]["cold"]["overlap"]:
        raise ValueError("The recovered ordinary rank no longer matches the sealed finalist structure")
    fallback = "unusable_proof_pool"
    if slate is not None:
        start = now()
        reduced = v5_core.scan_context(reduced_input(prepared, slate), region, stable_noise, bound, "previous")
        setup = clocks(start)
        try:
            evaluate(reduced, setup, "reduced")
        except (ValueError, ArithmeticError):
            fallback = "invalid_reduced_evidence"
        else:
            fallback = fallback_reason(ranked["reduced"])
    formatted = {name: [dict(score=score, owners=[(key, norad, alias) for key, _, norad, alias in signature(node)])
                        for score, node in rows] for name, rows in ranked.items()}
    pair = compare_top_three(formatted["original"], formatted.get("reduced", []))
    costs = {name: sum(clocks["cpu_s"] for key, clocks in values.items() if key != "shared")
             + (slate_cost["cpu_s"] if name == "reduced" else 0.) for name, values in timings.items()}
    gate = (fallback is None and all(pair[key] for key in ("ordered_assignments", "within_score_tolerance"))
            and costs["original"]-costs["reduced"] >= 1.)
    return dict(global_rank=dict(
        pool=[labels[j] for j in slate or []], full_orbits=len(labels), input_proof_cpu_s=paid,
        selector=slate_cost, clocks=timings, elapsed_boundary="saved scan and cold rank without finalist fitting",
        cpu_s_including_paid_proof={key: value+paid for key, value in costs.items()},
        ranks=formatted, original_fallback_reason=fallback, pair=pair, warrants_complete_replay=gate,
    ))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output, additional_rank=rank_pair)
