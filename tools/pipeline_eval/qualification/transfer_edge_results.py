"""Score the sealed terminal guard on the paired second-site offers."""

import gzip
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km
from ..variants.compact_tile_interior import guard, margin
from . import screening_figures
from . import transfer_budget_results as common
from . import transfer_edge_trial as trial
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin

CONTROL = trial.base.METHODS["gate"]
CAPTION = (
    "One new simulated receiver, three paired tiles and authentic causal TLE history. "
    "Forced endpoints preserve the original fit when the candidate reaches a tile face."
)


def export(output: Path):
    common.sealed(output)
    locks = _read(output / "input-lock.json")
    truth = _read(output / "released-truth.json")
    prove = {
        "private/truth.json": encoded(truth) + b"\n",
        "private/seed.bin": bytes.fromhex(_read(output / "released-seed.json")["seed_hex"]),
        "public/cases.json": encoded(_read(output / "fresh-draw.json")) + b"\n",
    }
    if any(common.GEO._sha(raw) != locks[name] for name, raw in prove.items()):
        raise ValueError("released target material disagrees with the frozen input lock")
    records = _read(output / "predictions.json")
    modes = {
        method: {r["id"]: r for r in records if r["method"] == method}
        for method in (trial.METHOD, CONTROL)
    }
    candidates, controls = modes[trial.METHOD], modes[CONTROL]
    if (
        len(records) != 6
        or set(candidates) != set(controls)
        or set(candidates) != set(truth["roles"])
    ):
        raise ValueError("each withheld-side and containing offer requires two method results")
    if any(not common.matches(a, controls[ident]) for ident, a in candidates.items()):
        raise ValueError("the terminal guard changed input, history or tile")
    known = {r["id"]: r for r in _read(output / "requests.json")}
    if any(not common.matches(r, known[r["id"]]) for r in records):
        raise ValueError("the terminal guard replay changed its frozen request")
    target = truth["location"]
    rows, queries = [], []
    for ident, role in sorted(truth["roles"].items(), key=lambda item: trial.ROLES.index(item[1])):
        tile = candidates[ident]["tile"]
        queries.append(
            dict(
                id=ident,
                recording=candidates[ident]["capture_id"],
                truth=target,
                condition=(
                    "Near edge · site 1–2 km inside"
                    if role == "near-inside"
                    else common.LABELS[role]
                ),
                bindings={key: candidates[ident][key] for key in common.FIELDS},
            )
        )
        for method, indexed in modes.items():
            record = indexed[ident]
            result = record["result"]
            for arm in ARMS:
                part = result.get("arms", {}).get(arm, {})
                endpoint, forced = part.get("latlon"), part.get("forced_latlon")
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        role=role,
                        status=result["status"],
                        reason=result.get("reason"),
                        true_margin_km=roi_margin(target, tile),
                        solved_compact_margin_km=margin(endpoint or forced, tile)
                        if endpoint or forced
                        else None,
                        position_error_km=distance_km(endpoint, target),
                        forced_error_km=distance_km(forced, target),
                        rf_rms_hz=part.get("rf_rms_hz"),
                        wall_s=record["wall_s"],
                        false_publication=endpoint is not None and role == "near-outside",
                    )
                )
    earlier_root = trial.base.REPORT
    common.sealed(earlier_root)
    past_truth = _read(earlier_root / "released-truth.json")
    retrospective = []
    for r in _read(earlier_root / "predictions.json"):
        if r["cohort"] != "fresh" or r["method"] != CONTROL:
            continue
        decision = guard(r["result"], r["tile"])
        retrospective.append(
            dict(
                id=r["id"],
                role=past_truth["roles"][r["id"]],
                original_status=r["result"]["status"],
                counterfactual_status=decision["status"],
                exact_margin_km=decision["metrics"].get("exact_tile_margin_km"),
                reason=decision.get("reason"),
            )
        )
    save_json(output / "scores.json", dict(rows=rows, retrospective=retrospective))
    write(
        output / common.ARCHIVE,
        gzip.compress(b"".join(encoded(r) + b"\n" for r in records), mtime=0),
    )
    queries_name = "figure-queries.json"
    save_json(output / queries_name, dict(queries=queries))
    proof = ("source-lock.json", "prediction-lock.json", "input-lock.json", "released-truth.json")
    material = (*proof, queries_name, common.ARCHIVE)
    save_json(
        output / "figure-lock.json",
        dict(
            files={name: _sha(output / name) for name in material},
            cases=[q["id"] for q in queries],
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="compact-terminal-interior-guard",
                    method=trial.METHOD,
                    scope="transfer",
                    title="Compact terminal interior guard on an independent simulated site",
                    caption=CAPTION,
                    queries=queries_name,
                    seal="figure-lock.json",
                    cases="sealed",
                    provenance=list(proof),
                    series=[
                        dict(
                            key="candidate",
                            label="Terminal interior guard",
                            file=common.ARCHIVE,
                            value=trial.METHOD,
                            forced_label="Original endpoint at tile face",
                        ),
                        dict(
                            key="stock",
                            label="Recovery budget alone",
                            file=common.ARCHIVE,
                            value=CONTROL,
                            match=list(common.FIELDS),
                        ),
                    ],
                )
            ],
        ),
    )
    screening_figures.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    export(trial.REPORT)
