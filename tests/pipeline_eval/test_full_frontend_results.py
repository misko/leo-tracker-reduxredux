import csv
import gzip

import pytest

from tools.pipeline_eval.__main__ import encoded, references
from tools.pipeline_eval.qualification import full_frontend_results as full


def test_packer_requires_raw_factor_hash_in_position_request(tmp_path):
    run = tmp_path / "replay"
    run.mkdir()
    result = dict(
        status="ok",
        metrics={},
        arms={arm: dict(latlon=[0, 0]) for arm in full.ARMS},
        boundary="Complete recorded IQ to native GLRT and frozen no-repair v5 position",
    )
    (run / "predictions.jsonl").write_bytes(encoded(dict(id="DS26-0122", result=result)))
    (run / "native.json").write_bytes(b"{}")
    (run / "experimental-request.json").write_bytes(
        encoded(
            dict(
                role="baseline",
                job=dict(evaluation_reference=None, native_input=dict(sha256="mismatch")),
            )
        )
    )
    with pytest.raises(ValueError, match="not bound"):
        full.collect([run], tmp_path / "packed")


def test_six_recording_scorer_keeps_missing_fix_and_both_calibrations(tmp_path):
    refs = {r["id"]: r for panel in ("ds26-all159", "roof16") for r in references(panel, None)[1]}
    rows = []
    for case in full.TIMING_IDS:
        metrics = dict(
            recording_windows=4,
            processed_windows=3,
            invalid_capture=1,
            window_delivery_span_s=2,
            detector_cpu_s=0.12,
            raw_and_assembly_wall_s=1.5,
            candidate_s=0.8,
        )
        arms = {arm: dict(latlon=refs[case]["truth"]) for arm in ("c0", "fitted_c")}
        if case == "DS29-0174":
            arms["fitted_c"]["latlon"] = None
        result = dict(arms=arms, boundary="complete IQ to position", status="ok", metrics=metrics)
        rows.append(dict(id=case, result=result, worker_wall_s=2.3))

    def save(records):
        (tmp_path / "positions.jsonl.gz").write_bytes(
            gzip.compress(b"".join(encoded(r) + b"\n" for r in records))
        )

    save(rows)
    full.score(tmp_path)
    with (tmp_path / "distributions.csv").open() as f:
        by_key = {(r["dataset"], r["arm"], r["method"]): r for r in csv.DictReader(f)}
    assert by_key["DS29", "fitted_c", "native"]["attempts"] == "3"
    assert by_key["DS29", "fitted_c", "native"]["fixes"] == "2"
    assert by_key["DS29", "c0", "native"]["within_5_km"] == "3"
    assert len((tmp_path / "position-errors.csv").read_text().splitlines()) == 13
    save(rows[:-1])
    with pytest.raises(ValueError, match="complete fixed timing panel"):
        full.score(tmp_path)
