import pytest

from reports.ALGO08.v3 import adaptive_withhold_0107 as trial


def frozen_arguments():
    return [
        "/usr/bin/timeout", "--kill-after=2s", "90s", "python", "-IB", "/north/combined_raw_research.py",
        "--recording", "/old-recording", "--archive", "/old-archive", "--region", "/old-offer",
        "--output", "/old-output", "--eight-ms-native-history", "--catalogue-block-rank",
        "--portable-orbit-index", "/index", "--grid-feature-projection-library", "/projection",
        "--one-pass-web-png", "--named-survivor-finish", "--direct-orbit-figures",
        "--direct-residual-figures", "--prove-no-active-curvature",
    ]


def test_0107_reuses_north_adaptive_argv(monkeypatch, tmp_path):
    import json

    previous = frozen_arguments()
    binding = dict(original=previous, command=[*previous, trial.adaptive.FLAG], libraries={"short": "pinned"},
                   sources={name: "pinned" for name in (*trial.adaptive.ADAPTER, "combined_raw_research.py",
                                                         "unified_short_bootstrap.py")})
    verified = dict(binding_sha256=trial.NORTH_BINDING, passed=True)
    documents = {"binding.json": binding, "verified-result.json": verified}
    monkeypatch.setattr(trial, "checked", lambda path, pin: json.dumps(documents.get(path.name)))
    monkeypatch.setattr(trial.paired, "archived", lambda _: {"raw_binding": {"libraries": binding["libraries"]}})

    result = trial.frozen_command(previous, "/physical", "/causal", "/offer", tmp_path)
    expected = trial.paired.candidate_command(previous, "/physical", "/causal", "/offer", tmp_path)
    assert result == [*expected, trial.adaptive.FLAG]
    with pytest.raises(ValueError, match="exact accepted North"):
        trial.frozen_command([*previous, "--whole-stereo-blocks"], "/physical", "/causal", "/offer", tmp_path)
    binding["command"] = [*previous, trial.adaptive.FLAG, "--short-lane-mask"]
    with pytest.raises(ValueError, match="original full anchors"):
        trial.frozen_command(previous, "/physical", "/causal", "/offer", tmp_path)


def test_web_reads_real_withhold_and_all_position_products_are_unavailable(tmp_path):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    run_id = "algo08-v2-control"
    store = FastStandardAnalysisStore(tmp_path)
    detail = store.withhold(run_id, "no_active_curvature", session_id="session", raw_authority="raw",
                            region=dict(center=[37.5, -122], screen_center=[37.5, -122], width_km=25),
                            terminal_sha256="terminal", input_sha256="native")
    checked = trial.web(tmp_path, run_id)
    science = dict(receipt=detail, raw_authority="raw", reason="no_active_curvature")
    assert trial.standard_withhold(checked, dict(native_sha256="native", science=science))
    checked["products"]["position.png"] = 200
    assert not trial.standard_withhold(checked, dict(native_sha256="native", science=science))
    assert not trial.standard_withhold(trial.web(tmp_path, "algo08-v2-pending"),
                                       dict(native_sha256="native", science=science))
