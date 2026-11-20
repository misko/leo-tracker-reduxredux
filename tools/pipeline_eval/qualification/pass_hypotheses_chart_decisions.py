"""Authenticate terminal pass decisions in chart copies of frozen predictions."""

import gzip
import json
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, save_json
from ..scoring import ARMS, validate_result
from . import pass_hypotheses_trial as trial
from .armijo_finish_results import pack

OUT, world = trial.OUT, trial.world
MARKER = "terminal_position_decision"
MANIFEST = "terminal-decisions.json"
PANELS = ("containing", "omitted", "waveform")


def terminal_copy(row):
    if row["method"] not in trial.model.METHODS:
        return row
    result = row["result"]
    validate_result(result)
    metrics = result["metrics"]
    if (
        result["status"] != "withheld"
        or result["reason"] != "no_conditioned_in_tile_intersections"
        or metrics.get("position_attempted") is not False
        or metrics.get("in_tile_intersections") != 0
        or MARKER in metrics
        or set(result.get("arms", {})) != set(ARMS)
        or any(
            k not in point or point[k] is not None
            for point in result["arms"].values()
            for k in ("latlon", "forced_latlon")
        )
    ):
        raise ValueError(
            "only original pass receiver decisions without a numerical estimate qualify"
        )
    return row | {"result": result | {"metrics": metrics | {MARKER: True}}}


def rows(out, name):
    with gzip.open(out / name, "rt") as source:
        return list(map(json.loads, source))


def derive(out=OUT):
    prediction_path = "prediction-lock.json"
    authoritative = world.read(out / prediction_path)
    world.verify(out, authoritative["files"])
    source = rows(out, trial.PREDICTIONS)
    methods = trial.model.METHODS
    expected = Counter((i, m) for i in authoritative["cases"] for m in methods)
    if Counter((r["id"], r["method"]) for r in source) != expected:
        raise ValueError("original pass predictions do not contain each sealed offer and method")
    original = {(r["id"], r["method"]): r for r in source}
    markers = [
        dict(
            id=r["id"],
            method=r["method"],
            source_row_sha256=world.digest(encoded(r)),
            result_status=r["result"]["status"],
            result_reason=r["result"]["reason"],
            position_attempted=False,
            terminal_position_decision=True,
        )
        for r in source
    ]
    pending, seen = [], Counter()
    descriptor = world.read(out / "figures.json")
    for card in descriptor["charts"]:
        panel = card["id"].removeprefix(trial.model.METHODS[0] + "-")
        if panel not in PANELS or card["method"] != methods[0]:
            raise ValueError("terminal marker applies only to the pass hypothesis chart cohorts")
        legacy = f"{panel}-figure-lock.json"
        old = world.read(out / legacy)
        world.verify(out, old["files"])
        if card["cases"] != old["cases"]:
            raise ValueError("figure roster differs from its original sealed cohort")
        file = f"{panel}-positions.jsonl.gz"
        current = []
        for row in rows(out, file):
            if row["method"] in methods:
                key = row["id"], row["method"]
                if row != original[key]:
                    raise ValueError("figure row differs from the verified receiver result")
                seen[key] += 1
            current.append(terminal_copy(row))
        pending.append((card, panel, old, legacy, current))
    if seen != expected or set(p[1] for p in pending) != set(PANELS):
        raise ValueError("every terminal result must appear in exactly one chart cohort")
    save_json(
        out / MANIFEST,
        dict(
            version=1,
            original_predictions=trial.PREDICTIONS,
            original_predictions_sha256=authoritative["files"][trial.PREDICTIONS],
            original_prediction_lock_sha256=world.digest((out / prediction_path).read_bytes()),
            original_source_lock_sha256=authoritative["files"]["source-lock.json"],
            chart_transform_sha256=world.digest(Path(__file__).read_bytes()),
            records=markers,
        ),
    )
    for card, panel, old, legacy, current in pending:
        file = f"{panel}-terminal-positions.jsonl.gz"
        seal = f"{panel}-terminal-figure-lock.json"
        files = old["files"] | {
            file: pack(out, file, current),
            MANIFEST: world.digest((out / MANIFEST).read_bytes()),
            legacy: world.digest((out / legacy).read_bytes()),
        }
        save_json(out / seal, dict(cases=old["cases"], files=files))
        proof = (trial.PREDICTIONS, "source-lock.json", MANIFEST)
        card.update(
            seal=seal,
            provenance=[*dict.fromkeys([*card["provenance"], *proof])],
            caption="The receiver withheld before refinement because no conditioned pair survived.",
        )
        for series in card["series"]:
            series["file"] = file
    save_json(out / "figures.json", descriptor)


if __name__ == "__main__":
    derive()
