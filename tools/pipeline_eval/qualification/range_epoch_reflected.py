"""Spatial sensitivity of the observed reflected sign after the primary seal."""

from pathlib import Path

from ..__main__ import save_json
from . import range_epoch_model as m
from . import range_epoch_trial as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .input_factor_bridge import check, read


def run():
    out = trial.OUT
    plan = out / "reflected-spatial-plan.json"
    result = out / "reflected-spatial.json"
    seals = {
        name: _sha(out / name) for name in ("measurement-lock.json", "native-origin-lock.json")
    }
    if plan.exists():
        raise ValueError("reflected sensitivity already executed")
    for source in seals:
        for name, digest in read(out / source)["files"].items():
            check(out / name, digest)
    cases = (*trial.DEVELOPMENT, *trial.RESERVE)
    sources = {module.__name__: _sha(Path(module.__file__)) for module in (trial, m)}
    save_json(
        plan,
        dict(
            cases=cases,
            seals=seals,
            source_sha256=_sha(Path(__file__)),
            inputs=sources,
            decision=(
                "Preserve the original nine candidates, chronologic folds, two clock models, "
                "and score scales. Exploratory sign sensitivity was triggered by the sealed "
                "true-site control. Test the reflected range term on all original candidates "
                "and check the RF sign at the surveyed reference. These are the same rows and "
                "same roof as the primary diagnostics."
            ),
        ),
    )
    _, references = held_references(None, cases)
    centers = {r["id"]: r["truth"] for r in references}
    rows = []
    for ident in cases:
        arcs, sats, origin, rate, proof = trial.load_case(ident)
        state = trial.predict_states(arcs, sats, origin)
        geometry = []
        for label, radius, site in trial.geometric_offers(centers[ident]):
            delay, f = trial.geometry(arcs, state, site, rate)
            cfo = m.held_loss(arcs, m.frequency_residual(arcs, f))["arc_median_mae"]
            if label == "reference":
                opposite = m.held_loss(arcs, m.frequency_residual(arcs, [-p for p in f]))
                cfo_sign = dict(
                    physical_arc_mae_hz=cfo, reversed_arc_mae_hz=opposite["arc_median_mae"]
                )
            neg = [-d for d in delay]
            shared = trial.score_epochs(arcs, neg, rate)
            independent = trial.score_epochs(arcs, neg, rate, per_arc=True)
            epoch_shared = shared["arc_median_mae"] / m.EPOCH_UNIT
            epoch_arc = independent["arc_median_mae"] / m.EPOCH_UNIT
            geometry.append(
                dict(
                    location=label,
                    offset_km=radius,
                    timing_shared=shared,
                    timing_per_arc=independent,
                    score=dict(
                        reflected=epoch_shared,
                        reflected_per_arc=epoch_arc,
                        joint=cfo / m.CFO_UNIT + epoch_shared,
                        joint_per_arc=cfo / m.CFO_UNIT + epoch_arc,
                    ),
                )
            )
        ranks = {
            name: [r["location"] for r in sorted(geometry, key=lambda r: r["score"][name])]
            for name in geometry[0]["score"]
        }
        rows.append(
            dict(
                id=ident,
                held_points=proof["held_points"],
                geometry=geometry,
                rankings=ranks,
                cfo_sign=cfo_sign,
            )
        )
    save_json(result, rows)
    save_json(
        out / "reflected-spatial-lock.json", dict(files={p.name: _sha(p) for p in (plan, result)})
    )


if __name__ == "__main__":
    run()
