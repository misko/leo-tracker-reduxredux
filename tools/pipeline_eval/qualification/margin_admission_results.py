"""Score a sealed global margin gate and its unmodified wide comparator."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds
from ..variants import margin_admission
from . import margin_admission_inputs as inputs
from .fractional_runtime_whole import verify_request
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_trial import MODES
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file

OUT = inputs.REPORT
STOCK = margin_admission.STOCK


def sealed(directory, lock, name):
    files = inputs.read(directory / lock)["files"]
    for file, digest in files.items():
        if _sha(directory / file) != digest:
            raise ValueError(f"{file} differs from its prediction seal")
    if name not in files:
        raise ValueError(f"{name} requires a prediction seal")
    return [
        json.loads(line) for line in gzip.decompress((directory / name).read_bytes()).splitlines()
    ]


def confusion(probes, threshold):
    true_positive = sum(score >= threshold and teacher for _, score, teacher in probes)
    positives = sum(score >= threshold for _, score, _ in probes)
    targets = sum(teacher for _, _, teacher in probes)
    false_positive = positives - true_positive
    false_negative = targets - true_positive
    return dict(
        probes=len(probes),
        wide_positive=positives,
        teacher_positive=targets,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=len(probes) - targets - false_positive,
        teacher_recall=true_positive / targets if targets else None,
        teacher_negative_admission=(
            false_positive / (len(probes) - targets) if len(probes) > targets else None
        ),
        teacher_precision=true_positive / positives if positives else None,
    )


def agreement(locked):
    cutoffs = (STOCK, 0.035, 0.045, 0.060, 0.080, 0.100, locked)
    output = []
    for ident in inputs.HELD:
        _, doc, binding = inputs.load(ident)
        group = inputs.population(ident, doc, binding)
        first, last = min(row[0] for row in group), max(row[0] for row in group)
        bands = [[], [], [], []]
        for row in group:
            bands[min(3, 4 * (row[0] - first) // max(1, last - first))].append(row)
        for band, probes in zip(("all", "Q1", "Q2", "Q3", "Q4"), [group, *bands], strict=True):
            for i, cutoff in enumerate(cutoffs):
                output.append(
                    dict(
                        id=ident,
                        capture_quartile=band,
                        operating_point="scalar" if i == len(cutoffs) - 1 else f"{cutoff:g}",
                        threshold=cutoff,
                        **confusion(probes, cutoff),
                    )
                )
    return output


def agreement_figure(rows):
    import matplotlib.pyplot as plt

    fig, (operating, time) = plt.subplots(1, 2, figsize=(11, 4.2), layout="constrained")
    for ident in inputs.HELD:
        values = [r for r in rows if r["id"] == ident and r["capture_quartile"] == "all"]
        color = operating.plot(
            [100 * r["teacher_negative_admission"] for r in values],
            [100 * r["teacher_recall"] for r in values],
            marker=".",
            label=ident,
        )[0].get_color()
        selected = values[-1]
        operating.scatter(
            100 * selected["teacher_negative_admission"],
            100 * selected["teacher_recall"],
            marker="D",
            s=30,
            color=color,
        )
        recent = [r for r in rows if r["id"] == ident and r["capture_quartile"] != "all"]
        losses = [
            100 * (stock["teacher_recall"] - scalar["teacher_recall"])
            for stock, scalar in zip(
                recent[:: len(values)], recent[len(values) - 1 :: len(values)], strict=True
            )
        ]
        time.plot(range(1, 5), losses, marker="D", color=color)
    operating.set(
        title="Held teacher agreement",
        xlabel="Admission among capture-era negatives (%)",
        ylabel="Recall of capture-era positives (%)",
    )
    time.set(
        title="Recall cost at the calibrated cutoff",
        xlabel="Elapsed capture quarter",
        ylabel="Teacher recall lost (percentage points)",
        xticks=range(1, 5),
    )
    operating.legend(title="Diamond = calibrated cutoff")
    for axes in (operating, time):
        axes.grid(alpha=0.2)
    fig.savefig(OUT / "teacher-agreement.png", dpi=160)
    plt.close(fig)


def fit(value, case, arm):
    result = value["result"]
    row = result.get("arms", {}).get(arm, {})
    point = row.get("latlon")
    forced = row.get("forced_latlon")
    return dict(
        id=value["id"],
        method=value["method"],
        arm=arm,
        status=result["status"],
        reason=result.get("reason"),
        published=point is not None,
        latitude=point[0] if point is not None else None,
        longitude=point[1] if point is not None else None,
        error_km=distance_km(point, case["truth"]),
        forced_error_km=distance_km(forced, case["truth"]),
        conditional_rf_rms_hz=row.get("rf_rms_hz"),
        observations=result["metrics"].get("observations"),
        tracks=result["metrics"].get("tracks"),
    )


def summaries(scores):
    result = {}
    for method in sorted({r["method"] for r in scores}):
        result[method] = {}
        for arm in ARMS:
            rows = [r for r in scores if (r["method"], r["arm"]) == (method, arm)]
            errors = [r["error_km"] for r in rows]
            result[method][arm] = dict(
                scheduled=len(rows),
                status=dict(Counter(r["status"] for r in rows)),
                published=sum(r["published"] for r in rows),
                error_km=distribution(errors),
                within_km=thresholds(errors),
                conditional_rf_rms_hz=distribution([r["conditional_rf_rms_hz"] for r in rows]),
            )
    return result


def figures(rows):
    def series(mode, key, label):
        return dict(
            file="positions.jsonl.gz",
            key=key,
            label=label,
            native_field="paired_capture_sha256",
            value=MODES[mode],
            match=["tile", "catalog_sha256", "original_request_sha256", "wide_native_sha256"],
        )

    base = dict(
        scope="roof",
        cases="sealed",
        provenance=["prediction-lock.json", "scores.csv", "resources.csv"],
    )
    studies = [
        dict(
            base,
            caption=(
                "One margin calibrated to the capture-era detector's positive-probe prevalence. "
                "Identical stored wide GLRT, causal orbital history, region and solver. "
                "All four scheduled recordings remain in the denominator."
            ),
            id="wide-margin-admission",
            method=MODES["scalar"],
            seal="figure-lock.json",
            series=[
                series("scalar", "one", "Calibrated global margin"),
                series("original", "stock", "Original 0.025 margin"),
            ],
            title="Global fractional-margin admission on four held recordings",
        ),
    ]
    if any(r["method"] == MODES["thin"] for r in rows):
        restricted = dict(
            series("original", "stock", "Original 0.025 margin"), where={"id": "DS29-0127"}
        )
        studies.append(
            dict(
                base,
                caption=(
                    "DS29-0127. Hash selection and scalar admission pass the same count of "
                    "original wide candidates. The full original margin also appears."
                ),
                id="wide-margin-allocation-control",
                method=MODES["thin"],
                seal="thinning-figure-lock.json",
                series=[
                    series("thin", "one", "Hash-selected candidates"),
                    restricted,
                    dict(
                        series("scalar", "one_native_factors", "Calibrated global margin"),
                        where={"id": "DS29-0127"},
                    ),
                ],
                title="Candidate allocation at matched count on DS29-0127",
            )
        )
    files = {p: _sha(OUT / p) for p in ("positions.jsonl.gz", *base["provenance"])}
    save_json(OUT / "figure-lock.json", dict(cases=list(inputs.HELD), files=files))
    if len(studies) > 1:
        save_json(OUT / "thinning-figure-lock.json", dict(cases=["DS29-0127"], files=files))
    save_json(OUT / "figures.json", dict(version=1, charts=studies))


def resources(predictions):
    result = []
    for r in predictions:
        usage = r.get("position_resources") or {}
        terminal = usage.get("end", {})
        result.append(
            dict(
                id=r["id"],
                method=r["method"],
                status=r["result"]["status"],
                cpu=r["cpu"],
                cpu_s=usage.get("cpu_s"),
                worker_wall_s=usage.get("wall_s"),
                supervisor_wall_s=r["supervisor_wall_s"],
                peak_bytes=usage.get("peak_bytes"),
                oom_events=terminal.get("memory.events.oom"),
                oom_kills=terminal.get("memory.events.oom_kill"),
                swap_bytes=terminal.get("memory.swap.current"),
                positive_probes=r["after"]["positive_probes"],
                positive_candidates=r["after"]["positive_candidates"],
                wide_positive_candidates=r["before"]["positive_candidates"],
                evaluated_native_sha256=r["evaluated_native_sha256"],
            )
        )
    return result


def verify_native(rows, work, cutoff):
    receipts = {}
    for r in rows:
        ident, mode = r["id"], r["position_mode"]
        folder = work / mode / ident / "recording"
        _, parent = whole_iq.binding(ident)
        native, request = folder / "native.json", folder / "request.json"
        verify_request(inputs.read(request), parent, native_path=native, native_sha256=_sha(native))
        if _sha(native) != r["native_sha256"].removeprefix("sha256:"):
            raise ValueError("position input does not match the prediction lock")
        _, doc, authority = inputs.load(ident)
        if authority["wide_native_sha256"] != r["wide_native_sha256"]:
            raise ValueError("source factors differ from the held export")
        probes = doc["source"]["probes"]
        if mode == "original":
            if _sha(native) != r["wide_native_sha256"]:
                raise ValueError("unmodified input must equal the exact archived bytes")
        else:
            if mode == "scalar":
                margin_admission.bind(probes, cutoff)
            else:
                margin_admission.thin(
                    probes, r["after"]["positive_candidates"], doc["source"]["session_id"]
                )
            adjusted = inputs.read(native)
            for section, key in (("source", "analysis_manifest_sha256"), ("provenance", "run_id")):
                del adjusted[section][key]
                del doc[section][key]
            if adjusted != doc:
                raise ValueError("gate changed native data beyond the declared bits and lineage")
        receipts[ident + "/" + mode] = dict(
            native_sha256=_sha(native),
            request_sha256=_sha(request),
            causal_snapshots=parent["causal_snapshots"],
            method=mode,
        )
    save_json(OUT / "input-audit.json", receipts)


def publish(work, include_thin):
    rows = sealed(OUT, "prediction-lock.json", "predictions.jsonl.gz")
    expected = {(ident, MODES[mode]) for ident in inputs.HELD for mode in ("original", "scalar")}
    if len(rows) != len(expected) or {(r["id"], r["method"]) for r in rows} != expected:
        raise ValueError("the primary replay must retain all eight attempts")
    prior_lock = "all-figure-lock.json"
    earlier = {
        r["id"]: r
        for r in sealed(inputs.WIDE, prior_lock, "positions.jsonl.gz")
        if r["method"] == "scout-centers_control" and r["id"] in inputs.HELD
    }
    parity = {}
    for r in rows:
        if r["method"] != MODES["original"]:
            continue
        old = earlier[r["id"]]
        if (
            old["native_sha256"] != r["native_sha256"].removeprefix("sha256:")
            or r["native_sha256"].removeprefix("sha256:") != r["wide_native_sha256"]
            or old["catalog_sha256"] != r["catalogue_sha256"]
            or old["original_request_sha256"] != r["capture_request_sha256"]
            or old["tile"] != r["tile"]
        ):
            raise ValueError("unmodified replay differs from the archived receiver request")
        arms = {}
        for arm in ARMS:
            prev, new = (x["result"].get("arms", {}).get(arm, {}) for x in (old, r))
            if prev.get("latlon") is not None and new.get("latlon") is not None:
                arms[arm] = dict(
                    latlon_exact=prev["latlon"] == new["latlon"],
                    rf_rms_exact=prev.get("rf_rms_hz") == new.get("rf_rms_hz"),
                )
            else:
                arms[arm] = None
        parity[r["id"]] = dict(
            earlier_status=old["result"]["status"], replay_status=r["result"]["status"], arms=arms
        )
    if include_thin:
        (thin,) = sealed(OUT, "thinning-lock.json", "thinnings.jsonl.gz")
        (scalar,) = [r for r in rows if r["id"] == "DS29-0127" and r["method"] == MODES["scalar"]]
        if (
            (thin["id"], thin["method"]) != (scalar["id"], MODES["thin"])
            or any(
                thin[k] != scalar[k]
                for k in ("wide_native_sha256", "capture_request_sha256", "tile")
            )
            or thin["after"]["positive_candidates"] != scalar["after"]["positive_candidates"]
        ):
            raise ValueError("hash allocation is not matched to the scalar budget")
        rows.append(thin)

    cutoff = inputs.read(OUT / "threshold-lock.json")["threshold"]
    verify_native(rows, work, cutoff)
    _, originals = held_references(None, inputs.HELD)
    cases = {r["id"]: r for r in originals}
    scores = [fit(row, cases[row["id"]], arm) for row in rows for arm in ARMS]
    csv_file(OUT / "scores.csv", scores)
    csv_file(OUT / "resources.csv", resources(rows))
    old_scores = [
        dict(
            id=c["id"],
            method=mode,
            arm=arm,
            **{
                key: c["reference"][mode][arm].get(key)
                for key in ("status", "error_km", "rf_rms_hz", "wall_s")
            },
        )
        for c in originals
        for mode in ROLES
        for arm in ARMS
    ]
    csv_file(OUT / "capture-era-v5.csv", old_scores)
    teacher = agreement(cutoff)
    csv_file(OUT / "teacher-agreement.csv", teacher)
    agreement_figure(teacher)
    save_json(OUT / "scores.json", dict(arms=summaries(scores), original_control_parity=parity))
    write(
        OUT / "positions.jsonl.gz",
        compressed_rows(
            [
                dict(
                    row,
                    native_sha256=row["native_sha256"].removeprefix("sha256:"),
                    catalog_sha256=row["catalogue_sha256"],
                    original_request_sha256=row["capture_request_sha256"],
                    mode="matched-tile",
                )
                for row in rows
            ]
        ),
    )
    figures(rows)
    dependencies = [
        "prediction-lock.json",
        "scores.csv",
        "resources.csv",
        "teacher-agreement.csv",
        "teacher-agreement.png",
        "input-audit.json",
        "capture-era-v5.csv",
        "scores.json",
        "positions.jsonl.gz",
        "figures.json",
        "figure-lock.json",
    ]
    if include_thin:
        dependencies.extend(("thinning-lock.json", "thinning-figure-lock.json"))
    save_json(
        OUT / "score-lock.json",
        dict(
            files={name: _sha(OUT / name) for name in dependencies},
            exporter_sha256=_sha(Path(__file__)),
            earlier_wide_positions_sha256=_sha(inputs.WIDE / prior_lock),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, required=True)
    parser.add_argument("--include-thin", action="store_true")
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work, args.include_thin)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=OUT)


if __name__ == "__main__":
    main()
