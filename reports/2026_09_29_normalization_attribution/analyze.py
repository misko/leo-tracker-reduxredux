"""Exact algebraic attribution of the previously frozen catalogue scores."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_29_catalogue_normalization"


def components(row, partition):
    evidence = row[partition]
    # Full / retained signal density = (R / V) / retained numerator mass.
    count = math.log(row["retained_visible"] / row["visible"])
    numerator = -math.log(evidence["retained_mass"])
    background = math.log(evidence["retained_signal_probability"]) - math.log(
        evidence["full_signal_probability"]
    )
    actual = evidence["exact_full_log_score"] - evidence["retained_log_score"]
    error = abs(count + numerator + background - actual)
    assert error < 1e-8, error
    return dict(count=count, numerator=numerator, background=background, actual=actual), error


def main():
    # Verify the sealed source experiment, including its manifest and raw outputs.
    for line in (SOURCE / "evidence.sha256").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, name
    cases, errors = [], []
    for ds in ("DS7", "DS8", "DS9"):
        source = json.loads((SOURCE / f"{ds}.json").read_text())
        for partition in ("training", "full"):
            for tau in (-5, 0, 5):
                centers = {
                    r["track_id"]: r
                    for r in source["rows"]
                    if r["location_class"] == "center" and r["tau_s"] == tau
                }
                for location in ("n24", "n8_0", "n8_1", "n8_2"):
                    tracks = []
                    selected = [
                        r
                        for r in source["rows"]
                        if r["location_class"] == location and r["tau_s"] == tau
                    ]
                    assert {r["track_id"] for r in selected} == set(centers)
                    for row in selected:
                        base = centers[row["track_id"]]
                        current, err = components(row, partition)
                        center, base_err = components(base, partition)
                        errors.extend((err, base_err))
                        tracks.append(
                            dict(
                                track_id=row["track_id"],
                                **{k: current[k] - center[k] for k in current},
                                center_signal_probability=base[partition][
                                    "full_signal_probability"
                                ],
                                location_signal_probability=row[partition][
                                    "full_signal_probability"
                                ],
                            )
                        )
                    tracks.sort(key=lambda r: abs(r["actual"]), reverse=True)
                    totals = {k: sum(r[k] for r in tracks) for k in current}
                    gross = sum(abs(r["actual"]) for r in tracks)
                    cases.append(
                        dict(
                            dataset=ds,
                            partition=partition,
                            tau_s=tau,
                            location=location,
                            tracks=len(tracks),
                            **totals,
                            gross_absolute_change=gross,
                            top5_gross_fraction=sum(abs(r["actual"]) for r in tracks[:5])
                            / gross,
                            contributions=tracks,
                        )
                    )
    assert len(cases) == 72
    summary = dict(
        source_seal_sha256=hashlib.sha256((SOURCE / "evidence.sha256").read_bytes()).hexdigest(),
        max_identity_error=max(errors),
        max_count_change=max(abs(r["count"]) for r in cases),
        max_numerator_change=max(abs(r["numerator"]) for r in cases),
        max_background_change=max(abs(r["background"]) for r in cases),
        max_actual_change=max(abs(r["actual"]) for r in cases),
        cases=cases,
    )
    with (HERE / "result.json").open("x") as out:
        json.dump(summary, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, indent=2))
    for r in cases:
        if r["location"] == "n24" and r["tau_s"] == 0:
            print({k: v for k, v in r.items() if k != "contributions"})


if __name__ == "__main__":
    main()
