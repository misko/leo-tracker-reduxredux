"""Verify existing evidence and write an exclusive final benchmark closeout."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify(base, bindings):
    for name, expected in bindings.items():
        assert digest(base / name) == expected, str(base / name)
    return len(bindings)


def main():
    previous = {}
    counts = {}
    for number in range(2, 10):
        directory = ROOT / f"reports/2026_09_27_ds7_wave{number}"
        path = directory / "closeout.json"
        data = read(path)
        counts[f"wave{number}"] = {
            "source_files": verify(ROOT, data["source_files"]),
            "wave_files": verify(directory, data["wave_files"]),
        }
        previous[str(path.relative_to(ROOT))] = digest(path)
    seals = {}
    for path in sorted(HERE.rglob("seal.json")):
        data = read(path)
        assert data["schema"] == "ds7-run-seal/v1"
        count = verify(path.parent, data["files"])
        inventory = {
            str(p.relative_to(path.parent))
            for p in path.parent.rglob("*")
            if p.is_file() and p != path
        }
        assert inventory == set(data["files"]), str(path)
        seals[str(path.relative_to(HERE))] = count
    assert len(seals) == 8
    run = HERE / "solver/joint-v1"
    request = read(run / "full88/request.json")
    response = read(run / "full88/response.json")
    plan = read(run / "plan.json")
    expected = next(u for u in plan["units"] if u["unit_id"] == "full88")
    assert request["unit"] == expected
    assert len(set(expected["session_ids"])) == len(request["captures"]) == 88
    assert response["status"] == "ok" and response["converged"]
    assert response["boundary_hit"] is False
    score = read(HERE / "coordinator/joint-score-v1/scores.json")
    assert score["run_seal_sha256"] == digest(run / "seal.json")
    trial = score["trials"][0]
    assert trial["unit_id"] == "full88" and trial["qualified"]
    assert 0 <= trial["horizontal_error_m"] < 1000
    controls = {}
    for method in ("equal", "inverse_rms2", "lowest_rms75"):
        result = read(HERE / f"coordinator/controls-{method}-score-v1/scores.json")
        item = result["trials"][0]
        assert item["status"] == "abstained" and not item["qualified"]
        assert item["horizontal_error_m"] is None
        controls[method] = item
    residual = HERE / "residual/fixed-prediction-audit-terminal-receipt.json"
    assert residual.is_file()
    assert not (HERE / "residual/fixed-prediction-audit-v1.json").exists()
    output = HERE / "closeout.json"
    evidence = {
        str(p.relative_to(HERE)): digest(p)
        for p in sorted(HERE.rglob("*"))
        if p.is_file() and p != output and "__pycache__" not in p.parts
    }
    result = {
        "schema": "ds7-full88-final-closeout/v1",
        "closed_utc": datetime.now(timezone.utc).isoformat(),
        "goal_achieved": True,
        "claim_scope": "Complete pooled DS7 exposed single-site unsurveyed-reference benchmark",
        "joint": trial,
        "controls": controls,
        "residual_audit": "terminal failure; no result; no retry; no residual validation claimed",
        "previous_closeouts": previous,
        "verified_previous_binding_counts": counts,
        "verified_directory_seals": seals,
        "files": evidence,
    }
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"closeout_sha256": digest(output), "files": len(evidence),
                      "verified_seals": len(seals), "error_m": trial["horizontal_error_m"]}))


if __name__ == "__main__":
    main()
