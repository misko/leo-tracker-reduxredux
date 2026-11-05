"""Verify native and prepared application runs against the complete prior audit."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104")
ISOLATED = Path("/srv/bulk/leo-dev/algo07v3-isolation-20261105-runs")
sys.path.insert(0, str(REPO / "reports/2026_11_05_algo07v3_connected_presentation"))
from render import checked, digest  # noqa: E402


def main():
    previous = ROOT / "presentation004/fresh-candidate.json"
    expected = "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    assert digest(previous) == expected
    inputs = {"previous": dict(path=str(previous), sha256=expected)}
    rows = {}
    for name, path in {
        "prepared": ROOT / "engine001/prepared/result.json",
        "native": ROOT / "engine001/native/result.json",
        "isolated_native": ISOLATED / "native/result.json",
    }.items():
        value, receipt = checked(path)
        assert digest(path) == expected
        packet = value["presentation"]["packet"]
        assert packet["position_grid"]["complete"]
        assert packet["position_grid"]["evaluated_points"] == 179
        assert len(value["presentation"]["products"]) == 8
        for figure, sha in value["presentation"]["products"].items():
            actual = path.parent / (figure + ".png")
            published = (
                OUT.parent / "2026_11_05_algo07v3_connected_presentation" / (figure + ".png")
            )
            assert digest(actual) == digest(published) == sha
        timings = receipt["stage_timings"]
        assert len({r["stage"] for r in timings}) == len(timings)
        assert all(r["seconds"] >= 0 for r in timings)
        assert sum(r["seconds"] for r in timings) <= receipt["engine_seconds"]
        rows[name] = dict(
            scope=receipt["scope"],
            engine_seconds=receipt["engine_seconds"],
            qualification_seconds=receipt["seconds"],
            timings=timings,
            stage_seconds=sum(r["seconds"] for r in timings),
            associated={a: r["associated_points"] for a, r in packet["arms"].items()},
            native_points=len(packet["observations"]),
            grid_locations=179,
            exact_scientific_and_png_digest=expected,
        )
        inputs[name] = dict(path=str(path), sha256=digest(path))
        receipt_path = path.with_suffix(".receipt.json")
        inputs[name + "-receipt"] = dict(path=str(receipt_path), sha256=digest(receipt_path))
    isolation_file = ISOLATED / "isolation.json"
    isolation = json.loads(isolation_file.read_text())
    for key in (
        "old_installations_hidden", "old_bulk_data_hidden", "repository_reports_hidden",
        "input_bundle_read_only", "separate_network_namespace",
    ):
        assert isolation[key] is True, key
    bundle = Path(isolation["bundle"])
    manifest_path = bundle / "input-bindings.json"
    assert digest(manifest_path) == isolation["input_manifest_sha256"]
    manifest = json.loads(manifest_path.read_text())
    for name, sha in manifest["files"].items():
        path = (bundle / name).resolve()
        assert path.is_relative_to(bundle.resolve())
        assert digest(path) == sha
    assert manifest["snapshot_count"] == isolation["snapshot_count"] == 38
    inputs["isolation"] = dict(path=str(isolation_file), sha256=digest(isolation_file))
    inputs["isolation-inputs"] = dict(path=str(manifest_path), sha256=digest(manifest_path))
    repeat_path = ROOT / "repeats001/profile.json"
    repeats = json.loads(repeat_path.read_text())
    repeated_output = ROOT / "repeats001/engine/result.json"
    checked(repeated_output)
    assert digest(repeated_output) == expected
    assert repeats["qualification_completed"] is True
    assert repeats["numerical_calls_skipped"] == 0
    assert repeats["probe_sha256"] == digest(REPO / "tools/profile_algo07v3_repeats.py")
    assert repeats["engine_tool_sha256"] == digest(REPO / "tools/check_algo07v3_engine.py")
    for label, path in (
        ("repetition-profile", repeat_path), ("repetition-result", repeated_output),
        ("repetition-receipt", repeated_output.with_suffix(".receipt.json")),
    ):
        inputs[label] = dict(path=str(path), sha256=digest(path))
    (OUT / "repetition-profile.json").write_text(json.dumps(repeats, indent=2) + "\n")
    tests = ROOT / "engine001/tests.xml"
    suite = ET.parse(tests).getroot().find("testsuite")
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    inputs["tests"] = dict(path=str(tests), sha256=digest(tests))
    probe_tests = ROOT / "repeats001/tests.xml"
    probe_suite = ET.parse(probe_tests).getroot().find("testsuite")
    assert all(probe_suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    assert probe_suite.attrib["tests"] == "2"
    inputs["probe-tests"] = dict(path=str(probe_tests), sha256=digest(probe_tests))
    summary = dict(
        cases=rows,
        dataset_case="DS26-0002",
        tests=int(suite.attrib["tests"]),
        probe_tests=int(probe_suite.attrib["tests"]),
        native_to_png_exact=True,
        isolated_native_to_png_exact=True,
        isolation=isolation,
        repetition_probe_exact=True,
        publication_qualified=False,
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
    )
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "artifact-bindings.json").write_text(json.dumps(inputs, indent=2) + "\n")
    table = "| Stage | Prepared-input run (s) | Native-input run (s) |\n|---|---:|---:|\n"
    prepared = {r["stage"]: r["seconds"] for r in rows["prepared"]["timings"]}
    for row in rows["native"]["timings"]:
        name, seconds = row["stage"], row["seconds"]
        before = f"{prepared[name]:.3f}" if name in prepared else "Outside scope"
        table += f"| {name} | {before} | {seconds:.3f} |\n"
    (OUT / "stage-timings.md").write_text(table)
    selected = sorted(rows["native"]["timings"], key=lambda r: -r["seconds"])[:10]
    fig = Figure(figsize=(10, 6), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    bars = ax.barh(
        [r["stage"] for r in selected], [r["seconds"] for r in selected], color="#3076a8"
    )
    ax.invert_yaxis()
    ax.bar_label(bars, fmt="%.1f s", padding=4)
    ax.set_xlim(0, selected[0]["seconds"] * 1.15)
    ax.set_xlabel("Observed seconds, explicit stage clocks (shared host)")
    ax.set_title("DS26-0002 · standalone native ALGO07v3\nLargest ten non-overlapping stages")
    fig.savefig(OUT / "native-stages.png", dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
