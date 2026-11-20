"""Independently audit and score the sealed native probe availability cross."""

import argparse
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, distance_km
from . import support_cross
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .support_cross_trial import BAND, CASES, ORDER, REPORT, load, read, sources


def outside_treatment(doc):
    return (
        {k: v for k, v in doc.items() if k not in ("source", "provenance")},
        {k: v for k, v in doc["source"].items() if k not in ("probes", "analysis_manifest_sha256")},
        {k: v for k, v in doc["provenance"].items() if k != "run_id"},
    )


def audit_payload(work, results):
    verified = []
    source = sources()
    for ident in CASES:
        _, _, _, wide_bytes, capture_bytes = load(ident, source)
        data = {key: read(work / ident / key / "recording/native.json") for key in ORDER}
        for condition, original in (("wide", wide_bytes), ("capture", capture_bytes)):
            if (work / ident / condition / "recording/native.json").read_bytes() != original:
                raise ValueError("stock replay is not byte identical")
        wide, capture = (data[k]["source"]["probes"] for k in ("wide", "capture"))
        roster = support_cross.join(data["wide"], data["capture"])
        for name in ORDER:
            directory = work / ident / name
            prediction = results[ident, name]
            if (
                _sha(directory / "recording/native.json") != prediction["native_sha256"]
                or _sha(directory / "recording/request.json")
                != prediction["prepared_request_sha256"]
            ):
                raise ValueError("worker input differs from the sealed prediction")
            measured = data[name]["source"]["probes"]
            if name in ("capture", "wide"):
                continue
            if outside_treatment(data[name]) != outside_treatment(data["wide"]):
                raise ValueError("worker source changed outside lineage and diagnostic probes")
            removed, restored = 0, 0
            for a, b, actual, availability in zip(wide, capture, measured, roster, strict=True):
                if availability == "10" and name in ("remove", "both"):
                    removed += 1
                    if support_cross.metadata(actual) != support_cross.metadata(a) or any(
                        current != dict(earlier, **{support_cross.GATE: False})
                        for earlier, current in zip(
                            a["candidates"], actual["candidates"], strict=True
                        )
                    ):
                        raise ValueError("remove cell changed more than the wide-only gate bits")
                elif availability == "01" and name in ("restore", "both"):
                    if actual != b:
                        raise ValueError("restored probe is not byte-value identical to capture")
                    restored += 1
                elif actual != a:
                    raise ValueError("untreated wide measurement changed")
            verified.append(
                dict(
                    id=ident,
                    condition=name,
                    removed=removed,
                    restored=restored,
                    untouched=len(roster) - removed - restored,
                )
            )
    save_json(REPORT / "treatment-audit.json", verified)


def archive_comparison(rows):
    former = {
        r["id"]: r
        for r in sealed(BAND, "prediction-lock.json", "positions.jsonl.gz")
        if r["method"] == "regional_wide_full_iq" and r["id"] in CASES
    }
    out = []
    for ident in CASES:
        old, current = former[ident], rows[ident, "wide"]
        if any(old[k] != current[k] for k in ("native_sha256", "catalog_sha256", "tile")):
            raise ValueError("historical wide position used different factors, catalogue or offer")
        for arm in ARMS:
            a, b = (r["result"].get("arms", {}).get(arm, {}) for r in (old, current))
            p, q = a.get("latlon"), b.get("latlon")
            out.append(
                dict(
                    id=ident,
                    arm=arm,
                    historical=old["result"]["status"],
                    current=current["result"]["status"],
                    position_difference_km=distance_km(p, q),
                    exact_coordinates=p == q if p and q else None,
                    exact_rf_rms=a.get("rf_rms_hz") == b.get("rf_rms_hz") if p and q else None,
                )
            )
    return out


def resources(rows):
    records = []
    for r in rows:
        sample = r.get("position_resources") or {}
        end = sample.get("end", {})
        records.append(
            dict(
                id=r["id"],
                condition=r["condition"],
                terminal=r["terminal"],
                status=r["result"]["status"],
                support_probes=r["positive_probes"],
                positive_candidates=r["positive_candidates"],
                cpu=r["cpu"],
                cpu_s=sample.get("cpu_s"),
                wall_s=sample.get("wall_s"),
                external_wall_s=r["supervisor_wall_s"],
                peak_bytes=sample.get("peak_bytes"),
                oom_events=end.get("memory.events.oom"),
                oom_kills=end.get("memory.events.oom_kill"),
                swap_bytes=end.get("memory.swap.current"),
            )
        )
    return records


def graph_support(rows):
    fields = (
        "observations",
        "tracks",
        "initial_branches",
        "initial_arm_fits",
        "cavity_offered",
        "compact_projections",
        "c0_frequency_score",
        "fitted_c_frequency_score",
    )
    return [
        dict(
            id=r["id"],
            condition=r["condition"],
            status=r["result"]["status"],
            **{k: r["result"]["metrics"].get(k) for k in fields},
        )
        for r in rows
    ]


def effects(scores):
    indices = {(r["id"], r["condition"], r["arm"]): r for r in scores}
    comparisons = {
        "remove_on_wide": ("remove", "wide"),
        "remove_after_restore": ("both", "restore"),
        "restore_on_wide": ("restore", "wide"),
        "restore_after_remove": ("both", "remove"),
        "both_minus_capture": ("both", "capture"),
    }
    report = []
    for ident in CASES:
        for arm in ARMS:
            for measure in ("error_km", "conditional_rf_rms_hz", "observations", "tracks"):
                delta = {}
                for effect, conditions in comparisons.items():
                    after, before = (indices[ident, name, arm][measure] for name in conditions)
                    delta[effect] = (
                        after - before if after is not None and before is not None else None
                    )
                a, b = delta["remove_on_wide"], delta["remove_after_restore"]
                report.append(
                    dict(
                        id=ident,
                        arm=arm,
                        measure=measure,
                        **delta,
                        interaction=b - a if a is not None and b is not None else None,
                    )
                )
    return report


def chart_descriptors():
    labels = {
        "wide": "Exact stock wide",
        "capture": "Exact stock capture-era",
        "remove": "Remove wide-only positives",
        "restore": "Restore capture-only positives",
        "both": "Remove wide-only and restore capture-only positives",
    }

    def series(condition, key):
        return dict(
            file="positions.jsonl.gz",
            native_field="paired_capture_sha256",
            key=key,
            label=labels[condition],
            value="probe_support_" + condition,
            match=["tile", "catalog_sha256", "original_request_sha256", "parent_wide_sha256"],
        )

    dependencies = [
        "positions.jsonl.gz",
        "prediction-lock.json",
        "treatment-audit.json",
        "scores.csv",
    ]
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(CASES), files={k: _sha(REPORT / k) for k in dependencies}),
    )
    changes = [
        dict(
            id="probe-support-" + name,
            method="probe_support_" + name,
            scope="roof",
            cases="sealed",
            title=labels[name] + " in stored wide GLRT",
            caption=(
                "Oracle probe-availability intervention. All jointly positive probes retain "
                "the full wide candidates and winners. Stock capture keeps its own winners "
                "across all probes."
            ),
            seal="figure-lock.json",
            provenance=dependencies[1:],
            series=[
                series(name, "one"),
                series("wide", "stock"),
                series("capture", "one_native_factors"),
            ],
        )
        for name in ("remove", "restore", "both")
    ]
    save_json(REPORT / "figures.json", dict(version=1, charts=changes))


def publish(work):
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    plan = read(REPORT / "plan.json")
    if any(_sha(ROOT / name) != digest for name, digest in plan["files"].items()):
        raise ValueError("fixed experiment plan and source inventory differ")
    records = {(r["id"], r["condition"]): r for r in rows}
    expected = {(ident, name) for ident in CASES for name in ORDER}
    if len(rows) != len(expected) or set(records) != expected:
        raise ValueError("the 2×2 and exact two endpoints require all ten attempted services")
    audit_payload(work, records)
    csv_file(REPORT / "archive-parity.csv", archive_comparison(records))
    _, references = held_references(None, CASES)
    reference = {r["id"]: r for r in references}
    scores = [
        dict(fit(r, reference[r["id"]], arm), condition=r["condition"])
        for r in rows
        for arm in ARMS
    ]
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "effects.csv", effects(scores))
    csv_file(REPORT / "resources.csv", resources(rows))
    csv_file(REPORT / "graph-support.csv", graph_support(rows))
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows))
    chart_descriptors()
    files = (
        "prediction-lock.json",
        "treatment-audit.json",
        "archive-parity.csv",
        "scores.csv",
        "effects.csv",
        "resources.csv",
        "graph-support.csv",
        "positions.jsonl.gz",
        "figure-lock.json",
        "figures.json",
    )
    save_json(
        REPORT / "score-lock.json",
        dict(files={k: _sha(REPORT / k) for k in files}, exporter_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
