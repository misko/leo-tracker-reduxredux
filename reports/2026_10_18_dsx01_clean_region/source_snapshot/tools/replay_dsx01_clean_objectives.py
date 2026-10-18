"""Reconstruct saved endpoints from strict inputs and verify final source replay."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from map_dsx01_clean_legacy import make_problem
from map_dsx01_clean_region import factory, loss, refresh_quality
from probe_dsx01_cut_linear import CutScore
from run_dsx01_clean_region import OUTPUT, load_scan, standard_problem


def run():
    rows = []
    for k in range(1, 6):
        case = f"DSX01-S0{k}"
        scan, sigma = load_scan(case)
        directory = OUTPUT / case
        atlas = json.loads((directory / "atlas.json").read_text())
        node = min(atlas["nodes"], key=lambda r: r["score"])
        scan.strict_causal_history = json.loads((directory / "causal_history.json").read_text())
        refresh_quality(
            scan,
            standard_problem(scan, node["seed"], sigma, aliases=node["aliases"]),
            node["point"],
        )
        for path in sorted((directory / "surfaces").glob("*/result.json")):
            data = json.loads(path.read_text())
            name = data["method"]
            for arm, row in data["arms"].items():
                if name.startswith("linear_"):
                    normal = json.loads((directory / "surfaces/normal/result.json").read_text())
                    selected = normal["selected_assignment_node"]
                    p = factory(
                        scan,
                        selected,
                        sigma,
                        "normal",
                        arm == "fitted_c",
                        reference=normal["arms"][arm]["phase_reference_s"],
                    )
                    nominations = json.loads(
                        (directory / "fresh_linear_nominations.json").read_text()
                    )
                    variant = name[7:]
                    strict = set(nominations["strict_components"])
                    choices = [
                        dict(
                            r,
                            accepted=r["accepted"]
                            and (not variant.startswith("white") or r["component"] in strict),
                        )
                        for r in nominations["nominations"]
                    ]
                    kind = (
                        "shape"
                        if variant.endswith("shape")
                        else ("joint" if variant.startswith("white") else variant)
                    )
                    score = CutScore(p, choices, kind).score(row["fit"]["parameters"])["total"]
                elif name.startswith("legacy_"):
                    selected = data["selected_assignment_node"]
                    p = make_problem(scan, selected["seed"], name[7:], arm, selected["point"])
                    p.alias = selected["aliases"]
                    score = loss(p, row["fit"]["parameters"])
                else:
                    selected = data["selected_assignment_node"]
                    p = factory(
                        scan,
                        selected,
                        sigma,
                        name,
                        arm == "fitted_c",
                        reference=row["phase_reference_s"],
                    )
                    score = loss(p, row["fit"]["parameters"])
                gap = abs(score - row["fit"]["score"])
                if gap > 1e-7:
                    raise ValueError(f"endpoint replay mismatch {case}/{name}/{arm}: {gap}")
                precision = {}
                if not name.startswith("legacy_"):
                    checked = p.calculate(np.array(row["fit"]["parameters"]))
                    precision = {
                        key: checked[key]
                        for key in ("precision_iterations", "final_log_precision_change")
                        if key in checked
                    }
                rows.append(
                    dict(case=case, method=name, arm=arm, score_difference=gap, **precision)
                )
    write(
        OUTPUT / "endpoint_replay.json",
        dict(rows=rows, maximum_score_difference=max(r["score_difference"] for r in rows)),
    )
    print(len(rows), "endpoints replayed", flush=True)


if __name__ == "__main__":
    run()
