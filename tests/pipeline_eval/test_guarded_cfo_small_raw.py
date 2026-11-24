from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import guarded_cfo_small_raw as trial


def test_single_guarded_command_binds_resident_original_and_controls(tmp_path):
    pack = tmp_path / "oscillators"
    argv = list(map(str, trial.command(tmp_path, pack)))
    assert argv[2].endswith("/continued_cfo.py")
    for flag, expected in (
        ("--anchored-cfo-pack", pack),
        ("--recording", trial.RECORDING),
        ("--archive", trial.PRIOR / "tle"),
        ("--region", trial.PRIOR / "offer.json"),
        ("--output", tmp_path / "candidate"),
    ):
        assert argv[argv.index(flag) + 1] == str(expected)
    assert set(trial.ROUTE_FLAGS) <= set(argv)
    assert {"--cfo-refinement-library", "--bulk-root", "--select-before-cfo"}.isdisjoint(argv)
    assert all(argv[argv.index(flag) + 1] == str(trial.PRIOR / (name + ".so"))
               for flag, name in trial.LIBRARIES.items())
