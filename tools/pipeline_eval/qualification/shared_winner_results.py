"""Audit, score, and plot the sealed discordant-winner trials."""

import argparse
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS
from . import shared_winner_cross as cross
from .factor_cross import GATE, RANK, winner
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .shared_winner_trial import CASES, MODES, PARENT, REPORT, incoming, parent_lock, read, sources
from .support_cross_results import graph_support, outside_treatment, resources


def audit(work, support_work, rows):
    source, parent = sources(), parent_lock()
    metadata = {(r["id"], r["condition"]): r for r in rows}
    recorded = {r["id"]: r for r in sealed(REPORT, "prediction-lock.json", "selections.jsonl.gz")}
    records = []
    for ident in CASES:
        _, _, parent_record, base, donor, (changes, census) = incoming(
            ident, support_work, source, parent
        )
        if recorded[ident] != dict(id=ident, counts=census, choices=changes):
            raise ValueError("recorded physical classifications do not reproduce")
        a, b = (doc["source"]["probes"] for doc in (base, donor))
        for mode in MODES:
            selected = {r["index"]: r for r in changes if cross.selected(r, mode)}
            path = work / ident / mode / "recording"
            entry = metadata[ident, mode]
            native = path / "native.json"
            if (
                _sha(native) != entry["native_sha256"]
                or _sha(path / "request.json") != entry["prepared_request_sha256"]
                or entry["baseline_native_sha256"] != parent_record["native_sha256"]
                or len(selected) != entry["changed"]
            ):
                raise ValueError("worker request or treatment roster differs from the seal")
            document = read(native)
            if outside_treatment(document) != outside_treatment(base):
                raise ValueError("an untreated acquisition or manifest field changed")
            for i, (before, captured, after) in enumerate(
                zip(a, b, document["source"]["probes"], strict=True)
            ):
                if i not in selected:
                    if after != before:
                        raise ValueError("an untreated or physically matching probe changed")
                    continue
                row = selected[i]
                old, new = before["candidates"], after["candidates"]
                if mode == "wide_alternative":
                    index = row["wide_alternative"]
                    intended = old[index]
                else:
                    index = row["wide_winner"]
                    intended = dict(
                        captured["candidates"][row["capture_winner"]], **{RANK: old[index][RANK]}
                    )
                if winner(new) != index or new[index] != intended:
                    raise ValueError("new winner differs from the exact selected measurement")
                if {k: v for k, v in after.items() if k != "candidates"} != {
                    k: v for k, v in before.items() if k != "candidates"
                }:
                    raise ValueError("treatment changed a hardware probe field")
                for j, (prior, current) in enumerate(zip(old, new, strict=True)):
                    if j == index:
                        continue
                    gate = prior[GATE] and cross.priority(prior) <= cross.priority(intended)
                    if current != dict(prior, **{GATE: gate}):
                        raise ValueError("nonwinner measurement or unnecessary gate change")
            records.append(
                dict(
                    id=ident,
                    condition=mode,
                    replaced=len(selected),
                    preserved=len(a) - len(selected),
                )
            )
    save_json(REPORT / "treatment-audit.json", records)


def figures():
    fields = ("positions.jsonl.gz", "prediction-lock.json", "treatment-audit.json", "scores.csv")
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(CASES),
            files={name: _sha(REPORT / name) for name in fields},
        ),
    )

    def series(key, label, method):
        return dict(
            key=key,
            label=label,
            file="positions.jsonl.gz",
            value=method,
            native_field="paired_capture_sha256",
            match=[
                "tile",
                "catalog_sha256",
                "original_request_sha256",
                "parent_wide_sha256",
            ],
        )

    labels = (
        "Select an exported gated wide alternative",
        "Copy capture winner where no gated wide match exists",
        "Copy capture winner at every discordant probe",
    )
    specs = []
    for mode, label in zip(MODES, labels, strict=True):
        method = "shared_winner_" + mode
        specs.append(
            dict(
                id="shared-winner-" + mode.replace("_", "-"),
                method=method,
                scope="roof",
                cases="sealed",
                title=label + " on exact capture-era availability",
                caption=(
                    "Two stored recordings. All cells use the same positive-probe roster. "
                    "The hybrid leaves all shared winners wide. Exact stock capture lets "
                    "the same-family shared measurements also come from capture."
                ),
                seal="figure-lock.json",
                provenance=list(fields[1:]),
                series=[
                    series("one", label, method),
                    series("stock", "Exact-capture-support hybrid", "probe_support_both"),
                    series("one_native_factors", "Exact stock capture", "probe_support_capture"),
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=1, charts=specs))


def publish(work, support_work):
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    plan = read(REPORT / "plan.json")
    if any(_sha(ROOT / name) != expected for name, expected in plan["files"].items()):
        raise ValueError("the prospective protocol or its input authority changed")
    expected = {(ident, mode) for ident in CASES for mode in MODES}
    if len(rows) != len(expected) or {(r["id"], r["condition"]) for r in rows} != expected:
        raise ValueError("all six prespecified attempts are required")
    audit(work, support_work, rows)
    prior = [
        r
        for r in sealed(PARENT, "prediction-lock.json", "predictions.jsonl.gz")
        if r["id"] in CASES and r["condition"] in ("wide", "both", "capture")
    ]
    if len(prior) != 6:
        raise ValueError("missing a previously sealed stock or exact-support control")
    _, cases = held_references(None, CASES)
    references = {c["id"]: c for c in cases}
    records = [
        dict(fit(r, references[r["id"]], arm), condition=r["condition"], changed=r.get("changed"))
        for r in rows + prior
        for arm in ARMS
    ]
    controls = {(r["id"], r["arm"]): r for r in records if r["condition"] == "both"}
    for r in records:
        base = controls[r["id"], r["arm"]]
        for field in ("error_km", "conditional_rf_rms_hz"):
            a, b = r[field], base[field]
            r["delta_" + field] = a - b if a is not None and b is not None else None
    csv_file(REPORT / "scores.csv", records)
    csv_file(REPORT / "resources.csv", resources(rows))
    csv_file(REPORT / "graph-support.csv", graph_support(rows + prior))
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows + prior))
    figures()
    files = (
        "prediction-lock.json",
        "scores.csv",
        "resources.csv",
        "graph-support.csv",
        "treatment-audit.json",
        "positions.jsonl.gz",
        "figures.json",
        "figure-lock.json",
    )
    save_json(
        REPORT / "score-lock.json",
        dict(files={n: _sha(REPORT / n) for n in files}, source_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--support-work", required=True, type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work, args.support_work)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
