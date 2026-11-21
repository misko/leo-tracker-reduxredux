import ctypes as ct
import subprocess
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification import blind_compact_score as score
from tools.pipeline_eval.qualification import portable_verifier_run as stock
from tools.pipeline_eval.qualification.blind_compact_figures import cumulative
from tools.pipeline_eval.qualification.blind_compact_roster import METHODS, select
from tools.pipeline_eval.qualification.blind_compact_run import TRACE
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.qualification.single_scan_position import Factor
from tools.pipeline_eval.qualification.single_scan_trial import Native
from tools.pipeline_eval.qualification.timing_first_position import full_identity
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants import delay_product_native, timing_first_receiver, two_carrier


def test_selection_excludes_entire_previously_used_sessions_and_ignores_order_and_outcomes():
    rows = [dict(id=f"DS29-{i:04}", session_id=f"s{i}", score=i, error=100 - i) for i in range(12)]
    rows += [dict(rows[1], id="other-name"), dict(rows[2], id="duplicate")]
    selected = select(rows, {"DS29-0001"}, 8)
    assert len({r["session_id"] for r in selected}) == 8
    assert all(r["session_id"] != "s1" for r in selected)
    changed = [dict(row, score=1, error=-1) for row in reversed(rows)]
    assert [r["id"] for r in selected] == [r["id"] for r in select(changed, {"DS29-0001"}, 8)]
    with pytest.raises(ValueError, match="too few"):
        select(rows, set(), 13)


def test_cumulative_uses_assignment_and_preserves_ties():
    x, y = cumulative([None, 2.0, 2.0, 1.0], 4, (0.0, 3.0))
    assert x == [0, 1, 2, 2, 3] and y == [0, 0.25, 0.5, 0.75, 0.75]
    assert cumulative([None, None], 2, (0, 1)) == ([0, 1], [0, 0])
    with pytest.raises(ValueError, match="assigned"):
        cumulative([1.0], 2, (0.0, 2.0))


def test_scoring_rejects_missing_or_mutated_predictions_before_a_survey_join(tmp_path, monkeypatch):
    from tools.pipeline_eval.qualification.blind_compact_roster import seal

    monkeypatch.setattr(score, "OUT", tmp_path)
    monkeypatch.setattr(score, "WORK", tmp_path)
    monkeypatch.setattr(score, "read_bound", lambda _: {})
    (tmp_path / "PROTOCOL.md").write_text("protocol")
    case = {"id": "DS26-test", "panel": "DS26", "request": None}
    seal(
        tmp_path / "roster.json",
        dict(
            cases=[dict(case=case, cpu=1, order=METHODS)],
            protocol_sha256=_sha(tmp_path / "PROTOCOL.md"),
        ),
    )
    seal(tmp_path / "build.json", dict(roster_sha256=_sha(tmp_path / "roster.json")))
    monkeypatch.setattr(
        score.corpus, "references", lambda _: pytest.fail("survey opened before freeze")
    )
    with pytest.raises(ValueError, match="still pending"):
        score.score()
    method = tmp_path / "runs" / case["id"] / "original"
    method.mkdir(parents=True)
    folder = method / "attempt-test"
    folder.mkdir()
    (folder / "binding.json").write_text("file changed")
    seal(
        method / "outcome.json",
        dict(
            case=case["id"],
            dataset=case["panel"],
            cpu=1,
            method="original",
            prediction_path=str(folder / "prediction.json"),
            binding_sha256="stale",
            roster_sha256=_sha(tmp_path / "roster.json"),
            build_sha256=_sha(tmp_path / "build.json"),
        ),
    )
    with pytest.raises(ValueError, match="evidence changed"):
        score.score()
    assert not (tmp_path / "prediction-lock.json").exists()


def test_only_request_paths_and_content_identity_may_change(tmp_path):
    case = dict(id="DS29-test")
    native = tmp_path / "native.json"
    native.write_text("{}")
    digest = "sha256:" + _sha(native)
    request = dict(
        source={"sha256": "source"},
        native_manifest="m",
        role="baseline",
        job=dict(
            native_input={},
            identity=dict(session_id="s"),
            evaluation_reference=None,
            output_root="old",
            orbit_archive="original",
        ),
    )
    bound = deepcopy(request)
    job = bound["job"]
    job.update(
        native_input={"path": str(native), "sha256": digest}, output_root=str(tmp_path / "position")
    )
    job["identity"].update(input_sha256=digest, run_id=full_identity(case["id"], bound))
    score.verified_request(case, request, bound, native)
    for key in ("orbit_archive", "evaluation_reference"):
        changed = deepcopy(bound)
        changed["job"][key] = "different"
        with pytest.raises(ValueError, match="changed frozen"):
            score.verified_request(case, request, changed, native)


def test_summaries_pair_by_recording_and_keep_failed_runtime():
    rows = []
    for dataset in ("DS26", "DS29"):
        for arm in ("c0", "fitted_c"):
            for method in METHODS:
                values = (
                    [(1.0, 10.0), (None, 2.0)]
                    if method == "checked"
                    else [(2.0, 25.0), (2.0, 20.0)]
                )
                for i, (error, wall) in enumerate(values):
                    rows.append(
                        dict(
                            case=f"{dataset}-{i}",
                            dataset=dataset,
                            calibration=arm,
                            method=method,
                            error_km=error,
                            fix=error is not None,
                            conditional_rf_rms_hz=99 if error else None,
                            end_to_end_wall_s=wall,
                            hardware_span_s=5.0,
                            acquisition_wall_s=wall * 0.8,
                            solver_wall_s=wall * 0.2,
                            detector_cpu_s=1,
                        )
                    )
    result = next(
        r
        for r in score.summaries(rows)
        if (r["dataset"], r["method"], r["calibration"]) == ("pooled", "checked", "fitted_c")
    )
    assert (result["assigned"], result["fixes"], result["within_1km"], result["lost_fix"]) == (
        4,
        2,
        2,
        2,
    )
    assert result["median_end_to_end_wall_s"] == 6 and result["paired_median_speedup"] == 6.25
    assert result["within_recorded_duration"] == 2
    assert result["fix_within_recorded_duration"] == 0
    assert result["both_return"] == result["closer_on_common"] == 2
    assert result["paired_median_error_change_km"] == -1


def test_baseline_replay_audit_matches_signed_frequency_across_frame_wrap(tmp_path, monkeypatch):
    from tools.pipeline_eval.qualification.blind_compact_roster import seal

    def probe(i, hz=None, epoch=0):
        candidates = (
            []
            if hz is None
            else [
                dict(
                    passed_fractional_margin_gate=True,
                    fractional_margin=0.1,
                    candidate_rank=0,
                    integer_epoch_sample=0,
                    fractional_epoch_offset_samples=epoch,
                    fractional_tracking_cfo_hz=hz,
                )
            ]
        )
        return dict(visit_index=i, receiver_id=0, valid_start_counter=i * 10, candidates=candidates)

    original = [probe(0, -100.3, -0.002), probe(1), probe(2, 80)]
    fresh = [probe(2, -80), probe(0, -100, 13333.002), probe(1, 10)]
    monkeypatch.setattr(
        score,
        "read_bound",
        lambda _: dict(
            source=dict(probes=original, sample_rate_hz=10),
            last_sample_counter=30,
            provenance=dict(
                invalid_capture=1, skipped_fast_score=0, excluded_windows=[{"sample_start": -10}]
            ),
        ),
    )
    monkeypatch.setattr(score, "OUT", tmp_path)
    seal(tmp_path / "native.json", dict(source=dict(probes=fresh)))
    seal(
        tmp_path / "roster.json",
        dict(cases=[dict(case=dict(id="test", panel="DS29", native=None))]),
    )
    (row,) = score.original_replay_parity(
        {("test", "original"): dict(prediction_path=str(tmp_path / "prediction.json"))}
    )
    assert row["paired_probes"] == 3 and row["pass_status_agrees"] == row["both_passed"] == 2
    assert row["strongest_agrees_within_1hz_and_0p01_sample"] == 1
    assert row["hardware_span_s"] == 4


def test_cancellation_export_reproduces_native_peaks_for_signed_two_carrier_iq(tmp_path):
    binary = tmp_path / "receiver.so"
    subprocess.run(
        [
            "cc",
            *timing_first_receiver.FLAGS,
            "-shared",
            "-fPIC",
            "-DLEO_PRESENCE_ITERATIVE_FFT=1",
            "-I",
            str(stock.KERNEL / "native_presence"),
            str(timing_first_receiver.SOURCE.with_name("two_carrier_receiver.c")),
            str(two_carrier.SOURCE),
            str(timing_first_receiver.SOURCE),
            str(delay_product_native.SOURCE),
            *map(str, stock.SOURCES[1:]),
            str(TRACE),
            "-Wl,--wrap=portable_verifier_glrt",
            "-lm",
            "-o",
            str(binary),
        ],
        check=True,
    )
    pilot = qin_edge_pilot_frame(30000000, "lower")
    asset = np.concatenate(
        [
            qin_edge_pilot_frame(10000000, "lower", symbol_roll=r).view("<f4")
            for r in (0, CONTROL_SYMBOL_ROLL)
        ]
        + [delay_product_native.coefficients(4), pilot.view("<f4")]
    ).astype("<f4")
    noise = np.random.default_rng(8005).integers(-100, 101, size=(200000, 2, 2), dtype=np.int16)
    a, _ = unit_wave(pilot, 400, -308000, 143, False)
    b, _ = unit_wave(pilot, 17000, 221000, 201, True)
    raw, clips = mix(noise, 1, [(a, -7), (b, -9)])
    receiver = Native(binary, asset)
    try:
        peaks = receiver.run(SimpleNamespace(samples=raw), -800000, 800000)
        exporter = receiver.lib.cancellation_factors
        exporter.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_double,
            ct.c_double,
            ct.POINTER(Factor),
        ]
        assert not clips and len(peaks[1]) == 2 and not peaks[0]
        for lane in (0, 1):
            factors = (Factor * 2)()
            n = exporter(receiver.ctx, raw.ctypes.data, lane, -800000, 800000, factors)
            assert n == len(peaks[lane])
            for f, p in zip(factors[:n], peaks[lane], strict=True):
                assert (f.rank, f.hz, f.exact - f.control) == (p["rank"], p["hz"], p["margin"])
                assert abs((f.integer + f.offset - p["epoch"] + 6666.5) % 13333 - 6666.5) < 1e-7
    finally:
        receiver.close()
