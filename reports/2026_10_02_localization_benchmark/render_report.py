import json

from selection import ROOT


def number(value):
    return "—" if value is None else f"{value:.3f}"


def table(headers, rows):
    strings = [[str(value) for value in row] for row in [headers, *rows]]
    widths = [max(len(row[index]) for row in strings) for index in range(len(headers))]
    lines = [
        " | ".join(value.ljust(width) for value, width in zip(row, widths, strict=True))
        for row in strings
    ]
    lines.insert(1, "-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def render(report):
    original = [row for row in report["rows"] if row["dataset"] == "original_sample"]
    attempted = sum(row["attempted"] for row in report["rows"])
    successful = sum(row["success"] for row in report["rows"])
    sections = [
        "LOCALIZATION BENCHMARK: ORIGINAL SAMPLE + 16 RANDOM DS11 SINGLE SCANS",
        f"Attempted {attempted}/{len(report['rows'])}; optimizer successes {successful}.",
        "Original: " + report["selection"]["original_sample"],
        "All-data fits; no heldout observations. Reference error is post-fit evaluation only.",
        "Conditional persisted candidate evidence: this is NOT a blind-localization benchmark.",
        "Failed-fit errors are diagnostic only; DS11 error summaries use successful fits only.",
        "Success means numerical convergence, not correct satellite identities or position.",
        "\nORIGINAL SAMPLE (error km, assignment RMS Hz, runtime seconds)",
        table(
            ["Method", "Status", "Free", "Groups", "Error km", "RMS Hz", "Seconds"],
            [
                [
                    row["model"],
                    row["status"],
                    row["free_parameters"],
                    row["assigned_groups"],
                    number(row["reference_error_km"]),
                    number(row.get("fixed_assignment_rms_hz")),
                    number(row["runtime_s"]),
                ]
                for row in original
            ],
        ),
        "\nDS11 AGGREGATES (error km; always read success counts beside errors)",
        table(
            ["Method", "Attempted", "Success", "Median", "P90", "Worst", "<1 km", "<5 km"],
            [
                [
                    row["model"],
                    f"{row['attempted_scans']}/{row['requested_scans']}",
                    f"{row['successful_scans']}/{row['requested_scans']}",
                    number(row["median_error_km"]),
                    number(row["p90_error_km"]),
                    number(row["maximum_error_km"]),
                    row["within_1km"],
                    row["within_5km"],
                ]
                for row in report["summary"]
            ],
        ),
        "\nMODEL INTERPRETATION",
        "track_independent: position + one robust frequency intercept per retained track.",
        "track_constant: position + one shared constant intercept per RX.",
        "track_linear: position + one intercept and bounded +/-10 Hz/s slope per RX.",
        "glrt_fixed_N: position only; RX line from track_linear or explicitly labeled fallback.",
        "glrt_free_16: position + RX intercepts/slopes, profiled against raw group-exclusive GLRT.",
        "glrt_timing_3s: position + 64 satellite time shifts, sigma=1 s, bound +/-3 s; RX fixed.",
        "glrt_timing_10s: position + 64 shifts, sigma=10/3 s, bound +/-10 s; RX fixed.",
        "anchors: coherent long-track anchors, position + shared RX lines.",
        "extensions: iteratively extend anchors with coherent raw-GLRT support and refit.",
        "coherent_timing: extensions + support-gated per-satellite shifts, sigma=1 s, +/-3 s.",
        "Alias period: 1/4.4 microseconds = 227272.727 Hz. RX intercept epoch: scan time 150 s.",
        "Candidate counts use nested prefixes of each scan's frozen 64-satellite bank.",
        "All scans start from the same geographic prior; no cross-scan fitted initialization.",
        "Track and GLRT objectives use different observation sets/weights; do not rank by loss.",
        "More satellite candidates can reduce nearest-curve loss without improving position.",
        "Receipts/CSVs retain failures, initialization provenance, RX parameters and priors.",
    ]
    return "\n".join(sections) + "\n"


def main():
    report = json.loads((ROOT / "comparison.json").read_text())
    result = render(report)
    (ROOT / "comparison.txt").write_text(result)
    print(result)


if __name__ == "__main__":
    main()
