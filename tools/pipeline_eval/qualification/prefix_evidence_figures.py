"""Render standard both-arm position charts for frozen prefix-choice evidence."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import validate_result
from . import complete_detector_roster as official
from . import prefix_evidence_trial as trial
from . import screening_figures
from .full_v5_check import _sha
from .phase_support_results import pack
from .whole_pressure_trial import rows_from

RETROSPECTIVE = "prefix_evidence_retrospective"
ACTUAL = "prefix_evidence_causal"
STOCK, FIFTH = "prefix_evidence_fixed_stock", "prefix_evidence_fixed_fifth"


def row_index(rows, expected_ids, roles):
    out = {}
    ids = set(expected_ids)
    for row in rows:
        role = roles.get(row["method"])
        if row["id"] not in ids or role is None:
            continue
        key = row["id"], role
        if key in out:
            raise ValueError(f"More than one prediction for {key}")
        validate_result(row["result"])
        out[key] = row
    if out.keys() != {(ident, role) for ident in ids for role in set(roles.values())}:
        raise ValueError("Missing scheduled prediction row or explicit terminal result")
    return out


def retabulate(rows, choices):
    roles = {official.FOUR: STOCK, official.FIVE: FIFTH}
    index = row_index(rows, choices, roles)
    data = []
    for ident, evidence in choices.items():
        stock, fifth = (index[ident, m] for m in (STOCK, FIFTH))
        official.same_capture(stock, fifth)
        selected = evidence["chosen"]
        chosen = {"stock": stock, "fifth": fifth}[selected]
        data.extend(
            (
                dict(
                    chosen,
                    method=RETROSPECTIVE,
                    chosen_policy=selected,
                    source_method=chosen["method"],
                    measurement_scope="retrospective_entire_branch",
                ),
                dict(stock, method=STOCK),
                dict(fifth, method=FIFTH),
            )
        )
    return data


def actual_rows(rows, ids):
    roles = {
        official.FOUR: STOCK,
        official.FIVE: FIFTH,
        ACTUAL: ACTUAL,
        trial.receiver_choice_panel.STOCK: STOCK,
        trial.receiver_choice_panel.METHOD: FIFTH,
    }
    index = row_index(rows, ids, roles)
    data = []
    for ident in ids:
        actual = index[ident, ACTUAL]
        for m in (STOCK, FIFTH):
            original = index[ident, m]
            official.same_capture(actual, original)
            data.append(dict(original, method=m))
        data.append(dict(actual, measurement_scope="actual_compact_stock_warmup"))
    return data


def figure(out, key, role, title, caption, main_label, cases, rows, roof, reference):
    positions = f"{key}-figure-positions.jsonl.gz"
    refs = {name: f"{key}-{file}" for name, file in official.REFS.items()}
    for name, file in official.REFS.items():
        src = whole_iq.checked(roof / file, reference["files"][file])
        write(out / refs[name], src.read_bytes())
    pack(out / positions, rows)
    lock = f"{key}-figure-lock.json"
    provenance = list(refs.values())
    seal = dict(cases=list(cases), files={n: _sha(out / n) for n in (positions, *provenance)})
    save_json(out / lock, seal)
    return dict(
        id=f"prefix-evidence-{key}",
        method=role,
        scope="roof",
        title=title,
        caption=caption,
        cases="sealed",
        seal=lock,
        roof_references=refs,
        provenance=provenance,
        series=[
            dict(
                key=slot,
                file=positions,
                value=method,
                label=label,
                native_field=official.BINDINGS[0],
                match=list(official.BINDINGS),
            )
            for slot, method, label in (
                ("one", role, main_label),
                ("stock", STOCK, "Fixed four regions"),
                ("all_visits", FIFTH, "Fixed fifth center"),
            )
        ],
    )


def publish(out):
    measured_path = trial.REPORT / "prediction-lock.json"
    measurements = whole_iq.read(measured_path)
    choices = whole_iq.read(
        whole_iq.checked(
            trial.REPORT / "choices.json",
            measurements["files"]["choices.json"],
        )
    )
    if set(choices["cases"]) != set(measurements["cases"]):
        raise ValueError("The twenty prefix decisions differ from the sealed roster")
    previous = official.REPORT / "all-figure-lock.json"
    source_key = str(previous.relative_to(trial.SCREEN))
    frozen = whole_iq.read(whole_iq.checked(previous, measurements["input_receipts"][source_key]))
    fresh = trial.receiver_choice_panel.REPORT
    fresh_figure = fresh / "all-figure-lock.json"
    fresh_reference = whole_iq.read(fresh_figure)
    check = whole_iq.read(fresh / "score-lock.json")
    whole_iq.checked(fresh_figure, check["files"][fresh_figure.name])
    actual = rows_from(
        whole_iq.checked(
            trial.REPORT / "actual-positions.jsonl.gz",
            measurements["files"]["actual-positions.jsonl.gz"],
        )
    )
    known = rows_from(
        whole_iq.checked(
            official.REPORT / "all-positions.jsonl.gz",
            frozen["files"]["all-positions.jsonl.gz"],
        )
    )
    out.mkdir(parents=True, exist_ok=True)
    descriptors = [
        figure(
            out,
            "retrospective",
            RETROSPECTIVE,
            "Retrospective whole-branch choice from 24 seconds of pilot evidence",
            "Twenty frozen prefix decisions select measured entire-branch endpoints. Each choice "
            "shares the original recording and four capture-era v5 comparisons with its controls.",
            "Retrospective branch choice",
            choices["cases"],
            retabulate(known, choices["cases"]),
            official.REPORT,
            frozen,
        ),
        figure(
            out,
            "actual",
            ACTUAL,
            "Actual compact fits from stock warmup and the selected detector branch",
            "Three fresh compact fits consume authenticated post-acquisition factor arrays. "
            "Two use stock warmup then fifth-center factors. One reproduces stock throughout. "
            "The paired fixed controls and original v5 options use their published measurements.",
            "Actual prefix-composed compact",
            measurements["actual_cases"],
            actual_rows(actual, measurements["actual_cases"]),
            fresh,
            fresh_reference,
        ),
    ]
    for spec in descriptors:
        screening_figures._chart(out, spec, version=2)
    save_json(out / "figures.json", dict(version=2, charts=descriptors))
    screening_figures.generate(out / "charts", evidence=out)
    files = ["figures.json"]
    for spec in descriptors:
        name = spec["seal"]
        files.extend((name, *whole_iq.read(out / name)["files"]))
    files.extend(
        str(p.relative_to(out)) for p in sorted((out / "charts").rglob("*")) if p.is_file()
    )
    sources = (
        measured_path,
        previous,
        fresh_figure,
        Path(__file__),
        ROOT / "tests/pipeline_eval/test_prefix_evidence_figures.py",
    )
    save_json(
        out / "position-chart-lock.json",
        dict(
            cases=measurements["cases"],
            actual_cases=measurements["actual_cases"],
            files={n: _sha(out / n) for n in files},
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    publish(parser.parse_args().out)
