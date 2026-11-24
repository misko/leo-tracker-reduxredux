import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return [importlib.import_module(name) for name in ("unified_short_bootstrap", "combined_raw_research",
                                                      "eight_ms_native_receiver", "eight_ms_native_score")]


@pytest.mark.parametrize("settings", ({"short_lane_mask": "target"}, {"select_before_cfo": True},
                                      {"held_anchor_route": False}))
def test_live_mode_rejects_skipped_lanes_or_tail_before_opening_source(modules, settings):
    bootstrap, *_ = modules
    args = dict(eight_ms_native_history=True, one_pass_web_png=False, held_anchor_route=True) | settings
    with pytest.raises(ValueError, match="complete unrefined schedule"):
        bootstrap.run(SimpleNamespace(**args))


def test_native_profile_enters_unified_history_with_no_refinement_flags(modules, monkeypatch):
    _, combined, *_ = modules
    import sys

    def run(entry, *, run_name):
        assert Path(entry).name == "unified_short_bootstrap.py" and run_name == "__main__"
        assert sys.argv[1:] == ["--recording", "r", "--held-anchor-route", "--eight-ms-native-history"]

    monkeypatch.setattr(combined.runpy, "run_path", run)
    combined.native_eight(["--recording", "r"])


def test_native_history_refuses_wrong_parent_recipe(modules, tmp_path):
    *_, receiver, _ = modules
    from full_short_run import checked_recipe

    for recipe in (checked_recipe(), checked_recipe(eight_ms=True) | {"fixed_epoch_cfo_refinement": {}}):
        with pytest.raises(ValueError, match="original signed 20/8 ms recipe"):
            receiver.prepare({}, recipe, "s", "certified", tmp_path/"selection.json")
    assert not list(tmp_path.iterdir())


def test_scope_gate_charges_a_tail_and_requires_lower_total_acquisition(modules):
    score = modules[-1]

    def work(acquire, calls, tail):
        return {"acquisition": {"acquire": {"cpu_ns": acquire}, "native": {
            "native_cpu_ns": {"full": 3, "short_primary": calls}, "cfo_refinement": {"cpu_ns": tail}}}}

    assert score.admitted(work(10, 4, 0), work(11, 3, 2))
    assert not score.admitted(work(12, 4, 0), work(11, 3, 2))
    assert not score.admitted(work(10, 4, 0), work(11, 3, 1))


def test_unfiltered_native_signed_cfo_values_must_survive(modules):
    score = modules[-1]
    original = [{"candidates": [{"fractional_tracking_cfo_hz": -107.92}]}]
    kept = {"choice": {"route": "unfiltered"}, "refinement_calls": 0}
    score.unchanged_history(original, original, kept)
    with pytest.raises(ValueError, match="changed a signed measurement"):
        score.unchanged_history(original, [{"candidates": []}], kept)
    with pytest.raises(ValueError, match="zero later CFO calls"):
        score.unchanged_history(original, original, kept | {"refinement_calls": 1})


def test_image_inventory_compares_decoded_hash_and_canonical_dimensions(modules):
    check = modules[-1].same_images
    native = {"position": {"size": (1680, 960), "sha256": "encoded", "rgba_sha256": "decoded"}}
    archived = {"position": dict(native["position"], size=[1680, 960])}
    assert check(native, archived)
    assert not check(native, {"position": dict(archived["position"], rgba_sha256="different")})


def test_omitted_saved_handoff_uses_runtime_rebound_inside_combined_scope(modules, tmp_path, monkeypatch):
    from contextlib import contextmanager
    import eight_ms_native_live as live
    import empty_bootstrap as staged
    import raw_cfo_north_trial as saved

    _, combined, _, _ = modules
    request = dict(session="s", inventory="i", mirror_offer={})
    raw = dict(detector_recipe_sha256="sha256:recipe")
    files = {"omitted-binding.json": {"native_sha256": "sha256:detector", "containing_sha256": "seal"},
             "binding.json": {"libraries": {}}, "science-seal.json": {"request": request, "raw": raw},
             "detections.json": {"signed": True}}
    monkeypatch.setattr(live, "read", lambda path: files[path.name])
    monkeypatch.setattr(live, "checked", lambda path, _: json.dumps(files.get(path.name, {})))
    monkeypatch.setattr(saved, "native_file", lambda path: path/"detections.json")
    monkeypatch.setattr(staged, "bind_native", lambda *_: None)

    def original():
        raise AssertionError("The unbound runtime cannot reach omitted inference")

    monkeypatch.setattr(staged, "load_runtime", original)
    sentinel = object()

    @contextmanager
    def together(orbit, rank, portable, *, use_blocks):
        assert use_blocks and portable
        with monkeypatch.context() as scope:
            scope.setattr(staged, "load_runtime", lambda: sentinel)
            yield
        rank["counts"] = {"compact_calls": 2}

    def publish(request, target, offer, packet, native, raw, *, runtime, **_):
        assert runtime is sentinel and target == tmp_path/"omitted" and native == {"signed": True}

    monkeypatch.setattr(combined, "combined_runtime", together)
    monkeypatch.setattr(saved, "publish_saved", publish)
    live.omitted_worker(tmp_path)
    assert json.loads((tmp_path/"omitted-execution.json").read_bytes())["rank_status"] == "compacted"
