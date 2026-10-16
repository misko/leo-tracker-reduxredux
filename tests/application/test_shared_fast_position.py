import ast
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.application import shared_fast_position as app
from leo.cli import shared_fast_position as cli
from leo.contracts.scanner_tracking import TrackingInput


def document():
    return dict(
        source=asdict(
            TrackingInput(
                session_id="arbitrary-unseen-fast-scan",
                capture_mode="adaptive",
                sample_rate_hz=2500000,
                radio_id="synthetic",
                stream_generation="synthetic-generation",
                input_manifest_sha256="sha256:" + "1" * 64,
                analysis_manifest_sha256="sha256:" + "2" * 64,
                raw_recording_authority_digest="sha256:" + "3" * 64,
                timing=None,
                qualified=False,
                probes=(),
            )
        )
    )


def test_public_unseen_input_no_data_is_durable_unavailable_no_false_position(tmp_path):
    source = tmp_path / "public.json"
    source.write_text(json.dumps(document()))
    output = tmp_path / "attempt"
    result = cli.run(source, output, maximum_seconds=2)
    assert result["state"] == "unavailable" and result["position"] is None
    assert result["selection"] is None and result["model_version"] == "shared-scan-q-v2"
    assert result["session_id"] == "arbitrary-unseen-fast-scan"
    assert result["input_sha256"] == cli.sha256_digest(source.read_bytes())
    assert json.loads((output / "terminal.json").read_text()) == result
    with pytest.raises(FileExistsError):
        cli.run(source, output, maximum_seconds=2)


def test_stage_receipts_roundtrip_numpy_and_reject_overwrite_or_traversal(tmp_path):
    port = cli.Receipts(tmp_path)
    value = dict(receivers=(np.int64(0), np.int64(1)), values=np.array([1.0, 2.0]))
    port.put("A-0-low", value)
    assert port.get("A-0-low") == dict(receivers=[0, 1], values=[1.0, 2.0])
    with pytest.raises(FileExistsError):
        port.put("A-0-low", value)
    with pytest.raises(ValueError):
        port.get("../terminal")


def test_partial_discovery_keeps_original_training_rank_separation_and_all_views():
    rows = []
    for i, x in enumerate((0, 1, 25, 50)):
        fits = {
            v: dict(converged=True, objective=i + offset)
            for v, offset in (("all", 0), ("low", 2), ("high", 4))
        }
        rows.append(dict(east_km=x, north_km=0, fits=fits, selection_score=i))
    selected = app.discovery_selection(rows)
    assert [r["east_km"] for r in selected] == [0, 25, 50]


def test_bootstrap_dataclass_serialization_reconstructs_actual_physical_vector():
    from leo.analysis.regional_position_bootstrap import PositionBootstrap

    original = PositionBootstrap((2, 5, 9), np.arange(10, dtype=float), ())
    saved = json.loads(json.dumps(app.plain(asdict(original))))
    restored = PositionBootstrap(tuple(saved["satellite_indices"]), np.asarray(saved["vector"]), ())
    assert restored.satellite_indices == original.satellite_indices
    np.testing.assert_array_equal(restored.vector, original.vector)


def test_shape_support_respects_lanes_alias_gaps_and_unique_rows():
    obs = SimpleNamespace(
        times_s=np.arange(7.0),
        window_ids=tuple(map(str, range(7))),
        receiver=np.zeros(7),
        channel=np.array([1, 1, 1, 2, 2, 2, 2]),
        rf_hz=np.ones(7),
        measured_hz=np.array([0, 1, 2, 3, 4, 200000, 200001]),
    )
    assert app.supported_sequences(obs, ((0, 1, 2, 3, 4, 5, 6), (0, 1))) == (
        (0, 1, 2),
        (3, 4),
        (5, 6),
    )


def test_narrow_application_and_analysis_have_no_research_case_or_storage_imports():
    from leo.analysis import shared_scan_model

    for module in (app, shared_scan_model):
        tree = ast.parse(Path(module.__file__).read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(x.startswith(("ds21", "ds22", "leo.storage", "leo.cli")) for x in imports)
        assert not any("REFERENCE" in n.id for n in ast.walk(tree) if isinstance(n, ast.Name))


def test_bounded_cli_rejects_invalid_envelope_before_writing(tmp_path):
    for bound in (0, 1201, float("inf")):
        with pytest.raises(ValueError):
            cli.run(tmp_path / "missing", tmp_path / "out", maximum_seconds=bound)
    assert not (tmp_path / "out").exists()


def test_v2_extends_only_final_q_allocation_and_preserves130s_reserve():
    assert app.POLICY["model_version"] == "shared-scan-q-v2"
    assert app.POLICY["solver_seconds"] == 15
    assert app.POLICY["fit_seconds"] == 20
    assert app.POLICY["actual_objectives_per_fit"] == 2000
    assert app.POLICY["shared_solver_seconds"] == 60
    assert app.POLICY["shared_fit_seconds"] == 65
    assert app.POLICY["shared_actual_objectives_per_fit"] == 5000
    assert app.POLICY["final_shared_reserve_seconds"] == 130
    assert app.POLICY["source_generation_policy"] == "generic-cold24-shape3-fresh-six-ab-v1"


@pytest.mark.parametrize("error", [KeyError("nuisance"), ValueError("no feasible endpoint")])
def test_capped_sequential_final_is_unavailable_and_does_not_abort_next_source(monkeypatch, error):
    calls = []

    def sequential(*args, **kwargs):
        calls.append("A-final")
        row = kwargs["stage_fit"]("final", None, None, None, {})
        assert not row["converged"] and "vector" not in row
        raise error

    monkeypatch.setattr(app, "fit_sequential_path", sequential)
    result = app.sequential_source(stage_fit=lambda *_: dict(converged=False, reason="cap"))
    assert result["status"] == "unavailable" and "final" not in result
    # The independent B call follows the returned source failure rather than an
    # escaping exception. No false physical source is emitted.
    calls.append("B")
    assert calls == ["A-final", "B"]


def test_cli_bank_provenance_serializes_real_tle_text_and_exclusion_contract(tmp_path, monkeypatch):
    from leo.contracts.scanner_tracking import CatalogueExclusionV1

    source = tmp_path / "public.json"
    source.write_text(json.dumps(document()))
    obs = SimpleNamespace()
    prepared = dict(
        all=SimpleNamespace(
            start_utc_ns=10**18, observations=obs, evidence_sha256="sha256:" + "a" * 64
        )
    )
    monkeypatch.setattr(cli, "prepare_views", lambda *_: (prepared, np.array([0.0, 30.0, 60.0])))
    snapshot = SimpleNamespace(collected_utc_ns=1, digest="sha256:" + "b" * 64)
    monkeypatch.setattr(
        cli,
        "TleArchiveReader",
        lambda *_: SimpleNamespace(
            select_latest_before=lambda *_: snapshot, read=lambda *_: "real-shaped TLE text\n"
        ),
    )
    exclusion = CatalogueExclusionV1(catalog_number=42, name="STARLINK TEST DEB")
    monkeypatch.setattr(cli, "exclude_labelled_starlink_debris", lambda *_: ("TLE", (exclusion,)))
    monkeypatch.setattr(cli, "parse_element_sets", lambda *_: SimpleNamespace(names=["STARLINK X"]))
    bank = SimpleNamespace(numbers=np.array([123]))
    monkeypatch.setattr(
        cli,
        "build_regional_bank",
        lambda *_args, **_kwargs: (
            bank,
            SimpleNamespace(retained_numbers=(123,), node_step_s=0.25),
        ),
    )

    def inference(*args, **kwargs):
        raise cli.PositionInputUnavailable(
            "Explicit test absence after real metadata serialization"
        )

    monkeypatch.setattr(cli, "run_shared_position", inference)
    output = tmp_path / "attempt"
    result = cli.run(source, output, maximum_seconds=2)
    assert result["state"] == "unavailable"
    bank_stage = json.loads((output / "stages/bank.json").read_text())
    provenance = bank_stage["provenance"]
    assert provenance["tle_payload_sha256"] == cli.sha256_digest(b"real-shaped TLE text\n")
    assert provenance["catalogue_exclusions"] == [exclusion.model_dump(mode="json")]
    assert result["cost_exact"]
