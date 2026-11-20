"""Score four-slot, one-slot, and complete-input positions on the same recordings."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km
from . import arrival_queue_position as one_slot
from . import buffered_arrival_replay as trial
from . import buffered_arrival_results as actual
from . import screening_figures
from .bracketed_position_results import V5_OPTIONS
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from


def auth(path, expected=None):
    if expected:
        whole_iq.checked(path, expected)
    data = whole_iq.read(path)
    for name, digest in data["files"].items():
        whole_iq.checked(path.parent / name, digest)
    return data


def pairs(report):
    old = trial.BASE / "position-score-lock.json"
    receipt = auth(old, trial.BASE_POSITIONS)
    archived = {
        (r["id"], r["method"]): r for r in rows_from(old.parent / "matched-positions.jsonl.gz")
    }
    auth(report / "stage-lock.json")
    if set(receipt["cases"]) != set(trial.paced.CPUS):
        raise ValueError("matched one-slot study has a different capture roster")
    files, selected = ["stage-lock.json"], []
    for mode in trial.paced.MODES:
        lock = report / f"positions-{mode}-lock.json"
        details = auth(lock)
        name = f"position-{mode}-byte-bindings.json"
        checks = whole_iq.read(report / name)["cases"]
        files += [lock.name, *details["files"], name]
        current = rows_from(report / f"positions-{mode}.jsonl.gz")
        if len(current) != len(trial.paced.CPUS) or {r["id"] for r in current} != set(
            trial.paced.CPUS
        ):
            raise ValueError("four-slot endpoint roster is incomplete")
        for row in current:
            ident = row["id"]
            old_row = archived[ident, one_slot.METHODS[mode]]
            full = archived[ident, actual.FULL[mode]]
            if any(
                row[key] != old_row[key] or row[key] != full[key]
                for key in (
                    "tile",
                    "catalog_sha256",
                    "paired_capture_sha256",
                    "original_request_sha256",
                    "paired_paced_native_sha256",
                )
            ):
                raise ValueError(
                    "retained-input comparison changed the capture, catalogue or offer"
                )
            witness = checks[ident]
            if not row["dropped"] and row["result"]["status"] == "ok":
                expected_native = witness["exact_reused_native_sha256"]
                if (
                    expected_native != row["native_sha256"]
                    or expected_native != full["native_sha256"]
                ):
                    raise ValueError("archived complete-fit reuse lacks the exact matching bytes")
            elif row["dropped"] and row["result"]["status"] == "ok":
                if (
                    row["origin"] != "fresh paced-retained factor fit"
                    or row["native_sha256"] == full["native_sha256"]
                ):
                    raise ValueError("dropped visits require a real new numerical fit")
            selected.append((mode, row, old_row, full))
    return selected, files


def score(report):
    paired, files = pairs(report)
    _, reference = held_references(None, trial.paced.CPUS)
    truth = {r["id"]: r["truth"] for r in reference}
    scores, points, previous_v5 = [], [], []
    for mode, four, one, full in paired:
        ident = four["id"]
        for role, record in (
            ("four waiting", four),
            ("one waiting", one),
            ("all valid visits", full),
        ):
            points.append(record)
            fit = record["result"]
            for arm in ARMS:
                value = fit["arms"][arm]
                point = value.get("latlon")
                scores.append(
                    dict(
                        id=ident,
                        mode=mode,
                        support=role,
                        method=record["method"],
                        arm=arm,
                        status=fit["status"],
                        dropped=record["dropped"],
                        origin=record["origin"],
                        horizontal_position_error_km=distance_km(truth[ident], point),
                        shift_from_full_km=distance_km(
                            point, full["result"]["arms"][arm]["latlon"]
                        ),
                        rf_rms_hz=value.get("rf_rms_hz"),
                        frequency_score=fit["metrics"].get(f"{arm}_frequency_score"),
                        observations=fit["metrics"].get("observations"),
                        tracks=fit["metrics"].get("tracks"),
                        position_wall_s=record["resources"].get("wall_s"),
                        position_cpu_s=record["resources"].get("cpu_s"),
                    )
                )
    for ref in reference:
        for option in V5_OPTIONS:
            for arm in ARMS:
                value = ref["reference"][option][arm]
                previous_v5.append(
                    dict(
                        id=ref["id"],
                        option=option,
                        arm=arm,
                        status=value["status"],
                        error_km=value["error_km"],
                        rf_rms_hz=value.get("rf_rms_hz"),
                    )
                )
    pack(report / "matched-positions.jsonl.gz", points)
    csv_file(report / "buffered-positions.csv", scores)
    csv_file(report / "original-v5.csv", previous_v5)
    references = ("buffered-positions.csv", "original-v5.csv", "stage-lock.json")
    files += ["matched-positions.jsonl.gz", *references]
    seal = "position-score-lock.json"
    save_json(
        report / seal,
        dict(
            cases=list(trial.paced.CPUS),
            files={name: _sha(report / name) for name in files},
            one_slot_position_sha256=trial.BASE_POSITIONS,
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    charts = []
    for mode in trial.paced.MODES:
        label = "stock wide" if mode == "control" else "unconditional fifth center"
        series = []
        for key, display, method in (
            ("one", "Four waiting slots", actual.METHODS[mode]),
            ("stock", "One slot · historical", one_slot.METHODS[mode]),
            ("all_visits", "All valid visits · historical", actual.FULL[mode]),
        ):
            item = dict(
                key=key,
                label=display,
                file="matched-positions.jsonl.gz",
                value=method,
                native_field="paired_capture_sha256",
            )
            if key != "one":
                item["match"] = [
                    "paired_paced_native_sha256",
                    "catalog_sha256",
                    "tile",
                    "original_request_sha256",
                ]
            series.append(item)
        charts.append(
            dict(
                id=actual.PAGE_IDS[mode],
                method=actual.METHODS[mode],
                scope="roof",
                cases="sealed",
                seal=seal,
                title=f"Position after four-slot pacing · {label}",
                caption=(
                    "Two full saved-IQ recordings at their recorded delivery cadence. Earlier "
                    "one-slot and all-valid runs use the same inputs. Position fits use the "
                    "packets admitted by each queue; original v5 uses capture-era factors."
                ),
                provenance=list(references),
                series=series,
            )
        )
    save_json(report / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(report / "position-charts", evidence=report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    score(parser.parse_args().out)
