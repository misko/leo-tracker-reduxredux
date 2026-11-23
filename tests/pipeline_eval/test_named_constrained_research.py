import ast
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

import named_constrained_research as cli
from leo.contracts.digests import canonical_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def nodes(path):
    return {
        node.name if isinstance(node, (ast.ClassDef, ast.FunctionDef)) else node.targets[0].id: ast.dump(node)
        for node in ast.parse(path.read_text()).body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        or isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }


def test_portable_exact_gate_has_the_measured_arithmetic_and_source_checks():
    measured = nodes(cli.HERE / "stock_exact_gate_0402.py")
    noise = nodes(cli.HERE / "exact_noise_gate_0402.py")
    portable = nodes(cli.HERE / "prepared_constrained_checks.py")
    assert set(portable) == {
        "PreparedNoiseScreen", "WhiteProfile", "GateWork", "gate_binding", "validate_released_ports", "RELEASE_SOURCES"
    }
    assert portable == {key: (measured | noise)[key] for key in portable}


def flags(tmp_path):
    return ["--recording", str(tmp_path / "original"), "--archive", str(tmp_path),
            "--region", str(tmp_path / "offer.json"), "--output", str(tmp_path / "output")]


def test_default_is_stock_and_fitted_first_is_explicit(tmp_path):
    request = flags(tmp_path)
    assert cli.options(request).constrained == "stock"
    assert cli.options([*request, "--constrained", "fitted-first"]).constrained == "fitted-first"


@pytest.mark.parametrize("extra", [["--saved", "file"], ["--saved-digest", "invalid"], ["--saved-inventory", "file"]])
def test_saved_options_fail_closed(tmp_path, extra):
    with pytest.raises(SystemExit):
        cli.options([*flags(tmp_path), *extra])
    assert not (tmp_path / "output").exists()


def test_explicit_region_required_even_when_the_environment_has_a_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGO08_REGION_FILE", str(tmp_path / "offer.json"))
    request = flags(tmp_path)
    with pytest.raises(SystemExit):
        cli.options(request[:4] + request[6:])
    assert not (tmp_path / "output").exists()


def test_input_digest_failure_precedes_output_creation(tmp_path):
    (tmp_path / "offer.json").write_text("{}")
    (tmp_path / "packet").write_text("{}")
    request = cli.options([*flags(tmp_path), "--saved", str(tmp_path / "packet"), "--saved-digest", "0"*64])
    with pytest.raises(ValueError, match="Unreviewed bootstrap input"):
        cli.run(request)
    assert not request.output.exists()


def test_inventory_only_authorizes_the_original_recording_and_metadata(tmp_path):
    req = cli.options(flags(tmp_path))
    inventory = dict(recording_name=req.recording.name, window_count=1,
                     segments=[dict(windows=1, path=str(req.recording / "sealed"))])
    inv = tmp_path / "inventory.json"
    inv.write_text(json.dumps(inventory))
    digest = canonical_digest(inventory)
    session = "fast-" + digest[7:39]
    reader = cli.inventory_binding(req.recording, inv, session, digest)
    assert reader(object(), req.recording, verify_windows=False) == (session, digest, inventory)
    with pytest.raises(ValueError, match="metadata"):
        reader(object(), req.recording)
    with pytest.raises(ValueError, match="metadata"):
        reader(object(), req.recording.parent / "other", verify_windows=False)
    with pytest.raises(ValueError, match="original recording"):
        cli.inventory_binding(req.recording, inv, session, "sha256:"+"0"*64)
    inventory["segments"][0]["path"] = str(req.recording / ".." / "other")
    invalid = canonical_digest(inventory)
    inv.write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="original recording"):
        cli.inventory_binding(req.recording, inv, "fast-"+invalid[7:39], invalid)


def test_nomination_observation_respects_original_no_offer_and_returns_same_object():
    result = dict(status="complete", families=[dict(best=None, predictive_gain=2.0),
                                               dict(best=object(), predictive_gain=0.0)])
    observations = []
    observed = cli.observe_nominations(lambda: result, observations)
    assert observed() is result
    assert observations == [dict(status="complete", families=2, positive_offers=0)]
    result["families"][1]["predictive_gain"] = 0.01
    assert observed() is result
    assert observations[-1]["positive_offers"] == 1


def test_genuine_named_withheld_preserves_identity_reason_and_empty_media(tmp_path, monkeypatch):
    # The byte-pinned named DS30-0227 stock withholding has no trailing line break.
    archived = (Path(__file__).parent / "constrained-cli-withheld-0227.json").read_bytes().rstrip(b"\n")
    assert sha256(archived).hexdigest() == "c7b876c0e3a6633cce62f78043ac2d4eb2ccccd6accc23b0ed50659107b77e99"
    released = json.loads(archived)
    offer = tmp_path / "offer.json"
    offer.write_text(json.dumps(released["region"]))

    request = cli.options(flags(tmp_path))

    def archived_publication(args, *, optimized, saved, expected, analysis_scope):
        assert not optimized
        assert saved is expected is None
        store = FastStandardAnalysisStore(args.bulk_root)
        folder = store.folder(released["run_id"])
        folder.mkdir(parents=True)
        (folder / "withheld.json").write_bytes(archived)
        pub = dict(run_id=released["run_id"], decision=released["state"], terminal_sha256=released["terminal_sha256"])
        (args.bulk_root / "named-weak-exact.json").write_text(json.dumps(dict(
            publication=pub, frozen_specification="installed", detector_sha256="f"*64
        )))

    monkeypatch.setattr(cli, "named_publication", archived_publication)
    cli.run(request)
    receipt = json.loads((request.output / "named-constrained-research.json").read_text())
    assert receipt["publication"]["decision"] == "withheld"
    assert receipt["selected_rows"] == {}
    assert receipt["raw_authority"] == released["raw_authority"]
    assert receipt["named_input_sha256"] == released["input_sha256"]
    store = FastStandardAnalysisStore(request.output)
    detail = store.detail(released["run_id"])
    assert detail["reason"] == "no_active_curvature" and detail["artifacts"] == []
    assert not list(store.folder(released["run_id"]).glob("*.png"))
