from importlib import import_module
from pathlib import Path


def test_saved_simulations_use_the_same_repair_entry_point(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    runner = import_module("blind_joint_trial")
    calls = []
    monkeypatch.setattr(runner, "trial", lambda **received: calls.append(received))
    for site in ("south", "north"):
        for offer in ("containing", "far"):
            case = f"{site}-{offer}"
            destination = tmp_path / f"{case}.json"
            runner.main([case, str(destination), "--repair"])
            assert calls[-1] == dict(case=case, output=destination, repair=True)


def test_northern_receipts_can_be_scored_separately_with_existing_default(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    scorer = import_module("blind_joint_score")
    taken = []
    monkeypatch.setattr(scorer, "score", lambda **received: taken.append(received))
    paths = [tmp_path, tmp_path / "summary.json", tmp_path / "full.json.gz"]
    args = list(map(str, paths))
    scorer.main(args)
    assert taken[-1] == dict(directory=paths[0], summary=paths[1], full=paths[2], cases=None)
    scorer.main(args + ["--case", "north-containing", "--case", "north-far"])
    assert taken[-1]["cases"] == ["north-containing", "north-far"]
