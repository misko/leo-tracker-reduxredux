"""Freeze the matched geometry-prior study before accessing new outcomes."""

import datetime
import hashlib
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
runpy.run_path(str(HERE / "evaluate.py"), run_name="import_only")


def main():
    assert not (HERE / "protocol.json").exists()
    old_path = HERE.parent / "2026_10_09_position_error_iter78/protocol.json"
    old = json.loads(old_path.read_text())
    files = {ROOT / p for p in old["source_sha256"]}
    files.add(old_path)
    members = []
    for binding in old["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        directory = "2026_10_09_position_error_iter82" if member["dataset"] == "DS17" else (
            "2026_10_09_position_error_iter78"
        )
        path = HERE.parent / directory / "results" / f"{label}.json"
        control = json.loads(path.read_text())
        assert control["status"] == "complete" and control["member"] == member
        for arm in ("fitted-c", "zero-c"):
            assert control["raw"]["0.5"][arm]["converged"]
        files.add(path)
        members.append(dict(binding, control_source=str(path.relative_to(ROOT))))
    files.update(HERE.glob("*.py"))
    files.add(HERE / "README.md")
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename and filename.endswith(".py"):
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT / "reports") or "/worker/src/leo/" in str(path):
                files.add(path)
    for name in ("protocol.json", "protocol.sha256", "freeze.py"):
        files.add(HERE.parent / "2026_10_08_position_error_iter01" / name)
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(), members=members,
        variants=["uniform0.5", "protected0.25"], shards=2, maximum_seconds=90,
        maximum_iterations=600, total_fits=592,
        execution="Do not launch while iteration83 runners/evaluators remain live. "
        "At most two single-thread numerical workers. No source edits after execution.",
        controls="Reconstruct each archived0.5 raw objective within1e-6; "
        "verify uniform geometry wrapper objective/core/nuisance gradients against original "
        "uniform model within1e-10. Then fit both variants from identical archived upstream seeds.",
        candidate="Freeze at most two position-overlap slope modes at the shared fitted-derived "
        "hypothesis seed; protect sigma0.25, all other slope modes sigma0.5. "
        "Both c arms share seed, clock, bank, observations, projector, priors and budget. "
        "c0 locks staticc and RF-time terms. No warm starts across variants.",
        fallback="Independently unqualified fit keeps fixed archived0.5 operational result "
        "for that arm. Input failures remain explicit and prevent a full candidate claim.",
        reporting="Full148 and dataset/exposure subgroup distributions, paired regressions, "
        "raw convergence/fallbacks; separate frequency fit, complete membership and failures. "
        "No per-scan reference-error choice or cross-model score ranking.",
        validation="Consumed development. No reference-guided inference, deployment, RF "
        "or reserve outcome access. Independent randomized whole-group validation still required.",
        source_sha256={str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p):
                       hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
    )
    assert len(members) == 148
    (HERE / "protocol.json").write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen148 members,592 matched fits; NOT launched")


if __name__ == "__main__":
    main()
