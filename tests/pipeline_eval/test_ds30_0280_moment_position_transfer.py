from copy import deepcopy
from pathlib import Path

import ds30_0280_moment_position_transfer as transfer
import pytest


def __rf():
    candidate = dict(case=transfer.CASE,rank=68,pair_sha256="pair",rule_sha256=transfer.moment.PROJECTION_PIN,
                     enrollment_sha256=transfer.held.PLAN,projected=dict(moments_valid=True,surviving_edits=4))
    row = dict(eligible=8,scored=5,installed_empty=3,original={})
    field = dict(case=transfer.CASE,execution_rank=68,candidate=candidate,development_sha256=transfer.moment.DEVELOPMENT,
                 candidate_seal_sha256="candidate",previous_half_blend=row,moment_preserving=dict(row,
                     windows={"250Hz_2samples":dict(joint_before=3,joint_after=4)}),
                 waveform_reads=0,archive_reads=0,survey_reads=0,receiver_runs=0,solver_runs=0)
    return field,candidate


def test_position_admission_requires_nonworse_strict_and_nonzero_exact_edits():
    field,candidate = __rf()
    result = transfer.rf_admission(field,candidate,"candidate","sha256:pair")
    assert result == dict(strict_original=3,strict_projected=4,eligible=8,scored=5,installed_empty=3)
    failed = deepcopy(field)
    failed["moment_preserving"]["windows"]["250Hz_2samples"]["joint_after"] = 2
    with pytest.raises(ValueError,match="declined"):
        transfer.rf_admission(failed,candidate,"candidate","pair")
    candidate["projected"]["surviving_edits"] = 0
    with pytest.raises(ValueError,match="nonzero-edit"):
        transfer.rf_admission(field,candidate,"candidate","pair")


def test_declines_unmatched_rf_pair_and_installed_denominator():
    field,candidate = __rf()
    with pytest.raises(ValueError,match="exact original pair"):
        transfer.rf_admission(field,candidate,"candidate","different-pair")
    field["moment_preserving"]["scored"] = 4
    with pytest.raises(ValueError,match="changed its original measured"):
        transfer.rf_admission(field,candidate,"candidate","pair")


def test_alternate_mount_reuses_only_native_mount_on_dev_shm():
    run = Path("/tmp/qualified-0280")
    cell = run/"field/ordinary"
    argv = transfer.command(run,cell,"pin","ordinary",[],proof_only=True)
    i = argv.index("/dev/shm")
    assert argv[i-2:i+1] == ["--bind",str(transfer.mount_root(run)),"/dev/shm"]
    assert ["--bind",str(cell),str(cell)] == argv[argv.index(str(cell))-1:argv.index(str(cell))+2]
    archive = str(run/"field/stage/tle")
    assert argv[argv.index("--remount-ro")-3:argv.index("--remount-ro")] == ["--ro-bind",archive,archive]
    assert str(transfer.WORKER.parent) in str(transfer.capsule.WORKER)


def test_archive_device_check_requires_complete_same_device_directory(tmp_path,monkeypatch):
    stage = tmp_path/"stage"
    archive = stage/"tle/archive/space-track"
    cell = tmp_path/"ordinary"
    archive.mkdir(parents=True)
    cell.mkdir()
    names = {f"{i}.tle":f"signed-{i}" for i in range(47)}
    for name in names:
        (archive/name).write_text("data")
    transfer.saved.write(stage/"catalogue.json",names)
    transfer.verify_archive_mount(cell,{"stage":str(stage)})
    assert transfer.saved.document(cell/"archive-device-proof.json")["body_count"] == 47
    (archive/"1.tle").unlink()
    with pytest.raises(ValueError,match="47 staged"):
        transfer.verify_archive_mount(cell,{"stage":str(stage)})
