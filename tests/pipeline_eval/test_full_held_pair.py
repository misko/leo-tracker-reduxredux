import json

from tools.pipeline_eval.qualification import full_held_pair as held
from tools.pipeline_eval.qualification import full_held_scores as scoring


def test_held_roster_uses_ids_only_and_excludes_both_development_cases():
    sample = {
        "DS26-0036": {"error": 0},
        "DS26-0122": {"error": 1},
        "DS26-0237": {"error": 2},
        "DS29-0082": {"error": 0},
        "DS29-0174": {"error": 2},
        "DS29-0247": {"error": 1},
    }
    first = held.roster(sample)
    second = held.roster(dict.fromkeys(reversed(sample), "withheld"))
    assert first == second
    assert first["selected"] == ["DS26-0237", "DS29-0174"]
    excluded = {
        r["id"]: r["disposition"] for r in first["ranked"] if r["disposition"] != "selected"
    }
    assert excluded == {
        "DS26-0036": "development",
        "DS29-0082": "development",
        "DS26-0122": "hash-rank",
        "DS29-0247": "hash-rank",
    }


def test_failed_factor_only_attempt_keeps_both_no_fix_arms(tmp_path):
    ident = "DS26-0237"
    folder = tmp_path / "control"
    (folder / ident).mkdir(parents=True)
    (folder / f"{ident}-service.json").write_text(
        json.dumps(
            dict(
                systemd=dict(Result="oom-kill"),
                elapsed_s=28.5,
            )
        )
    )
    (folder / f"{ident}-begin.json").write_text(json.dumps(dict(start=dict(cgroup="/cap", pid=9))))
    (folder / f"{ident}-systemd.log").write_text("stage: signed_context")
    pins = dict(
        inputs={
            ident: dict(
                native_sha256="ordinary",
                catalog_sha256="causal",
                tile={"id": "original"},
            )
        }
    )
    row, evidence = held.stock(tmp_path, ident, pins)
    assert row["result"]["status"] == "failed"
    assert row["result"]["reason"] == "oom-kill"
    assert row["result"]["arms"] == {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}
    assert row["worker_wall_s"] == 28.5
    assert evidence["position"] is None
    assert evidence["service_log"] == "stage: signed_context"


def test_held_scores_join_each_dataset_reference_panel(monkeypatch):
    def reference(panel):
        return {
            "ds26-all159": [{"id": "DS26-0237", "group": "DS26"}],
            "roof16": [{"id": "DS29-0174", "group": "DS29"}],
        }[panel]

    monkeypatch.setattr(scoring.corpus, "references", reference)
    _, rows = scoring.held_references("roof16", ["DS26-0237", "DS29-0174"])
    assert [r["id"] for r in rows] == ["DS26-0237", "DS29-0174"]
