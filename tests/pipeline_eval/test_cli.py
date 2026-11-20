import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.scoring import score


def _result(point, status="ok"):
    return {
        "boundary": "position solver",
        "status": status,
        "metrics": {},
        "reason": "receiver decision",
        "arms": {arm: {"latlon": point} for arm in ("c0", "fitted_c")},
    }


def test_omitted_predictions_and_forced_points_stay_in_the_denominator():
    refs = [
        dict(
            id=str(i),
            recording=str(i),
            truth=[0, 0],
            group="DS26",
            condition="present",
            reference={
                "baseline": {a: {"error_km": 0, "latlon": [0, 0]} for a in ("c0", "fitted_c")}
            },
        )
        for i in range(3)
    ]
    result = _result(None, "withheld")
    result["arms"]["fitted_c"]["forced_latlon"] = [0, 0.01]
    submitted = {"0": {"result": _result([0, 0])}, "1": {"result": result}}
    summary, rows = score(refs, submitted)
    assert len(rows) == 6
    a = next(g for g in summary["groups"] if g["arm"] == "fitted_c")
    assert a["within_km"]["5"] == a["error_km"]["n"] == 1
    assert a["attempts"] == 3 and a["lost_v5_fixes"] == 2
    assert a["forced_error_km"]["p50"] == pytest.approx(1.11195, abs=0.0001)
    assert a["decision_counts"] == {"published": 1, "withheld": 1, "missing": 1}
    assert a["keeps_v5_panel"] is False


def test_missing_offer_distinguishes_abstention_and_unavailable():
    refs = [
        dict(
            id=str(i),
            recording=str(i),
            truth=[0, 0],
            group="Field",
            condition="missing",
            reference={},
        )
        for i in range(3)
    ]
    preds = {
        str(i): {"result": _result(point, status)}
        for i, (point, status) in enumerate(
            [([0, 3], "ok"), (None, "withheld"), (None, "unavailable")]
        )
    }
    summary, _ = score(refs, preds)
    g = summary["groups"][0]
    assert g["false_publications"] == 1
    assert g["decision_counts"] == dict(published=1, withheld=1, unavailable=1)


def test_duplicate_and_unknown_external_rows_rejected(tmp_path):
    r = json.dumps({"id": "z", "result": _result([0, 0])}) + "\n"
    file = tmp_path / "input.jsonl"
    file.write_text(r + r)
    with pytest.raises(ValueError, match="duplicate"):
        cli.read_predictions(file)
    with pytest.raises(ValueError, match="outside"):
        score([], {"z": {"result": _result([0, 0])}})


def test_stage_only_report_shows_its_timing_without_a_failed_position(capsys):
    _, refs = cli.references("smoke", ["DS26-0036"])
    result = dict(
        status="ok", boundary="decoded IQ to peak", metrics={"control_s": 4, "candidate_s": 2}
    )
    report, _ = score(refs, {refs[0]["id"]: {"result": result}})
    cli.show_result(dict(panel="smoke", method="detector", **report))
    printed = capsys.readouterr().out
    assert "2.00× (n=1)" in printed and "stage-only measurement (n=1)" in printed
    assert "fixes" not in printed


def test_frozen_external_score_matches_both_arms_and_runs_without_archives(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "absent"))
    monkeypatch.setenv("PIPELINE_EVAL_BLIND_ROOT", str(tmp_path / "absent"))
    _, refs = cli.references("smoke", None)
    pred = tmp_path / "positions.jsonl"
    with pred.open("w") as stream:
        for case in refs:
            arms = {
                arm: {"latlon": ref["latlon"]} for arm, ref in case["reference"]["baseline"].items()
            }
            item = dict(
                id=case["id"],
                result=dict(boundary="test reference", status="ok", metrics={}, arms=arms),
            )
            stream.write(json.dumps(item) + "\n")
    args = [
        "score",
        "--panel",
        "smoke",
        "--predictions",
        str(pred),
        "--name",
        "example",
        "--out",
        str(tmp_path),
        "--require-v5",
    ]
    assert cli.main(args) == 0
    folder = tmp_path / "smoke" / "example"
    first = (folder / "current").resolve()
    for arm in ("c0", "fitted_c"):
        figure = folder / ("position-errors-" + arm + ".png")
        assert figure.resolve().parent == first
        assert figure.read_bytes().startswith(b"\x89PNG")
    assert not any(
        g["v5_coordinate_delta_km"]["max"]
        for g in json.loads((first / "summary.json").read_bytes())["groups"]
    )
    assert cli.main(args) == 0 and (folder / "current").resolve() != first
    assert (first / "errors.csv").is_file()
    assert (
        cli.main(
            [
                "figures",
                "--panel",
                "smoke",
                "--runs",
                str(tmp_path),
                "--out",
                str(tmp_path / "figures"),
                "--arm",
                "c0",
            ]
        )
        == 0
    )
    assert (tmp_path / "figures/c0/example.png").is_file()
    assert cli.main(["compare", "--panel", "smoke", "--out", str(tmp_path)]) == 0
    assert "example,DS29,present" in (tmp_path / "smoke" / "comparison.csv").read_text()
    assert (
        cli.main(["plot", "--panel", "smoke", "--variant", "example", "--out", str(tmp_path)]) == 0
    )
    assert (tmp_path / "smoke" / "errors-fitted_c.png").read_bytes().startswith(b"\x89PNG")
    pred.write_text("")
    assert cli.main(args) == 1


def test_subset_outputs_do_not_replace_full_roster(tmp_path):
    _, refs = cli.references("smoke", None)
    whole = cli.run_folder(tmp_path, "smoke", "example", refs, None)
    partial = cli.run_folder(tmp_path, "smoke", "example", refs[:1], [refs[0]["id"]])
    assert partial.parent == whole and partial.name.startswith("subset-")


@pytest.mark.parametrize("panel", ["convergence", "screening"])
def test_research_figures_panel_routes_to_figure_backend(tmp_path, monkeypatch, panel):
    from tools.pipeline_eval import figure_books

    calls = []

    def generate(out, arms, variants, runs, panel, additional, evidence):
        calls.append((out, arms, variants, runs, panel, additional, evidence))

    monkeypatch.setattr(figure_books, "generate", generate)
    assert cli.main(["figures", "--panel", panel, "--out", str(tmp_path)]) == 0
    assert calls == [(tmp_path, ("fitted_c", "c0"), None, None, panel, False, None)]


def test_full_command_scores_only_its_selected_recording_and_preserves_evidence(
    tmp_path, monkeypatch
):
    from tools.pipeline_eval.qualification import recording_to_v5

    case_id = "DS26-0036"
    _, refs = cli.references("smoke", [case_id])
    point = refs[0]["reference"]["baseline"]["c0"]["latlon"]
    response = _result(point)
    response["arms"]["fitted_c"]["latlon"] = refs[0]["reference"]["baseline"]["fitted_c"]["latlon"]

    def replay(selected, source, cpus, timeout, library):
        assert selected == case_id and cpus == [0, 1] and timeout == 1200
        cli.write(
            source / "predictions.jsonl", cli.encoded(dict(id=selected, result=response)) + b"\n"
        )

    monkeypatch.setattr(recording_to_v5, "run_recording", replay)
    cmd = ["full", "--case", case_id, "--cpus", "0", "1", "--out", str(tmp_path), "--require-v5"]
    assert cli.main(cmd) == 0
    current = cli.run_folder(tmp_path, "smoke", "native-to-v5", refs, [case_id]) / "current"
    assert (current / "recording/predictions.jsonl").read_bytes() == (
        current / "predictions.jsonl"
    ).read_bytes()
    report = json.loads((current / "summary.json").read_bytes())
    assert report["ids"] == [case_id] and all(g["keeps_v5_panel"] for g in report["groups"])

    def absent(*args):
        raise FileNotFoundError(2, "file not found", "detector.so")

    monkeypatch.setattr(recording_to_v5, "run_recording", absent)
    assert cli.main(cmd) == 1
    report = json.loads((current / "summary.json").read_bytes())
    assert report["statuses"] == {"unavailable": 1}


def test_timeout_and_readonly_output_validation(tmp_path):
    for value in ("nan", "inf", "-1"):
        with pytest.raises(ValueError, match="finite and positive"):
            cli.main(["run", "--timeout", value, "--out", str(tmp_path)])
    symlink = tmp_path / "cache"
    symlink.symlink_to("/mnt/qnap01/blocked")
    with pytest.raises(ValueError, match="read-only"):
        cli.local_output(symlink / "case.json")


def test_folded_doppler_identity_tracks_native_kernel_changes(tmp_path):
    python_module = tmp_path / "folded_doppler.py"
    kernel = python_module.with_suffix(".c")
    python_module.write_bytes(b"driver")
    kernel.write_bytes(b"first")
    initial = cli.implementation_digest("folded_doppler_global", python_module)
    assert cli.implementation_digest("folded_doppler_matched_tile", python_module) == initial
    kernel.write_bytes(b"second")
    assert cli.implementation_digest("folded_doppler_global", python_module) != initial


@pytest.mark.parametrize(
    "name",
    [
        "v5_batched_salvage",
        "v5_catalogue_memory",
        "v5_stream_prepare",
        "v5_shared_search",
        "v5_two_refresh",
        "v5_likelihood_reuse",
        "v5_secant_fit",
        "v5_stable_phase",
        "v5_secant_two_refresh",
        "v5_screen_winner",
        "v5_screen_secant",
        "v5_armijo_fit",
        "v5_armijo_tail",
        "v5_armijo_finish",
        "v5_armijo_aligned_finish",
        "v5_pruned_finish",
        "v5_stream_recovery",
        "v5_screened_pruned_finish",
        "v5_recovery_bank_reuse",
        "v5_discovery_memory",
        "v5_lazy_pair",
        "contiguous_prefix_180",
        "raw_robust",
        "periodic_anchor",
        "robust_orbit_fit",
        "robust_support",
        "joint_orbits",
    ],
)
def test_standalone_variants_are_runnable_from_standard_benchmark(name):
    import importlib

    assert name in cli.VARIANTS
    assert callable(importlib.import_module(cli.module_name(name)).run)


@pytest.mark.parametrize(
    ("name", "options"),
    [
        ("v5_two_refresh", {}),
        ("v5_likelihood_reuse", {}),
        ("v5_secant_fit", {"mode": "secant"}),
        ("v5_stable_phase", {}),
        ("v5_secant_two_refresh", {}),
        ("v5_screen_winner", {"mode": "reference"}),
        ("v5_screen_secant", {"mode": "secant"}),
        ("v5_armijo_fit", {}),
        ("v5_armijo_tail", {"method": "tail"}),
        ("v5_armijo_finish", {}),
        ("v5_armijo_aligned_finish", {}),
        ("v5_pruned_finish", {}),
        ("v5_stream_recovery", {}),
        ("v5_screened_pruned_finish", {}),
        ("v5_recovery_bank_reuse", {}),
        ("v5_discovery_memory", {}),
        ("v5_lazy_pair", {}),
    ],
)
def test_convergence_v5_runs_receive_the_standard_bound_case(name, options, tmp_path, monkeypatch):
    import importlib

    sealed = dict(id="example", native_path="verified", native_sha256="sha256:frozen")

    def run(case, work_dir, **kwargs):
        assert case == sealed and work_dir == tmp_path and kwargs == options
        return _result([1, 2])

    monkeypatch.setattr(importlib.import_module(cli.module_name(name)), "run", run)
    request, output = tmp_path / "request.json", tmp_path / "output.json"
    cli.save_json(request, sealed)
    cli.child(name, request, output, tmp_path)
    record = json.loads(output.read_bytes())
    assert record["id"] == sealed["id"] and record["result"]["status"] == "ok"


@pytest.mark.parametrize(
    "variant",
    [
        "v5_armijo_aligned_finish",
        "v5_pruned_finish",
        "v5_stream_recovery",
        "v5_screened_pruned_finish",
    ],
)
@pytest.mark.parametrize(
    ("panel", "center", "reason"),
    [
        ("Field", (37.906, -122.545), "only for roof recordings"),
        ("DS26", (38.0, -122.545), "original single 25 km roof tile"),
        ("DS26", (37.906, -122.545), "Native detector input is unavailable"),
    ],
)
def test_aligned_finish_default_domain(tmp_path, monkeypatch, variant, panel, center, reason):
    from tools.pipeline_eval.variants import orbit_projector

    monkeypatch.setattr(orbit_projector, "compile_kernel", lambda _: None)
    case = dict(id="unbound", panel=panel, regions=[dict(center=center, width_km=25.0)])
    request, output = tmp_path / "request.json", tmp_path / "output.json"
    cli.save_json(request, case)
    cli.child(variant, request, output, tmp_path)
    result = json.loads(output.read_bytes())["result"]
    assert result["status"] == "unavailable"
    assert reason in result["reason"]
    assert result["arms"] == {arm: {"latlon": None} for arm in cli.ARMS}


def test_joint_orbits_standard_worker_keeps_exact_track_catalogue_and_tile_binding(tmp_path):
    observation = tmp_path / "observations.json"
    catalog = tmp_path / "causal.tle"
    observation.write_bytes(b'{"tracks":[],"duration_s":10}')
    catalog.write_bytes(b"test catalogue")
    tile = dict(id="tile", center=[1, 2], width_km=25)
    case = dict(
        id="example",
        observation_path=str(observation),
        catalog_path=str(catalog),
        regions=[tile],
    )
    binding = dict(
        observation_sha256=sha256(observation.read_bytes()).hexdigest(),
        catalog_sha256=sha256(catalog.read_bytes()).hexdigest(),
        tile=tile,
    )
    row = cli.run_one("joint_orbits", case, tmp_path, seconds=10, affinity=None)
    assert row["input_binding"] == binding
    assert row["input_sha256"] == sha256(cli.encoded(binding)).hexdigest()
    assert row["result"]["status"] == "withheld"
    assert row["result"]["reason"] == "insufficient_track_inventory"


@pytest.mark.parametrize(
    ("offers", "reason"),
    [([], "single supplied tile required"), ([{}], "missing anonymous tracks or causal catalogue")],
)
def test_joint_orbits_does_not_substitute_single_tile_or_prepared_inputs(tmp_path, offers, reason):
    request, output = tmp_path / "request.json", tmp_path / "output.json"
    cli.save_json(request, dict(id="example", regions=offers))
    cli.child("joint_orbits", request, output, tmp_path)
    row = json.loads(output.read_bytes())
    assert row["input_sha256"] is None
    assert row["result"]["status"] == "unavailable"
    assert row["result"]["reason"] == reason


def test_whole_single_receiver_uses_selected_roof_panel_and_detector(tmp_path, monkeypatch):
    from tools.pipeline_eval.qualification import recording_to_v5

    case = "DS29-0174"
    refs = cli.references("roof16", [case])[1]

    def replay(case_id, source, cpus, timeout, library, *, detector):
        assert case_id == case and detector == "single-rx0"
        result = _result(refs[0]["truth"])
        cli.write(source / "predictions.jsonl", cli.encoded(dict(id=case, result=result)) + b"\n")

    monkeypatch.setattr(recording_to_v5, "run_recording", replay)
    assert (
        cli.main(["full", "--case", case, "--detector", "single-rx0", "--out", str(tmp_path)]) == 0
    )
    current = cli.run_folder(tmp_path, "roof16", "single_rx0", refs, [case]) / "current"
    assert json.loads((current / "summary.json").read_bytes())["ids"] == [case]


@pytest.mark.parametrize(
    ("variant", "function", "tile_format"),
    [
        ("point_votes_global", "solve", None),
        ("point_votes_matched_tile", "solve", "center"),
        ("rate_triplets_global", "run", None),
        ("rate_triplets_matched_tile", "run", "offer"),
        ("folded_doppler_global", "solve", None),
        ("folded_doppler_matched_tile", "solve", "center"),
        ("pass_geometry_global", "run", None),
        ("pass_geometry_matched_tile", "run", "offer"),
        ("joint_pass_id_matched_tile", "run", "offer"),
        ("region_challenge_matched_tile", "run", "offer"),
    ],
)
def test_cold_worker_dispatch_and_verified_digest(
    tmp_path, monkeypatch, variant, function, tile_format
):
    from importlib import import_module

    from tools.pipeline_eval.qualification import cold_input

    case_id = "test"
    capture = SimpleNamespace(
        case_id=case_id,
        native_sha256=sha256(b"GLRT").hexdigest(),
        catalog_sha256=sha256(b"TLE").hexdigest(),
        cutoff_utc_ns=40,
        catalog_timestamp_ns=30,
    )
    offer = dict(id="original", center=[1, 2])
    expected_binding = vars(capture).copy()
    expected_tile = None
    if tile_format is not None:
        expected_binding["matched_tile"] = dict(offer, width_km=25.0)
        expected_tile = (
            tuple(offer["center"]) if tile_format == "center" else expected_binding["matched_tile"]
        )

    def load(selected):
        assert selected == case_id
        return capture

    def matched_offers(selected):
        assert selected == case_id and tile_format is not None
        return [offer]

    def solve(received, *, tile):
        assert received is capture and tile == expected_tile
        receipt = json.loads((tmp_path / "cold-input.json").read_bytes())
        assert receipt["input_binding"] == expected_binding
        return _result([1, 2])

    monkeypatch.setattr(cold_input, "load", load)
    monkeypatch.setattr(cold_input, "matched_offers", matched_offers)
    monkeypatch.setattr(import_module(cli.module_name(variant)), function, solve)
    case, output = (tmp_path / name for name in ("input.json", "output.json"))
    cli.save_json(case, {"id": case_id})
    cli.child(variant, case, output, tmp_path)
    prediction = json.loads(output.read_bytes())
    assert prediction["input_binding"] == expected_binding
    assert prediction["input_sha256"] == sha256(cli.encoded(expected_binding)).hexdigest()
    with pytest.raises(ValueError, match="only a recording ID"):
        cli.save_json(case, {"id": case_id, "regions": [offer]})
        cli.child(variant, case, output, tmp_path)


def test_cold_worker_failure_retains_verified_input_binding(tmp_path, monkeypatch):
    binding = dict(case_id="test", native_sha256="native", catalog_sha256="catalog")
    digest = sha256(cli.encoded(binding)).hexdigest()

    def launch(command, **kwargs):
        cli.save_json(
            Path(command[-1]) / "cold-input.json",
            dict(input_binding=binding, input_sha256=digest),
        )
        return SimpleNamespace(wait=lambda **kwargs: None, returncode=1)

    monkeypatch.setattr(cli.subprocess, "Popen", launch)
    record = cli.run_one("point_votes_global", {"id": "test"}, tmp_path, 1, None)
    assert record["result"]["status"] == "failed"
    assert record["input_binding"] == binding and record["input_sha256"] == digest


@pytest.mark.parametrize(
    ("variant", "reason"),
    [
        ("point_votes_global", "frozen GLRT candidate probes"),
        ("contiguous_prefix_180", "complete frozen GLRT and v5 bindings"),
        ("raw_robust", "frozen"),
        ("periodic_anchor", "no authenticated dual-detector schedule"),
    ],
)
def test_id_only_run_scores_unavailable_transfer_without_legacy_inputs(
    tmp_path, monkeypatch, variant, reason
):
    case = cli.references("transfer16", None)[1][0]["id"]
    refs = cli.references("transfer16", [case])[1]

    def legacy_inputs(*args):
        pytest.fail("cold-only run resolved legacy inputs")

    monkeypatch.setattr(cli, "public_cases", legacy_inputs)
    args = [
        "run",
        "--panel",
        "transfer16",
        "--case",
        case,
        "--variant",
        variant,
        "--out",
        str(tmp_path),
        "--cache",
        str(tmp_path / "cache"),
    ]
    assert cli.main(args) == 0
    current = cli.run_folder(tmp_path, "transfer16", variant, refs, [case]) / "current"
    report = json.loads((current / "summary.json").read_bytes())
    prediction = cli.read_predictions(current / "predictions.jsonl")[case]
    assert report["statuses"] == {"unavailable": 1}
    assert prediction["input_sha256"] is None
    assert reason in prediction["result"]["reason"]
    assert not (tmp_path / "cache").exists()
    assert cli.main([*args, "--require-inputs"]) == 1


def test_all_routes_each_worker_to_its_public_inputs(tmp_path, monkeypatch):
    from tools.pipeline_eval.variants import lean_receiver_cli_benchmark

    case_id = "DS26-0036"
    calls, resolved, native_resolved = set(), [], []
    legacy_case = dict(id=case_id, graph_path="graph", regions=["site"])
    native_case = dict(id=case_id, files={"native": "capture"}, capture=42)

    def legacy_inputs(panel, refs, cache):
        resolved.append((panel, [r["id"] for r in refs]))
        return [legacy_case]

    def native_inputs(panel, ids):
        native_resolved.append((panel, ids))
        return [native_case]

    def run(variant, case, *_):
        calls.add(variant)
        if variant in cli.ID_ONLY_VARIANTS:
            assert case == {"id": case_id}
        elif variant in cli.NATIVE_PUBLIC_VARIANTS:
            assert case == native_case
        else:
            assert case == legacy_case
        return dict(id=case_id, result=_result([1, 2]), worker_wall_s=0)

    def scored(panel, method, refs, records, folder):
        report, _ = score(refs, records)
        return dict(report, panel=panel, method=method)

    monkeypatch.setattr(cli, "public_cases", legacy_inputs)
    monkeypatch.setattr(lean_receiver_cli_benchmark, "cases", native_inputs)
    monkeypatch.setattr(cli, "run_one", run)
    monkeypatch.setattr(cli, "scored_files", scored)
    assert cli.main(["run", "--case", case_id, "--variant", "all", "--out", str(tmp_path)]) == 0
    assert resolved == [("smoke", [case_id])]
    assert native_resolved == [("smoke", [case_id])]
    assert calls == set(cli.VARIANTS) - cli.OPT_IN_VARIANTS


def test_joint_pass_implementation_digest_includes_rate_triplets(tmp_path):
    module = tmp_path / "joint_pass_id.py"
    module.write_bytes(b"joint pass")
    dependency = tmp_path / "rate_triplets.py"
    dependency.write_bytes(b"first triplet version")
    first = cli.implementation_digest("joint_pass_id_matched_tile", module)
    assert first == sha256(module.read_bytes() + dependency.read_bytes()).hexdigest()
    dependency.write_bytes(b"second triplet version")
    assert cli.implementation_digest("joint_pass_id_matched_tile", module) != first


def test_joint_orbits_implementation_digest_binds_solver_and_causal_geometry(tmp_path):
    pipeline = tmp_path / "tools" / "pipeline_eval"
    variants = pipeline / "variants"
    sky = tmp_path / "src" / "leo" / "sky"
    files = [
        variants / "joint_orbits_benchmark.py",
        variants / "joint_orbits.py",
        variants / "robust_orbit_fit.py",
        variants / "robust_em.py",
        variants / "projected_fit.py",
        pipeline / "reference" / "grid.py",
        sky / "frames.py",
        sky / "propagation.py",
        sky / "sampling.py",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    original = cli.implementation_digest("joint_orbits", files[0])
    assert original == sha256(b"".join(p.read_bytes() for p in files)).hexdigest()
    for dependency in files[1:]:
        raw = dependency.read_bytes()
        dependency.write_bytes(raw + b" changed")
        assert cli.implementation_digest("joint_orbits", files[0]) != original
        dependency.write_bytes(raw)


@pytest.mark.parametrize(
    ("variant", "policies"),
    [
        ("v5_secant_two_refresh", ("v5_secant_fit.py", "v5_two_refresh.py")),
        ("v5_stable_phase", ("v5_secant_fit.py",)),
        ("v5_armijo_fit", ("v5_secant_fit.py",)),
        ("v5_armijo_tail", ("v5_armijo_fit.py", "v5_secant_fit.py")),
        ("v5_orbit_domain", ("v5_secant_fit.py",)),
        ("v5_previous_orbit", ("v5_secant_fit.py",)),
        ("v5_armijo_finish", ("v5_armijo_fit.py", "compact_finish.py")),
        (
            "v5_armijo_aligned_finish",
            ("v5_armijo_finish.py", "v5_armijo_fit.py", "compact_finish.py"),
        ),
        (
            "v5_pruned_finish",
            (
                "v5_armijo_aligned_finish.py",
                "v5_armijo_finish.py",
                "v5_armijo_fit.py",
                "compact_finish.py",
            ),
        ),
        (
            "v5_stream_recovery",
            (
                "v5_armijo_aligned_finish.py",
                "v5_armijo_finish.py",
                "v5_armijo_fit.py",
                "compact_finish.py",
            ),
        ),
        (
            "v5_screened_pruned_finish",
            (
                "v5_pruned_finish.py",
                "v5_screen_winner.py",
                "v5_shared_search.py",
                "v5_armijo_aligned_finish.py",
                "v5_armijo_finish.py",
                "v5_armijo_fit.py",
                "compact_finish.py",
            ),
        ),
        ("v5_discovery_memory", ("v5_secant_fit.py",)),
        ("v5_lazy_pair", ("compact_finish.py",)),
        ("v5_recovery_bank_reuse", ("compact_finish.py",)),
    ],
)
def test_compact_variants_bind_their_policies_and_solver(tmp_path, variant, policies):
    files = [
        tmp_path / "variants" / name
        for name in (
            variant + ".py",
            *policies,
            "orbit_projector.py",
            "orbit_projector.c",
            "v5_core.py",
            "v5_lean.py",
        )
    ]
    if variant in (
        "v5_armijo_aligned_finish",
        "v5_pruned_finish",
        "v5_stream_recovery",
        "v5_screened_pruned_finish",
    ):
        files.append(tmp_path / "qualification" / "armijo_finish_phase_retry.py")
    for path in files:
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(path.name.encode())
    initial = cli.implementation_digest(variant, files[0])
    worker = files[0].read_bytes()
    if variant == "v5_armijo_tail":
        worker += b"\0method=tail"
    assert initial == sha256(worker + b"".join(p.read_bytes() for p in files[1:])).hexdigest()
    for dependency in files[1:]:
        original = dependency.read_bytes()
        dependency.write_bytes(original + b" changed")
        assert cli.implementation_digest(variant, files[0]) != initial
        dependency.write_bytes(original)


def test_screening_fingerprints_use_mode_and_only_its_solver(tmp_path):
    names = (
        "v5_screen_winner.py",
        "orbit_projector.py",
        "orbit_projector.c",
        "v5_core.py",
        "v5_lean.py",
    )
    dependencies = [tmp_path / name for name in names]
    for path in dependencies:
        path.write_bytes(path.name.encode())
    module, *shared = dependencies
    digest = sha256(module.read_bytes() + b"\x00mode=reference")
    for path in shared:
        digest.update(path.read_bytes())
    reference = cli.implementation_digest("v5_screen_winner", module)
    assert reference == digest.hexdigest()
    secant = tmp_path / "v5_secant_fit.py"
    secant.touch()
    original = cli.implementation_digest("v5_screen_secant", module)
    assert original != reference
    secant.write_bytes(b"changed optimizer")
    assert cli.implementation_digest("v5_screen_secant", module) != original
    assert cli.implementation_digest("v5_screen_winner", module) == reference
    shared[1].write_bytes(b"changed projector")
    assert cli.implementation_digest("v5_screen_winner", module) != reference


def test_region_challenge_is_tile_only_and_binds_both_solver_dependencies(tmp_path):
    files = [
        tmp_path / name for name in ("region_challenge.py", "rate_triplets.py", "joint_pass_id.py")
    ]
    for path in files:
        path.write_bytes(path.name.encode())
    initial = cli.implementation_digest("region_challenge_matched_tile", files[0])
    assert initial == sha256(b"".join(p.read_bytes() for p in files)).hexdigest()
    for dependency in files[1:]:
        original = dependency.read_bytes()
        dependency.write_bytes(original + b" changed")
        assert cli.implementation_digest("region_challenge_matched_tile", files[0]) != initial
        dependency.write_bytes(original)
    with pytest.raises(ValueError, match="unknown experiment"):
        cli.module_name("region_challenge_global")


@pytest.mark.parametrize("variant", ["raw_robust", "periodic_anchor"])
def test_archive_bound_worker_reports_exact_fitter_input_binding(tmp_path, monkeypatch, variant):
    import importlib

    case_id = "example"
    binding = dict(input_sha256=sha256(b"fitter packet").hexdigest(), native_sha256="native")

    def run(case, directory):
        assert case == {"id": case_id} and directory == tmp_path
        return dict(_result([1, 2]), input_binding=binding)

    monkeypatch.setattr(importlib.import_module(cli.module_name(variant)), "run", run)
    request, output = tmp_path / "request.json", tmp_path / "output.json"
    cli.save_json(request, {"id": case_id})
    cli.child(variant, request, output, tmp_path)
    record = json.loads(output.read_bytes())
    assert record["input_binding"] == binding
    assert record["input_sha256"] == binding["input_sha256"]


def test_prefix_benchmark_passes_authenticated_prefix_to_measured_position(tmp_path, monkeypatch):
    from tools.pipeline_eval.variants import contiguous_prefix_180 as adapter

    rate, first = 10_000_000, 100
    after = dict(monotonic_ns=2, realtime_ns=12)
    late_start = first + 180 * rate
    document = dict(
        source=dict(
            sample_rate_hz=rate,
            probe_ms=20,
            analysis_manifest_sha256="original",
            probes=[
                dict(
                    visit_index=visit,
                    receiver_id=rx,
                    channel=visit + 1,
                    probe_index=0,
                    probe_start_ms=0,
                    valid_start_counter=counter,
                )
                for visit, counter in enumerate((first, late_start))
                for rx in range(2)
            ],
        ),
        provenance=dict(
            window_count=2, processed_windows=2, invalid_capture=0, excluded_windows=[]
        ),
        clock_anchor=dict(
            sample_counter=first, before=dict(monotonic_ns=1, realtime_ns=11), after=after
        ),
        delivery_clocks=[after, dict(monotonic_ns=180_000_000_003, realtime_ns=180_000_000_013)],
        last_sample_counter=late_start + rate // 50,
    )
    archive = tmp_path / "archive.json"
    cli.save_json(archive, document)
    archive_digest = sha256(archive.read_bytes()).hexdigest()
    sealed = dict(
        id="example",
        native=dict(path=archive.name, sha256=archive_digest),
        request=dict(sha256="sealed request"),
        track_config=dict(sha256="sealed track configuration"),
        catalog=dict(sha256="sealed catalogue"),
    )
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path))
    monkeypatch.setattr(adapter, "_load_case", lambda case_id: sealed)

    def position(case, derived, directory, metrics, variant):
        prefix = json.loads(derived.read_bytes())
        assert case == sealed and directory == tmp_path and variant == "capture-era-prefix"
        assert prefix["clock_anchor"] == document["clock_anchor"]
        assert prefix["source"]["probes"] == document["source"]["probes"][:2]
        assert metrics["next_sample_end_counter"] > metrics["prefix_cutoff_counter"]
        return dict(
            result=_result([1, 2]), inference_factor_sha256=sha256(derived.read_bytes()).hexdigest()
        )

    monkeypatch.setattr(adapter, "position", position)
    request, output = tmp_path / "request.json", tmp_path / "output.json"
    cli.save_json(request, {"id": "example"})
    cli.child("contiguous_prefix_180", request, output, tmp_path)
    record = json.loads(output.read_bytes())
    binding = record["input_binding"]
    assert binding["prefix_seconds"] == 180
    assert binding["capture_native_sha256"] == archive_digest
    assert binding["inference_factor_sha256"] != archive_digest
    assert record["input_sha256"] == sha256(cli.encoded(binding)).hexdigest()
    archive.write_bytes(b"changed")
    with pytest.raises(ValueError, match="frozen digest"):
        adapter.run({"id": "example"}, tmp_path)
