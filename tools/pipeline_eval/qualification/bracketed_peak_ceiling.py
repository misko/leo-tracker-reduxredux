"""Count which capture-only detections a choice among the original wide rows could recover."""

import argparse
import csv
from collections import Counter
from math import isfinite
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import bracketed_peak as method
from . import bracketed_peak_trial as trial
from .factor_cross import winner
from .full_v5_check import BULK, _load_case, _sha
from .prefix_figures import csv_file


def classification(probe, reference, rate):
    period = rate / method.FRAME_RATE_HZ
    target = method.Peak.from_candidate(probe, probe["valid_start_counter"], reference)
    complete = []
    for row in probe["candidates"]:
        values = [row.get(key) for key in method.NUMERIC_FIELDS]
        if not all(isinstance(x, (float, int)) and isfinite(x) for x in values):
            continue
        peak = method.Peak.from_candidate(probe, probe["valid_start_counter"], row)
        epoch = abs(method.wrapped(peak.epoch - target.epoch, period))
        cfo = abs(method.wrapped(peak.cfo_hz - target.cfo_hz, method.FOLD_HZ))
        positive = (
            row["fractional_exact_score"] > row["fractional_control_score"]
            and row["fractional_margin"] > 0
        )
        complete.append((epoch, cfo, positive))
    strict = [
        positive
        for e, f, positive in complete
        if e <= method.EPOCH_TOLERANCE and f <= method.CFO_TOLERANCE
    ]
    loose = any(e <= 20 and f <= method.CFO_TOLERANCE for e, f, _ in complete)
    if not complete:
        category = "no_complete_row"
    elif not any(e <= method.EPOCH_TOLERANCE for e, _, _ in complete):
        category = "no_near_epoch"
    elif not strict:
        category = "only_wrong_cfo"
    elif not any(strict):
        category = "family_nonpositive_margin"
    else:
        category = "family_positive_margin"
    return category, loose


def measure(out):
    if (out / "availability-lock.json").exists():
        raise FileExistsError("choose a fresh output for a new availability measurement")
    groups = {}
    for name in ("selection-lock.json", "measurement-lock.json"):
        for file, expected in trial.read(out / name)["files"].items():
            if _sha(out / file) != expected:
                raise ValueError("the original measurement is no longer intact")
    with (out / "bracketed-peaks.csv").open(newline="") as stream:
        expected = {
            r["id"]: int(r["capture_positive_wide_negative"])
            for r in csv.DictReader(stream)
            if r["mode"] == "bracketed"
        }
    plan = trial.read(out / "source-lock.json")
    save_json(
        out / "availability-plan.json",
        dict(
            protocol_sha256=_sha(out / "AVAILABILITY.md"),
            measurement_sha256=_sha(out / "measurement-lock.json"),
            runner_sha256=_sha(Path(__file__)),
            selection_runner_sha256=_sha(Path(trial.__file__)),
        ),
    )
    labels = (
        "no_complete_row",
        "no_near_epoch",
        "only_wrong_cfo",
        "family_nonpositive_margin",
        "family_positive_margin",
    )
    for case in trial.CASES:
        wide, _ = trial.wide(case, plan)
        path = BULK / _load_case(case)["native"]["path"]
        if _sha(path) != plan["inputs"][case]["capture_native_sha256"]:
            raise ValueError("capture native file changed")
        original = trial.read(path)
        groups[case] = counts = Counter()
        source = wide["source"]
        for p, q in zip(source["probes"], original["source"]["probes"], strict=True):
            if not trial.exact_probe(p, q):
                raise ValueError("opportunity metadata do not match")
            j = winner(q["candidates"])
            if j is None or winner(p["candidates"]) is not None:
                continue
            label, loose = classification(p, q["candidates"][j], source["sample_rate_hz"])
            counts[label] += 1
            counts["within_20_samples_and_1khz"] += int(loose)
        if sum(counts[label] for label in labels) != expected[case]:
            raise ValueError("availability population differs from sealed selection scoring")
    rows = [
        dict(
            id=case,
            capture_positive_wide_negative=expected[case],
            **{k: c[k] for k in (*labels, "within_20_samples_and_1khz")},
        )
        for case, c in groups.items()
    ]
    csv_file(out / "availability.csv", rows)
    trial.lock_files(
        out,
        "availability-lock.json",
        ("availability.csv", "availability-plan.json", "measurement-lock.json"),
    )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.OUT)
    print(measure(parser.parse_args().out))
