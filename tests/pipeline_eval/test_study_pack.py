import csv
import json
from hashlib import sha256
from zipfile import ZipFile

import pytest
from PIL import Image

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import study_pack


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def positions(folder):
    binding = sha256(b"observations").hexdigest()
    results = {
        "position": [
            dict(
                status="ok",
                boundary="sealed observations to position",
                metrics={"c0_frequency_score": 9.5},
                arms={
                    "c0": {"latlon": [0.01, 0], "rf_rms_hz": 25},
                    "fitted_c": {"latlon": None, "status": "unavailable", "reason": "single RF"},
                },
            ),
            dict(status="timed_out", reason="Fit deadline", boundary="Fit", metrics={}),
        ],
        "detector": [dict(status="ok", boundary="IQ", metrics={"position_attempted": False})] * 2,
    }
    cases = ["one", "two"]
    queries = [
        dict(
            id=case,
            condition="held",
            recording=case,
            truth=[0, 0],
            bindings={"input_sha256": binding},
        )
        for case in cases
    ]
    charts, rows = [], []
    for ident, outcomes in results.items():
        charts.append(
            dict(
                id=ident,
                method=ident,
                scope="transfer",
                title=f"A held {ident} test",
                caption="Two scheduled recordings.",
                cases="sealed",
                seal="result-lock.json",
                queries="queries.json",
                series=[dict(key="candidate", label="Candidate", file="rows.jsonl", value=ident)],
            )
        )
        rows.extend(
            dict(id=case, method=ident, input_sha256=binding, result=result)
            for case, result in zip(cases, outcomes, strict=True)
        )
    cli.save_json(folder / "queries.json", {"queries": queries})
    cli.write(folder / "rows.jsonl", b"\n".join(cli.encoded(row) for row in rows))
    cli.save_json(folder / "figures.json", dict(version=2, charts=charts))
    cli.save_json(
        folder / "result-lock.json",
        dict(
            cases=cases,
            files={name: digest(folder / name) for name in ("queries.json", "rows.jsonl")},
        ),
    )


def stage(folder, *, ident="timing", sealed=True, image="measurement.png"):
    spec = dict(
        version=1,
        id=ident,
        title="Detector timing",
        sample="One recording",
        boundary="IQ to detector",
        note="Wall-clock measurement.",
        seal="timing-lock.json",
        image=image,
        csv="measurement.csv",
    )
    cli.save_json(folder / "stage-figure.json", spec)
    if sealed:
        Image.new("RGB", (100, 80), "white").save(folder / image)
        cli.write(folder / spec["csv"], b"recording,wall_ms\none,10\n")
        cli.save_json(
            folder / spec["seal"],
            dict(files={name: digest(folder / name) for name in (image, spec["csv"])}),
        )


def test_pack_discovers_root_and_nested_evidence_and_preserves_outcomes(tmp_path):
    source = tmp_path / "trial"
    positions(source)
    stage(source / "arbitrary-scope" / "nested")
    stage(source / "awaiting-receipt", ident="pending", sealed=False)
    out = source / "benchmark"
    assert cli.main(["benchmark", "--study", str(source), "--pack", "--out", str(out)]) == 0
    assert not (source / "index.html").exists()
    evidence = json.loads((out / "study-evidence.json").read_bytes())
    assert evidence["studies"] == {
        ".": {"position_charts": ["position"], "stage_charts": []},
        "arbitrary-scope": {"position_charts": [], "stage_charts": ["timing"]},
        "awaiting-receipt": {"position_charts": [], "stage_charts": []},
    }
    assert [row["state"] for row in evidence["descriptors"]["figures.json"]] == [
        "exported",
        "stage_only",
    ]
    assert evidence["descriptors"]["awaiting-receipt/stage-figure.json"][0]["state"] == "unsealed"
    assert len(evidence["source_sha256"]) == 5
    assert all(digest(source / path) == hash_ for path, hash_ in evidence["source_sha256"].items())
    assert 'href="../result-lock.json"' in (out / "index.html").read_text()
    with ZipFile(out / study_pack.pack.ZIP) as bundle:
        assert b"one,10" in bundle.read("stage-charts/timing.csv")
        summary = list(csv.DictReader(bundle.read("summary.csv").decode().splitlines()))
        assert [
            (r["arm"], r["scheduled"], r["published"], r["timed_out"], r["unavailable"])
            for r in summary
        ] == [
            ("c0", "2", "1", "1", "0"),
            ("fitted_c", "2", "0", "1", "1"),
        ]
        scores = list(csv.DictReader(bundle.read("position-rf.csv").decode().splitlines()))
        assert (scores[0]["rf_rms_hz"], scores[0]["frequency_score"]) == ("25", "9.5")
        assert summary[1]["median_km"] == summary[1]["rf_p50_hz"] == ""
        checksums = json.loads(bundle.read("artifact-sha256.json"))["files"]
        assert all(
            sha256(bundle.read(path)).hexdigest() == hash_ for path, hash_ in checksums.items()
        )
    with pytest.raises(ValueError, match="new output directory"):
        study_pack.run(source, out)
    copy = tmp_path / "copy"
    study_pack.run(source, copy)
    assert digest(copy / study_pack.pack.ZIP) == digest(out / study_pack.pack.ZIP)


def test_stage_only_pack_and_invalid_stage_paths(tmp_path):
    source = tmp_path / "trial"
    stage(source)
    stage(source / "nested", ident="pending", sealed=False, image="../escape.png")
    out = tmp_path / "benchmark"
    with pytest.raises(ValueError, match="name a file within"):
        study_pack.run(source, out)
    assert not out.exists()
    stage(source / "nested", ident="pending", sealed=False)
    cli.write(source / "measurement.csv", b"recording,wall_ms\none,11\n")
    with pytest.raises(ValueError, match="assets differ from the sealed stage results"):
        study_pack.run(source, out)
    assert not out.exists()
    stage(source)
    study_pack.run(source, out)
    with ZipFile(out / study_pack.pack.ZIP) as bundle:
        assert "stage-charts/timing.png" in bundle.namelist()
        assert "summary.csv" not in bundle.namelist()
        assert "positions.csv" not in bundle.namelist()


def test_duplicate_chart_and_aliased_descriptor_are_rejected(tmp_path):
    source = tmp_path / "trial"
    positions(source)
    stage(source / "arbitrary", ident="position", sealed=False)
    out = tmp_path / "benchmark"
    with pytest.raises(ValueError, match="duplicate study chart IDs"):
        study_pack.run(source, out)
    (source / "aliased").mkdir()
    (source / "aliased" / "figures.json").symlink_to(source / "figures.json")
    with pytest.raises(ValueError, match="regular local file"):
        study_pack.run(source, out)
    assert not out.exists()


def test_pack_requires_study_selector():
    with pytest.raises(SystemExit):
        cli.main(["benchmark", "--pack", "--receiver", "receiver-deadline"])
