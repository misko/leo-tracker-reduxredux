"""Score the sealed held-face evidence and its exact terminal and native controls."""

import gzip

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km
from . import edge_evidence_trial as trial
from . import edge_holdout_results as inherited
from . import screening_figures
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin
from .transfer_budget_results import FIELDS, matches, sealed

BASELINE = "v5_secant_transfer_interior"
STOCK = "v5_secant_transfer_stock"
ARCHIVE = "chart-positions.jsonl.gz"


def frozen_terminal(row):
    """Build the exact original decision on the same scientific endpoint."""
    return dict(row, method=BASELINE, result=trial.prior.edge.guard(row["result"], row["tile"]))


def roof_parity(output, measured):
    old = trial.legacy.REPORT
    sealed(old)
    original = next(
        r for r in _read(old / "predictions.json") if r["id"] == trial.legacy.compact.ROOF
    )
    if not matches(measured, original):
        raise ValueError("the authentic shifted comparison changed numerical inputs")
    checks = {
        arm: dict(
            endpoint_equal=measured["result"].get("arms", {}).get(arm)
            == original["result"].get("arms", {}).get(arm)
        )
        for arm in ARMS
    }
    save_json(
        output / "measured-parity.json",
        dict(
            control_lock_sha256=_sha(old / "prediction-lock.json"),
            status=measured["result"]["status"],
            control_status=original["result"]["status"],
            arms=checks,
        ),
    )
    return dict(original, method=BASELINE)


def score(output):
    sealed(output)
    raw = _read(output / "predictions.json")
    planned = {(row["id"], row["mode"]): row for row in _read(output / "requests.json")}
    observed = {(row["id"], row["mode"]): row for row in raw}
    if (
        len(raw) != 10
        or observed.keys() != planned.keys()
        or any(not matches(r, planned[key]) for key, r in observed.items())
    ):
        raise ValueError("held face evidence must use all locked offers")
    measured = observed[trial.legacy.compact.ROOF, "edge"]
    roof_control = roof_parity(output, measured)
    _, [reference] = trial.legacy.compact.portable.references(
        "ds26-common127", [trial.legacy.compact.portable.ROOF_CASE]
    )
    truth, public, receipts = (
        _read(output / name)
        for name in ("released-labels.json", "public-captures.json", "input-lock.json")
    )
    if len(truth) != 2 or truth.keys() != public.keys():
        raise ValueError("expected two fresh blinded sites")
    reference_by_case = {}
    for capture, scene in truth.items():
        for folder, material in (("private", scene), ("public", public[capture])):
            if receipts[f"{folder}/{capture}.json"] != trial.prior.INPUTS.cold._sha(
                encoded(material) + b"\n"
            ):
                raise ValueError(
                    "a public or private input differs from its prospective commitment"
                )
        for ident, role in scene["roles"].items():
            if (
                observed[ident, "edge"]["native_sha256"]
                != receipts[f"public/{capture}.native.json"]
            ):
                raise ValueError("native input changed")
            reference_by_case[ident] = (scene["location"], role, "fresh")
    reference_by_case[measured["id"]] = (reference["truth"], "authentic", "roof")

    rows, normalized, queries = [], [], []
    for ident, (site, role, study) in reference_by_case.items():
        candidate = observed[ident, "edge"]
        tile = candidate["tile"]
        old = roof_control if study == "roof" else frozen_terminal(candidate)
        pairs = [candidate, old]
        if (ident, "control") in observed:
            stock = observed[ident, "control"]
            if not matches(stock, candidate):
                raise ValueError("independent stock run on a different request")
            pairs.append(stock)
        queries.append(
            dict(
                id=ident,
                recording=candidate["capture_id"],
                truth=site,
                condition=inherited.NAMES.get(role, "Measured roof · shifted offer"),
                bindings={key: candidate[key] for key in FIELDS},
                study=study,
            )
        )
        for prediction in pairs:
            normalized.append(dict(prediction, study=study))
            result = prediction["result"]
            detail = result["metrics"].get("edge_evidence", {}) if prediction is candidate else {}
            for arm in ARMS:
                fit = result.get("arms", {}).get(arm, {})
                point, forced = fit.get("latlon"), fit.get("forced_latlon")
                tested = detail.get("arms", {}).get(arm, {})
                rows.append(
                    dict(
                        id=ident,
                        capture_id=candidate["capture_id"],
                        study=study,
                        arm=arm,
                        method=prediction["method"],
                        status=result["status"],
                        reason=result.get("reason"),
                        role=role,
                        true_margin_km=roi_margin(site, tile),
                        position_error_km=distance_km(point, site),
                        forced_error_km=distance_km(forced, site),
                        conditional_rf_rms_hz=fit.get("rf_rms_hz"),
                        validation=tested,
                        evidence_status=detail.get("status"),
                        evidence_wall_s=detail.get("wall_s"),
                        replay_wall_s=prediction["wall_s"]
                        if prediction["method"] != BASELINE
                        else None,
                        false_publication=point is not None and role.endswith("outside"),
                    )
                )
    write(
        output / ARCHIVE, gzip.compress(b"".join(encoded(r) + b"\n" for r in normalized), mtime=0)
    )
    save_json(output / "scores.json", rows)
    return queries


def figures(output, queries):
    specs = []
    provenance = ("prediction-lock.json", "input-lock.json", "source-lock.json")
    for name, title in (
        ("fresh", "Held Doppler evidence near a compact tile face at two simulated sites"),
        ("roof", "Held-face wrapper parity on a shifted measured roof tile"),
    ):
        roster = [
            {k: v for k, v in q.items() if k != "study"} for q in queries if q["study"] == name
        ]
        stem = f"compact-held-face-{name}"
        query, seal = f"{stem}-queries.json", f"{stem}-lock.json"
        save_json(output / query, dict(queries=roster))
        save_json(
            output / seal,
            dict(
                cases=[q["id"] for q in roster],
                files={f: _sha(output / f) for f in (*provenance, ARCHIVE, query)},
            ),
        )
        specs.append(
            dict(
                id=stem,
                method=trial.METHOD,
                scope="transfer",
                cases="sealed",
                title=title,
                caption="Both methods use the same full fit. In a face contact, matched inside and "
                "outside continuations are evaluated on the same withheld orbit blocks.",
                seal=seal,
                queries=query,
                provenance=list(provenance),
                series=[
                    dict(
                        key="candidate",
                        label="Conditional held-face evidence",
                        file=ARCHIVE,
                        value=trial.METHOD,
                        where=dict(study=name),
                        forced_label="Weak · forced endpoint",
                    ),
                    dict(
                        key="stock",
                        label="Frozen terminal interior rule",
                        file=ARCHIVE,
                        value=BASELINE,
                        where=dict(study=name),
                        match=list(FIELDS),
                        forced_label="Original face rejection · forced",
                    ),
                ],
            )
        )
    [stock_offer] = [r["id"] for r in _read(output / "requests.json") if r["mode"] == "control"]
    special = next(q for q in queries if q["id"] == stock_offer)
    query, seal = "far-stock-queries.json", "far-stock-lock.json"
    save_json(output / query, dict(queries=[{k: v for k, v in special.items() if k != "study"}]))
    save_json(
        output / seal,
        dict(
            cases=[stock_offer], files={f: _sha(output / f) for f in (*provenance, ARCHIVE, query)}
        ),
    )
    specs.append(
        dict(
            id="compact-held-face-far-stock",
            method=trial.METHOD,
            scope="transfer",
            cases="sealed",
            title="Independent stock compact replay on the fresh far omission",
            caption="Both workers used identical native factors, causal history and tile.",
            seal=seal,
            queries=query,
            provenance=list(provenance),
            series=[
                dict(
                    key="candidate",
                    label="Staged compact receiver",
                    file=ARCHIVE,
                    value=trial.METHOD,
                    where={"id": stock_offer},
                ),
                dict(
                    key="stock",
                    label="Independent stock compact",
                    file=ARCHIVE,
                    value=STOCK,
                    where={"id": stock_offer},
                    match=list(FIELDS),
                ),
            ],
        )
    )
    save_json(output / "figures.json", dict(version=1, charts=specs))
    screening_figures.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    figures(trial.REPORT, score(trial.REPORT))
