"""Verify isolated native-to-publication evidence and the unchanged WebUI routes."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = Path("/srv/bulk/leo-dev/algo07v3-publication-20261105")
sys.path.insert(0, str(REPO / "reports/2026_11_05_algo07v3_connected_presentation"))
from render import digest  # noqa: E402

from leo.api.fast_standard_analysis import standard_analysis_router  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.storage import localization_v3_codec  # noqa: E402
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore  # noqa: E402
from leo.storage.localization_v3 import LocalizationV3Store  # noqa: E402


def main():
    expected = "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    receipt = json.loads((RUN / "result.receipt.json").read_text())
    assert digest(RUN / "result.json") == receipt["output_sha256"]
    for name, row in receipt["modules"].items():
        assert digest(RUN / "source" / (name + ".py")) == row["sha256"]
    assert digest(RUN / "source/qualification-tool.py") == receipt["tool"]["sha256"]
    for path, sha in receipt["inputs"].items():
        assert digest(path) == sha
    result = json.loads((RUN / "result.json").read_text())
    assert receipt["output_sha256"] == expected
    run_id = receipt["publication"]["run_id"]
    scientific = LocalizationV3Store(RUN / "publication")
    public = FastStandardAnalysisStore(RUN / "publication")
    loaded = scientific.load(run_id)
    assert loaded["sha256"] == receipt["scientific_receipt"]["sha256"]
    assert loaded["receipt"] == receipt["scientific_receipt"]["receipt"]
    config = json.loads((RUN / "configuration.json").read_text())
    assert canonical_digest(config["configuration"]) == config["sha256"]
    assert loaded["evidence"]["provenance"]["configuration_sha256"] == config["sha256"]
    assert loaded["evidence"]["provenance"]["modules"] == receipt["modules"]
    assert loaded["evidence"]["provenance"]["implementation_sha256"] == canonical_digest(
        {k: v["sha256"] for k, v in receipt["modules"].items()}
    )
    isolation = json.loads((RUN / "isolation.json").read_text())
    for key in (
        "old_installations_hidden",
        "old_bulk_data_hidden",
        "repository_reports_hidden",
        "input_bundle_read_only",
        "separate_network_namespace",
    ):
        assert isolation[key] is True
    bundle = Path("/srv/bulk/leo-dev/algo07v3-isolation-20261105")
    assert digest(bundle / "input-bindings.json") == isolation["input_manifest_sha256"]
    inputs = json.loads((bundle / "input-bindings.json").read_text())
    for name, sha in inputs["files"].items():
        source = (bundle / name).resolve()
        assert source.is_relative_to(bundle)
        assert digest(source) == sha

    app = FastAPI()
    app.include_router(standard_analysis_router(public))
    client = TestClient(app)
    url = f"/api/v2/fast-scans/{run_id}/standard-analysis"
    response = client.get(url)
    assert response.status_code == 200
    detail = response.json()
    assert detail["state"] == "complete"
    assert detail["arms"]["c0"]["associated_points"] == 2783
    assert detail["arms"]["fitted_c"]["associated_points"] == 2783
    artifacts = {}
    for row in detail["artifacts"]:
        name, sha = row["name"], row["sha256"]
        response = client.get(url + f"/{name}.png", params=dict(sha256=sha))
        assert response.status_code == 200 and response.content == loaded["pngs"][name]
        actual = hashlib.sha256(response.content).hexdigest()
        assert sha == "sha256:" + actual
        assert actual == result["presentation"]["products"][name]
        previous = OUT.parent / "2026_11_05_algo07v3_connected_presentation" / (name + ".png")
        assert digest(previous) == actual
        assert (
            client.get(url + f"/{name}.png", params=dict(sha256="sha256:stale")).status_code == 404
        )
        artifacts[name] = dict(sha256=actual, bytes=len(response.content), HTTP_status=200)
    for name, value in (
        ("position-grid", public.position_grid(run_id)),
        ("position-path", public.position_path(run_id)),
    ):
        response = client.get(url + f"/{name}.json")
        assert response.status_code == 200 and response.json() == value
        assert value["binding"]["terminal_sha256"] == loaded["sha256"]
    assert public.position_grid(run_id)["complete"]
    assert public.position_grid(run_id)["evaluated_points"] == 179

    # The adapter owns this path. Reading its archive statistics is report-only,
    # not a runtime dependency or an application-to-storage path construction.
    archive_path = next((RUN / "publication/localization-v3-v1" / run_id).glob("*.zip"))
    with zipfile.ZipFile(archive_path) as archive:
        png_digests = {row["sha256"] for row in artifacts.values()}
        members = archive.infolist()
        arrays = [
            m for m in members if m.filename != "values.json" and m.filename not in png_digests
        ]
        metadata = archive.getinfo("values.json")
        sizes = dict(
            archive_bytes=archive_path.stat().st_size,
            distinct_npy_entries=len(arrays),
            array_bytes=sum(m.file_size for m in arrays),
            metadata_uncompressed_bytes=metadata.file_size,
            metadata_compressed_bytes=metadata.compress_size,
            png_bytes=sum(row["bytes"] for row in artifacts.values()),
        )
    suite = ET.parse(RUN / "tests.xml").getroot().find("testsuite")
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    assert int(suite.attrib["tests"]) == 587
    inline_suite = ET.parse(RUN / "inline-tests.xml").getroot().find("testsuite")
    assert all(inline_suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    assert inline_suite.attrib["tests"] == "588"
    benchmark = json.loads((RUN / "codec-abba.json").read_text())
    assert benchmark["candidate_codec"]["sha256"] == digest(localization_v3_codec.__file__)
    assert benchmark["reference_codec"]["sha256"] == digest(benchmark["reference_codec"]["path"])
    assert benchmark["tool_sha256"] == digest(REPO / "tools/benchmark_algo07v3_evidence.py")
    assert benchmark["source_receipt"]["sha256"] == digest(RUN / "result.receipt.json")
    assert [r["side"] for r in benchmark["rows"]] == [
        "reference",
        "candidate",
        "candidate",
        "reference",
    ]
    assert all(r["all_fields_exact"] and r["all_pngs_exact"] for r in benchmark["rows"])
    means = {
        side: {
            key: sum(r[key] for r in benchmark["rows"] if r["side"] == side) / 2
            for key in ("pack_seconds", "unpack_seconds", "total_seconds", "bytes")
        }
        for side in ("reference", "candidate")
    }
    codec_speedup = means["reference"]["total_seconds"] / means["candidate"]["total_seconds"]
    optimized = json.loads((RUN / "inline-publication.json").read_text())
    assert optimized["codec_sha256"] == benchmark["candidate_codec"]["sha256"]
    assert optimized["script_sha256"] == digest(OUT / "replay.py")
    assert optimized["source_receipt_sha256"] == digest(RUN / "result.receipt.json")
    improved = LocalizationV3Store(RUN / "inline-publication").load(run_id)
    assert improved["sha256"] == optimized["scientific_receipt"]["sha256"]
    candidate = next(r for r in benchmark["rows"] if r["side"] == "candidate")
    assert improved["receipt"]["result_sha256"] == "sha256:" + candidate["raw_sha256"]
    improved_public = FastStandardAnalysisStore(RUN / "inline-publication")
    for name, png in loaded["pngs"].items():
        assert improved_public.artifact(run_id, name) == png
    assert improved_public.position_grid(run_id)["complete"]
    assert improved_public.position_path(run_id)["binding"]["terminal_sha256"] == improved["sha256"]
    (OUT / "codec-abba.json").write_text(json.dumps(benchmark, indent=2) + "\n")
    timings = {k: v for k, v in receipt.items() if k.endswith("seconds")}
    assert (
        abs(
            sum(
                timings[k]
                for k in (
                    "native_to_render_seconds",
                    "evidence_projection_seconds",
                    "scientific_save_seconds",
                    "UI_publication_seconds",
                )
            )
            - timings["native_to_publication_seconds"]
        )
        < 1e-6
    )
    summary = dict(
        case="DS26-0002",
        exact_science_and_pngs=True,
        expected_sha256=expected,
        tests=588,
        original_native_run_tests=587,
        artifact_count=len(artifacts),
        grid_locations=179,
        isolation=isolation,
        archive=sizes,
        timings=timings,
        codec_means=means,
        codec_only_speedup=codec_speedup,
        optimized_publication_only_seconds=optimized["total_seconds"],
        candidate_native_publication_completed=True,
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
        production_execution_qualified=False,
        deployed=False,
    )
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    bindings = {
        name: dict(path=str(RUN / name), sha256=digest(RUN / name))
        for name in (
            "result.json",
            "result.receipt.json",
            "configuration.json",
            "isolation.json",
            "tests.xml",
            "inline-tests.xml",
            "inline-publication.json",
            "codec-abba.json",
        )
    }
    bindings["scientific_archive"] = dict(path=str(archive_path), sha256=digest(archive_path))
    (OUT / "artifact-bindings.json").write_text(json.dumps(bindings, indent=2) + "\n")
    (OUT / "HTTP-artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    names = [
        "Native GLRT → PNGs",
        "Evidence projection",
        "Scientific archive save",
        "Verify and publish UI",
    ]
    values = [
        timings[k]
        for k in (
            "native_to_render_seconds",
            "evidence_projection_seconds",
            "scientific_save_seconds",
            "UI_publication_seconds",
        )
    ]
    fig = Figure(figsize=(10, 7), layout="constrained")
    FigureCanvasAgg(fig)
    axes = fig.subplots(2, 1)
    for ax, labels, seconds in ((axes[0], names, values), (axes[1], names[1:], values[1:])):
        bars = ax.barh(labels, seconds, color="#3076a8")
        ax.invert_yaxis()
        ax.bar_label(bars, fmt="%.2f s", padding=3)
        ax.set_xlim(0, max(seconds) * 1.2)
        ax.set_xlabel("Wall seconds · unpaired observation")
    axes[0].set_title("Native input → publication: 477.36 s")
    axes[1].set_title("Publication portion enlarged")
    fig.savefig(OUT / "publication-timing.png", dpi=160)
    fig = Figure(figsize=(7, 4), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    labels = ["Prototype scalar blobs", "Inline scalar bytes"]
    pack = [means[s]["pack_seconds"] for s in ("reference", "candidate")]
    unpack = [means[s]["unpack_seconds"] for s in ("reference", "candidate")]
    ax.barh(labels, pack, label="Encode", color="#3076a8")
    bars = ax.barh(labels, unpack, left=pack, label="Decode", color="#65aa98")
    ax.bar_label(
        bars, labels=[f"{p + u:.2f} s" for p, u in zip(pack, unpack, strict=True)], padding=4
    )
    ax.invert_yaxis()
    ax.set_xlim(0, means["reference"]["total_seconds"] * 1.2)
    ax.set_xlabel("Mean wall seconds · ABBA · same completed scientific state")
    ax.set_title(f"Serialization only: {codec_speedup:.2f}× faster · all fields/PNGs exact")
    ax.legend()
    fig.savefig(OUT / "codec-timing.png", dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
