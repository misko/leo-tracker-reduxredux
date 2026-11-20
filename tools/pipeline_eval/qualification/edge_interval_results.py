"""Score signed subscan intervals separately from full-position and RF endpoints."""

import gzip
from math import cos, radians

import numpy as np

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km
from . import edge_holdout_results as inherited
from . import edge_interval_trial as trial
from . import screening_figures
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin
from .transfer_budget_results import FIELDS, matches, sealed

STOCK = "v5_secant_transfer_stock"
FIELD = "v5_secant_transfer_interior"
POSITIONS = "figure-positions.jsonl.gz"


def face_truth(result, tile, truth):
    """Project the scoring reference on the exact normal used by the frozen worker."""
    arms = {
        arm: dict(latlon=r.get("latlon") or r.get("forced_latlon"))
        for arm, r in result["arms"].items()
    }
    if any(r["latlon"] is None for r in arms.values()):
        return None
    span = trial.old.edge_evidence.normal_hypotheses(dict(arms=arms), tile)
    if span is None:
        return None
    inside, face, outside = span
    lat, lon = tile["center"]
    target = np.asarray(((truth[1] - lon) * 111.32 * cos(radians(lat)), (truth[0] - lat) * 111))
    return float((target - face) @ (inside - outside) / np.linalg.norm(inside - outside))


def verified(output):
    sealed(output)
    raw, requests = (_read(output / r) for r in ("predictions.json", "requests.json"))
    observed = {(r["id"], r["mode"]): r for r in raw}
    expected = {(r["id"], r["mode"]): r for r in requests}
    if len(raw) != 10 or len(observed) != 10 or observed.keys() != expected.keys():
        raise ValueError("incomplete or substituted prospective roster")
    if any(not matches(row, expected[key]) for key, row in observed.items()):
        raise ValueError("scientific input differs from the sealed request")
    return observed


def geometry(output, observed):
    truth, public, receipts = (
        _read(output / r) for r in ("released-labels.json", "public-captures.json", "inputs.json")
    )
    if len(truth) != 2 or truth.keys() != public.keys():
        raise ValueError("expect two distinct fresh synthetic receiver locations")
    labels = {}
    for name, case in sorted(truth.items(), key=lambda t: -t[1]["location"][0]):
        for folder, doc in (("private", case), ("public", public[name])):
            digest = trial.prior.INPUTS.cold._sha(encoded(doc) + b"\n")
            if receipts[f"{folder}/{name}.json"] != digest:
                raise ValueError("prospective coordinate or input commitment changed")
        for ident, role in case["roles"].items():
            if (
                observed[ident, "interval"]["native_sha256"]
                != receipts[f"public/{name}.native.json"]
            ):
                raise ValueError("prospective native input differs from scored labels")
            labels[ident] = (case["location"], role, "synthetic")
    legacy = trial.old.legacy.compact
    _, [roof] = legacy.portable.references("ds26-common127", [legacy.portable.ROOF_CASE])
    labels[trial.MEASURED] = (roof["truth"], "shifted-roof", "measured")
    return labels


def score(output):
    observed = verified(output)
    labels = geometry(output, observed)
    scored, compact, queries = [], [], []
    for ident, (truth, role, scope) in labels.items():
        candidate = observed[ident, "interval"]
        result = candidate["result"]
        tile = candidate["tile"]
        baseline = dict(candidate, method=FIELD, result=trial.prior.edge.guard(result, tile))
        condition = inherited.NAMES.get(role, "Authentic roof · 22 km shifted tile")
        queries.append(
            dict(
                id=ident,
                scope=scope,
                truth=truth,
                condition=condition,
                recording=candidate["capture_id"],
                bindings={k: candidate[k] for k in FIELDS},
                stock_replay=(ident, "control") in observed,
            )
        )
        material = [candidate, baseline]
        if actual := observed.get((ident, "control")):
            if not matches(actual, candidate):
                raise ValueError("independent stock negative control differs from tested packet")
            material.append(actual)
        for row in material:
            compact.append(dict(row, scope=scope))
            fit = row["result"]
            interval = fit["metrics"].get("edge_evidence", {}) if row is candidate else {}
            signed_reference = face_truth(fit, tile, truth) if interval else None
            for arm in ARMS:
                part = fit.get("arms", {}).get(arm, {})
                point, forced = part.get("latlon"), part.get("forced_latlon")
                margin = roi_margin(truth, tile)
                scored.append(
                    dict(
                        id=ident,
                        scope=scope,
                        role=role,
                        latitude=truth[0],
                        method=row["method"],
                        arm=arm,
                        status=fit["status"],
                        reason=fit.get("reason"),
                        true_margin_km=margin,
                        position_error_km=distance_km(point, truth),
                        forced_error_km=distance_km(forced, truth),
                        compact_endpoint_margin_km=(
                            trial.prior.edge.margin(point or forced, tile)
                            if point or forced
                            else None
                        ),
                        chosen_rf_hz=part.get("rf_rms_hz"),
                        interval=interval.get("arms", {}).get(arm),
                        signed_reference_km=signed_reference,
                        interval_wall_s=interval.get("wall_s"),
                        interval_status=interval.get("status"),
                        worker_wall_s=row["wall_s"] if row["method"] != FIELD else None,
                        false_publication=point is not None and margin < 0,
                    )
                )
    save_json(output / "scores.json", scored)
    write(output / POSITIONS, gzip.compress(b"".join(encoded(r) + b"\n" for r in compact), mtime=0))
    return scored, queries


def figure_book(output, queries):
    proof = ("prediction-lock.json", "inputs.json", "source-lock.json")
    choices = (
        ("synthetic", "New simulated sites", [q for q in queries if q["scope"] == "synthetic"]),
        (
            "measured",
            "Authentic shifted roof offer",
            [q for q in queries if q["scope"] == "measured"],
        ),
        ("independent", "Independent stock far control", [q for q in queries if q["stock_replay"]]),
    )
    charts = []
    for name, title, subset in choices:
        query, seal = f"{name}-queries.json", f"{name}-figure-lock.json"
        list_queries = [
            {k: v for k, v in q.items() if k not in {"scope", "stock_replay"}} for q in subset
        ]
        save_json(output / query, dict(queries=list_queries))
        save_json(
            output / seal,
            dict(
                files={p: _sha(output / p) for p in (*proof, query, POSITIONS)},
                cases=[q["id"] for q in subset],
            ),
        )
        separate = name == "independent"
        where = {"id": subset[0]["id"]} if separate else {"scope": name}
        control = "Independent stock compact" if separate else "Frozen paired interior rule"
        charts.append(
            dict(
                id=f"compact-subscan-interval-{name}",
                method=trial.METHOD,
                scope="transfer",
                cases="sealed",
                title=f"Compact near-edge position interval · {title}",
                caption="Both arms use matched native inputs and causal orbital history. "
                "Forced estimates preserve a terminal full-fit endpoint when available.",
                seal=seal,
                queries=query,
                provenance=list(proof),
                series=[
                    dict(
                        key="candidate",
                        label="Subscan position interval",
                        file=POSITIONS,
                        value=trial.METHOD,
                        where=where,
                        forced_label="Subscan gate · forced endpoint",
                    ),
                    dict(
                        key="stock",
                        label=control,
                        file=POSITIONS,
                        where=where,
                        match=list(FIELDS),
                        value=STOCK if separate else FIELD,
                    ),
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(output / "figures", evidence=output)


def interval_plot(output, scored):
    from matplotlib import pyplot as plt

    fitted = [r for r in scored if r["method"] == trial.METHOD and r["interval"] is not None]
    named = {(r["id"], r["arm"]): r for r in fitted}
    cases = list(dict.fromkeys(r["id"] for r in fitted))
    if not cases:
        return
    fig, pads = plt.subplots(1, 2, figsize=(12, max(3.1, 1.7 + 0.55 * len(cases))), sharex=True)
    for arm, axis in zip(ARMS, pads, strict=True):
        axis.axvline(0, color="#516275", ls="--", lw=1.2)
        for j, ident in enumerate(cases):
            r = named[ident, arm]
            values = r["interval"]
            if interval := values.get("interval_km"):
                low, high = interval
                mean = values["mean_inward_km"]
                axis.errorbar(
                    mean, j, xerr=[[mean - low], [high - mean]], fmt="o", color="#11746a", capsize=4
                )
                axis.plot(values["subscan_inward_km"], [j] * 4, "|", color="#516275", alpha=0.6)
            if r["signed_reference_km"] is not None:
                axis.plot(
                    r["signed_reference_km"],
                    j - 0.14,
                    marker="D",
                    ms=5.5,
                    mfc="white",
                    mec="#aa5223",
                    linestyle="none",
                )
            axis.text(
                0.02,
                j + 0.18,
                values["state"].replace("_", " "),
                transform=axis.get_yaxis_transform(),
                fontsize=8,
            )
        axis.set_yticks(
            range(len(cases)),
            [
                f"{named[i, arm]['role'].replace('-', ' ')} at {named[i, arm]['latitude']:.1f}°"
                for i in cases
            ],
        )
        axis.set_ylim(-0.5, len(cases) - 0.45)
        axis.set(
            title="Zero calibration" if arm == "c0" else "Fitted calibration",
            xlabel="Signed distance from fitted tile face (km, positive inside)",
        )
        axis.grid(axis="x", alpha=0.2)
    fig.suptitle("Disjoint response-subset estimates around the original compact tile face")
    fig.text(
        0.5,
        0.013,
        "Ticks are four fitted subscans. Open diamonds show scoring references.",
        ha="center",
        color="#516275",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(output / "signed-subscan-intervals.png", dpi=170)
    fig.savefig(output / "signed-subscan-intervals.pdf")
    plt.close(fig)


if __name__ == "__main__":
    rows, queries = score(trial.REPORT)
    figure_book(trial.REPORT, queries)
    interval_plot(trial.REPORT, rows)
