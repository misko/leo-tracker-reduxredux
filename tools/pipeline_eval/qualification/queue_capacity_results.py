"""Score the locked selected-packet fits and render the queue-load sensitivity."""

import argparse
import csv
from math import isclose
from pathlib import Path

from .. import figure_books, whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import queue_capacity as study
from .arrival_clock import simulate as historical_queue
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

SCORES = "position-scores.csv"
HISTORICAL = "capture-era-v5.csv"
IMAGES = ("queue-capacity.png", "queue-capacity.pdf")
PARITY = "one-x-audit.json"
LABELS = {"stock": "Stock", "fifth": "Fifth center", "adaptive": "Adaptive"}
COLOR = {"stock": "#195883", "fifth": "#bd4e29", "adaptive": "#087a65"}


def checked_positions(report):
    lock = whole_iq.read(report / study.PREDICTIONS)
    if lock["cases"] != list(study.CPUS):
        raise ValueError("the position seal does not contain the complete two-case study")
    for file, digest in lock["files"].items():
        if Path(file).name != file:
            raise ValueError("the position seal cannot name files outside the report")
        whole_iq.checked(report / file, digest)
    plan = whole_iq.read(report / study.PLAN)
    rows = list(rows_from(report / study.POSITIONS))
    keys = [f"{r['id']}/{r['policy']}" for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != plan["trials"].keys():
        raise ValueError("the numerical study must retain all six policies/recordings once")
    for key, row in zip(keys, rows, strict=True):
        if any(row.get(k) != value for k, value in plan["trials"][key].items()):
            raise ValueError("the sealed fit does not bind the original modeled selection")
        validate_result(row["result"])
    return rows


def model_rows(report):
    with (report / study.MODEL).open() as fp:
        rows = list(csv.DictReader(fp))
    identities = {(r["id"], r["mode"], float(r["cpu_scale"])) for r in rows}
    expected = {
        (ident, mode, scale / 4)
        for ident in study.CPUS
        for mode in study.POLICIES
        for scale in study.SCALES
    }
    if len(rows) != len(expected) or identities != expected:
        raise ValueError("queue model omitted a reserved scale, policy or recording")
    return rows


def replay_legacy_audit(report):
    previous, dropped, historical_sha = study.history()
    prior = whole_iq.read(study.original.QUEUE / "source-lock.json")
    rows = []
    for ident in study.CPUS:
        refs = {}
        for mode, alias in study.original.ARCHIVE.items():
            source = prior["cases"][ident]["modes"][alias]
            refs[mode] = study.arrival_queue.readgz(study.original.QUEUE / source["events"])
        study.validate_events(refs)
        for mode, alias in study.original.ARCHIVE.items():
            key = ident, alias
            trace = study.replay(refs, mode, 4)
            row = study.summarize(ident, mode, 4, refs, trace)
            old = previous[key]
            old_drops = dropped.get(key, [])
            study.one_x(old, old_drops, row, trace)
            full = [
                (
                    r["visit"],
                    r["arrival_ns"],
                    "detector" if r["status"] == "processed" else r["status"],
                    r["detector_cpu_ns"],
                    r["detector_wall_ns"],
                )
                for r in refs[mode]
            ]
            minimum = historical_queue(full, 1)["max_waiting"]
            wall = sum(r[-1] for r in full) / 1e9
            if minimum != int(old["minimum_lossless_waiting"]) or not isclose(
                wall, float(old["offered_wall_s"]), rel_tol=1e-12
            ):
                raise ValueError("archived wall total or unbounded queue metadata differs")
            rows.append(
                dict(
                    exact_cpu_queue_parity=True,
                    id=ident,
                    policy=mode,
                    recorded_legacy_row=old,
                    dropped_visit_ids=[r["visit"] for r in old_drops],
                )
            )
    save_json(report / PARITY, dict(historical_stage_sha256=historical_sha, matches=rows))


def scores(records, reference):
    rows, history = [], []
    for row in records:
        result, counts, resources = row["result"], row["counts"], row["resources"]
        ref = reference[row["id"]]
        for arm in ARMS:
            estimate = result["arms"][arm]
            error = distance_km(estimate["latlon"], ref["truth"])
            baseline = ref["reference"]["baseline"][arm]["error_km"]
            rows.append(
                dict(
                    id=row["id"],
                    policy=row["policy"],
                    arm=arm,
                    scale=row["model_scale"],
                    status=result["status"],
                    reason=result.get("reason"),
                    scheduled=counts["recorded"],
                    invalid=counts["invalid_capture"],
                    admitted=counts["emitted"],
                    dropped=counts["queue_drop"],
                    fifth_calls=counts["fifth"],
                    stock_calls=counts["stock"],
                    error_km=error,
                    within_10pct_original_v5=(
                        None if baseline is None else error is not None and error <= 1.10 * baseline
                    ),
                    conditional_rf_rms_hz=estimate.get("rf_rms_hz"),
                    conditional_frequency_score=result["metrics"].get(arm + "_frequency_score"),
                    prepared_count=result["metrics"].get("observations"),
                    prepared_tracks=result["metrics"].get("tracks"),
                    fit_origin="exact archived native match" if row["reuse"] else "fresh",
                    timing_scope=resources["timing_scope"],
                    measured_fit_cpu_s=resources.get("cpu_s"),
                    measured_fit_wall_s=resources.get("wall_s"),
                    fresh_fit_cgroup_peak_bytes=resources.get("peak_bytes"),
                    **{f"{name}_km": ref["reference"][name][arm]["error_km"] for name in ROLES},
                )
            )
    for ident, ref in reference.items():
        for arm in ARMS:
            for mode in ROLES:
                r = ref["reference"][mode][arm]
                history.append(
                    dict(
                        id=ident,
                        arm=arm,
                        option=mode,
                        status=r["status"],
                        error_km=r["error_km"],
                        archived_rf_rms_hz=r.get("rf_rms_hz"),
                        archived_wall_s=r.get("wall_s"),
                    )
                )
    return rows, history


def plot(out, rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(13.4, 6.8), layout="constrained")
    metrics = (
        ("dropped", "Dropped visits", "Count"),
        ("age_p95_ms", "P95 age of completed visits", "Milliseconds"),
        ("fifth_calls", "Fifth-center work", "% of admitted visits"),
    )
    for ident, row in zip(study.CPUS, axes, strict=True):
        for ax, (metric, title, label) in zip(row, metrics, strict=True):
            for mode in study.POLICIES:
                points = sorted(
                    (
                        float(r["cpu_scale"]),
                        float(r[metric])
                        / (max(1, int(r["completed"])) / 100 if metric == "fifth_calls" else 1),
                    )
                    for r in rows
                    if r["id"] == ident and r["mode"] == mode
                )
                x, y = zip(*points, strict=True)
                ax.plot(x, y, marker="o", markersize=4, color=COLOR[mode], label=LABELS[mode])
            ax.axvline(study.FOCUS / 4, ls="--", color="0.47", lw=1)
            ax.set(
                title=f"{ident} · {title}", xlabel="Common CPU duration multiplier", ylabel=label
            )
    axes[0, 0].legend(loc="upper left", frameon=False, fontsize=9)
    fig.suptitle("One detector worker, one waiting slot, identical recorded arrivals")
    fig.savefig(out / IMAGES[0], dpi=160)
    fig.savefig(out / IMAGES[1], metadata={"CreationDate": None})
    plt.close(fig)


def finalize(out):
    stage = "stage-figure.json"
    score_lock = "score-lock.json"
    provenance = [study.PREDICTIONS, study.MODEL, SCORES, HISTORICAL, PARITY]
    save_json(
        out / stage,
        dict(
            version=1,
            id="queue-capacity-load",
            title="Detector policy sensitivity under identical arrivals",
            sample="13,546 physical visits across two recordings, seven common CPU scales",
            boundary="Recorded arrivals and measured native-call CPU → counterfactual finite queue",
            note=(
                "The vertical marker is the frozen 2.25× packet selection for the separately "
                "measured compact fits. The model excludes OS scheduling and decoder overhead."
            ),
            seal=score_lock,
            image=IMAGES[0],
            pdf=IMAGES[1],
            csv=study.MODEL,
        ),
    )
    members = (stage, *IMAGES, study.PLAN, study.POSITIONS, *provenance)
    save_json(
        out / score_lock,
        dict(cases=list(study.CPUS), files={name: _sha(out / name) for name in members}),
    )
    keys = {"adaptive": "one", "stock": "stock", "fifth": "one_native_factors"}
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="queue-capacity-position",
                    method=study.METHOD["adaptive"],
                    scope="roof",
                    cases="sealed",
                    title="Compact fixes after a 2.25× queue load",
                    caption=(
                        "One worker and one waiting slot at the same modeled load. Selected native "
                        "packets feed compact phase-release. Original v5 uses capture-era factors. "
                        "Both calibration arms are measured."
                    ),
                    seal=score_lock,
                    provenance=provenance,
                    series=[
                        dict(
                            key=keys[mode],
                            file=study.POSITIONS,
                            value=study.METHOD[mode],
                            label=LABELS[mode],
                            native_field="paired_capture_sha256",
                            match=[
                                "tile",
                                "catalog_sha256",
                                "original_request_sha256",
                                "model_scale",
                            ],
                        )
                        for mode in ("adaptive", "stock", "fifth")
                    ],
                )
            ],
        ),
    )
    figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out)


def run(out):
    report = study.REPORT
    positions = checked_positions(report)
    queue = model_rows(report)
    _, cases = held_references(None, study.CPUS)
    rows, history = scores(positions, {r["id"]: r for r in cases})
    out.mkdir(exist_ok=True, parents=True)
    csv_file(out / SCORES, rows)
    csv_file(out / HISTORICAL, history)
    plot(out, queue)
    if out == report:
        replay_legacy_audit(out)
        finalize(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=local_output)
    run(parser.parse_args().out)
