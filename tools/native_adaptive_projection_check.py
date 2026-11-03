#!/usr/bin/env python3
"""Compare native projection against frozen public-store DS9 observations."""

import argparse
import hashlib
import json
import pathlib
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--binary", required=True)
    p.add_argument("--fixture", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    p.add_argument("--export-input", type=pathlib.Path)
    p.add_argument("--native-output", type=pathlib.Path)
    a = p.parse_args()
    rows = [json.loads(x) for x in a.fixture.read_text().splitlines()]
    lines = []
    for row in rows:
        s, c = row["source"], row["candidate"]
        values = [
            s[k]
            for k in (
                "rate",
                "anchor_counter",
                "anchor_utc_ns",
                "generation",
                "visit",
                "window_counter",
                "probe_index",
                "receiver",
                "channel",
                "upper_edge",
                "actual_rf_hz",
                "utc_bracket_width_ns",
                "input_digest",
                "analysis_digest",
                "continuity_qualified",
            )
        ]
        values += [
            c[k]
            for k in (
                "rank",
                "integer_epoch",
                "fractional_offset",
                "tracking_cfo_hz",
                "exact_score",
                "control_score",
                "margin",
                "complete",
            )
        ]
        lines.append("\t".join(str(int(v)) if isinstance(v, bool) else str(v) for v in values))
    encoded = "\n".join(lines) + "\n"
    if a.export_input:
        a.export_input.write_text(encoded)
    if a.native_output:
        result = a.native_output.read_text()
    else:
        result = subprocess.run(
            [a.binary], input=encoded, text=True, capture_output=True, check=True, timeout=120
        ).stdout
    actual = result.splitlines()
    if len(actual) != len(rows):
        raise ValueError("native output count differs")
    failures, retained = [], 0
    max_ns, max_uncertainty, max_m2, max_m3 = 0, 0.0, 0.0, 0.0
    for index, (row, line) in enumerate(zip(rows, actual, strict=True)):
        e = row["expected"]
        if e is None:
            if line != "unavailable":
                failures.append([index, "unexpected observation"])
            continue
        retained += 1
        fields = line.split("\t")
        if len(fields) != 9:
            failures.append([index, "missing observation"])
            continue
        if fields[:2] != [e["candidate_id"], e["source_group_id"]]:
            failures.append([index, "identity mismatch"])
        ns = max(
            abs(int(fields[i + 2]) - e[k])
            for i, k in enumerate(
                ("support_start_utc_ns", "support_center_utc_ns", "support_end_utc_ns")
            )
        )
        unc = abs(float(fields[6]) - e["standard_uncertainty_hz"])
        m2 = abs(float(fields[7]) - e["factorial_support_moments_s"][2])
        m3 = abs(float(fields[8]) - e["factorial_support_moments_s"][3])
        max_ns, max_uncertainty = max(max_ns, ns), max(max_uncertainty, unc)
        max_m2, max_m3 = max(max_m2, m2), max(max_m3, m3)
        if (
            ns > 1
            or unc > 1e-9
            or m2 > 1e-18
            or m3 > 1e-18
            or float(fields[5]) != row["candidate"]["tracking_cfo_hz"]
        ):
            failures.append([index, "numerical mismatch", ns, unc, m2, m3])
    report = dict(
        status="pass" if not failures else "fail",
        records=len(rows),
        expected_observations=retained,
        failures=failures,
        tolerances=dict(utc_ns=1, uncertainty_hz=1e-9, moments=1e-18),
        max_errors=dict(
            utc_ns=max_ns, uncertainty_hz=max_uncertainty, moment2=max_m2, moment3=max_m3
        ),
        fixture_sha256=hashlib.sha256(a.fixture.read_bytes()).hexdigest(),
        scope="projection boundary; saved fractional candidates, not IQ-to-location",
    )
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
