"""Conditional association and residual audit of already sealed endpoints."""
import json
from pathlib import Path

import numpy as np

import run

HERE = Path(__file__).resolve().parent


def candidate_summary(train, visible, norads):
    train = np.asarray(train)
    visible = np.asarray(visible, dtype=bool)
    assert len(train) == len(visible) == len(norads) and visible.any()
    scores = np.where(visible, train, -np.inf)
    index = int(np.argmax(scores))
    return index, dict(norad=int(norads[index]),
                       conditional_row_mass=float(np.exp(scores[index]-np.logaddexp.reduce(scores))))


def main():
    plan = run.read(HERE / "plan.json")
    outcome = run.read(HERE / "outcome.json")
    assert outcome["plan_sha256"] == run.digest(HERE / "plan.json")
    assert outcome["geographic_errors_evaluated"]
    for path, expected in outcome["sources"].items():
        assert run.digest(path) == expected
    documents, fast, _, _ = run.context(plan)
    diagnosis_path = run.HILL / "source_loo/diagnose.py"
    diagnosis = run.module("waveform_association_diagnosis", diagnosis_path)
    _, _, _, verified, sidecar_path, mappings = diagnosis.validate_inputs(0)
    assert [t["track_id"] for t in documents[0]["tracks"]] == [t["track_id"] for t in verified[0]["tracks"]]
    targets = {row["track_id"] for row in plan["corrections"][run.ARMS[0]]}
    arms = {}
    for arm in ("control",) + run.ARMS:
        docs = documents if arm == "control" else run.patch_documents(documents, plan["corrections"][arm])
        endpoint = outcome["control"] if arm == "control" else outcome["selected"][arm]
        geometry = fast.Stationary(docs[0], plan["config"])
        rows = []
        for track in docs[0]["tracks"]:
            prediction, visible = geometry.prediction(track, np.asarray(endpoint["x"]))
            residuals = track["y"][None, :]-prediction
            train, _, audits, offsets = fast.profile(residuals, track["mask"])
            assert all(row["converged"] for row in audits)
            index, row = candidate_summary(train, visible, mappings[0][track["track_id"]])
            residual = residuals[index, track["mask"]]-offsets[index]
            row.update(track_id=track["track_id"], corrected_target=track["track_id"] in targets,
                       training_rms_hz=float(np.sqrt(np.mean(residual**2))),
                       training_median_absolute_residual_hz=float(np.median(abs(residual))))
            rows.append(row)
        arms[arm] = rows
    baseline = {r["track_id"]:r["norad"] for r in arms["control"]}
    changed = {arm:sum(r["norad"] != baseline[r["track_id"]] for r in arms[arm]) for arm in run.ARMS}
    sources = [HERE / "plan.json", HERE / "outcome.json", HERE / "run.py", Path(__file__),
               HERE / "test_association_audit.py", diagnosis_path, sidecar_path]
    result = dict(schema="ds11-waveform-conditional-association-audit/v1",
                  identities_are_authenticated=False, position_refit_performed=False,
                  arms=arms, changed_map_norads=changed,
                  sources={str(p):run.digest(p) for p in sources})
    run.write(HERE / "association_audit.json", result)
    print(json.dumps(dict(changed_map_norads=changed,
                         targets={k:[r for r in v if r["corrected_target"]] for k,v in arms.items()}), indent=2))


if __name__ == "__main__":
    main()
