import hashlib
import json
from pathlib import Path

from run import receiver
from timing import full_scores, log_integral, timing_nodes

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    plan = json.loads((HERE.parent / "2026_09_29_donor_residual_transfer/plan.json").read_text())
    rows, hashes = [], {}
    for path in sorted(HERE.glob("DS*_d[01].json")):
        original = json.loads(path.read_text())
        failed = [(a, t) for a in original["arms"] for t in a["target_scans"] if not t["qualified"]]
        if not failed:
            continue
        for name, digest in original["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        unit = next(u for u in plan["units"] if u["unit_id"] == original["unit"])
        docs = receiver.baseline.load_documents(
            dict(config=plan["config"], inputs=unit["group"]["inputs"])
        )
        for arm, target in failed:
            doc = next(d for d in docs if d["session_id"] == target["session_id"])
            model = receiver.TrendMixturePosition(
                [doc], plan["config"], receiver.baseline.Stationary, 0.2
            )
            scores = []
            for order in (64, 128):
                nodes, weights = timing_nodes(order, model.models[0].taus)
                scores.append(log_integral(full_scores(model, arm["x"][:2], nodes), weights))
            difference = abs(scores[0] - scores[1])
            row = dict(
                unit=original["unit"],
                direction=original["direction"],
                sigma=arm["sigma"],
                session_id=target["session_id"],
                original=target,
                log_score=scores[0],
                audit_log_score=scores[1],
                quadrature_difference=difference,
                qualified=bool(difference <= 0.01),
            )
            rows.append(row)
            print(row, flush=True)
    for name in ("refine.py", "timing.py", "NUMERICAL-REFINEMENT.md"):
        p = HERE / name
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (HERE / "refinement.json").write_text(
        json.dumps(dict(rows=rows, hashes=hashes), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
