import hashlib
import os
import shutil
import sys
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import projector_roof as roof
from tools.pipeline_eval.scoring import ARMS


def test_roof_scoring_preserves_frozen_roster_and_counts_failed_fix():
    refs = roof.roster()
    ids26 = [r["id"] for r in refs if r["group"] == "DS26"]
    ids29 = [r["id"] for r in refs if r["group"] == "DS29"]
    assert hashlib.sha256("\n".join(ids26).encode()).hexdigest() == (
        "4a92e0abf550a9c55cc1bd4836f927bdcb5269e4d8b011af77241bc0a3eeb784"
    )
    assert ids29 == [
        "DS29-0082",
        "DS29-0127",
        "DS29-0174",
        "DS29-0247",
        "DS29-0316",
        "DS29-0357",
        "DS29-0519",
        "DS29-0604",
    ]
    records, archive = {}, {}
    for ref in refs:
        ident = ref["id"]
        points = ref["reference"]["baseline"]
        cavity = {arm: dict(latlon=points[arm]["latlon"], conditional_rms_hz=73.0) for arm in ARMS}
        archive[ident] = (ref, "confirmation", {"stages": {"cavity": cavity, "final": cavity}})
        result = dict(status="ok", boundary="test cavity", metrics={}, arms=points)
        if ident == "DS26-0002":
            result = dict(status="timed_out", reason="deadline", boundary="worker", metrics={})
        records[ident] = dict(id=ident, result=result, source="confirmation")

    for bad in (
        {k: v for k, v in records.items() if k != "DS26-0002"},
        {**records, "DS26-0020": records["DS26-0002"]},
        {**records, "DS26-0002": records["DS26-0004"]},
    ):
        with pytest.raises(ValueError, match="frozen recording roster"):
            roof.comparison_rows(refs, bad, archive)

    rows = roof.comparison_rows(refs, records, archive)
    assert len(rows) == 270
    failure = [row for row in rows if row["recording"] == "DS26-0002"]
    assert len(failure) == 2
    assert all(
        r["status"] == "timed_out"
        and r["orbit_projector_error_km"] is None
        and r["cavity_coordinate_delta_m"] is None
        and r["baseline_error_km"] is not None
        for r in failure
    )
    by_method = {(r["dataset"], r["arm"], r["method"]): r for r in roof.distribution_rows(rows)}
    for arm in ARMS:
        ds26 = by_method["DS26", arm, roof.METHOD]
        assert (ds26["scheduled"], ds26["published"]) == (127, 126)
        assert ds26["coordinate_comparisons"] == 126
        assert ds26["max_coordinate_delta_m"] == 0
        assert not ds26["passes_no_repair_v5_10pct"]
        assert by_method["DS29", arm, roof.METHOD]["published"] == 8
        assert by_method["DS26", arm, "baseline"]["median_conditional_rms_hz"] == 73.0
        assert by_method["DS26", arm, "baseline"]["median_original_report_rms_hz"] != 73.0
        assert by_method["DS26", arm, "selective-gap"]["conditional_rms_recordings"] == 0


def test_prediction_reuse_rejects_different_input_module_or_kernel():
    case = {"id": "DS26-0036", "native_sha256": "the frozen native digest"}
    module, kernel = hashes = roof.source_hashes()
    record = dict(
        id=case["id"],
        input_sha256=roof.input_hash(case),
        implementation_sha256=module,
        result=dict(
            status="ok",
            boundary=roof.orbit_projector.BOUNDARY,
            metrics={"kernel_sha256": kernel},
            arms={arm: {"latlon": [37.85, -122.49]} for arm in ARMS},
        ),
    )
    assert roof.validate_prediction(record, hashes, case=case) == record
    changed_case = dict(case, native_sha256="a different native digest")
    with pytest.raises(ValueError, match="frozen request"):
        roof.validate_prediction(record, hashes, case=changed_case)

    forged_module = dict(record, implementation_sha256="0" * 64)
    forged_kernel = deepcopy(record)
    forged_kernel["result"]["metrics"]["kernel_sha256"] = "0" * 64
    for forged in (forged_module, forged_kernel):
        with pytest.raises(ValueError, match="provenance differs"):
            roof.validate_prediction(forged, hashes, case=case)

    missing_kernel = deepcopy(record)
    missing_kernel["result"]["metrics"].pop("kernel_sha256")
    with pytest.raises(ValueError, match="provenance differs"):
        roof.validate_prediction(missing_kernel, hashes, case=case, allow_failure=True)


def test_score_only_rebuilds_csvs_and_catches_archive_tampering(tmp_path, monkeypatch):
    receipts = tmp_path / "previous"
    receipts.mkdir()
    for name in (roof.TIMING_RECEIPT, roof.STRESS_RECEIPT):
        shutil.copyfile(roof.REPORT / name, receipts / name)
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    for name in ("development.jsonl.gz", "confirmation.jsonl.gz"):
        shutil.copyfile(roof.CHECKPOINTS / name, checkpoints / name)

    for name in (roof.PREDICTIONS, roof.ARCHIVE_RECEIPT):
        shutil.copyfile(roof.REPORT / name, tmp_path / name)
    monkeypatch.setattr(roof, "load_cases", lambda *args: pytest.fail("opened the native archive"))
    monkeypatch.setattr(roof, "source_hashes", lambda: pytest.fail("opened live scorer sources"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "projector_roof",
            "--score-only",
            "--out",
            str(tmp_path),
            "--receipts",
            str(receipts),
            "--checkpoints",
            str(checkpoints),
        ],
    )
    roof.main()
    comparison = tmp_path / "roof-comparison.csv"
    distributions = tmp_path / "roof-distributions.csv"
    expected = tuple((roof.REPORT / file.name).read_bytes() for file in (comparison, distributions))
    assert (comparison.read_bytes(), distributions.read_bytes()) == expected
    assert len(expected[0].splitlines()) == 271
    assert len(expected[1].splitlines()) == 37
    comparison.unlink()
    distributions.unlink()
    roof.main()
    assert (comparison.read_bytes(), distributions.read_bytes()) == expected

    with (receipts / roof.STRESS_RECEIPT).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="roof archive digest differs for stress"):
        roof.main()


def test_fresh_panel_reruns_seven_stale_cases_and_rescores_as_current(tmp_path, monkeypatch):
    receipts = tmp_path / "historical"
    receipts.mkdir()
    for name in (roof.TIMING_RECEIPT, roof.STRESS_RECEIPT):
        shutil.copyfile(roof.REPORT / name, receipts / name)
    archive = roof.read_archive_receipt(roof.REPORT / roof.ARCHIVE_RECEIPT)
    historical = archive["implementation_sha256"], archive["kernel_sha256"]
    hashes = "0" * 64, historical[1]
    assert hashes != historical
    refs = [{"id": ident} for ident in roof.SOURCES]
    cases = {entry["id"]: entry for entry in refs}
    measured = []
    monkeypatch.setattr(roof, "source_hashes", lambda: hashes)
    monkeypatch.setattr(roof, "load_cases", lambda *args: cases)

    def measure(method, case, *_):
        assert method == roof.METHOD
        measured.append(case["id"])
        return dict(
            id=case["id"],
            input_sha256=roof.input_hash(case),
            implementation_sha256=hashes[0],
            worker_wall_s=0.01,
            result=dict(
                status="ok",
                boundary=roof.orbit_projector.BOUNDARY,
                metrics={"kernel_sha256": hashes[1]},
                arms={arm: dict(latlon=[37.85, -122.49]) for arm in ARMS},
            ),
        )

    monkeypatch.setattr(roof, "run_one", measure)
    cpu = min(os.sched_getaffinity(0))
    work = tmp_path / "work"
    historical_journal = work / "predictions"
    historical_journal.mkdir(parents=True)
    ident = roof.TIMING_IDS[0]
    old_record = roof.reuse(receipts, historical)[ident]
    old_journal_file = historical_journal / f"{ident}.json"
    old_journal_file.write_bytes(roof.encoded(old_record))

    def run():
        return roof.run_panel(refs, work, receipts, tmp_path / "cache", [cpu], 1)

    records, confirmed = run()
    assert confirmed == hashes
    assert measured == list(roof.SOURCES)
    assert all(record["source"] == "confirmation" for record in records.values())
    assert old_journal_file.read_bytes() == roof.encoded(old_record)
    assert roof.encoded(run()[0]) == roof.encoded(records)
    assert len(measured) == len(roof.SOURCES)

    monkeypatch.setattr(roof, "publish_scores", lambda *args: None)
    roof.save_archive(tmp_path, refs, records, receipts, roof.CHECKPOINTS, hashes)
    roof.rescore_archive(tmp_path, refs, receipts, roof.CHECKPOINTS)

    forged = dict(records[ident], implementation_sha256=historical[0])
    roof.save_archive(
        tmp_path, refs, {**records, ident: forged}, receipts, roof.CHECKPOINTS, hashes
    )
    with pytest.raises(ValueError, match="implementation or kernel provenance differs"):
        roof.rescore_archive(tmp_path, refs, receipts, roof.CHECKPOINTS)

    (new_journal_file,) = (work / "versions").glob(f"*/predictions/{ident}.json")
    new_journal_file.write_bytes(roof.encoded(forged))
    with pytest.raises(ValueError, match="implementation or kernel provenance differs"):
        run()

    with (receipts / roof.TIMING_RECEIPT).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="roof archive digest differs for projector-pairs"):
        roof.run_panel(refs, tmp_path / "corrupt", receipts, tmp_path / "cache", [cpu], 1)
    assert len(measured) == len(roof.SOURCES)


def test_same_version_must_match_the_original_reused_result(tmp_path):
    refs = roof.roster()
    archive = roof.read_archive_receipt(roof.REPORT / roof.ARCHIVE_RECEIPT)
    hashes = archive["implementation_sha256"], archive["kernel_sha256"]
    reused = roof.reuse(roof.REPORT, hashes, rerun_stale=True)
    assert set(reused) == set(roof.SOURCES)

    predictions = roof.read_predictions(roof.REPORT / roof.PREDICTIONS)
    ident = roof.TIMING_IDS[0]
    different = deepcopy(predictions[ident])
    different["result"]["arms"]["c0"]["latlon"][0] += 0.001
    roof.save_archive(
        tmp_path,
        refs,
        {**predictions, ident: different},
        roof.REPORT,
        roof.CHECKPOINTS,
        hashes,
    )
    with pytest.raises(ValueError, match=f"{ident} roof prediction differs from the reused result"):
        roof.rescore_archive(tmp_path, refs, roof.REPORT, roof.CHECKPOINTS)
