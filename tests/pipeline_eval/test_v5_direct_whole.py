import hashlib
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import direct_whole_results as results
from tools.pipeline_eval.qualification import direct_whole_trial as trial
from tools.pipeline_eval.variants import v5_direct_whole as position


def test_handoff_passes_verified_factor_and_distinct_centres(tmp_path):
    p = tmp_path / "native.json"
    p.write_bytes(b"{}")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    job = dict(
        native_input={"path": str(p), "sha256": "sha256:" + digest},
        track_config={"path": "/path/tracks.json", "sha256": "b" * 64},
        identity={"session_id": "synthetic"},
        evaluation_reference=None,
        tle_root="/path/catalogue",
        search_center=[37.906, -122.545],
        screen_center=[37.5, -122.0],
    )
    args = trial.position_flags(tmp_path, job, digest)
    assert args[args.index("--native-sha256") + 1] == digest
    assert args[args.index("--archive") + 1] == "/path/catalogue"
    assert args[-6:] == ["--tile", "37.906", "-122.545", "--screen-center", "37.5", "-122.0"]
    with pytest.raises(ValueError, match="declared prepared input"):
        trial.position_flags(tmp_path, dict(job, evaluation_reference={}), digest)
    p.write_bytes(b"[]")
    with pytest.raises(ValueError, match="declared prepared input"):
        trial.position_flags(tmp_path, job, digest)


def test_optional_width_is_forwarded_in_explicit_argv():
    args = position.explicit_arguments(
        native="/a",
        native_sha256="d",
        track_config="/b",
        config_sha256="e",
        session="test",
        archive="/c",
        native_backend="/d",
        library="/e",
        tile=[1, 2],
        screen_center=[1, 2],
        width_km=9,
    )
    assert args[args.index("--width-km") + 1] == "9"


def test_position_must_inherit_same_capped_pid_and_module():
    begin = {"pid": 5, "cgroup": "/test"}
    measured = dict(
        begin,
        cpus=[18],
        **{
            "memory.max": 512 * 1024**2,
            "memory.swap.max": 0,
            "memory.swap.current": 0,
            "memory.events.oom_kill": 0,
        },
    )
    packet = dict(
        start=dict(measured, monotonic_s=2),
        end=dict(measured, monotonic_s=9),
        entry=str(trial.SLIM / "module.py"),
        evaluator_modules=[],
    )
    results.validate_stage_receipt(begin, packet)
    with pytest.raises(ValueError, match="explicit slim source contract"):
        results.validate_stage_receipt(begin, dict(packet, evaluator_modules=["bad"]))
    with pytest.raises(ValueError):
        wrong = deepcopy(packet)
        wrong["end"]["pid"] += 1
        results.validate_stage_receipt(begin, wrong)
