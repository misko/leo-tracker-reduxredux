import pytest

from reports.ALGO08.v3 import legacy_map_writer_0016 as trial


def test_replay_shape_only_ignores_the_worktree_and_relocated_output_maps():
    argv = ["timeout", "--kill-after=2s", "75s", "python", "-IB", "/a/legacy_block_all_entry.py",
            "--output", "/a/run", "--legacy-map-custody", "/a/maps/custody.json",
            "--legacy-map-library", "/a/maps/decoder.so", "--archive", "/active/causal",
            "--legacy-map-custody-sha256", "trusted-map"]
    relocated = [arg.replace("/a/", "/b/", 1) if arg.startswith("/a/") else arg for arg in argv]
    assert trial.command_shape(argv) == trial.command_shape(relocated)
    relocated[-1] = "other-map"
    assert trial.command_shape(argv) != trial.command_shape(relocated)
    with pytest.raises(ValueError, match="explicit --output"):
        trial.command_shape([*argv, "--output", "/extra"])


def test_audit_comparison_preserves_fields_and_member_counts():
    audit = {"setup": {"cpu_s": 0.01, "elapsed_s": 0.02},
             "members": [{"map_kind": "exception", "counts": {"full": 4},
                          "map_file": {"wall_ns": 100, "cpu_ns": 99, "input_blocks": 2}}]}
    new = {"setup": {"cpu_s": 0.02, "elapsed_s": 0.03},
           "members": [{"map_kind": "exception", "counts": {"full": 4},
                        "map_file": {"wall_ns": 101, "cpu_ns": 97, "input_blocks": 0}}]}
    assert trial.scientific_audit(audit) == trial.scientific_audit(new)
    new["members"][0]["counts"]["full"] += 1
    assert trial.scientific_audit(audit) != trial.scientific_audit(new)
    new["members"][0]["counts"]["full"] -= 1
    del new["setup"]["elapsed_s"]
    assert trial.scientific_audit(audit) != trial.scientific_audit(new)
